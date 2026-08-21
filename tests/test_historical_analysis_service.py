from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories import historical_repository as repository_module
from app.repositories.historical_repository import HistoricalRepository
from app.services.historical_analysis_service import (
    HistoricalAnalysisExecutionError,
    HistoricalAnalysisValidationError,
    HistoricalDataIntegrityError,
    HistoricalDataNotReadyError,
    HistoricalSavedRunError,
    NoMatchingObservationsError,
    create_historical_analysis,
    get_historical_analysis_run,
    list_historical_analysis_runs,
    normalize_historical_filters,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "cohort.db"
    initialize_database(path)
    return path


def _seed_cohort_fixture(database_path: Path) -> None:
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
            "CUS_003", "1990-01-01", "Non-binary", "California", 110_000, 4,
            "Permanent Resident", "Owner", "Postgraduate", "Self-employed",
            "Self-employed", "Married",
        ),
        (
            "CUS_004", "1960-06-15", "Female", "Maine", 260_000, 5,
            "Citizen", "Owner", "Doctorate", "Retired", "Retired", "Widowed",
        ),
    )
    observations = (
        (
            "CS_001", "CUS_001", "CMP_A", "PRD_1", "Campaign A", "Acquisition",
            "Email", "Product One", "Category One", "2025-01-01", 1, 0, 0, 0,
            0, 0, None, None,
        ),
        (
            "CS_002", "CUS_001", "CMP_A", "PRD_1", "Campaign A", "Acquisition",
            "Email", "Product One", "Category One", "2025-01-15", 1, 1, 1, 1,
            1, 1, 100.0, 40.0,
        ),
        (
            "CS_003", "CUS_001", "CMP_OUT", "PRD_2", "Outside Campaign", "Retention",
            "Social", "Product Two", "Category Two", "2025-05-01", 1, 1, 0, 1,
            1, 1, 75.0, 25.0,
        ),
        (
            "CS_004", "CUS_002", "CMP_A", "PRD_1", "Campaign A", "Acquisition",
            "Email", "Product One", "Category One", "2025-01-01", 1, 1, 1, 1,
            0, 0, 50.0, 20.0,
        ),
        (
            "CS_005", "CUS_002", "CMP_OUT", "PRD_2", "Outside Campaign", "Retention",
            "Social", "Product Two", "Category Two", "2025-05-15", 1, 1, 0, 1,
            1, 1, 80.0, 30.0,
        ),
        (
            "CS_006", "CUS_003", "CMP_B", "PRD_2", "Campaign B", "Retention",
            "Direct", "Product Two", "Category Two", "2025-01-31", 0, 1, 1, 1,
            1, 1, 60.0, 20.0,
        ),
        (
            "CS_007", "CUS_003", "CMP_B", "PRD_2", "Campaign B", "Retention",
            "Direct", "Product Two", "Category Two", "2025-06-15", 1, 0, 0, 0,
            0, 0, None, None,
        ),
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
                campaign_attributed_sale_flag, pu_label,
                net_sales_amount, gross_margin_amount
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '2025-01-01', '2025-12-31', ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            observations,
        )


def _assert_customer_invariant(result: dict) -> None:
    summary = result["summary"]
    assert summary["positive_customer_count"] + summary["unlabeled_customer_count"] == (
        summary["selected_customer_count"]
    )


def test_filter_normalization_defaults_stable_json_and_validation(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)

    normalized = normalize_historical_filters(
        database_path,
        {
            "analysis_name": "  Stable cohort  ",
            "campaign_ids": [" CMP_B ", "CMP_A", "CMP_A"],
            "product_categories": ["Category Two", " Category One "],
        },
    )

    assert normalized.analysis_name == "Stable cohort"
    assert normalized.campaign_ids == ["CMP_A", "CMP_B"]
    assert normalized.product_categories == ["Category One", "Category Two"]
    assert normalized.contact_date_from.isoformat() == "2025-01-01"
    assert normalized.contact_date_to.isoformat() == "2025-06-15"
    assert normalized.contacted_only is True
    assert normalized.conversion_definition == "ATTRIBUTED_PURCHASE"

    generated = normalize_historical_filters(database_path, {})
    assert generated.analysis_name == "Historical analysis: 2025-01-01 to 2025-06-15"

    invalid_values = (
        {"analysis_name": "   "},
        {"campaign_ids": ["CMP_A", " "]},
        {"campaign_ids": [f"CMP_{index:02d}" for index in range(26)]},
        {"contact_date_from": "2025-02-01", "contact_date_to": "2025-01-01"},
        {"conversion_definition": "NOT_SUPPORTED"},
        {"sort_expression": "customer_id; DROP TABLE customers"},
    )
    for value in invalid_values:
        with pytest.raises(HistoricalAnalysisValidationError):
            normalize_historical_filters(database_path, value)


def test_empty_history_is_not_ready(database_path: Path) -> None:
    with pytest.raises(HistoricalDataNotReadyError, match="not loaded"):
        create_historical_analysis(database_path, {})

    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM historical_analysis_runs"
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("conversion_definition", "expected_positive", "expected_unlabeled"),
    (
        ("ATTRIBUTED_PURCHASE", 1, 1),
        ("ANY_PURCHASE", 2, 0),
        ("RESPONSE", 2, 0),
    ),
)
def test_conversion_definitions_use_any_matching_row_at_customer_grain(
    database_path: Path,
    conversion_definition: str,
    expected_positive: int,
    expected_unlabeled: int,
) -> None:
    _seed_cohort_fixture(database_path)

    result = create_historical_analysis(
        database_path,
        {
            "campaign_ids": ["CMP_A"],
            "conversion_definition": conversion_definition,
        },
    )

    assert result["summary"]["observation_count"] == 3
    assert result["summary"]["selected_customer_count"] == 2
    assert result["summary"]["positive_customer_count"] == expected_positive
    assert result["summary"]["unlabeled_customer_count"] == expected_unlabeled
    _assert_customer_invariant(result)


def test_outside_filter_activity_contacted_only_and_inclusive_dates(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)

    campaign_a = create_historical_analysis(
        database_path,
        {"campaign_ids": ["CMP_A"], "conversion_definition": "ATTRIBUTED_PURCHASE"},
    )
    assert campaign_a["summary"]["positive_customer_count"] == 1
    assert campaign_a["summary"]["unlabeled_customer_count"] == 1

    contacted = create_historical_analysis(
        database_path,
        {"campaign_ids": ["CMP_B"], "conversion_definition": "RESPONSE"},
    )
    all_observations = create_historical_analysis(
        database_path,
        {
            "campaign_ids": ["CMP_B"],
            "contacted_only": False,
            "conversion_definition": "RESPONSE",
        },
    )
    assert contacted["summary"]["observation_count"] == 1
    assert contacted["summary"]["positive_customer_count"] == 0
    assert all_observations["summary"]["observation_count"] == 2
    assert all_observations["summary"]["positive_customer_count"] == 1

    boundary = create_historical_analysis(
        database_path,
        {
            "contact_date_from": "2025-01-01",
            "contact_date_to": "2025-01-01",
        },
    )
    assert boundary["summary"]["observation_count"] == 2
    assert boundary["summary"]["selected_customer_count"] == 2


@pytest.mark.parametrize(
    ("filter_name", "filter_value", "expected_observations"),
    (
        ("campaign_ids", ["CMP_A"], 3),
        ("product_ids", ["PRD_1"], 3),
        ("product_categories", ["Category One"], 3),
        ("campaign_channels", ["Email"], 3),
        ("campaign_types", ["Acquisition"], 3),
    ),
)
def test_each_multi_select_filter_works_alone(
    database_path: Path,
    filter_name: str,
    filter_value: list[str],
    expected_observations: int,
) -> None:
    _seed_cohort_fixture(database_path)

    result = create_historical_analysis(database_path, {filter_name: filter_value})

    assert result["summary"]["observation_count"] == expected_observations
    _assert_customer_invariant(result)


def test_combined_filters_and_sql_looking_values_are_parameterized(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)

    combined = create_historical_analysis(
        database_path,
        {
            "campaign_ids": ["CMP_A"],
            "product_ids": ["PRD_1"],
            "product_categories": ["Category One"],
            "campaign_channels": ["Email"],
            "campaign_types": ["Acquisition"],
        },
    )
    assert combined["summary"]["observation_count"] == 3

    with pytest.raises(NoMatchingObservationsError, match="No campaign observations"):
        create_historical_analysis(
            database_path,
            {"campaign_ids": ["CMP_A') OR 1=1 --"]},
        )

    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 4
        failed = connection.execute(
            """
            SELECT status, results_json
            FROM historical_analysis_runs
            ORDER BY analysis_run_id DESC
            LIMIT 1
            """
        ).fetchone()
    assert tuple(failed) == ("FAILED", None)


def test_profiles_reconcile_age_birthdays_and_state_other_bucket(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cohort_fixture(database_path)
    monkeypatch.setattr(repository_module, "STATE_PROFILE_LIMIT", 2)

    result = create_historical_analysis(database_path, {})
    profiles = result["profiles"]

    expected_counts = {
        "selected": 3,
        "positive": 2,
        "unlabeled": 1,
        "historical_baseline": 4,
    }
    for group_name, group_count in expected_counts.items():
        for profile in profiles[group_name].values():
            assert profile["group_count"] == group_count
            assert sum(item["count"] for item in profile["categories"]) == group_count
            assert sum(item["share"] for item in profile["categories"]) == pytest.approx(
                1.0 if group_count else 0.0,
                abs=0.000002,
            )

    selected_ages = {
        item["label"]: item["count"]
        for item in profiles["selected"]["age_band"]["categories"]
    }
    assert selected_ages == {"18–24": 1, "25–34": 1, "35–44": 1}
    baseline_ages = {
        item["label"]: item["count"]
        for item in profiles["historical_baseline"]["age_band"]["categories"]
    }
    assert baseline_ages["18–24"] == 1
    assert baseline_ages["25–34"] == 1
    assert baseline_ages["65+"] == 1
    states = profiles["historical_baseline"]["state"]["categories"]
    assert len(states) == 2
    assert sum(item["count"] for item in states) == 4
    assert any(item["label"] == "Other" and item["count"] == 3 for item in states)


def test_completed_run_reopens_identically_and_json_is_stable(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)

    created = create_historical_analysis(
        database_path,
        {
            "analysis_name": "  Reopen test  ",
            "campaign_ids": ["CMP_B", "CMP_A", "CMP_A"],
        },
    )
    reopened = get_historical_analysis_run(database_path, created["analysis_run_id"])

    assert reopened == created
    with get_connection(database_path) as connection:
        stored = connection.execute(
            """
            SELECT filters_json, results_json, status, error_message
            FROM historical_analysis_runs
            WHERE analysis_run_id = ?
            """,
            (created["analysis_run_id"],),
        ).fetchone()
    assert stored["status"] == "COMPLETED"
    assert stored["error_message"] is None
    assert stored["filters_json"] == json.dumps(
        created["filters"],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert json.loads(stored["results_json"])["summary"] == created["summary"]


def test_failed_run_keeps_internal_diagnostics_but_public_result_is_sanitized(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cohort_fixture(database_path)
    private_detail = r"C:\private\campaign.db SELECT * FROM customers"

    def fail_analysis(_self, _filters):
        raise RuntimeError(private_detail)

    monkeypatch.setattr(HistoricalRepository, "analyze_cohort", fail_analysis)

    with pytest.raises(HistoricalAnalysisExecutionError) as exc_info:
        create_historical_analysis(database_path, {"analysis_name": "Failure test"})
    assert private_detail not in str(exc_info.value)

    with get_connection(database_path) as connection:
        row = dict(
            connection.execute(
                """
                SELECT * FROM historical_analysis_runs
                ORDER BY analysis_run_id DESC
                LIMIT 1
                """
            ).fetchone()
        )
    assert row["status"] == "FAILED"
    assert row["results_json"] is None
    assert private_detail in row["error_message"]

    public = get_historical_analysis_run(database_path, row["analysis_run_id"])
    assert public["failure_message"] == "The historical analysis could not be completed."
    assert private_detail not in json.dumps(public)


def test_newest_first_listing_pagination_and_corrupt_json_handling(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)
    run_ids = [
        create_historical_analysis(database_path, {"analysis_name": f"Run {index}"})[
            "analysis_run_id"
        ]
        for index in range(3)
    ]

    page = list_historical_analysis_runs(database_path, limit=2, offset=1)
    assert [item["analysis_run_id"] for item in page] == [run_ids[1], run_ids[0]]
    assert all("profiles" not in item for item in page)
    with pytest.raises(HistoricalAnalysisValidationError):
        list_historical_analysis_runs(database_path, limit=101, offset=0)
    with pytest.raises(HistoricalAnalysisValidationError):
        list_historical_analysis_runs(database_path, limit=20, offset=-1)

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE historical_analysis_runs SET results_json = ? WHERE analysis_run_id = ?",
            ('{"summary": NaN}', run_ids[-1]),
        )
    with pytest.raises(HistoricalSavedRunError) as exc_info:
        get_historical_analysis_run(database_path, run_ids[-1])
    assert "NaN" not in str(exc_info.value)


def test_inconsistent_attributed_labels_fail_without_partial_results(database_path: Path) -> None:
    _seed_cohort_fixture(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE campaign_sales SET pu_label = 1 WHERE campaign_sales_id = 'CS_001'"
        )

    with pytest.raises(HistoricalDataIntegrityError, match="consistency checks"):
        create_historical_analysis(database_path, {"campaign_ids": ["CMP_A"]})

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT status, results_json, error_message
            FROM historical_analysis_runs
            ORDER BY analysis_run_id DESC
            LIMIT 1
            """
        ).fetchone()
    assert row["status"] == "FAILED"
    assert row["results_json"] is None
    assert "HistoricalDataIntegrityError" in row["error_message"]


def test_public_results_have_no_pii_ids_sql_paths_or_demographic_queries(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cohort_fixture(database_path)
    statements: list[str] = []
    real_get_connection = repository_module.get_connection

    @contextmanager
    def traced_get_connection(path, *, write=False):
        with real_get_connection(path, write=write) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    monkeypatch.setattr(repository_module, "get_connection", traced_get_connection)
    result = create_historical_analysis(database_path, {})

    public_text = json.dumps(result)
    for prohibited in (
        "CUS_001", "customer_id", "person_id", "first_name", "last_name",
        "phone_number", "email", "SELECT ", "C:\\",
    ):
        assert prohibited not in public_text
    assert all("demographics" not in statement.lower() for statement in statements)
