from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.target_group_preview_service as preview_service
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_targeting_context_service import (
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)
from app.services.target_group_preview_service import (
    get_target_group_preview,
    search_target_group_preview,
)
from app.services.targeting_intelligence_service import _resolution
from tests.test_saved_audience_service import _seed_fixture


@pytest.fixture
def ready_target_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, int]:
    database_path = tmp_path / "phase9-target-group.db"
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
            "income_groups": ["<25K", "50K-74,999", "75K-99,999"],
            "marital_statuses": ["Married", "Single"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=targeting_context_id,
    )

    def ready_resolution(*_args, **_kwargs):
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="READY",
            explanation="Verified explicit general source.",
            explicitly_linked=True,
            technical_details={"scoring_run_id": scoring_run_id},
        )

    monkeypatch.setattr(
        preview_service,
        "resolve_targeting_intelligence",
        ready_resolution,
    )
    return database_path, targeting_context_id


def test_exact_preview_reconciles_disjoint_business_filters(
    ready_target_group: tuple[Path, int],
) -> None:
    database_path, targeting_context_id = ready_target_group

    first = get_target_group_preview(
        database_path, targeting_context_id=targeting_context_id
    )
    second = get_target_group_preview(
        database_path, targeting_context_id=targeting_context_id
    )

    assert first == second
    assert first["currentness_label"] == "Up to date"
    assert first["kpis"] == {
        "potential_customers_available": 6,
        "matching_your_preferences": 2,
        "selected_for_target_group": 2,
        "percent_of_available_people": pytest.approx(100 / 3),
        "average_targeting_match_score": pytest.approx(0.85),
        "strongest_match": pytest.approx(0.94),
        "lowest_selected_match": pytest.approx(0.76),
    }
    bands = first["targeting_match_score_distribution"]
    assert [item["category"] for item in bands] == [
        "0.90–1.00",
        "0.80–<0.90",
        "0.70–<0.80",
        "0.60–<0.70",
        "0.00–<0.60",
    ]
    assert [item["count"] for item in bands] == [1, 0, 1, 0, 0]
    assert sum(item["count"] for item in bands) == 2
    assert set(first["demographic_mix"]) == {
        "Age Mix",
        "Gender Mix",
        "Where They Are Located",
        "Income Mix",
        "Marital Status Mix",
    }
    for distribution in first["demographic_mix"].values():
        assert sum(item["count"] for item in distribution) == 2
    explanation = first["why_these_people"].lower()
    assert "broad threshold of 0.60" in explanation
    assert "predict a purchase outcome" in explanation


def test_search_uses_stable_keyset_without_duplicate_ids(
    ready_target_group: tuple[Path, int],
) -> None:
    database_path, targeting_context_id = ready_target_group

    first = search_target_group_preview(
        database_path,
        targeting_context_id=targeting_context_id,
        page_size=1,
        cursor=None,
    )
    second = search_target_group_preview(
        database_path,
        targeting_context_id=targeting_context_id,
        page_size=1,
        cursor=first["next_cursor"],
    )

    rows = first["rows"] + second["rows"]
    assert [row["potential_customer_id"] for row in rows] == [
        "PER_000002",
        "PER_000005",
    ]
    assert len({row["potential_customer_id"] for row in rows}) == len(rows)
    assert first["has_more"] is True
    assert second["has_more"] is False
    assert second["next_cursor"] is None
    assert set(rows[0]) == {
        "potential_customer_id",
        "targeting_match_score",
        "top_matching_percent",
        "match_strength",
        "age",
        "gender",
        "state",
        "individual_yearly_income",
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "family_member_count",
        "type_of_employment",
    }
    assert not (
        {"name", "email", "phone", "street_address", "customer_id"} & set(rows[0])
    )


def test_preview_api_is_gated_and_validates_cursor(
    ready_target_group: tuple[Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, targeting_context_id = ready_target_group
    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            preview = client.get(
                f"/api/campaign-planner/contexts/{targeting_context_id}/target-group-preview"
            )
            search = client.post(
                f"/api/campaign-planner/contexts/{targeting_context_id}/target-group-search",
                json={"page_size": 1, "cursor": None},
            )
            invalid_cursor = client.post(
                f"/api/campaign-planner/contexts/{targeting_context_id}/target-group-search",
                json={"page_size": 1, "cursor": "not-a-valid-cursor"},
            )
            assert preview.status_code == 200
            assert search.status_code == 200
            assert list(search.json()["rows"][0]) == [
                "potential_customer_id",
                "targeting_match_score",
                "top_matching_percent",
                "match_strength",
                "age",
                "gender",
                "state",
                "individual_yearly_income",
                "marital_status",
                "education",
                "employment_status",
                "resident_status",
                "resident_type",
                "family_member_count",
                "type_of_employment",
            ]
            assert invalid_cursor.status_code == 422

            monkeypatch.setattr(
                preview_service,
                "resolve_targeting_intelligence",
                lambda *_args, **_kwargs: _resolution(
                    targeting_context_id=targeting_context_id,
                    status="NEEDS_REFRESH",
                    explanation="Audience preparation needs refresh.",
                    explicitly_linked=True,
                ),
            )
            blocked = client.get(
                f"/api/campaign-planner/contexts/{targeting_context_id}/target-group-preview"
            )
            assert blocked.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_selected_demographic_bucket_can_return_an_exact_zero_state(
    ready_target_group: tuple[Path, int],
) -> None:
    database_path, targeting_context_id = ready_target_group
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "VERY_STRONG",
            "states": ["Ohio"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=targeting_context_id,
    )

    preview = get_target_group_preview(
        database_path, targeting_context_id=targeting_context_id
    )
    page = search_target_group_preview(
        database_path,
        targeting_context_id=targeting_context_id,
        page_size=25,
        cursor=None,
    )

    assert preview["currentness_label"] == "Up to date"
    assert preview["kpis"]["matching_your_preferences"] == 0
    assert preview["kpis"]["selected_for_target_group"] == 0
    assert preview["kpis"]["percent_of_available_people"] == 0
    assert preview["kpis"]["average_targeting_match_score"] is None
    assert preview["kpis"]["strongest_match"] is None
    assert preview["kpis"]["lowest_selected_match"] is None
    assert "contains 0 potential customers" in preview["why_these_people"]
    assert page["rows"] == []
    assert page["has_more"] is False


def test_default_preview_ui_is_business_friendly_and_privacy_safe() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "target-group-preview.js").read_text(
        encoding="utf-8"
    )

    for label in (
        "Potential Customers Available",
        "Matching Your Preferences",
        "Selected for Target Group",
        "% of Available People",
        "Average Targeting Match Score",
        "Strongest Match",
        "Lowest Selected Match",
        "Why these people?",
    ):
        assert label in html
    accessible_header = '<thead><tr><th scope="col">Potential Customer ID</th>'
    assert accessible_header in html
    table_head = html.split(accessible_header, 1)[1].split("</thead>", 1)[0]
    assert table_head.count('scope="col"') == 7
    assert all(field not in table_head.lower() for field in ("email", "phone", "street"))
    assert "row.customer_id" not in script
    assert "next_cursor" in script
    assert "renderedCustomerIds" in script
    assert 'querySelector("#planner-next-4").disabled = state !== "ready"' in script
