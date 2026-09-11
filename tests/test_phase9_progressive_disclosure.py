from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.schemas.campaign_targeting import (
    Phase9CampaignDraftResponse,
    TargetGroupPreviewResponse,
)
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_targeting_context_service import (
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)
from app.services.target_group_campaign_service import (
    save_target_group_and_create_campaign_draft,
)
from app.services.target_group_preview_service import get_target_group_preview
from app.services.targeting_intelligence_service import link_targeting_intelligence
from tests.test_saved_audience_service import _seed_fixture


@pytest.fixture(scope="module")
def audited_phase9_flow(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    database_path = tmp_path_factory.mktemp("phase9-progressive") / "audit.db"
    initialize_database(database_path)
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    context = save_campaign_targeting_context(
        database_path,
        {
            "product_ids": ["PRD_001"],
            "campaign_types": [],
            "campaign_categories": [],
            "offer_types": [],
            "campaign_channel": "EMAIL",
            "historical_campaign_channels": [],
        },
    )
    targeting_context_id = int(context["targeting_context_id"])
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "age_groups": ["25-34", "45-54"],
            "income_groups": ["50K-74,999", "75K-99,999"],
            "marital_statuses": ["Married", "Single"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=targeting_context_id,
    )
    linked = link_targeting_intelligence(
        database_path,
        targeting_context_id=targeting_context_id,
        scoring_run_id=scoring_run_id,
    )
    assert linked.status == "READY"
    preview = get_target_group_preview(
        database_path, targeting_context_id=targeting_context_id
    )
    draft = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload={
            "target_group_name": "Progressive Disclosure Group",
            "target_group_description": "Audit-safe target group",
            "campaign_name": "Progressive Disclosure Campaign",
            "campaign_description": "Business campaign",
            "planned_launch_date": "2026-10-20",
        },
    )
    TargetGroupPreviewResponse.model_validate(preview)
    Phase9CampaignDraftResponse.model_validate(draft)
    return {
        "database_path": database_path,
        "scoring_run_id": scoring_run_id,
        "preview": preview,
        "draft": draft,
    }


def _assert_no_pii_keys(value: Any) -> None:
    prohibited = {
        "first_name",
        "last_name",
        "email",
        "phone",
        "address_line_1",
        "address_line_2",
        "city",
        "postal_code",
        "customer_id",
        "person_id",
    }
    if isinstance(value, dict):
        assert prohibited.isdisjoint(value)
        for child in value.values():
            _assert_no_pii_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_pii_keys(child)


def test_business_explanation_covers_context_preferences_strength_size_and_currentness(
    audited_phase9_flow: dict[str, Any],
) -> None:
    preview = audited_phase9_flow["preview"]
    explanation = preview["why_these_people"]

    assert preview["kpis"]["selected_for_target_group"] == 2
    assert "current, up-to-date Target Group contains 2 potential customers" in explanation
    assert "Email request" in explanation
    assert "1 selected product" in explanation
    assert "age: 25-34, 45-54" in explanation
    assert "income: 50K-74,999, 75K-99,999" in explanation
    assert "marital status: Married, Single" in explanation
    assert "Broad setting" in explanation
    assert "a wider degree of similarity" in explanation
    assert "do not establish why a person will act" in explanation


def test_collapsed_technical_provenance_matches_backend_and_contains_no_pii(
    audited_phase9_flow: dict[str, Any],
) -> None:
    database_path: Path = audited_phase9_flow["database_path"]
    scoring_run_id = audited_phase9_flow["scoring_run_id"]
    preview_details = audited_phase9_flow["preview"]["technical_details"]
    draft = audited_phase9_flow["draft"]
    draft_details = draft["technical_details"]

    with get_connection(database_path) as connection:
        source = dict(
            connection.execute(
                """
                SELECT s.*, m.analysis_run_id
                FROM scoring_runs AS s
                JOIN model_runs AS m ON m.model_run_id = s.model_run_id
                WHERE s.scoring_run_id = ?
                """,
                (scoring_run_id,),
            ).fetchone()
        )
        metadata = dict(
            connection.execute(
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (draft["saved_target_group"]["saved_target_group_id"],),
            ).fetchone()
        )
    summary = json.loads(source["score_summary_json"])

    for details in (preview_details, draft_details):
        assert details["scoring_run_id"] == source["scoring_run_id"]
        assert details["model_run_id"] == source["model_run_id"]
        assert details["analysis_run_id"] == source["analysis_run_id"]
        assert details["selected_candidate"] == source["selected_candidate"]
        assert details["model_role_policy_version"] == source[
            "model_role_policy_version"
        ]
        assert details["feature_contract_version"] == source[
            "feature_contract_version"
        ]
        assert details["feature_contract_sha256"] == source[
            "feature_contract_sha256"
        ]
        assert details["artifact_sha256"] == source["artifact_sha256"]
        assert details["customer_source_checksum"] == summary[
            "customer_source_checksum"
        ]
        assert details["campaign_sales_source_checksum"] == summary[
            "campaign_sales_source_checksum"
        ]
        assert details["demographic_source_checksum"] == summary[
            "demographic_source_checksum"
        ]
        assert details["source_status"] == "READY"
        assert details["source_currentness"] == "UP_TO_DATE"
        assert details["audience_filter_hash"] == metadata[
            "filter_branches_sha256"
        ]
        _assert_no_pii_keys(details)

    assert preview_details["saved_audience_id"] is None
    assert draft_details["saved_audience_id"] == metadata["audience_id"]
    for field in (
        "targeting_intelligence_resolution_contract_version",
        "campaign_targeting_context_contract_version",
        "targeting_segment_contract_version",
        "business_match_strength_contract_version",
        "audience_filter_contract_version",
        "target_group_preview_contract_version",
        "target_group_campaign_contract_version",
        "saved_target_group_contract_version",
    ):
        if draft_details[field] is not None:
            assert draft_details[field] == "1"


def test_default_business_path_hides_jargon_and_keeps_accessible_analyst_tools() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    preview_service = (
        root / "app" / "services" / "target_group_preview_service.py"
    ).read_text(encoding="utf-8")
    targeting_script = (
        root / "frontend" / "js" / "targeting-intelligence.js"
    ).read_text(encoding="utf-8")
    review_script = (root / "frontend" / "js" / "campaign-review.js").read_text(
        encoding="utf-8"
    )

    why_source = preview_service.split("def _why_these_people", 1)[1].split(
        "def _filter_branches_hash", 1
    )[0]
    for jargon in (
        "run_id",
        "sha256",
        "artifact",
        "selected_candidate",
        "contract_version",
        "saved_audience_id",
    ):
        assert jargon not in why_source.casefold()

    step_four_and_five = html.split('id="planner-step-panel-4"', 1)[1].split(
        'id="campaigns-view"', 1
    )[0]
    default_markup = re.sub(
        r"<details\b.*?</details>", "", step_four_and_five, flags=re.DOTALL
    )
    for technical_label in (
        "Scoring run",
        "Source analysis",
        "Model run",
        "Artifact SHA-256",
        "Audience filter hash",
        "Saved Audience ID",
        "contract version",
    ):
        assert technical_label not in default_markup

    assert html.count("<summary>View technical details</summary>") >= 2
    assert '<details id="planner-intelligence-advanced"' in html
    assert '<details id="planner-review-technical"' in html
    assert '<details id="planner-intelligence-advanced" class=' in html
    assert '<details id="planner-review-technical" class=' in html
    assert "<details id=\"planner-intelligence-advanced\" open" not in html
    assert "<details id=\"planner-review-technical\" open" not in html
    assert "Advanced / Analyst Tools" in html
    for capability in (
        "Historical Analysis",
        "Model Training &amp; Prospect Scoring",
        "Audience Explorer",
    ):
        assert capability in html
    assert "UX separation only" in html
    for label in (
        "Targeting / scoring run",
        "Source analysis",
        "Model run",
        "Selected candidate",
        "Feature contract version",
        "Model policy",
        "Customer source checksum",
        "Artifact SHA-256",
        "Audience filter hash",
        "Saved Audience ID",
        "Saved Target Group contract",
    ):
        assert label in targeting_script
    assert "renderPhase9TechnicalDetails" in review_script
    assert "innerHTML" not in targeting_script
    assert "innerHTML" not in review_script


def test_business_navigation_exposes_saved_target_groups_and_insights() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    app_script = (root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    saved_groups_script = (
        root / "frontend" / "js" / "saved-target-groups.js"
    ).read_text(encoding="utf-8")

    assert 'data-view-target="saved-target-groups"' in html
    assert 'data-view-target="insights"' in html
    assert 'data-view="saved-target-groups"' in html
    assert 'data-view="insights"' in html
    assert '"saved-target-groups": "Saved Target Groups"' in app_script
    assert 'insights: "Insights"' in app_script
    assert "/api/audiences?limit=100&offset=0" in saved_groups_script
    assert 'group.is_current ? "Up to date" : "Needs refresh"' in saved_groups_script
    for forbidden in ("email", "phone", "street", "customer_id"):
        assert forbidden not in saved_groups_script.lower()
