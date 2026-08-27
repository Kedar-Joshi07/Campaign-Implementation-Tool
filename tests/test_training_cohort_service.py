from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories import historical_repository as historical_repository_module
from app.repositories import model_training_repository as model_repository_module
from app.repositories.historical_repository import HistoricalRepository
from app.repositories.model_training_repository import RAW_TRAINING_COLUMNS
from app.schemas.historical import HistoricalAnalysisFilters
from app.services.historical_analysis_service import create_historical_analysis
from app.services.training_cohort_service import (
    TrainingCohortReconciliationError,
    TrainingCohortRunError,
    reconstruct_training_cohort,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "training-cohort.db"
    initialize_database(path)
    return path


def _seed_training_fixture(database_path: Path) -> None:
    customers = (
        (
            "CUS_001", "2000-06-15", "Female", "Ohio", 30_000, 1,
            "Citizen", "Owner", "College", "Employed", "Salaried", "Single",
        ),
        (
            "CUS_002", "2000-06-16", "Male", "Texas", 60_000, 2,
            "Citizen", "Renter", "Graduate", "Employed", "Contract", "Married",
        ),
        (
            "CUS_003", "1990-01-01", None, "California", 110_000, 4,
            "Permanent Resident", "Owner", "Postgraduate", "Self-employed",
            "Self-employed", "Married",
        ),
        (
            "CUS_004", "1960-06-15", "Female", "Maine", 260_000, 5,
            "Citizen", "Owner", "Doctorate", "Retired", "Retired", "Widowed",
        ),
    )
    observations = (
        ("CS_001", "CUS_001", "CMP_A", "PRD_1", "2025-01-01", 1, 0, 0, 0, 0),
        ("CS_002", "CUS_001", "CMP_A", "PRD_1", "2025-01-15", 1, 1, 1, 1, 1),
        ("CS_003", "CUS_001", "CMP_OUT", "PRD_2", "2025-05-01", 1, 0, 1, 1, 1),
        ("CS_004", "CUS_002", "CMP_A", "PRD_1", "2025-01-01", 1, 1, 1, 0, 0),
        ("CS_005", "CUS_002", "CMP_OUT", "PRD_2", "2025-05-15", 1, 0, 1, 1, 1),
        ("CS_006", "CUS_003", "CMP_B", "PRD_2", "2025-01-31", 0, 1, 1, 1, 1),
        ("CS_007", "CUS_003", "CMP_B", "PRD_2", "2025-06-15", 1, 0, 0, 0, 0),
    )

    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, gender, state,
                individual_yearly_income, family_member_count,
                resident_status, resident_type, education, employment_status,
                type_of_employment, marital_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            customers,
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                product_name, product_category,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                ?, ?, ?, ?, 'Campaign', 'Acquisition', 'Email',
                'Product', 'Category',
                '2025-01-01', '2025-12-31', ?, ?, 0, ?, ?, ?, ?
            )
            """,
            observations,
        )
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,
                source_path,
                started_at,
                completed_at,
                status,
                rows_read,
                rows_inserted,
                rows_rejected,
                source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "customers",
                "data/customers_fixture.csv",
                "2026-08-26T00:00:00Z",
                "2026-08-26T00:00:05Z",
                "COMPLETED",
                4,
                4,
                0,
                "c" * 64,
            ),
        )
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,
                source_path,
                started_at,
                completed_at,
                status,
                rows_read,
                rows_inserted,
                rows_rejected,
                source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "campaign_sales",
                "data/campaign_sales_fixture.csv",
                "2026-08-26T00:00:06Z",
                "2026-08-26T00:00:10Z",
                "COMPLETED",
                7,
                7,
                0,
                "d" * 64,
            ),
        )


def _create_analysis(
    database_path: Path,
    **filters: object,
) -> dict[str, object]:
    return create_historical_analysis(database_path, filters)


@pytest.mark.parametrize(
    ("conversion_definition", "expected_labels"),
    (
        ("ATTRIBUTED_PURCHASE", {"CUS_001": 1, "CUS_002": 0}),
        ("ANY_PURCHASE", {"CUS_001": 1, "CUS_002": 1}),
        ("RESPONSE", {"CUS_001": 1, "CUS_002": 1}),
    ),
)
def test_reconstructs_one_customer_row_and_all_conversion_definitions(
    database_path: Path,
    conversion_definition: str,
    expected_labels: dict[str, int],
) -> None:
    _seed_training_fixture(database_path)
    saved = _create_analysis(
        database_path,
        campaign_ids=["CMP_A"],
        conversion_definition=conversion_definition,
    )

    cohort = reconstruct_training_cohort(database_path, saved["analysis_run_id"])
    labels = cohort.frame.set_index("customer_id")["pu_label"].astype(int).to_dict()

    assert cohort.observation_count == 3
    assert cohort.selected_customer_count == 2
    assert labels == expected_labels
    assert cohort.positive_customer_count == sum(expected_labels.values())
    assert cohort.unlabeled_customer_count == 2 - sum(expected_labels.values())
    assert cohort.frame["customer_id"].is_unique
    assert tuple(cohort.frame.columns) == RAW_TRAINING_COLUMNS
    assert cohort.approximate_memory_bytes > 0
    assert "CMP_OUT" not in cohort.frame.astype(str).to_string()


def test_contacted_only_inclusive_dates_and_age_reference_are_preserved(
    database_path: Path,
) -> None:
    _seed_training_fixture(database_path)
    contacted_saved = _create_analysis(
        database_path,
        campaign_ids=["CMP_B"],
        conversion_definition="RESPONSE",
    )
    all_saved = _create_analysis(
        database_path,
        campaign_ids=["CMP_B"],
        contacted_only=False,
        conversion_definition="RESPONSE",
    )
    boundary_saved = _create_analysis(
        database_path,
        contact_date_from="2025-01-01",
        contact_date_to="2025-01-01",
    )
    default_saved = _create_analysis(database_path)

    contacted = reconstruct_training_cohort(
        database_path, contacted_saved["analysis_run_id"]
    )
    all_observations = reconstruct_training_cohort(
        database_path, all_saved["analysis_run_id"]
    )
    boundary = reconstruct_training_cohort(database_path, boundary_saved["analysis_run_id"])
    default = reconstruct_training_cohort(database_path, default_saved["analysis_run_id"])

    assert (contacted.observation_count, contacted.positive_customer_count) == (1, 0)
    assert (all_observations.observation_count, all_observations.positive_customer_count) == (
        2,
        1,
    )
    assert boundary.observation_count == 2
    assert set(boundary.frame["customer_id"]) == {"CUS_001", "CUS_002"}
    ages = default.frame.set_index("customer_id")["age"].astype(int).to_dict()
    assert default.reference_date == "2025-06-15"
    assert ages == {"CUS_001": 25, "CUS_002": 24, "CUS_003": 35}


def test_returned_frame_has_only_frozen_fields_and_nullable_types(
    database_path: Path,
) -> None:
    _seed_training_fixture(database_path)
    saved = _create_analysis(database_path)

    cohort = reconstruct_training_cohort(database_path, saved["analysis_run_id"])

    assert tuple(cohort.frame.columns) == RAW_TRAINING_COLUMNS
    assert cohort.frame.dtypes.to_dict() == {
        "customer_id": pd.StringDtype(),
        "pu_label": pd.Int8Dtype(),
        "age": pd.Int64Dtype(),
        "gender": pd.StringDtype(),
        "state": pd.StringDtype(),
        "individual_yearly_income": pd.Float64Dtype(),
        "marital_status": pd.StringDtype(),
        "education": pd.StringDtype(),
        "employment_status": pd.StringDtype(),
        "resident_status": pd.StringDtype(),
        "resident_type": pd.StringDtype(),
        "family_member_count": pd.Int64Dtype(),
        "type_of_employment": pd.StringDtype(),
    }
    prohibited = {
        "person_id", "first_name", "last_name", "email", "phone_number",
        "address_line_1", "campaign_id", "product_id", "response_flag",
        "purchase_flag", "net_sales_amount", "gross_margin_amount",
    }
    assert prohibited.isdisjoint(cohort.frame.columns)
    assert pd.isna(cohort.frame.set_index("customer_id").loc["CUS_003", "gender"])


def test_source_count_or_label_mutation_is_a_hard_stop(database_path: Path) -> None:
    _seed_training_fixture(database_path)
    saved = _create_analysis(
        database_path,
        campaign_ids=["CMP_A"],
        conversion_definition="ATTRIBUTED_PURCHASE",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute("DELETE FROM campaign_sales WHERE campaign_sales_id = 'CS_002'")

    with pytest.raises(
        TrainingCohortReconciliationError,
        match="campaign_sales.*provenance.*count",
    ):
        reconstruct_training_cohort(database_path, saved["analysis_run_id"])


def test_missing_running_failed_and_invalid_analysis_ids_are_rejected(
    database_path: Path,
) -> None:
    _seed_training_fixture(database_path)
    normalized = HistoricalAnalysisFilters.model_validate(
        {
            "analysis_name": "State fixture",
            "contact_date_from": "2025-01-01",
            "contact_date_to": "2025-06-15",
        }
    )
    repository = HistoricalRepository(database_path)
    running_id = repository.insert_analysis_run(
        analysis_name=normalized.analysis_name,
        created_at="2026-08-21T00:00:00Z",
        conversion_definition=normalized.conversion_definition,
        filters_json=json.dumps(
            normalized.filter_payload(), sort_keys=True, separators=(",", ":")
        ),
    )
    failed_id = repository.insert_analysis_run(
        analysis_name=normalized.analysis_name,
        created_at="2026-08-21T00:00:01Z",
        conversion_definition=normalized.conversion_definition,
        filters_json=json.dumps(
            normalized.filter_payload(), sort_keys=True, separators=(",", ":")
        ),
    )
    repository.fail_analysis_run(
        analysis_run_id=failed_id,
        completed_at="2026-08-21T00:00:02Z",
        error_message="internal fixture detail",
    )

    for analysis_run_id in (running_id, failed_id, 999, 0, -1, True):
        with pytest.raises(TrainingCohortRunError):
            reconstruct_training_cohort(database_path, analysis_run_id)


@pytest.mark.parametrize("column", ("filters_json", "results_json"))
def test_malformed_saved_filters_or_results_are_rejected(
    database_path: Path,
    column: str,
) -> None:
    _seed_training_fixture(database_path)
    saved = _create_analysis(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            f"UPDATE historical_analysis_runs SET {column} = ? WHERE analysis_run_id = ?",
            ("not-valid-json", saved["analysis_run_id"]),
        )

    with pytest.raises(TrainingCohortRunError, match="could not be validated"):
        reconstruct_training_cohort(database_path, saved["analysis_run_id"])


def test_reconstruction_path_executes_no_demographics_sql(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_training_fixture(database_path)
    saved = _create_analysis(database_path)
    statements: list[str] = []
    original_get_connection = get_connection

    @contextmanager
    def traced_connection(*args: object, **kwargs: object):
        with original_get_connection(*args, **kwargs) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    monkeypatch.setattr(
        historical_repository_module,
        "get_connection",
        traced_connection,
    )
    monkeypatch.setattr(model_repository_module, "get_connection", traced_connection)

    cohort = reconstruct_training_cohort(database_path, saved["analysis_run_id"])

    assert cohort.selected_customer_count == 3
    assert statements
    assert all("demographics" not in statement.casefold() for statement in statements)
