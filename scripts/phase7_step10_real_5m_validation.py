from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
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
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    find_current_canonical_run_for_model_lightweight,
)
from app.services.saved_audience_service import save_audience

DATABASE_PATH = Path("data/campaign_poc.db")
EVIDENCE_PATH = Path("docs/evidence/phase7_real_5m_acceptance.json")
FORBIDDEN_EXPORT_FIELDS = {
    "ethnicity",
    "religion",
    "occupation_industry",
    "family_yearly_income",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "customer_id",
    "phone_number",
}

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


def _response_json(response) -> dict[str, Any] | list[Any]:
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Invalid JSON response ({response.status_code}).") from exc


def _request_json(client: TestClient, method: str, url: str, **kwargs: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    response = client.request(method, url, **kwargs)
    elapsed = time.perf_counter() - started
    return response, elapsed


def _assert_status(response, expected: int, *, context: str) -> None:
    if response.status_code != expected:
        detail = response.text[:500]
        raise RuntimeError(
            f"{context} failed: expected status {expected}, got {response.status_code}. detail={detail}"
        )


def _resolve_canonical_context(database_path: Path) -> dict[str, int]:
    with get_connection(database_path) as connection:
        model_run_rows = connection.execute(
            """
            SELECT model_run_id
            FROM model_runs
            WHERE status = 'COMPLETED'
            ORDER BY model_run_id DESC
            LIMIT 200
            """
        ).fetchall()

    for row in model_run_rows:
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

    raise RuntimeError("No current canonical completed scoring run was found.")


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
            "description": "Phase 7 Step 10 validation fixture",
            "scoring_run_id": scoring_run_id,
            "filters": filters,
            "selection": selection,
            "include_profile_snapshot": True,
        },
    )
    elapsed = time.perf_counter() - started
    payload["_creation_seconds"] = elapsed
    return payload


def _analyze_csv(csv_bytes: bytes) -> dict[str, Any]:
    csv_text = csv_bytes.decode("utf-8")
    reader = csv.DictReader(csv_text.splitlines())
    fieldnames = reader.fieldnames or []

    duplicate_count = 0
    seen_person_ids: set[str] = set()
    person_order_hasher = hashlib.sha256()
    row_count = 0

    for row in reader:
        row_count += 1
        person_id = str(row.get("person_id", "")).strip()
        person_order_hasher.update(person_id.encode("utf-8"))
        person_order_hasher.update(b"\n")
        if person_id in seen_person_ids:
            duplicate_count += 1
        seen_person_ids.add(person_id)

    return {
        "columns": fieldnames,
        "row_count": row_count,
        "duplicate_person_id_count": duplicate_count,
        "person_id_order_sha256": person_order_hasher.hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }


def _latest_event(client: TestClient, campaign_id: int) -> dict[str, Any]:
    response, _ = _request_json(client, "GET", f"/api/campaigns/{campaign_id}/exports?limit=20")
    _assert_status(response, 200, context="List campaign export events")
    events = _response_json(response)
    if not isinstance(events, list) or not events:
        raise RuntimeError("No export events found after export operation.")
    if not isinstance(events[0], dict):
        raise RuntimeError("Invalid export event payload shape.")
    return events[0]


def _campaign_create_finalize_export(
    client: TestClient,
    *,
    campaign_name: str,
    channel: str,
    saved_audience_id: int,
    expected_columns: list[str],
    repeat_export: bool,
) -> dict[str, Any]:
    create_response, create_seconds = _request_json(
        client,
        "POST",
        "/api/campaigns",
        json={
            "campaign_name": campaign_name,
            "description": "Phase 7 Step 10 end-to-end validation",
            "channel": channel,
            "planned_launch_date": "2026-12-01",
            "saved_audience_id": saved_audience_id,
        },
    )
    _assert_status(create_response, 201, context=f"Create {channel} campaign")
    campaign = _response_json(create_response)
    assert isinstance(campaign, dict)
    campaign_id = int(campaign["campaign_id"])

    finalize_response, finalize_seconds = _request_json(
        client,
        "POST",
        f"/api/campaigns/{campaign_id}/finalize",
    )
    _assert_status(finalize_response, 200, context=f"Finalize {channel} campaign")

    run_results: list[dict[str, Any]] = []
    export_runs = 2 if repeat_export else 1

    for run_index in range(export_runs):
        export_response, export_seconds = _request_json(
            client,
            "GET",
            f"/api/campaigns/{campaign_id}/export.csv?acknowledge_pii=true",
        )
        _assert_status(export_response, 200, context=f"Export {channel} campaign run {run_index + 1}")

        csv_stats = _analyze_csv(export_response.content)
        if csv_stats["columns"] != expected_columns:
            raise RuntimeError(
                f"{channel} export columns mismatch: {csv_stats['columns']} != {expected_columns}"
            )

        forbidden_in_header = sorted(set(csv_stats["columns"]) & FORBIDDEN_EXPORT_FIELDS)
        if forbidden_in_header:
            raise RuntimeError(f"Forbidden export fields present: {forbidden_in_header}")

        event = _latest_event(client, campaign_id)
        if event.get("status") != "COMPLETED":
            raise RuntimeError(f"Expected COMPLETED export event, found {event.get('status')}")

        deliverable_count = int(event["deliverable_count"])
        selected_count = int(event["selected_count"])
        undeliverable_count = int(event["undeliverable_count"])
        row_count = int(event["row_count"])

        if deliverable_count + undeliverable_count != selected_count:
            raise RuntimeError("Deliverability reconciliation failed in export event payload.")
        if row_count != deliverable_count:
            raise RuntimeError("Export row_count must equal deliverable_count.")
        if row_count != int(csv_stats["row_count"]):
            raise RuntimeError("CSV row count does not match export event row_count.")
        if int(csv_stats["duplicate_person_id_count"]) != 0:
            raise RuntimeError("Duplicate person_id detected in exported CSV.")

        run_results.append(
            {
                "run": run_index + 1,
                "export_seconds": round(export_seconds, 6),
                "throughput_rows_per_second": round(
                    (row_count / export_seconds) if export_seconds > 0 else 0.0,
                    3,
                ),
                "event": {
                    "export_event_id": event["export_event_id"],
                    "status": event["status"],
                    "selected_count": selected_count,
                    "deliverable_count": deliverable_count,
                    "undeliverable_count": undeliverable_count,
                    "row_count": row_count,
                    "csv_sha256": event["csv_sha256"],
                    "started_at": event["started_at"],
                    "completed_at": event["completed_at"],
                },
                "csv_analysis": csv_stats,
            }
        )

    reproducibility = {
        "runs_compared": len(run_results),
        "selected_order_identical": True,
        "deliverable_count_identical": True,
        "csv_checksum_identical": True,
    }

    if len(run_results) >= 2:
        first = run_results[0]
        second = run_results[1]
        reproducibility = {
            "runs_compared": 2,
            "selected_order_identical": (
                first["csv_analysis"]["person_id_order_sha256"]
                == second["csv_analysis"]["person_id_order_sha256"]
            ),
            "deliverable_count_identical": (
                first["event"]["deliverable_count"] == second["event"]["deliverable_count"]
            ),
            "csv_checksum_identical": (
                first["event"]["csv_sha256"] == second["event"]["csv_sha256"]
            ),
        }

    return {
        "campaign_id": campaign_id,
        "create_seconds": round(create_seconds, 6),
        "finalize_seconds": round(finalize_seconds, 6),
        "runs": run_results,
        "reproducibility": reproducibility,
    }


def _simulate_source_drift_and_validate(
    *,
    source_database: Path,
    campaign_id: int,
) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="phase7_step10_"))
    drift_db = temp_dir / "campaign_poc_drift_copy.db"
    shutil.copy2(source_database, drift_db)

    initialize_database(drift_db)

    with get_connection(drift_db, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,
                source_path,
                started_at,
                completed_at,
                status,
                rows_read,
                rows_inserted,
                rows_rejected,
                source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "demographics",
                "demographics_source_drift.csv.gz",
                "2026-12-15T00:00:00Z",
                "2026-12-15T00:10:00Z",
                "COMPLETED",
                5_000_000,
                5_000_000,
                0,
                "f" * 64,
            ),
        )

    app.dependency_overrides[get_database_path] = lambda: drift_db
    try:
        with TestClient(app) as drift_client:
            currentness_response, _ = _request_json(
                drift_client,
                "GET",
                f"/api/campaigns/{campaign_id}/currentness",
            )
            _assert_status(currentness_response, 200, context="Campaign currentness after source drift")
            currentness = _response_json(currentness_response)
            assert isinstance(currentness, dict)

            export_response, _ = _request_json(
                drift_client,
                "GET",
                f"/api/campaigns/{campaign_id}/export.csv?acknowledge_pii=true",
            )

            if export_response.status_code != 409:
                raise RuntimeError(
                    "Expected 409 export block on drift copy, got "
                    f"{export_response.status_code}: {export_response.text[:500]}"
                )
            blocked_detail = export_response.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()

    return {
        "copy_database_path": str(drift_db),
        "campaign_currentness_is_current": bool(currentness.get("is_current")),
        "campaign_currentness_issues": currentness.get("issues", []),
        "export_blocked_status": 409,
        "export_blocked_detail": blocked_detail,
    }


def main() -> None:
    database_path = initialize_database(DATABASE_PATH)

    app.dependency_overrides[get_database_path] = lambda: database_path
    email_campaign_id: int | None = None
    scoring_run_id: int | None = None
    model_run_id: int | None = None
    preparation_status: dict[str, Any] | None = None
    saved_audiences: dict[str, dict[str, Any]] = {}
    email_result: dict[str, Any] | None = None
    direct_mail_result: dict[str, Any] | None = None
    try:
        canonical_context = _resolve_canonical_context(database_path)
        scoring_run_id = int(canonical_context["scoring_run_id"])
        model_run_id = int(canonical_context["model_run_id"])
        preparation_status = _ensure_prepared(database_path, scoring_run_id)

        saved_audiences["small_topn_1k"] = _create_saved_audience(
            database_path,
            audience_name="Phase7 Step10 Small TopN 1K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 1000},
        )
        saved_audiences["medium_topn_50k"] = _create_saved_audience(
            database_path,
            audience_name="Phase7 Step10 Medium TopN 50K",
            scoring_run_id=scoring_run_id,
            filters={},
            selection={"mode": "TOP_N", "target_count": 50000},
        )
        saved_audiences["large_top_decile"] = _create_saved_audience(
            database_path,
            audience_name="Phase7 Step10 Large Top Decile",
            scoring_run_id=scoring_run_id,
            filters={"top_percentile_max": 10},
            selection={"mode": "ALL_MATCHING"},
        )
        saved_audiences["demographic_all_matching"] = _create_saved_audience(
            database_path,
            audience_name="Phase7 Step10 Demographic All Matching",
            scoring_run_id=scoring_run_id,
            filters={"state": ["California"], "age_min": 30, "age_max": 60},
            selection={"mode": "ALL_MATCHING"},
        )

        with TestClient(app) as client:
            email_result = _campaign_create_finalize_export(
                client,
                campaign_name="Phase7 Step10 Email Campaign",
                channel="EMAIL",
                saved_audience_id=int(saved_audiences["small_topn_1k"]["audience_id"]),
                expected_columns=EMAIL_COLUMNS,
                repeat_export=True,
            )
            email_campaign_id = int(email_result["campaign_id"])

            direct_mail_result = _campaign_create_finalize_export(
                client,
                campaign_name="Phase7 Step10 Direct Mail Campaign",
                channel="DIRECT_MAIL",
                saved_audience_id=int(saved_audiences["medium_topn_50k"]["audience_id"]),
                expected_columns=DIRECT_MAIL_COLUMNS,
                repeat_export=True,
            )
    finally:
        app.dependency_overrides.clear()

    if email_campaign_id is None:
        raise RuntimeError("Email campaign validation did not produce a campaign id.")
    if scoring_run_id is None or model_run_id is None or preparation_status is None:
        raise RuntimeError("Canonical context was not resolved.")
    if email_result is None or direct_mail_result is None:
        raise RuntimeError("Campaign export validations did not complete.")

    stale_validation = _simulate_source_drift_and_validate(
        source_database=database_path,
        campaign_id=email_campaign_id,
    )

    evidence = {
        "generated_at": _utc_now(),
        "scope": "phase7_step10_real_5m_end_to_end_validation",
        "database": {
            "path": str(database_path),
            "schema_version": SCHEMA_VERSION,
            "no_data_regeneration": True,
            "no_model_retraining_or_rescoring": True,
        },
        "canonical_context": {
            "scoring_run_id": scoring_run_id,
            "model_run_id": model_run_id,
            "audience_preparation": {
                "prepared": bool(preparation_status.get("prepared")),
                "boundary_count": int(preparation_status.get("boundary_count", 0)),
                "rank_contract_version": str(preparation_status.get("rank_contract_version", "")),
                "ready_for_current_audience_actions": bool(
                    preparation_status.get("ready_for_current_audience_actions")
                ),
            },
        },
        "saved_audience_cases": {
            key: {
                "audience_id": int(value["audience_id"]),
                "resolved_count": int(value["definition"]["resolved_count"]),
                "selection_mode": str(value["definition"]["selection_mode"]),
                "target_count": value["definition"].get("target_count"),
                "is_current": bool(value["currentness"]["is_current"]),
                "create_seconds": round(float(value["_creation_seconds"]), 6),
            }
            for key, value in saved_audiences.items()
        },
        "email_e2e": email_result,
        "direct_mail_e2e": direct_mail_result,
        "stale_source_drift_on_db_copy": stale_validation,
        "quality_checks": {
            "forbidden_fields_absent_in_export_headers": True,
            "no_duplicate_person_id_in_export_rows": True,
            "deliverability_reconciliation_verified": True,
        },
        "browser_e2e": {
            "status": "captured_separately",
            "note": "Interactive browser flow evidence captured in phase7_final_acceptance_and_freeze.json",
        },
    }

    if EVIDENCE_PATH.exists():
        EVIDENCE_PATH.unlink()
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"Wrote Step 10 evidence: {EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
