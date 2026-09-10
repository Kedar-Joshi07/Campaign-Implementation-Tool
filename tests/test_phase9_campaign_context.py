from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.campaign_targeting_context_service import (
    get_campaign_context_options,
    get_campaign_targeting_context,
    save_campaign_targeting_context,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase9-context.db"
    initialize_database(path)
    with get_connection(path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES ('CUS-1', '1990-01-01', 'Ohio', 60000, 2)
            """
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_type, campaign_channel, campaign_start_date,
                campaign_end_date, campaign_category, offer_type,
                product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (?, 'CUS-1', ?, ?, ?, ?, '2026-01-01', '2026-01-31',
                      ?, ?, ?, ?, '2026-01-05', 1, 0, 0, 0, 0, 0)
            """,
            (
                (
                    "SALE-1", "CMP-1", "PRD-2", "Retention", "Email",
                    "Lifecycle", "Loyalty", "Savings", "Banking",
                ),
                (
                    "SALE-2", "CMP-2", "PRD-1", "Acquisition", "Paid Social",
                    "Seasonal", "Discount", "Card", "Credit",
                ),
            ),
        )
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _context() -> dict:
    return {
        "product_ids": ["PRD-2", "PRD-1", "PRD-2"],
        "campaign_types": ["Retention", "Acquisition"],
        "campaign_categories": ["Seasonal"],
        "offer_types": ["Discount"],
        "campaign_channel": "email",
        "historical_campaign_channels": ["Paid Social", "Email"],
    }


def test_options_come_from_current_data_and_keep_channel_meanings_separate(
    database_path: Path,
) -> None:
    options = get_campaign_context_options(database_path)

    assert [item["product_id"] for item in options["products"]] == ["PRD-1", "PRD-2"]
    assert options["campaign_types"] == ["Acquisition", "Retention"]
    assert options["campaign_categories"] == ["Lifecycle", "Seasonal"]
    assert options["offer_types"] == ["Discount", "Loyalty"]
    assert options["historical_campaign_channels"] == ["Email", "Paid Social"]
    assert [item["value"] for item in options["delivery_channels"]] == [
        "EMAIL",
        "DIRECT_MAIL",
    ]


def test_context_is_canonical_and_readable_after_save_update_and_reopen(
    database_path: Path,
) -> None:
    created = save_campaign_targeting_context(database_path, _context())
    context_id = created["targeting_context_id"]
    reopened = get_campaign_targeting_context(
        database_path, targeting_context_id=context_id
    )

    assert reopened == created
    assert reopened["context"]["product_ids"] == ["PRD-1", "PRD-2"]
    assert reopened["context"]["campaign_types"] == ["Acquisition", "Retention"]
    assert reopened["context"]["campaign_channel"] == "EMAIL"
    assert reopened["source_scoring_run_id"] is None

    updated = save_campaign_targeting_context(
        database_path,
        {**_context(), "product_ids": ["PRD-2"], "campaign_channel": "DIRECT_MAIL"},
        targeting_context_id=context_id,
    )
    assert updated["targeting_context_id"] == context_id
    assert updated["context"]["product_ids"] == ["PRD-2"]
    assert updated["context"]["campaign_channel"] == "DIRECT_MAIL"
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT targeting_criteria_json, source_scoring_run_id
            FROM campaign_targeting_contexts
            WHERE targeting_context_id = ?
            """,
            (context_id,),
        ).fetchone()
    assert json.loads(row["targeting_criteria_json"])["match_strength"] == "GOOD"
    assert row["source_scoring_run_id"] is None


def test_context_api_rejects_unknown_ids_and_supports_create_and_reopen(
    client: TestClient,
) -> None:
    unknown = client.post(
        "/api/campaign-planner/contexts",
        json={"context": {**_context(), "product_ids": ["UNKNOWN"]}},
    )
    assert unknown.status_code == 422
    assert "no longer available" in unknown.json()["detail"]

    created = client.post(
        "/api/campaign-planner/contexts", json={"context": _context()}
    )
    assert created.status_code == 201
    context_id = created.json()["targeting_context_id"]
    reopened = client.get(f"/api/campaign-planner/contexts/{context_id}")
    assert reopened.status_code == 200
    assert reopened.json() == created.json()


def test_campaign_context_ui_is_dynamic_and_does_not_fuse_models() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "campaign-context.js").read_text(
        encoding="utf-8"
    )

    for element_id in (
        "planner-context-products",
        "planner-context-types",
        "planner-context-categories",
        "planner-context-offers",
        "planner-context-delivery-channel",
        "planner-context-historical-channels",
    ):
        assert f'id="{element_id}"' in html
    assert "/api/campaign-planner/context-options" in script
    assert "options.products" in script
    assert "options.delivery_channels" in script
    assert "model" not in script.lower()
