"""HTTP response coverage for bounded calibration fail-closed states."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_database_path
from app.routers import potential_customer_search
from app.services.source_currentness_service import (
    GovernedCalibrationEligibility,
    public_calibration_currentness,
)


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
