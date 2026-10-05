"""HTTP response coverage for bounded calibration fail-closed states."""

# ruff: noqa: F401 - imported pytest fixture is intentionally injected.

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.routers import potential_customer_search
from app.services.source_currentness_service import (
    GovernedCalibrationEligibility,
    public_calibration_currentness,
)
from tests.test_intelligence_attestation_currentness import (
    attestation_case,
    verified_generation_source,
)
from tests.test_preflight_materialization_parity import _context, parity_case


@pytest.mark.parametrize(
    ("status", "reason", "eligible", "expected_currentness"),
    (
        ("NOT_AVAILABLE", "GOVERNED_CALIBRATION_NOT_AVAILABLE", False, "NOT_AVAILABLE"),
        ("CURRENT", "ELIGIBLE", True, "CURRENT"),
        ("STALE", "AUTHORITATIVE_SOURCES_STALE", False, "STALE"),
        ("INELIGIBLE", "CALIBRATION_GOVERNANCE_INCOMPATIBLE", False, "UNVERIFIED"),
        ("INELIGIBLE", "CALIBRATION_LINEAGE_INVALID", False, "UNVERIFIED"),
        ("CANDIDATE", "CALIBRATION_NOT_PROMOTED", False, "NOT_AVAILABLE"),
        ("REJECTED", "CALIBRATION_NOT_PROMOTED", False, "NOT_AVAILABLE"),
        ("UNVERIFIED", "CURRENT_ATTESTATION_REQUIRED", False, "UNVERIFIED"),
    ),
)
def test_preflight_internal_states_have_bounded_http_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    reason: str,
    eligible: bool,
    expected_currentness: str,
) -> None:
    decision = GovernedCalibrationEligibility(
        eligible,
        1 if status != "NOT_AVAILABLE" else None,
        status,
        reason,
        "Bounded safe calibration status.",
    )
    assert public_calibration_currentness(decision) == expected_currentness
    response = {
        "demographic_count": 0,
        "bucket_count": 0,
        "intersection_count": 0,
        "qualifying_count": 0,
        "selected_count": 0,
        "demo_ready": False,
        "generation_id": 1,
        "scoring_run_id": 1,
        "calibration_artifact_id": decision.calibration_artifact_id,
        "calibration_currentness": expected_currentness,
        "calibration_eligibility": "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        "calibration_reason_code": reason,
        "safe_message": decision.safe_message,
        "criteria_sha256": "a" * 64,
        "filter_branches_sha256": "b" * 64,
        "catalog_version": "c" * 64,
        "source_identity_sha256": "d" * 64,
        "selection_contract_version": "2",
        "selection_mode": "ALL_MATCHING",
        "target_count": None,
    }
    monkeypatch.setattr(
        potential_customer_search,
        "exact_preflight",
        lambda *_args, **_kwargs: response,
    )
    application = FastAPI()
    application.include_router(potential_customer_search.router)
    application.dependency_overrides[get_database_path] = lambda: tmp_path / "unused.db"

    with TestClient(application) as client:
        result = client.post(
            "/api/potential-customer-search/preflight",
            json={
                "context": {},
                "criteria": {},
                "propensity_bucket": "0.70",
            },
        )

    assert result.status_code == 200, result.text
    assert result.json()["calibration_currentness"] == expected_currentness
    assert result.json()["calibration_reason_code"] == reason


@pytest.mark.parametrize(
    ("scenario", "expected_currentness", "expected_reason"),
    (
        ("NO_CALIBRATION", "NOT_AVAILABLE", "GOVERNED_CALIBRATION_NOT_AVAILABLE"),
        ("CURRENT", "CURRENT", "ELIGIBLE"),
        ("STALE", "STALE", "AUTHORITATIVE_SOURCES_STALE"),
        ("LEGACY_V1", "UNVERIFIED", "CALIBRATION_GOVERNANCE_INCOMPATIBLE"),
        ("MALFORMED_LINEAGE", "UNVERIFIED", "CALIBRATION_LINEAGE_INVALID"),
        ("WRONG_MODEL", "UNVERIFIED", "CALIBRATION_GOVERNANCE_INCOMPATIBLE"),
        ("CANDIDATE", "NOT_AVAILABLE", "CALIBRATION_NOT_PROMOTED"),
        ("REJECTED", "NOT_AVAILABLE", "CALIBRATION_NOT_PROMOTED"),
        ("UNVERIFIED", "UNVERIFIED", "CURRENT_ATTESTATION_REQUIRED"),
    ),
)
def test_real_database_preflight_states_are_bounded_through_http(
    parity_case,
    scenario: str,
    expected_currentness: str,
    expected_reason: str,
) -> None:
    path, _root, context_id, generation, calibration_id = parity_case
    with get_connection(path, write=True) as connection:
        if scenario == "NO_CALIBRATION":
            connection.execute(
                "DELETE FROM calibrated_propensity_scores WHERE calibration_artifact_id=?",
                (calibration_id,),
            )
            connection.execute(
                "DELETE FROM score_calibration_artifacts WHERE calibration_artifact_id=?",
                (calibration_id,),
            )
        elif scenario == "STALE":
            connection.execute(
                """UPDATE data_import_runs SET source_checksum=?
                   WHERE import_id=(SELECT MAX(import_id) FROM data_import_runs
                                    WHERE dataset_name='demographics'
                                      AND status='COMPLETED')""",
                ("f" * 64,),
            )
        elif scenario == "LEGACY_V1":
            connection.execute(
                """UPDATE score_calibration_artifacts
                   SET calibration_contract_version='1'
                   WHERE calibration_artifact_id=?""",
                (calibration_id,),
            )
        elif scenario == "MALFORMED_LINEAGE":
            connection.execute(
                """UPDATE score_calibration_artifacts SET split_lineage_json='{}'
                   WHERE calibration_artifact_id=?""",
                (calibration_id,),
            )
        elif scenario == "WRONG_MODEL":
            columns = [
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(model_runs)")
                if row["name"] != "model_run_id"
            ]
            column_sql = ",".join(f'"{column}"' for column in columns)
            wrong_model_id = int(
                connection.execute(
                    f"""INSERT INTO model_runs ({column_sql})
                         SELECT {column_sql} FROM model_runs WHERE model_run_id=?""",
                    (generation["model_run_id"],),
                ).lastrowid
            )
            connection.execute(
                """UPDATE score_calibration_artifacts SET model_run_id=?
                   WHERE calibration_artifact_id=?""",
                (wrong_model_id, calibration_id),
            )
        elif scenario in {"CANDIDATE", "REJECTED"}:
            connection.execute(
                """UPDATE score_calibration_artifacts SET status=?
                   WHERE calibration_artifact_id=?""",
                (scenario, calibration_id),
            )
        elif scenario == "UNVERIFIED":
            connection.execute("DELETE FROM intelligence_verification_attestations")

    application = FastAPI()
    application.include_router(potential_customer_search.router)
    application.dependency_overrides[get_database_path] = lambda: path
    with TestClient(application) as client:
        result = client.post(
            "/api/potential-customer-search/preflight",
            json={
                "context": _context(path, context_id),
                "criteria": {},
                "propensity_bucket": "0.70",
            },
        )

    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["calibration_currentness"] == expected_currentness
    assert payload["calibration_reason_code"] == expected_reason
    assert payload["calibration_eligibility"] == (
        "ELIGIBLE" if scenario == "CURRENT" else "NOT_ELIGIBLE"
    )
