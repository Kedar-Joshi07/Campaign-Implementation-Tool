from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    REQUIRED_INDEX_STATEMENTS,
    initialize_database,
    initialize_required_indexes,
    verify_required_indexes,
)
from app.services.data_reconciliation_service import (
    STATUS_ERROR,
    STATUS_NOT_LOADED,
    STATUS_OK,
    STATUS_WARNING,
    run_reconciliation,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "reconciliation.db"


def _expected_counts(count: int = 1) -> dict[str, dict[str, int | bool]]:
    return {
        dataset: {"expected_count": count, "exact_match_required": True}
        for dataset in ("customers", "campaign_sales", "demographics")
    }


def _seed_fixture(database_path: Path, *, broken: bool = False) -> None:
    initialize_database(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("CUS_001", "1990-01-15", "California", 60_000, 3),
        )
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CS_001",
                "CUS_001",
                "CMP_001",
                "PRD_001",
                "2025-01-01",
                "2025-01-31",
                "2025-01-10",
                1,
                1,
                1,
                1,
                0 if broken else 1,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO demographics (
                person_id, age, state, individual_yearly_income,
                family_member_count, number_of_children_in_family,
                number_of_adults_in_family, family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PER_001",
                35,
                "California",
                60_000,
                3,
                1,
                1 if broken else 2,
                50_000 if broken else 100_000,
            ),
        )


def test_required_indexes_are_created_and_verified(database_path: Path) -> None:
    timings = initialize_required_indexes(database_path)
    status = verify_required_indexes(database_path)

    assert len(REQUIRED_INDEX_STATEMENTS) == 17
    assert set(timings) == set(REQUIRED_INDEX_STATEMENTS)
    assert all(seconds >= 0 for seconds in timings.values())
    assert all(status.values())
    assert not any(name.endswith("customer_id_pk") for name in REQUIRED_INDEX_STATEMENTS)


def test_empty_database_is_not_loaded(database_path: Path) -> None:
    result = run_reconciliation(database_path, _expected_counts())

    assert result["overall_status"] == STATUS_NOT_LOADED
    assert {
        dataset["status"] for dataset in result["datasets"].values()
    } == {STATUS_NOT_LOADED}
    assert all(
        dataset["metrics"]["total_rows"] == 0
        for dataset in result["datasets"].values()
    )


def test_valid_small_fixture_is_ok_and_reports_metrics(database_path: Path) -> None:
    _seed_fixture(database_path)

    result = run_reconciliation(database_path, _expected_counts())

    assert result["overall_status"] == STATUS_OK
    assert result["datasets"]["customers"]["metrics"] == {
        "total_rows": 1,
        "distinct_customer_id": 1,
        "min_date_of_birth": "1990-01-15",
        "max_date_of_birth": "1990-01-15",
        "null_or_blank_critical_identifiers": 0,
    }
    assert result["datasets"]["campaign_sales"]["metrics"][
        "invalid_customer_fk_count"
    ] == 0
    assert result["datasets"]["demographics"]["metrics"][
        "family_arithmetic_violation_count"
    ] == 0
    assert result["total_query_seconds"] >= 0
    assert all(
        dataset["query_seconds"] >= 0 for dataset in result["datasets"].values()
    )


def test_deliberately_broken_fixture_is_error(database_path: Path) -> None:
    _seed_fixture(database_path, broken=True)

    result = run_reconciliation(database_path, _expected_counts())

    assert result["overall_status"] == STATUS_ERROR
    assert result["datasets"]["campaign_sales"]["status"] == STATUS_ERROR
    assert result["datasets"]["campaign_sales"]["structural_issues"][
        "pu_consistency_violation_count"
    ] == 1
    assert result["datasets"]["demographics"]["status"] == STATUS_ERROR
    assert result["datasets"]["demographics"]["structural_error_count"] == 2


def test_exact_expected_count_mismatch_is_warning(database_path: Path) -> None:
    _seed_fixture(database_path)
    policies = _expected_counts(count=2)

    result = run_reconciliation(database_path, policies)

    assert result["overall_status"] == STATUS_WARNING
    assert all(
        dataset["status"] == STATUS_WARNING
        for dataset in result["datasets"].values()
    )
    assert all(
        dataset["expected_count_match"] is False
        for dataset in result["datasets"].values()
    )


def test_non_exact_customer_target_does_not_warn(database_path: Path) -> None:
    _seed_fixture(database_path)
    policies = _expected_counts()
    policies["customers"] = {"expected_count": 125_000, "exact_match_required": False}

    result = run_reconciliation(database_path, policies)

    customer_result = result["datasets"]["customers"]
    assert customer_result["status"] == STATUS_OK
    assert customer_result["expected_count_match"] is False
    assert customer_result["exact_match_required"] is False
