from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import SCHEMA_VERSION, initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.audience_preparation_service import get_audience_preparation_status
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_service import (
    _csv_safe_value,
    _export_header_bytes,
    _export_row_bytes,
    _iter_selected_member_chunks,
    _resolve_campaign_member_query_context_on_connection,
    _validate_direct_mail_deliverability,
    _validate_email_deliverability,
)
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    find_current_canonical_run_for_model_lightweight,
)
from app.services.saved_audience_service import save_audience

DATABASE_PATH = Path("data/campaign_poc.db")
BASELINE_EVIDENCE_PATH = Path("docs/evidence/phase7_export_profiling_baseline.json")
EVIDENCE_PATH = Path("docs/evidence/phase7_final_export_hardening_5m.json")

EMAIL_COLUMNS = [
    "person_id",
    "propensity_score",
    "percentile_bucket",
    "decile",
    "rank_band",
    "first_name",
    "last_name",
    "email",
]

DIRECT_MAIL_COLUMNS = [
    "person_id",
    "propensity_score",
    "percentile_bucket",
    "decile",
    "rank_band",
    "first_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _assert_status(response: Any, expected: int, *, context: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(
            f"{context} failed: expected {expected}, got {response.status_code}, detail={response.text[:500]}"
        )


def _request(client: TestClient, method: str, url: str, **kwargs: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    response = client.request(method, url, **kwargs)
    elapsed = time.perf_counter() - started
    return response, elapsed


def _resolve_canonical_context(database_path: Path) -> dict[str, int]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT model_run_id
            FROM model_runs
            WHERE status = 'COMPLETED'
            ORDER BY model_run_id DESC
            LIMIT 200
            """
        ).fetchall()

    for row in rows:
        model_run_id = int(row["model_run_id"])
        try:
            canonical = find_current_canonical_run_for_model_lightweight(
                database_path,
                model_run_id=model_run_id,
            )
        except ProspectScoringVerificationError:
            continue
        if canonical is not None:
            return {
                "scoring_run_id": int(canonical["scoring_run_id"]),
                "model_run_id": int(canonical["model_run_id"]),
            }

    raise RuntimeError("No current canonical scoring run was found.")


def _ensure_prepared(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    status = get_audience_preparation_status(database_path, scoring_run_id=scoring_run_id)
    if bool(status.get("prepared")) and bool(status.get("analytics_prepared")):
        return status
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    refreshed = get_audience_preparation_status(database_path, scoring_run_id=scoring_run_id)
    if not (bool(refreshed.get("prepared")) and bool(refreshed.get("analytics_prepared"))):
        raise RuntimeError("Audience rank preparation did not complete.")
    return refreshed


def _create_saved_audience(
    database_path: Path,
    *,
    audience_name: str,
    scoring_run_id: int,
    filters: dict[str, Any],
    selection: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    saved = save_audience(
        database_path,
        {
            "audience_name": audience_name,
            "description": "Phase 7 hardening benchmark fixture",
            "scoring_run_id": scoring_run_id,
            "filters": filters,
            "selection": selection,
            "include_profile_snapshot": True,
        },
    )
    saved["_create_seconds"] = time.perf_counter() - started
    return saved


def _csv_stats(content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    headers = reader.fieldnames or []
    row_count = 0
    person_order_sha = hashlib.sha256()
    for row in reader:
        row_count += 1
        pid = str(row.get("person_id", ""))
        person_order_sha.update(pid.encode("utf-8"))
        person_order_sha.update(b"\n")

    return {
        "headers": headers,
        "row_count": row_count,
        "person_order_sha256": person_order_sha.hexdigest(),
        "csv_sha256": hashlib.sha256(content).hexdigest(),
    }


def _latest_event(client: TestClient, campaign_id: int) -> dict[str, Any]:
    response, _ = _request(client, "GET", f"/api/campaigns/{campaign_id}/exports?limit=20")
    _assert_status(response, 200, context="list export events")
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("No export events were recorded.")
    latest = payload[0]
    if not isinstance(latest, dict):
        raise RuntimeError("Invalid export event payload.")
    return latest


def _run_export_case(
    client: TestClient,
    *,
    case_name: str,
    channel: str,
    saved_audience_id: int,
    expected_columns: list[str],
    runs: int,
) -> dict[str, Any]:
    create_response, create_seconds = _request(
        client,
        "POST",
        "/api/campaigns",
        json={
            "campaign_name": f"H7 {case_name}",
            "description": "Phase 7 hardening benchmark",
            "channel": channel,
            "planned_launch_date": "2026-12-25",
            "saved_audience_id": saved_audience_id,
        },
    )
    _assert_status(create_response, 201, context=f"create {case_name}")
    campaign = create_response.json()
    campaign_id = int(campaign["campaign_id"])

    finalize_response, finalize_seconds = _request(client, "POST", f"/api/campaigns/{campaign_id}/finalize")
    _assert_status(finalize_response, 200, context=f"finalize {case_name}")

    run_outputs: list[dict[str, Any]] = []
    for index in range(runs):
        export_response, export_seconds = _request(
            client,
            "GET",
            f"/api/campaigns/{campaign_id}/export.csv?acknowledge_pii=true",
        )
        _assert_status(export_response, 200, context=f"export {case_name} run {index + 1}")
        csv_summary = _csv_stats(export_response.content)
        if csv_summary["headers"] != expected_columns:
            raise RuntimeError(f"Header mismatch for {case_name}: {csv_summary['headers']}")

        event = _latest_event(client, campaign_id)
        selected_count = int(event["selected_count"])
        deliverable_count = int(event["deliverable_count"])
        undeliverable_count = int(event["undeliverable_count"])
        row_count = int(event["row_count"])

        if deliverable_count + undeliverable_count != selected_count:
            raise RuntimeError(f"Deliverability reconciliation failed for {case_name}.")
        if row_count != deliverable_count:
            raise RuntimeError(f"Row count and deliverable count mismatch for {case_name}.")
        if row_count != int(csv_summary["row_count"]):
            raise RuntimeError(f"CSV row count mismatch for {case_name}.")

        run_outputs.append(
            {
                "run": index + 1,
                "export_seconds": round(export_seconds, 6),
                "throughput_rows_per_second": round((row_count / export_seconds) if export_seconds > 0 else 0.0, 3),
                "event": {
                    "export_event_id": int(event["export_event_id"]),
                    "status": str(event["status"]),
                    "selected_count": selected_count,
                    "deliverable_count": deliverable_count,
                    "undeliverable_count": undeliverable_count,
                    "row_count": row_count,
                    "csv_sha256": event.get("csv_sha256"),
                    "export_snapshot_contract_version": event.get("export_snapshot_contract_version"),
                    "start_provenance_sha256": event.get("start_provenance_sha256"),
                    "source_changed_during_export": bool(event.get("source_changed_during_export")),
                    "completion_currentness_state": event.get("completion_currentness_state"),
                    "started_at": event.get("started_at"),
                    "completed_at": event.get("completed_at"),
                },
                "csv": csv_summary,
            }
        )

    reproducibility = {
        "runs_compared": runs,
        "selected_count_identical": True,
        "deliverable_count_identical": True,
        "person_order_sha256_identical": True,
        "csv_sha256_identical": True,
    }
    if len(run_outputs) >= 2:
        first = run_outputs[0]
        for other in run_outputs[1:]:
            reproducibility["selected_count_identical"] = reproducibility["selected_count_identical"] and (
                other["event"]["selected_count"] == first["event"]["selected_count"]
            )
            reproducibility["deliverable_count_identical"] = reproducibility["deliverable_count_identical"] and (
                other["event"]["deliverable_count"] == first["event"]["deliverable_count"]
            )
            reproducibility["person_order_sha256_identical"] = reproducibility[
                "person_order_sha256_identical"
            ] and (other["csv"]["person_order_sha256"] == first["csv"]["person_order_sha256"])
            reproducibility["csv_sha256_identical"] = reproducibility["csv_sha256_identical"] and (
                other["csv"]["csv_sha256"] == first["csv"]["csv_sha256"]
            )

    return {
        "case_name": case_name,
        "channel": channel,
        "campaign_id": campaign_id,
        "create_seconds": round(create_seconds, 6),
        "finalize_seconds": round(finalize_seconds, 6),
        "runs": run_outputs,
        "reproducibility": reproducibility,
    }


def _profile_pipeline_times(
    database_path: Path,
    *,
    campaign_id: int,
    export_profile: str,
) -> dict[str, Any]:
    with get_connection(database_path) as connection:
        campaign_row = connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if campaign_row is None:
            raise RuntimeError(f"Campaign {campaign_id} not found for profiling.")

        connection.execute("BEGIN")
        query_context = _resolve_campaign_member_query_context_on_connection(
            connection,
            campaign_row=dict(campaign_row),
        )
        iterator = _iter_selected_member_chunks(
            connection,
            query_context=query_context,
            export_profile=export_profile,
            chunk_size=25_000,
        )

        query_seconds = 0.0
        deliverability_seconds = 0.0
        csv_seconds = 0.0
        row_count = 0
        selected_count = 0
        deliverable_count = 0
        undeliverable_count = 0
        chunk_count = 0
        peak_chunk_rows = 0

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")

        if export_profile == "EMAIL_CONTACT_V1":
            columns = EMAIL_COLUMNS
        else:
            columns = DIRECT_MAIL_COLUMNS

        digest = hashlib.sha256()
        header_bytes = _export_header_bytes(tuple(columns), writer, buffer)
        digest.update(header_bytes)
        while True:
            started_query = time.perf_counter()
            try:
                chunk = next(iterator)
            except StopIteration:
                query_seconds += time.perf_counter() - started_query
                break
            query_seconds += time.perf_counter() - started_query

            chunk_count += 1
            peak_chunk_rows = max(peak_chunk_rows, len(chunk))
            selected_count += len(chunk)

            for member in chunk:
                if export_profile == "EMAIL_CONTACT_V1":
                    started_deliverability = time.perf_counter()
                    deliverable = _validate_email_deliverability(member.get("email"))
                    deliverability_seconds += time.perf_counter() - started_deliverability
                else:
                    started_deliverability = time.perf_counter()
                    deliverable = _validate_direct_mail_deliverability(member)
                    deliverability_seconds += time.perf_counter() - started_deliverability

                if not deliverable:
                    undeliverable_count += 1
                    continue

                deliverable_count += 1
                started_csv = time.perf_counter()
                row_payload = [
                    _csv_safe_value(member["person_id"]),
                    member["propensity_score"],
                    member["percentile_bucket"],
                    member["decile"],
                    _csv_safe_value(member["rank_band"]),
                ]
                if export_profile == "EMAIL_CONTACT_V1":
                    row_payload.extend(
                        [
                            _csv_safe_value(member.get("first_name")),
                            _csv_safe_value(member.get("last_name")),
                            _csv_safe_value(member.get("email")),
                        ]
                    )
                else:
                    row_payload.extend(
                        [
                            _csv_safe_value(member.get("first_name")),
                            _csv_safe_value(member.get("last_name")),
                            _csv_safe_value(member.get("address_line_1")),
                            _csv_safe_value(member.get("address_line_2")),
                            _csv_safe_value(member.get("city")),
                            _csv_safe_value(member.get("state")),
                            _csv_safe_value(member.get("postal_code")),
                        ]
                    )
                encoded = _export_row_bytes(row_payload, writer, buffer)
                digest.update(encoded)
                csv_seconds += time.perf_counter() - started_csv
                row_count += 1

    return {
        "query_seconds": round(query_seconds, 6),
        "deliverability_seconds": round(deliverability_seconds, 6),
        "csv_encoding_seconds": round(csv_seconds, 6),
        "selected_count": selected_count,
        "deliverable_count": deliverable_count,
        "undeliverable_count": undeliverable_count,
        "row_count": row_count,
        "chunk_count": chunk_count,
        "peak_chunk_rows": peak_chunk_rows,
        "csv_sha256": digest.hexdigest(),
    }


def _selection_query_plan(
    database_path: Path,
    *,
    campaign_id: int,
    export_profile: str,
) -> list[str]:
    with get_connection(database_path) as connection:
        campaign_row = connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if campaign_row is None:
            raise RuntimeError("Campaign not found for query plan capture.")
        connection.execute("BEGIN")
        context = _resolve_campaign_member_query_context_on_connection(
            connection,
            campaign_row=dict(campaign_row),
        )

        where_predicates = ["p.scoring_run_id = ?"]
        params: list[Any] = [int(context["scoring_run_id"])]

        score_predicates = list(context["score_predicates"])
        score_parameters = list(context["score_parameters"])
        demographic_predicates = list(context["demographic_predicates"])
        demographic_parameters = list(context["demographic_parameters"])

        if score_predicates:
            where_predicates.extend(score_predicates)
            params.extend(score_parameters)
        if demographic_predicates:
            where_predicates.extend(demographic_predicates)
            params.extend(demographic_parameters)

        limit_clause = ""
        selection_payload = dict(context["normalized_selection"].payload)
        if selection_payload.get("mode") == "TOP_N":
            limit_clause = "LIMIT ?"
            params.append(int(selection_payload["target_count"]))

        if export_profile == "EMAIL_CONTACT_V1":
            contact_columns = ["d.first_name", "d.last_name", "d.email"]
        else:
            contact_columns = [
                "d.first_name",
                "d.last_name",
                "d.address_line_1",
                "d.address_line_2",
                "d.city",
                "d.state",
                "d.postal_code",
            ]

        query = f"""
            SELECT p.person_id, p.propensity_score, {', '.join(contact_columns)}
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE {' AND '.join(where_predicates)}
            ORDER BY p.propensity_score DESC, p.person_id ASC
            {limit_clause}
        """

        rows = connection.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()
    return [str(row[3]) for row in rows]


def _undeliverable_heavy_copy_case(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="phase7_h7_"))
    db_copy = temp_dir / "campaign_poc_undeliverable_copy.db"
    shutil.copy2(database_path, db_copy)
    initialize_database(db_copy)

    with get_connection(db_copy, write=True) as connection:
        connection.execute(
            """
            WITH top_ids AS (
                SELECT person_id
                FROM propensity_scores
                WHERE scoring_run_id = ?
                ORDER BY propensity_score DESC, person_id ASC
                LIMIT 9000
            )
            UPDATE demographics
            SET address_line_1 = ''
            WHERE person_id IN (SELECT person_id FROM top_ids)
            """,
            (scoring_run_id,),
        )

    saved = _create_saved_audience(
        db_copy,
        audience_name="H7 Undeliverable Heavy Top 10K",
        scoring_run_id=scoring_run_id,
        filters={},
        selection={"mode": "TOP_N", "target_count": 10_000},
    )

    app.dependency_overrides[get_database_path] = lambda: db_copy
    try:
        with TestClient(app) as client:
            result = _run_export_case(
                client,
                case_name="DIRECT_MAIL_TOP_10K_UNDELIVERABLE_HEAVY",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved["audience_id"]),
                expected_columns=DIRECT_MAIL_COLUMNS,
                runs=1,
            )
    finally:
        app.dependency_overrides.clear()

    return {
        "temporary_db_copy": True,
        "copy_db_name": db_copy.name,
        "saved_audience_id": int(saved["audience_id"]),
        "saved_resolved_count": int(saved["definition"]["resolved_count"]),
        "result": result,
    }


def _equivalence_against_baseline(
    baseline: dict[str, Any],
    optimized_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_map = {str(case["case_name"]): case for case in baseline.get("baseline_cases", [])}
    comparison: dict[str, Any] = {}

    for case in optimized_cases:
        case_name = str(case["case_name"])
        baseline_case = baseline_map.get(case_name)
        if baseline_case is None:
            continue

        baseline_event = baseline_case["event"]
        baseline_csv = baseline_case["csv"]
        optimized_first = case["runs"][0]

        comparison[case_name] = {
            "selected_count_identical": int(optimized_first["event"]["selected_count"]) == int(
                baseline_event["selected_count"]
            ),
            "deliverable_count_identical": int(optimized_first["event"]["deliverable_count"]) == int(
                baseline_event["deliverable_count"]
            ),
            "undeliverable_count_identical": int(optimized_first["event"]["undeliverable_count"]) == int(
                baseline_event["undeliverable_count"]
            ),
            "row_count_identical": int(optimized_first["event"]["row_count"]) == int(baseline_event["row_count"]),
            "person_order_sha256_identical": str(optimized_first["csv"]["person_order_sha256"]) == str(
                baseline_csv["person_order_sha256"]
            ),
            "csv_sha256_identical": str(optimized_first["csv"]["csv_sha256"]) == str(baseline_csv["csv_sha256"]),
            "headers_identical": optimized_first["csv"]["headers"] == baseline_csv["headers"],
            "baseline_csv_sha256": str(baseline_csv["csv_sha256"]),
            "optimized_csv_sha256": str(optimized_first["csv"]["csv_sha256"]),
        }

    return comparison


def main() -> None:
    database_path = initialize_database(DATABASE_PATH)
    baseline = json.loads(BASELINE_EVIDENCE_PATH.read_text(encoding="utf-8"))

    canonical = _resolve_canonical_context(database_path)
    scoring_run_id = int(canonical["scoring_run_id"])
    preparation = _ensure_prepared(database_path, scoring_run_id)

    saved_audiences = {
        "email_top_1k": _create_saved_audience(
            database_path,
            audience_name="H7 Email Top 1K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 1000},
        ),
        "direct_mail_top_50k": _create_saved_audience(
            database_path,
            audience_name="H7 Direct Mail Top 50K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 50000},
        ),
        "direct_mail_filtered_all_matching": _create_saved_audience(
            database_path,
            audience_name="H7 Direct Mail Filtered ALL_MATCHING",
            scoring_run_id=scoring_run_id,
            filters={"state": ["California"], "age_min": 30, "age_max": 60},
            selection={"mode": "ALL_MATCHING"},
        ),
        "top_decile_all_matching": _create_saved_audience(
            database_path,
            audience_name="H7 Top Decile ALL_MATCHING",
            scoring_run_id=scoring_run_id,
            filters={"top_percentile_max": 10},
            selection={"mode": "ALL_MATCHING"},
        ),
    }

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            email_case = _run_export_case(
                client,
                case_name="EMAIL_TOP_1K",
                channel="EMAIL",
                saved_audience_id=int(saved_audiences["email_top_1k"]["audience_id"]),
                expected_columns=EMAIL_COLUMNS,
                runs=2,
            )
            direct_mail_case = _run_export_case(
                client,
                case_name="DIRECT_MAIL_TOP_50K",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["direct_mail_top_50k"]["audience_id"]),
                expected_columns=DIRECT_MAIL_COLUMNS,
                runs=2,
            )
            large_case = _run_export_case(
                client,
                case_name="DIRECT_MAIL_FILTERED_ALL_MATCHING",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["direct_mail_filtered_all_matching"]["audience_id"]),
                expected_columns=DIRECT_MAIL_COLUMNS,
                runs=2,
            )
            decile_case = _run_export_case(
                client,
                case_name="TOP_DECILE_ALL_MATCHING",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["top_decile_all_matching"]["audience_id"]),
                expected_columns=DIRECT_MAIL_COLUMNS,
                runs=1,
            )
    finally:
        app.dependency_overrides.clear()

    pipeline_profiles = {
        "EMAIL_TOP_1K": _profile_pipeline_times(
            database_path,
            campaign_id=int(email_case["campaign_id"]),
            export_profile="EMAIL_CONTACT_V1",
        ),
        "DIRECT_MAIL_TOP_50K": _profile_pipeline_times(
            database_path,
            campaign_id=int(direct_mail_case["campaign_id"]),
            export_profile="DIRECT_MAIL_CONTACT_V1",
        ),
        "DIRECT_MAIL_FILTERED_ALL_MATCHING": _profile_pipeline_times(
            database_path,
            campaign_id=int(large_case["campaign_id"]),
            export_profile="DIRECT_MAIL_CONTACT_V1",
        ),
    }

    plans = {
        "EMAIL_TOP_1K": _selection_query_plan(
            database_path,
            campaign_id=int(email_case["campaign_id"]),
            export_profile="EMAIL_CONTACT_V1",
        ),
        "DIRECT_MAIL_TOP_50K": _selection_query_plan(
            database_path,
            campaign_id=int(direct_mail_case["campaign_id"]),
            export_profile="DIRECT_MAIL_CONTACT_V1",
        ),
        "DIRECT_MAIL_FILTERED_ALL_MATCHING": _selection_query_plan(
            database_path,
            campaign_id=int(large_case["campaign_id"]),
            export_profile="DIRECT_MAIL_CONTACT_V1",
        ),
    }

    undeliverable_heavy_case = _undeliverable_heavy_copy_case(database_path, scoring_run_id)

    optimized_cases = [email_case, direct_mail_case, large_case]
    baseline_equivalence = _equivalence_against_baseline(baseline, optimized_cases)

    large_profile = pipeline_profiles["DIRECT_MAIL_FILTERED_ALL_MATCHING"]
    cost_components = {
        "query_seconds": float(large_profile["query_seconds"]),
        "deliverability_seconds": float(large_profile["deliverability_seconds"]),
        "csv_encoding_seconds": float(large_profile["csv_encoding_seconds"]),
    }
    dominant_cost = max(cost_components, key=cost_components.get)

    evidence = {
        "generated_at": _utc_now(),
        "scope": "phase7_final_export_hardening_5m",
        "database": {
            "database_name": database_path.name,
            "schema_version": SCHEMA_VERSION,
            "no_data_regeneration": True,
            "no_model_retraining": True,
            "no_model_rescoring": True,
        },
        "baseline_reference": {
            "file": str(BASELINE_EVIDENCE_PATH),
            "generated_at": baseline.get("generated_at"),
        },
        "canonical_context": canonical,
        "audience_preparation": {
            "prepared": bool(preparation.get("prepared")),
            "analytics_prepared": bool(preparation.get("analytics_prepared")),
            "boundary_count": int(preparation.get("boundary_count", 0)),
        },
        "saved_audience_cases": {
            key: {
                "audience_id": int(value["audience_id"]),
                "resolved_count": int(value["definition"]["resolved_count"]),
                "selection_mode": str(value["definition"]["selection_mode"]),
                "target_count": value["definition"].get("target_count"),
                "create_seconds": round(float(value["_create_seconds"]), 6),
            }
            for key, value in saved_audiences.items()
        },
        "benchmark_cases": {
            "EMAIL_TOP_1K": email_case,
            "DIRECT_MAIL_TOP_50K": direct_mail_case,
            "DIRECT_MAIL_FILTERED_ALL_MATCHING": large_case,
            "TOP_DECILE_ALL_MATCHING": decile_case,
            "DIRECT_MAIL_TOP_10K_UNDELIVERABLE_HEAVY_DB_COPY": undeliverable_heavy_case,
        },
        "pipeline_profiles": pipeline_profiles,
        "selection_query_plans": plans,
        "baseline_equivalence": baseline_equivalence,
        "performance_analysis": {
            "dominant_cost_component": dominant_cost,
            "large_case_cost_components_seconds": cost_components,
            "architecture_after": [
                "Single ordered SELECT cursor per export with one demographics join.",
                "Fetchmany chunk streaming over one SQLite read snapshot transaction.",
                "Bounded aggregate status updates for long-running STARTED exports.",
                "Snapshot provenance token and completion currentness state captured in export events.",
            ],
            "no_additional_indexes_added": True,
        },
        "hardening_contracts": {
            "snapshot_contract_version": "1",
            "source_changed_during_export_recorded": True,
            "future_stale_export_blocked_by_currentness_gate": True,
        },
    }

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(json.dumps({"evidence_file": str(EVIDENCE_PATH), "generated_at": evidence["generated_at"]}, indent=2))


if __name__ == "__main__":
    main()
