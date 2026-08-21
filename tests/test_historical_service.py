from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories import historical_repository as repository_module
from app.services.historical_service import (
    get_historical_options,
    get_historical_overview,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "historical.db"
    initialize_database(path)
    return path


def _seed_customer(connection, customer_id: str) -> None:
    connection.execute(
        """
        INSERT INTO customers (
            customer_id, date_of_birth, state,
            individual_yearly_income, family_member_count
        ) VALUES (?, '1990-01-15', 'Ohio', 60000, 2)
        """,
        (customer_id,),
    )


def _seed_historical_fixture(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for customer_id in ("CUS_001", "CUS_002", "CUS_003"):
            _seed_customer(connection, customer_id)

        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                campaign_start_date, campaign_end_date,
                product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                net_sales_amount, gross_margin_amount,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "CS_001", "CUS_001", "CMP_001", "PRD_001",
                    "Campaign One", "Retention", "Email",
                    "2025-01-01", "2025-01-31", "Product One", "Category A",
                    "2025-01-05", 1, 1, 1, 1, 100.0, 40.0, 1, 1,
                ),
                (
                    "CS_002", "CUS_001", "CMP_001", "PRD_001",
                    "Campaign One Alternate", "Retention", "Email",
                    "2025-01-01", "2025-01-31", "Product One Alternate", "Category A",
                    "2025-01-20", 1, 0, 0, 0, None, None, 0, 0,
                ),
                (
                    "CS_003", "CUS_002", "CMP_002", "PRD_002",
                    "Campaign Two", "Acquisition", "Social",
                    "2025-02-01", "2025-02-28", "Product Two", "Category B",
                    "2025-02-10", 1, 1, 1, 1, 50.0, 20.0, 0, 0,
                ),
                (
                    "CS_004", "CUS_002", "CMP_002", "PRD_002",
                    "Campaign Two", "Acquisition", "Social",
                    "2025-02-01", "2025-02-28", "Product Two", "Category B",
                    "2025-02-25", 0, 0, 0, 0, None, None, 0, 0,
                ),
                (
                    "CS_005", "CUS_003", "CMP_003", "PRD_003",
                    "Campaign Three", "Retention", "Direct",
                    "2025-03-01", "2025-03-31", "Product Three", "Category B",
                    "2025-03-10", 1, 1, 0, 0, 0.0, None, 0, 0,
                ),
            ),
        )


def test_options_are_real_deduplicated_stable_and_have_frozen_defaults(
    database_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _seed_historical_fixture(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                campaign_start_date, campaign_end_date,
                product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                'CS_BLANK', 'CUS_003', 'CMP_BLANK', 'PRD_BLANK',
                ' ', ' ', NULL, '2025-03-01', '2025-03-31',
                ' ', ' ', '2025-03-05', 1, 0, 0, 0, 0, 0
            )
            """
        )

    with caplog.at_level(logging.INFO):
        options = get_historical_options(database_path)

    assert options["available_date_from"] == "2025-01-05"
    assert options["available_date_to"] == "2025-03-10"
    assert options["campaigns"] == [
        {"campaign_id": "CMP_001", "campaign_name": "Campaign One"},
        {"campaign_id": "CMP_002", "campaign_name": "Campaign Two"},
        {"campaign_id": "CMP_003", "campaign_name": "Campaign Three"},
    ]
    assert options["product_categories"] == ["Category A", "Category B"]
    assert options["products"] == [
        {
            "product_id": "PRD_001",
            "product_name": "Product One",
            "product_category": "Category A",
        },
        {
            "product_id": "PRD_002",
            "product_name": "Product Two",
            "product_category": "Category B",
        },
        {
            "product_id": "PRD_003",
            "product_name": "Product Three",
            "product_category": "Category B",
        },
    ]
    assert options["campaign_channels"] == ["Direct", "Email", "Social"]
    assert options["campaign_types"] == ["Acquisition", "Retention"]
    assert [item["value"] for item in options["conversion_definitions"]] == [
        "ATTRIBUTED_PURCHASE",
        "ANY_PURCHASE",
        "RESPONSE",
    ]
    assert options["defaults"] == {
        "campaign_ids": [],
        "product_ids": [],
        "product_categories": [],
        "campaign_channels": [],
        "campaign_types": [],
        "contact_date_from": "2025-01-05",
        "contact_date_to": "2025-03-10",
        "contacted_only": True,
        "conversion_definition": "ATTRIBUTED_PURCHASE",
    }
    assert "Inconsistent campaign labels detected" in caplog.text
    assert "Inconsistent product labels detected" in caplog.text
    assert "query_count=6" in caplog.text


def test_option_arrays_are_bounded(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_historical_fixture(database_path)
    monkeypatch.setattr(repository_module, "CAMPAIGN_OPTION_LIMIT", 2)
    monkeypatch.setattr(repository_module, "PRODUCT_OPTION_LIMIT", 2)
    monkeypatch.setattr(repository_module, "CATEGORY_OPTION_LIMIT", 1)
    monkeypatch.setattr(repository_module, "CHANNEL_OPTION_LIMIT", 2)
    monkeypatch.setattr(repository_module, "CAMPAIGN_TYPE_OPTION_LIMIT", 1)

    options = get_historical_options(database_path)

    assert [item["campaign_id"] for item in options["campaigns"]] == [
        "CMP_001", "CMP_002"
    ]
    assert [item["product_id"] for item in options["products"]] == [
        "PRD_001", "PRD_002"
    ]
    assert options["product_categories"] == ["Category A"]
    assert options["campaign_channels"] == ["Direct", "Email"]
    assert options["campaign_types"] == ["Acquisition"]


def test_overview_counts_rates_financials_and_ordering_reconcile(
    database_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _seed_historical_fixture(database_path)

    with caplog.at_level(logging.INFO):
        overview = get_historical_overview(database_path)

    assert overview["summary"] == {
        "observation_count": 5,
        "contacted_count": 4,
        "engaged_count": 3,
        "response_count": 2,
        "purchase_count": 2,
        "attributed_purchase_count": 1,
        "net_sales_amount": 150.0,
        "gross_margin_amount": 60.0,
        "distinct_customer_count": 3,
        "distinct_campaign_count": 3,
        "distinct_product_count": 3,
        "contact_date_from": "2025-01-05",
        "contact_date_to": "2025-03-10",
        "engagement_rate": 0.75,
        "response_rate": 0.5,
        "purchase_rate": 0.5,
        "attributed_purchase_rate": 0.25,
    }
    assert [row["month"] for row in overview["monthly_trend"]] == [
        "2025-01", "2025-02", "2025-03"
    ]
    assert [row["observation_count"] for row in overview["monthly_trend"]] == [2, 2, 1]
    assert overview["monthly_trend"][0]["net_sales_amount"] == 100.0
    assert overview["monthly_trend"][1]["purchase_rate"] == 1.0
    assert [row["label"] for row in overview["channel_performance"]] == [
        "Email", "Social", "Direct"
    ]
    assert [row["label"] for row in overview["product_category_performance"]] == [
        "Category B", "Category A"
    ]
    assert [row["campaign_id"] for row in overview["top_campaigns"]] == [
        "CMP_001", "CMP_002", "CMP_003"
    ]
    assert [row["product_id"] for row in overview["top_products"]] == [
        "PRD_001", "PRD_002", "PRD_003"
    ]
    assert overview["label_distribution"] == [
        {
            "pu_label": 1,
            "label": "Known positive observations",
            "observation_count": 1,
        },
        {
            "pu_label": 0,
            "label": "Unlabeled observations",
            "observation_count": 4,
        },
    ]
    assert sum(row["observation_count"] for row in overview["monthly_trend"]) == 5
    assert sum(row["observation_count"] for row in overview["channel_performance"]) == 5
    assert sum(row["purchase_count"] for row in overview["monthly_trend"]) == 2
    assert sum(row["net_sales_amount"] for row in overview["monthly_trend"]) == 150.0
    assert sum(row["net_sales_amount"] for row in overview["channel_performance"]) == 150.0
    assert sum(
        row["net_sales_amount"] for row in overview["product_category_performance"]
    ) == 150.0
    assert "query_count=7" in caplog.text


def test_breakdown_limit_combines_remaining_groups_into_other(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_historical_fixture(database_path)
    monkeypatch.setattr(repository_module, "CHANNEL_BREAKDOWN_LIMIT", 2)

    channels = get_historical_overview(database_path)["channel_performance"]

    assert len(channels) == 2
    assert channels[0]["label"] == "Other"
    assert channels[0]["observation_count"] == 3
    assert channels[1]["label"] == "Email"
    assert channels[1]["observation_count"] == 2
    assert sum(row["observation_count"] for row in channels) == 5


def test_zero_contact_and_empty_database_results_are_json_safe(database_path: Path) -> None:
    empty_options = get_historical_options(database_path)
    empty_overview = get_historical_overview(database_path)

    assert empty_options["available_date_from"] is None
    assert empty_options["available_date_to"] is None
    assert empty_options["campaigns"] == []
    assert empty_options["defaults"]["contact_date_from"] is None
    assert empty_overview["summary"]["observation_count"] == 0
    assert empty_overview["summary"]["contact_date_from"] is None
    assert empty_overview["monthly_trend"] == []
    assert empty_overview["label_distribution"] == []

    with get_connection(database_path, write=True) as connection:
        _seed_customer(connection, "CUS_ZERO")
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                campaign_start_date, campaign_end_date,
                product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                'CS_ZERO', 'CUS_ZERO', 'CMP_ZERO', 'PRD_ZERO',
                'Zero Contact', 'Retention', 'Email',
                '2025-01-01', '2025-01-31',
                'Zero Product', 'Zero Category', '2025-01-05',
                0, 1, 1, 1, 1, 1
            )
            """
        )

    zero_contact = get_historical_overview(database_path)
    assert zero_contact["summary"]["contacted_count"] == 0
    assert zero_contact["summary"]["engaged_count"] == 1
    assert zero_contact["summary"]["engagement_rate"] == 0.0
    assert zero_contact["summary"]["response_rate"] == 0.0
    assert zero_contact["summary"]["purchase_rate"] == 0.0
    assert zero_contact["summary"]["attributed_purchase_rate"] == 0.0
    assert "NaN" not in json.dumps(zero_contact)
    assert "Infinity" not in json.dumps(zero_contact)


def test_services_execute_fixed_query_counts_without_demographic_access(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_historical_fixture(database_path)
    statements: list[str] = []
    real_get_connection = repository_module.get_connection

    @contextmanager
    def traced_get_connection(path):
        with real_get_connection(path) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    monkeypatch.setattr(repository_module, "get_connection", traced_get_connection)

    options = get_historical_options(database_path)
    overview = get_historical_overview(database_path)

    aggregate_queries = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("SELECT", "WITH"))
    ]
    assert len(aggregate_queries) == 13
    assert all("demographics" not in statement.lower() for statement in statements)

    forbidden_keys = {
        "customer_id", "person_id", "first_name", "last_name", "address_line_1",
        "address_line_2", "phone_number", "email",
    }

    def assert_no_raw_fields(value) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_no_raw_fields(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_raw_fields(nested)

    assert_no_raw_fields(options)
    assert_no_raw_fields(overview)
