from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.match_strength_recommendation_service as recommendation_service
import app.services.target_group_preview_service as preview_service
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_targeting_context_service import (
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)
from app.services.match_strength_recommendation_service import (
    MATCH_STRENGTH_DISCLAIMER,
    _recommend_strength,
    get_match_strength_recommendation,
)
from app.services.targeting_intelligence_service import _resolution
from tests.test_saved_audience_service import _seed_fixture


@pytest.fixture
def recommendation_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, int]:
    database_path = tmp_path / "phase9-recommendation.db"
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
            "match_strength": "GOOD",
            "selection_mode": "TOP_N",
            "target_count": 1,
        },
        targeting_context_id=targeting_context_id,
    )

    monkeypatch.setattr(
        preview_service,
        "resolve_targeting_intelligence",
        lambda *_args, **_kwargs: _resolution(
            targeting_context_id=targeting_context_id,
            status="READY",
            explanation="Verified explicit general source.",
            explicitly_linked=True,
            technical_details={"scoring_run_id": scoring_run_id},
        ),
    )
    monkeypatch.setattr(
        recommendation_service,
        "MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT",
        4,
    )
    monkeypatch.setattr(
        recommendation_service,
        "MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER",
        2.0,
    )
    return database_path, targeting_context_id


def test_exact_comparison_holds_other_criteria_and_ignores_top_n_cap(
    recommendation_context: tuple[Path, int],
) -> None:
    database_path, targeting_context_id = recommendation_context

    first = get_match_strength_recommendation(
        database_path, targeting_context_id=targeting_context_id
    )
    second = get_match_strength_recommendation(
        database_path, targeting_context_id=targeting_context_id
    )

    assert first == second
    assert first["recommendation_rule_version"] == "1"
    assert first["practical_minimum_count"] == 4
    assert first["very_strong_minimum_multiplier"] == 2.0
    assert first["very_strong_minimum_count"] == 8
    assert first["recommendation_status"] == "RECOMMENDED"
    assert first["recommendation_reason"] == "STRONG_USABLE"
    assert first["recommended_match_strength"] == "STRONG"
    assert first["disclaimer"] == MATCH_STRENGTH_DISCLAIMER
    comparisons = first["comparisons"]
    assert [item["match_strength"] for item in comparisons] == [
        "VERY_STRONG",
        "STRONG",
        "GOOD",
        "BROAD",
    ]
    assert [item["exact_matching_count"] for item in comparisons] == [3, 4, 5, 5]
    assert [item["percent_of_available_population"] for item in comparisons] == [
        pytest.approx(50.0),
        pytest.approx(100 * 4 / 6),
        pytest.approx(100 * 5 / 6),
        pytest.approx(100 * 5 / 6),
    ]
    assert [item["change_from_current"] for item in comparisons] == [-2, -1, 0, 0]
    assert [item["relationship_to_current"] for item in comparisons] == [
        "NARROWER",
        "NARROWER",
        "CURRENT",
        "BROADER",
    ]
    assert [item["recommended"] for item in comparisons] == [False, True, False, False]


@pytest.mark.parametrize(
    ("counts", "minimum", "very_strong_minimum", "expected_strength", "expected_reason"),
    [
        (
            {"VERY_STRONG": 5, "STRONG": 6, "GOOD": 7, "BROAD": 8},
            5,
            5,
            "VERY_STRONG",
            "VERY_STRONG_USABLE",
        ),
        (
            {"VERY_STRONG": 4, "STRONG": 5, "GOOD": 7, "BROAD": 8},
            5,
            10,
            "STRONG",
            "STRONG_USABLE",
        ),
        (
            {"VERY_STRONG": 3, "STRONG": 4, "GOOD": 5, "BROAD": 8},
            5,
            10,
            "GOOD",
            "GOOD_USABLE",
        ),
        (
            {"VERY_STRONG": 2, "STRONG": 3, "GOOD": 4, "BROAD": 5},
            5,
            10,
            None,
            "BROAD_ONLY_USABLE",
        ),
        (
            {"VERY_STRONG": 1, "STRONG": 2, "GOOD": 3, "BROAD": 4},
            5,
            10,
            None,
            "ALL_TOO_SMALL",
        ),
    ],
)
def test_versioned_rule_has_no_silent_broad_fallback(
    counts: dict[str, int],
    minimum: int,
    very_strong_minimum: int,
    expected_strength: str | None,
    expected_reason: str,
) -> None:
    recommended, reason, _heading, _explanation = _recommend_strength(
        counts,
        practical_minimum_count=minimum,
        very_strong_minimum_count=very_strong_minimum,
    )

    assert recommended == expected_strength
    assert reason == expected_reason


def test_api_response_is_exact_and_ready_gated(
    recommendation_context: tuple[Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, targeting_context_id = recommendation_context
    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/campaign-planner/contexts/{targeting_context_id}"
                "/match-strength-recommendation"
            )
            assert response.status_code == 200
            assert response.json()["recommended_match_strength"] == "STRONG"

            monkeypatch.setattr(
                preview_service,
                "resolve_targeting_intelligence",
                lambda *_args, **_kwargs: _resolution(
                    targeting_context_id=targeting_context_id,
                    status="NOT_AVAILABLE",
                    explanation="No source is explicitly linked.",
                    explicitly_linked=False,
                ),
            )
            blocked = client.get(
                f"/api/campaign-planner/contexts/{targeting_context_id}"
                "/match-strength-recommendation"
            )
            assert blocked.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_comparison_ui_uses_business_copy_and_sequential_requests() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "target-group-preview.js").read_text(
        encoding="utf-8"
    )
    panel = html.split('id="planner-match-strength-panel"', 1)[1].split(
        "</section>", 1
    )[0]

    assert "Match Strength Comparison" in panel
    assert "Exact match-strength comparison" in panel
    load_function = script.split("export async function loadTargetGroupPreview", 1)[1]
    assert load_function.index("const preview = await") < load_function.index(
        "const recommendation = await"
    ) < load_function.index("const page = await")
    for forbidden in (
        "precision",
        "recall",
        "classifier threshold",
        "roc",
        "auc",
        "calibration",
        "posterior probability",
    ):
        assert forbidden not in (panel + script).lower()
    assert "Recommended" in script
    assert "relationship_to_current" in script
