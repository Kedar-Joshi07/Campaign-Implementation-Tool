from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.campaign_targeting as campaign_targeting_router
from app.dependencies import get_database_path
from app.main import app
from app.services.campaign_targeting_context_service import CampaignContextServiceError
from app.services.campaign_targeting_contract_service import (
    CampaignTargetingContractValidationError,
    normalize_business_targeting_criteria,
    normalize_campaign_targeting_context,
)


REFERENCE_VALUES = {
    "product_ids": {"PRD-001"},
    "campaign_types": {"Retention"},
    "campaign_categories": {"Lifecycle"},
    "offer_types": {"Loyalty"},
    "campaign_channels": {"Email"},
    "gender": {"Female"},
    "state": {"Ohio"},
    "marital_status": {"Married"},
    "education": {"Graduate"},
    "employment_status": {"Employed"},
    "resident_status": {"Owner"},
    "resident_type": {"House"},
    "type_of_employment": {"Salaried"},
}


def _assert_validation_message(payload: dict, expected: str) -> None:
    with pytest.raises(CampaignTargetingContractValidationError) as failure:
        normalize_business_targeting_criteria(
            payload, allowed_values=REFERENCE_VALUES
        )
    message = str(failure.value)
    assert expected in message
    for internal_term in ("target_count", "selection_mode", "ValidationError"):
        assert internal_term not in message


def test_business_validation_covers_required_removed_and_unavailable_context() -> None:
    with pytest.raises(
        CampaignTargetingContractValidationError,
        match="Choose at least one currently available product",
    ):
        normalize_campaign_targeting_context(
            {
                "product_ids": [],
                "campaign_types": [],
                "campaign_categories": [],
                "offer_types": [],
                "campaign_channel": "EMAIL",
            },
            allowed_values=REFERENCE_VALUES,
        )

    with pytest.raises(
        CampaignTargetingContractValidationError, match="no longer available"
    ) as removed:
        normalize_campaign_targeting_context(
            {
                "product_ids": ["REMOVED-PRODUCT"],
                "campaign_types": [],
                "campaign_categories": [],
                "offer_types": [],
                "campaign_channel": "EMAIL",
            },
            allowed_values=REFERENCE_VALUES,
        )
    assert "Refresh the choices" in str(removed.value)


def test_business_validation_covers_strength_conflict_zero_and_top_n() -> None:
    _assert_validation_message(
        {"match_strength": "IMPOSSIBLE"},
        "Choose one of the available Targeting Match options",
    )
    _assert_validation_message(
        {"family_member_count_min": 5, "family_member_count_max": 2},
        "minimum family size that is not higher than the maximum",
    )
    _assert_validation_message(
        {"family_member_count_min": 0},
        "Family size must be a whole number greater than zero",
    )
    _assert_validation_message(
        {"selection_mode": "TOP_N"},
        "Enter a whole number greater than zero",
    )


def test_frontend_exposes_loading_empty_retry_currentness_and_safe_save_states() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    preview = (root / "frontend" / "js" / "target-group-preview.js").read_text(
        encoding="utf-8"
    )
    intelligence = (
        root / "frontend" / "js" / "targeting-intelligence.js"
    ).read_text(encoding="utf-8")
    review = (root / "frontend" / "js" / "campaign-review.js").read_text(
        encoding="utf-8"
    )
    context = (root / "frontend" / "js" / "campaign-context.js").read_text(
        encoding="utf-8"
    )
    targeting = (root / "frontend" / "js" / "business-targeting.js").read_text(
        encoding="utf-8"
    )

    for element_id in (
        "planner-context-loading",
        "planner-context-empty",
        "planner-context-error",
        "planner-target-preview-loading",
        "planner-target-preview-empty",
        "planner-target-preview-error",
        "planner-save-success",
        "planner-review-error",
    ):
        assert f'id="{element_id}"' in html
    assert "The exact result is zero" in html
    assert 'setPreviewState(isEmpty ? "empty" : "ready")' in preview
    assert 'READY: "Up to date"' in intelligence
    assert 'STALE: "Needs refresh"' in intelligence
    assert 'NOT_AVAILABLE: "Not available"' in intelligence
    assert "saveInFlight" in review
    assert "Save is already in progress" in review
    assert "idempotent_replay" in review
    assert "showSaveError" in context
    assert "showSaveError" in targeting


def test_unexpected_backend_error_is_sanitized_for_business_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args, **_kwargs):
        raise CampaignContextServiceError(
            "sqlite SELECT failed at C:\\private\\project; RuntimeError"
        )

    monkeypatch.setattr(campaign_targeting_router, "get_target_group_preview", explode)
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "safe-errors.db"
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/campaign-planner/contexts/1/target-group-preview"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "try again" in detail
    for unsafe in ("sqlite", "SELECT", "private", "RuntimeError", "\\project"):
        assert unsafe not in detail
