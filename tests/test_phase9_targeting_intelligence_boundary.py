from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.targeting_intelligence_service as intelligence_service
from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.services.campaign_targeting_context_service import (
    save_campaign_targeting_context,
)
from app.services.targeting_intelligence_service import (
    link_targeting_intelligence,
    resolve_targeting_intelligence,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase9-intelligence.db"
    initialize_database(path)
    with get_connection(path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES ('CUS-1', '1990-01-01', 'Texas', 60000, 2)
            """
        )
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_type, campaign_channel, campaign_start_date,
                campaign_end_date, campaign_category, offer_type,
                product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                'SALE-1', 'CUS-1', 'CMP-1', 'PRD-1', 'Retention', 'Email',
                '2026-01-01', '2026-01-31', 'Lifecycle', 'Loyalty',
                'Savings', 'Banking', '2026-01-05', 1, 0, 0, 0, 0, 0
            )
            """
        )
    return path


@pytest.fixture
def targeting_context_id(database_path: Path) -> int:
    saved = save_campaign_targeting_context(
        database_path,
        {
            "product_ids": ["PRD-1"],
            "campaign_types": ["Retention"],
            "campaign_categories": ["Lifecycle"],
            "offer_types": ["Loyalty"],
            "campaign_channel": "EMAIL",
            "historical_campaign_channels": ["Email"],
        },
    )
    return int(saved["targeting_context_id"])


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _context_row(source_id: int | None) -> dict:
    return {
        "targeting_context_id": 1,
        "source_scoring_run_id": source_id,
        "campaign_context_json": json.dumps(
            {
                "campaign_targeting_context_contract_version": "1",
                "product_ids": ["PRD-1"],
                "campaign_types": ["Retention"],
                "campaign_categories": ["Lifecycle"],
                "offer_types": ["Loyalty"],
                "campaign_channel": "EMAIL",
                "historical_campaign_channels": ["Email"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _source(*, status: str = "COMPLETED", filters: dict | None = None) -> dict:
    return {
        "scoring_run_id": 41,
        "scoring_status": status,
        "model_run_id": 31,
        "analysis_run_id": 21,
        "feature_contract_version": "1",
        "feature_contract_sha256": "f" * 64,
        "artifact_sha256": "a" * 64,
        "score_summary_json": json.dumps(
            {
                "customer_source_checksum": "c" * 64,
                "campaign_sales_source_checksum": "s" * 64,
                "demographic_source_checksum": "d" * 64,
            }
        ),
        "analysis_filters_json": json.dumps(filters or {}),
    }


def _mock_linked_source(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: dict,
    currentness: dict | None = None,
) -> None:
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context",
        lambda _self, _context_id: _context_row(41),
    )
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_targeting_source_details",
        lambda _self, _source_id: source,
    )
    if currentness is not None:
        monkeypatch.setattr(
            intelligence_service,
            "resolve_current_scoring_context_lightweight",
            lambda *_args, **_kwargs: currentness,
        )
        monkeypatch.setattr(
            intelligence_service,
            "get_audience_preparation_status",
            lambda *_args, **_kwargs: {
                "ready_for_current_audience_actions": True,
                "prepared": True,
                "analytics_prepared": True,
                "currentness_issues": [],
            },
        )


def test_no_link_is_not_available_and_never_searches_for_latest(
    database_path: Path,
    targeting_context_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("an unlinked context must not inspect or select a scoring run")

    monkeypatch.setattr(
        intelligence_service,
        "resolve_current_scoring_context_lightweight",
        forbidden,
    )
    resolution = resolve_targeting_intelligence(
        database_path, targeting_context_id=targeting_context_id
    )

    assert resolution.status == "NOT_AVAILABLE"
    assert resolution.explicitly_linked is False
    assert resolution.can_preview is False
    assert resolution.message == "Targeting is not yet available for this campaign"


def test_incomplete_link_needs_refresh(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_linked_source(monkeypatch, source=_source(status="RUNNING"))
    resolution = resolve_targeting_intelligence(database_path, targeting_context_id=1)

    assert resolution.status == "NEEDS_REFRESH"
    assert resolution.can_preview is False


def test_completed_noncanonical_link_is_stale(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_linked_source(
        monkeypatch,
        source=_source(),
        currentness={"is_canonical": False, "issues": ["demographics changed"]},
    )
    resolution = resolve_targeting_intelligence(database_path, targeting_context_id=1)

    assert resolution.status == "STALE"
    assert resolution.can_preview is False
    assert resolution.issues == ["demographics changed"]


def test_current_link_with_mismatched_scope_is_incompatible(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_linked_source(
        monkeypatch,
        source=_source(filters={"product_ids": ["PRD-OTHER"]}),
        currentness={"is_canonical": True, "issues": []},
    )
    resolution = resolve_targeting_intelligence(database_path, targeting_context_id=1)

    assert resolution.status == "INCOMPATIBLE_CONTEXT"
    assert resolution.can_preview is False
    assert resolution.context_specific is True
    assert "products" in resolution.compatibility_checked_dimensions


def test_current_explicit_general_source_is_ready_without_product_claim(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_linked_source(
        monkeypatch,
        source=_source(filters={}),
        currentness={"is_canonical": True, "issues": []},
    )
    resolution = resolve_targeting_intelligence(database_path, targeting_context_id=1)

    assert resolution.status == "READY"
    assert resolution.can_preview is True
    assert resolution.explicitly_linked is True
    assert resolution.context_specific is False
    assert resolution.context_changed_source is False
    assert "not product-specific" in resolution.explanation


def test_boundary_api_defaults_to_not_available_without_source(
    client: TestClient, targeting_context_id: int
) -> None:
    response = client.get(
        f"/api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_AVAILABLE"
    assert response.json()["can_preview"] is False


def test_advanced_link_action_attaches_only_the_explicit_candidate(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, int | None] = {}
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context",
        lambda _self, _context_id: _context_row(None),
    )
    monkeypatch.setattr(
        intelligence_service,
        "_resolve_for_source",
        lambda *_args, **_kwargs: intelligence_service._resolution(
            targeting_context_id=1,
            status="READY",
            explanation="Verified explicit source.",
            explicitly_linked=True,
        ),
    )

    def capture_link(_self, *, targeting_context_id, scoring_run_id, timestamp):
        captured["context"] = targeting_context_id
        captured["source"] = scoring_run_id
        captured["timestamp_present"] = bool(timestamp)
        return True

    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "set_source_scoring_run_id",
        capture_link,
    )
    resolution = link_targeting_intelligence(
        database_path, targeting_context_id=1, scoring_run_id=41
    )

    assert resolution.status == "READY"
    assert captured == {"context": 1, "source": 41, "timestamp_present": True}


def test_normal_business_ui_has_no_raw_source_picker_and_blocks_preview() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "targeting-intelligence.js").read_text(
        encoding="utf-8"
    )

    assert 'id="planner-intelligence-state"' in html
    assert 'id="planner-next-4" class="button button-primary" type="button" disabled' in html
    assert "No estimated or fabricated count is shown" in html
    assert "Advanced technical details" in html
    assert 'name="scoring_run_id"' not in html
    assert "latest" not in script.lower()
    assert "resolution.can_preview" in script
    for status in (
        "READY",
        "NEEDS_REFRESH",
        "STALE",
        "NOT_AVAILABLE",
        "INCOMPATIBLE_CONTEXT",
    ):
        assert f'{status}:' in script
    assert 'READY: "Up to date"' in script
    assert 'NEEDS_REFRESH: "Needs refresh"' in script
    assert 'INCOMPATIBLE_CONTEXT: "Not available"' in script
    assert 'document.querySelector("#planner-next-4").disabled = !resolution.can_preview' in script
