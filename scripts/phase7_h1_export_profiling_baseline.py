from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import SCHEMA_VERSION, initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.audience_preparation_service import get_audience_preparation_status
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_service import _resolve_campaign_member_query_context
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    find_current_canonical_run_for_model_lightweight,
)
from app.services.saved_audience_service import save_audience

DATABASE_PATH = Path("data/campaign_poc.db")
EVIDENCE_PATH = Path("docs/evidence/phase7_export_profiling_baseline.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _assert_status(response: Any, expected: int, *, context: str) -> None:
    if response.status_code != expected:
        detail = response.text[:500]
        raise RuntimeError(
            f"{context} failed: expected status {expected}, got {response.status_code}. detail={detail}"
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
        raise RuntimeError("Audience preparation did not complete successfully.")
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
    payload = save_audience(
        database_path,
        {
            "audience_name": audience_name,
            "description": "Phase 7 hardening baseline profiling",
            "scoring_run_id": scoring_run_id,
            "filters": filters,
            "selection": selection,
            "include_profile_snapshot": True,
        },
    )
    payload["_create_seconds"] = time.perf_counter() - started
    return payload


def _csv_stats(content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    fieldnames = reader.fieldnames or []
    count = 0
    pid_sha = hashlib.sha256()
    for row in reader:
        count += 1
        person_id = str(row.get("person_id", ""))
        pid_sha.update(person_id.encode("utf-8"))
        pid_sha.update(b"\n")
    return {
        "headers": fieldnames,
        "row_count": count,
        "person_order_sha256": pid_sha.hexdigest(),
        "csv_sha256": hashlib.sha256(content).hexdigest(),
    }


def _latest_event(client: TestClient, campaign_id: int) -> dict[str, Any]:
    response, _ = _request(client, "GET", f"/api/campaigns/{campaign_id}/exports?limit=20")
    _assert_status(response, 200, context="list campaign export events")
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("No export event was recorded.")
    latest = payload[0]
    if not isinstance(latest, dict):
        raise RuntimeError("Latest event payload is invalid.")
    return latest


def _campaign_export_case(
    client: TestClient,
    *,
    case_name: str,
    channel: str,
    saved_audience_id: int,
) -> dict[str, Any]:
    create_response, create_seconds = _request(
        client,
        "POST",
        "/api/campaigns",
        json={
            "campaign_name": f"H1 Baseline {case_name}",
            "description": "Phase 7 hardening baseline",
            "channel": channel,
            "planned_launch_date": "2026-12-20",
            "saved_audience_id": saved_audience_id,
        },
    )
    _assert_status(create_response, 201, context=f"create campaign {case_name}")
    campaign = create_response.json()
    campaign_id = int(campaign["campaign_id"])

    finalize_response, finalize_seconds = _request(
        client,
        "POST",
        f"/api/campaigns/{campaign_id}/finalize",
    )
    _assert_status(finalize_response, 200, context=f"finalize campaign {case_name}")

    export_response, export_seconds = _request(
        client,
        "GET",
        f"/api/campaigns/{campaign_id}/export.csv?acknowledge_pii=true",
    )
    _assert_status(export_response, 200, context=f"export campaign {case_name}")

    event = _latest_event(client, campaign_id)
    stats = _csv_stats(export_response.content)

    selected_count = int(event["selected_count"])
    deliverable_count = int(event["deliverable_count"])
    undeliverable_count = int(event["undeliverable_count"])
    row_count = int(event["row_count"])

    if deliverable_count + undeliverable_count != selected_count:
        raise RuntimeError("Deliverability reconciliation failed in baseline case.")
    if row_count != deliverable_count:
        raise RuntimeError("Row count and deliverable count diverged in baseline case.")
    if row_count != int(stats["row_count"]):
        raise RuntimeError("CSV row count mismatch in baseline case.")

    return {
        "case_name": case_name,
        "channel": channel,
        "campaign_id": campaign_id,
        "create_seconds": round(create_seconds, 6),
        "finalize_seconds": round(finalize_seconds, 6),
        "export_seconds": round(export_seconds, 6),
        "throughput_rows_per_second": round((row_count / export_seconds) if export_seconds > 0 else 0.0, 3),
        "event": {
            "export_event_id": int(event["export_event_id"]),
            "status": str(event["status"]),
            "selected_count": selected_count,
            "deliverable_count": deliverable_count,
            "undeliverable_count": undeliverable_count,
            "row_count": row_count,
            "csv_sha256": str(event["csv_sha256"]),
            "started_at": str(event["started_at"]),
            "completed_at": str(event["completed_at"]),
        },
        "csv": stats,
    }


def _selection_query_plan(database_path: Path, campaign_id: int) -> dict[str, Any]:
    with get_connection(database_path) as connection:
        campaign_row = connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if campaign_row is None:
            raise RuntimeError("Campaign row was not found for plan capture.")
    context = _resolve_campaign_member_query_context(database_path, dict(campaign_row))

    scoring_run_id = int(context["scoring_run_id"])
    score_predicates = list(context["score_predicates"])
    score_parameters = list(context["score_parameters"])
    demographic_predicates = list(context["demographic_predicates"])
    demographic_parameters = list(context["demographic_parameters"])
    selection_payload = dict(context["normalized_selection"].payload)

    join_clause = ""
    where_predicates = ["p.scoring_run_id = ?"]
    params: list[Any] = [scoring_run_id]

    if score_predicates:
        where_predicates.extend(score_predicates)
        params.extend(score_parameters)
    if demographic_predicates:
        join_clause = "INNER JOIN demographics d ON d.person_id = p.person_id"
        where_predicates.extend(demographic_predicates)
        params.extend(demographic_parameters)

    limit = 25000
    if selection_payload.get("mode") == "TOP_N":
        target_count = int(selection_payload.get("target_count") or 0)
        if target_count > 0:
            limit = min(limit, target_count)

    params.append(limit)

    query = f"""
        SELECT p.person_id, p.propensity_score
        FROM propensity_scores p
        {join_clause}
        WHERE {' AND '.join(where_predicates)}
        ORDER BY p.propensity_score DESC, p.person_id ASC
        LIMIT ?
    """

    with get_connection(database_path) as connection:
        plan_rows = connection.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()

    return {
        "selection_mode": selection_payload.get("mode"),
        "target_count": selection_payload.get("target_count"),
        "has_demographic_predicates": bool(demographic_predicates),
        "plan": [str(row[3]) for row in plan_rows],
    }


def main() -> None:
    database_path = initialize_database(DATABASE_PATH)
    source_text = Path("app/services/campaign_service.py").read_text(encoding="utf-8")

    canonical = _resolve_canonical_context(database_path)
    scoring_run_id = int(canonical["scoring_run_id"])
    preparation = _ensure_prepared(database_path, scoring_run_id)

    saved_audiences = {
        "email_top_1k": _create_saved_audience(
            database_path,
            audience_name="H1 Baseline Email Top 1K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 1000},
        ),
        "direct_mail_top_50k": _create_saved_audience(
            database_path,
            audience_name="H1 Baseline Direct Mail Top 50K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 50000},
        ),
        "direct_mail_all_matching_filtered": _create_saved_audience(
            database_path,
            audience_name="H1 Baseline Direct Mail Filtered ALL_MATCHING",
            scoring_run_id=scoring_run_id,
            filters={"state": ["California"], "age_min": 30, "age_max": 60},
            selection={"mode": "ALL_MATCHING"},
        ),
    }

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            email_case = _campaign_export_case(
                client,
                case_name="EMAIL_TOP_1K",
                channel="EMAIL",
                saved_audience_id=int(saved_audiences["email_top_1k"]["audience_id"]),
            )
            direct_mail_case = _campaign_export_case(
                client,
                case_name="DIRECT_MAIL_TOP_50K",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["direct_mail_top_50k"]["audience_id"]),
            )
            all_matching_case = _campaign_export_case(
                client,
                case_name="DIRECT_MAIL_FILTERED_ALL_MATCHING",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["direct_mail_all_matching_filtered"]["audience_id"]),
            )
    finally:
        app.dependency_overrides.clear()

    plans = {
        "email_top_1k": _selection_query_plan(database_path, email_case["campaign_id"]),
        "direct_mail_top_50k": _selection_query_plan(database_path, direct_mail_case["campaign_id"]),
        "direct_mail_filtered_all_matching": _selection_query_plan(database_path, all_matching_case["campaign_id"]),
    }

    dominant_unnecessary_work = [
        "Selected-member retrieval repeats ordered selection query for every 25K page via keyset loop.",
        "Each page performs temp ID table delete/insert churn before second demographics lookup.",
        "Percentile classification scans all 100 boundaries for each selected row.",
    ]

    evidence = {
        "generated_at": _utc_now(),
        "scope": "phase7_export_profiling_baseline",
        "database": {
            "path": str(database_path),
            "schema_version": SCHEMA_VERSION,
            "no_data_regeneration": True,
            "no_model_retraining": True,
            "no_model_rescoring": True,
        },
        "canonical_context": canonical,
        "audience_preparation": {
            "prepared": bool(preparation.get("prepared")),
            "analytics_prepared": bool(preparation.get("analytics_prepared")),
            "boundary_count": int(preparation.get("boundary_count", 0)),
        },
        "saved_audiences": {
            key: {
                "audience_id": int(value["audience_id"]),
                "resolved_count": int(value["definition"]["resolved_count"]),
                "selection_mode": str(value["definition"]["selection_mode"]),
                "target_count": value["definition"].get("target_count"),
                "creation_seconds": round(float(value["_create_seconds"]), 6),
            }
            for key, value in saved_audiences.items()
        },
        "baseline_cases": [email_case, direct_mail_case, all_matching_case],
        "selection_query_plan_samples": plans,
        "implementation_signals": {
            "keyset_loop_present": "def _iter_selected_member_chunks" in source_text,
            "temp_id_table_rejoin_present": "CREATE TEMP TABLE IF NOT EXISTS temp_campaign_export_ids" in source_text,
            "boundary_linear_scan_present": "for row in boundaries:" in source_text,
        },
        "dominant_unnecessary_work": dominant_unnecessary_work,
        "next_gate": "H2 optimize unnecessary repeated work while preserving exact output equivalence.",
    }

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"evidence_file": str(EVIDENCE_PATH), "generated_at": evidence["generated_at"]}, indent=2))


if __name__ == "__main__":
    main()
