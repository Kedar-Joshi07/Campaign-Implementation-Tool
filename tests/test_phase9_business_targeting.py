from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.campaign_targeting_context_service import (
    CampaignContextValidationError,
    get_business_targeting_criteria,
    get_business_targeting_options,
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase9-business-targeting.db"
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
        connection.executemany(
            """
            INSERT INTO demographics (
                person_id, gender, age, state, individual_yearly_income,
                marital_status, education, employment_status, resident_status,
                resident_type, family_member_count, number_of_children_in_family,
                number_of_adults_in_family, type_of_employment, family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "P-1", "Female", 22, "Texas", 20000, "Single", "Graduate",
                    "Employed", "Owner", "House", 3, 1, 2, "Salaried", 90000,
                ),
                (
                    "P-2", "Male", 40, "Ohio", 65000, "Married", "High School",
                    "Retired", "Renter", "Apartment", 1, 0, 1, "Self-employed", 65000,
                ),
                (
                    "P-3", None, 70, "Texas", 180000, None, None,
                    None, None, None, 5, 2, 3, None, 220000,
                ),
            ),
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


def _criteria() -> dict:
    return {
        "match_strength": "strong",
        "genders": ["Female"],
        "age_groups": ["35-44", "18-24"],
        "states": ["Texas", "Ohio", "Texas"],
        "income_groups": ["50K-74,999", "<25K"],
        "marital_statuses": ["Single"],
        "education_levels": ["Graduate"],
        "employment_statuses": ["Employed"],
        "resident_statuses": ["Owner"],
        "resident_types": ["House"],
        "employment_types": ["Salaried"],
        "family_member_count_min": 2,
        "family_member_count_max": 5,
        "top_matching_percent": 20,
        "selection_mode": "TOP_N",
        "target_count": 250,
    }


def test_targeting_options_are_backend_owned_current_and_explicit(
    database_path: Path,
) -> None:
    options = get_business_targeting_options(database_path)

    assert options["default_match_strength"] == "GOOD"
    assert [item["value"] for item in options["match_strengths"]] == [
        "VERY_STRONG", "STRONG", "GOOD", "BROAD"
    ]
    assert [item["minimum_score"] for item in options["match_strengths"]] == [
        0.9, 0.8, 0.7, 0.6
    ]
    assert [item["recommended"] for item in options["match_strengths"]] == [
        False, False, True, False
    ]
    assert [item["value"] for item in options["age_groups"]] == [
        "18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"
    ]
    assert options["genders"] == ["Female", "Male", "Unknown/Other"]
    assert options["states"] == ["Ohio", "Texas"]
    assert options["family_size_minimum"] == 1
    assert options["family_size_maximum"] == 5
    assert "city" not in options and "postal_code" not in options and "street" not in options


def test_targeting_criteria_are_canonical_persisted_and_keep_disjoint_branches(
    database_path: Path, targeting_context_id: int
) -> None:
    saved = save_business_targeting_criteria(
        database_path,
        _criteria(),
        targeting_context_id=targeting_context_id,
    )
    reopened = get_business_targeting_criteria(
        database_path, targeting_context_id=targeting_context_id
    )

    assert reopened == saved
    assert saved["criteria"]["match_strength"] == "STRONG"
    assert saved["criteria"]["states"] == ["Ohio", "Texas"]
    assert saved["criteria"]["age_groups"] == ["18-24", "35-44"]
    assert saved["criteria"]["income_groups"] == ["<25K", "50K-74,999"]
    assert len(saved["audience_filter_branches"]) == 4
    assert saved["audience_selection"] == {"mode": "TOP_N", "target_count": 250}
    assert saved["source_scoring_run_id"] is None


def test_backend_rejects_unknown_values_and_invalid_ranges(
    database_path: Path, targeting_context_id: int
) -> None:
    with pytest.raises(CampaignContextValidationError, match="no longer available"):
        save_business_targeting_criteria(
            database_path,
            {**_criteria(), "states": ["Atlantis"]},
            targeting_context_id=targeting_context_id,
        )
    with pytest.raises(
        CampaignContextValidationError, match="minimum family size"
    ):
        save_business_targeting_criteria(
            database_path,
            {**_criteria(), "family_member_count_min": 6, "family_member_count_max": 2},
            targeting_context_id=targeting_context_id,
        )


def test_targeting_api_validates_saves_and_reopens(
    client: TestClient, targeting_context_id: int
) -> None:
    options = client.get("/api/campaign-planner/targeting-options")
    assert options.status_code == 200
    assert options.json()["default_match_strength"] == "GOOD"

    saved = client.put(
        f"/api/campaign-planner/contexts/{targeting_context_id}/targeting-criteria",
        json={"criteria": _criteria()},
    )
    assert saved.status_code == 200
    reopened = client.get(
        f"/api/campaign-planner/contexts/{targeting_context_id}/targeting-criteria"
    )
    assert reopened.status_code == 200
    assert reopened.json() == saved.json()

    invalid = client.put(
        f"/api/campaign-planner/contexts/{targeting_context_id}/targeting-criteria",
        json={"criteria": {**_criteria(), "genders": ["Unsupported"]}},
    )
    assert invalid.status_code == 422


def test_targeting_ui_has_progressive_disclosure_visible_chips_and_clear_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "business-targeting.js").read_text(
        encoding="utf-8"
    )

    assert 'id="planner-targeting-more"' in html
    assert "More targeting options" in html
    assert 'id="planner-targeting-chips"' in html
    assert 'id="planner-targeting-clear-all"' in html
    assert "street, ZIP, or city-level targeting" in html
    assert "/api/campaign-planner/targeting-options" in script
    assert "options.match_strengths" in script
    assert "Remove ${text}" in script
    assert "selected" in script
