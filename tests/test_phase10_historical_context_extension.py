from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.services.historical_analysis_service import (
    NoMatchingObservationsError,
    create_historical_analysis,
    get_historical_analysis_run,
    resolve_current_canonical_contact_date_range,
)
from app.services.historical_service import get_historical_options
from app.services.phase10_context_identity_service import (
    normalize_modeling_context,
    resolve_phase10_historical_filters,
)
from app.services.training_cohort_service import reconstruct_training_cohort


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase10-historical-context.db"
    initialize_database(path)
    customers = (
        ("C1", "1990-01-01", "Ohio"),
        ("C2", "1985-06-15", "Texas"),
        ("C3", "1975-03-20", "Maine"),
    )
    observations = (
        (
            "S1", "C1", "P1", "Lifecycle", "Loyalty", "2025-01-01",
            0, 0, 0,
        ),
        (
            "S2", "C1", "P2", "Lifecycle", "Bundle", "2025-01-05",
            1, 1, 1,
        ),
        (
            "S3", "C2", "P1", "Lifecycle", "Loyalty", "2025-01-10",
            0, 0, 0,
        ),
        (
            "S4", "C3", "P2", "Acquisition", "Discount", "2025-02-01",
            1, 1, 1,
        ),
        (
            "S5", "C3", "P3", "Lifecycle", "Discount", "2025-02-02",
            0, 0, 0,
        ),
    )
    with get_connection(path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, ?, ?, 50000, 2)
            """,
            customers,
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_category,
                campaign_channel, offer_type, product_name, product_category,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                ?, ?, 'CMP', ?, 'Campaign', 'Retention', ?,
                'Email', ?, 'Product', 'Product category',
                '2025-01-01', '2025-12-31', ?,
                1, 0, 0, ?, ?, ?
            )
            """,
            observations,
        )
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, '2026-09-01T00:00:00Z',
                      '2026-09-01T00:00:01Z', 'COMPLETED', ?, ?, 0, ?)
            """,
            (
                ("customers", "data/customers.csv", 3, 3, "c" * 64),
                ("campaign_sales", "data/campaign_sales.csv", 5, 5, "d" * 64),
            ),
        )
    return path


def test_empty_new_filters_preserve_behavior_and_options_are_exact(
    database_path: Path,
) -> None:
    omitted = create_historical_analysis(database_path, {"analysis_name": "Omitted"})
    explicit = create_historical_analysis(
        database_path,
        {
            "analysis_name": "Explicit",
            "campaign_categories": [],
            "offer_types": [],
        },
    )

    assert omitted["summary"] == explicit["summary"]
    assert omitted["filters"]["campaign_categories"] == []
    assert omitted["filters"]["offer_types"] == []
    options = get_historical_options(database_path)
    assert options["campaign_categories"] == ["Acquisition", "Lifecycle"]
    assert options["offer_types"] == ["Bundle", "Discount", "Loyalty"]
    assert options["defaults"]["campaign_categories"] == []
    assert options["defaults"]["offer_types"] == []


@pytest.mark.parametrize(
    ("filters", "expected"),
    (
        ({"campaign_categories": ["Lifecycle"]}, (4, 3, 1)),
        ({"offer_types": ["Loyalty"]}, (2, 2, 0)),
        (
            {
                "campaign_categories": ["Lifecycle"],
                "offer_types": ["Bundle", "Discount"],
            },
            (2, 2, 1),
        ),
    ),
)
def test_category_offer_and_combined_filter_semantics(
    database_path: Path,
    filters: dict[str, list[str]],
    expected: tuple[int, int, int],
) -> None:
    result = create_historical_analysis(database_path, filters)

    assert (
        result["summary"]["observation_count"],
        result["summary"]["selected_customer_count"],
        result["summary"]["positive_customer_count"],
    ) == expected


def test_multi_product_filters_remain_customer_grain_with_any_positive(
    database_path: Path,
) -> None:
    saved = create_historical_analysis(
        database_path,
        {
            "product_ids": ["P1", "P2"],
            "campaign_categories": ["Lifecycle"],
            "offer_types": ["Loyalty", "Bundle"],
        },
    )
    cohort = reconstruct_training_cohort(database_path, saved["analysis_run_id"])

    assert cohort.observation_count == 3
    assert cohort.selected_customer_count == 2
    assert cohort.frame["customer_id"].is_unique
    assert cohort.frame.set_index("customer_id")["pu_label"].astype(int).to_dict() == {
        "C1": 1,
        "C2": 0,
    }


def test_multi_product_positive_policy_covers_each_branch_once_without_fusion(
    database_path: Path,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, '1990-01-01', 'Ohio', 50000, 2)
            """,
            (("C4",), ("C5",), ("C6",), ("C7",)),
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_category,
                campaign_channel, offer_type, product_name, product_category,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                ?, ?, 'CMP-MATRIX', ?, 'Matrix campaign', 'Retention', 'Matrix',
                'Email', 'Matrix offer', 'Product', 'Product category',
                '2025-03-01', '2025-03-31', '2025-03-01',
                1, 0, 0, ?, ?, ?
            )
            """,
            (
                ("SM1", "C4", "P1", 1, 1, 1),
                ("SM2", "C5", "P2", 1, 1, 1),
                ("SM3", "C6", "P1", 0, 0, 0),
                ("SM4", "C7", "P1", 1, 1, 1),
                ("SM5", "C7", "P2", 1, 1, 1),
            ),
        )
        connection.execute(
            """
            UPDATE data_import_runs SET rows_read = 7, rows_inserted = 7
            WHERE dataset_name = 'customers' AND status = 'COMPLETED'
            """
        )
        connection.execute(
            """
            UPDATE data_import_runs SET rows_read = 10, rows_inserted = 10
            WHERE dataset_name = 'campaign_sales' AND status = 'COMPLETED'
            """
        )

    saved = create_historical_analysis(
        database_path,
        {
            "product_ids": ["P1", "P2"],
            "campaign_categories": ["Matrix"],
            "offer_types": ["Matrix offer"],
        },
    )
    cohort = reconstruct_training_cohort(database_path, saved["analysis_run_id"])
    labels = cohort.frame.set_index("customer_id")["pu_label"].astype(int).to_dict()

    assert cohort.observation_count == 5
    assert cohort.selected_customer_count == 4
    assert cohort.positive_customer_count == 3
    assert cohort.unlabeled_customer_count == 1
    assert cohort.frame["customer_id"].is_unique
    assert labels == {"C4": 1, "C5": 1, "C6": 0, "C7": 1}
    assert set(cohort.frame["pu_label"].astype(int)) == {0, 1}


def test_zero_result_and_old_saved_json_compatibility(database_path: Path) -> None:
    with pytest.raises(NoMatchingObservationsError):
        create_historical_analysis(
            database_path,
            {"campaign_categories": ["Does not exist"]},
        )

    saved = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    run_id = saved["analysis_run_id"]
    with get_connection(database_path, write=True) as connection:
        stored = connection.execute(
            "SELECT filters_json FROM historical_analysis_runs WHERE analysis_run_id = ?",
            (run_id,),
        ).fetchone()
        old_payload = json.loads(stored["filters_json"])
        old_payload.pop("campaign_categories")
        old_payload.pop("offer_types")
        connection.execute(
            "UPDATE historical_analysis_runs SET filters_json = ? WHERE analysis_run_id = ?",
            (
                json.dumps(old_payload, sort_keys=True, separators=(",", ":")),
                run_id,
            ),
        )

    reopened = get_historical_analysis_run(database_path, run_id)
    cohort = reconstruct_training_cohort(database_path, run_id)
    assert reopened["filters"]["campaign_categories"] == []
    assert reopened["filters"]["offer_types"] == []
    assert cohort.filters["campaign_categories"] == []
    assert cohort.filters["offer_types"] == []
    assert cohort.selected_customer_count == saved["summary"]["selected_customer_count"]


def test_phase10_filters_use_exact_current_canonical_date_range(
    database_path: Path,
) -> None:
    context = normalize_modeling_context(
        {
            "product_ids": ["P2", "P1"],
            "campaign_types": ["Retention"],
            "campaign_categories": ["Lifecycle"],
            "offer_types": ["Bundle"],
            "historical_campaign_channels": ["Email"],
        }
    )

    assert resolve_current_canonical_contact_date_range(database_path) == (
        "2025-01-01",
        "2025-02-02",
    )
    resolved = resolve_phase10_historical_filters(str(database_path), context)
    assert resolved.contact_date_from.isoformat() == "2025-01-01"
    assert resolved.contact_date_to.isoformat() == "2025-02-02"
    assert resolved.product_ids == ["P1", "P2"]
    assert resolved.campaign_categories == ["Lifecycle"]
    assert resolved.offer_types == ["Bundle"]
    assert resolved.contacted_only is True
    assert resolved.conversion_definition == "ATTRIBUTED_PURCHASE"
