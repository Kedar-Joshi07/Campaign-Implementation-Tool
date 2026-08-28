from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.saved_audience_service import (
    SAVED_AUDIENCE_EMPTY_MESSAGE,
    SavedAudienceServiceNotFoundError,
    SavedAudienceServiceValidationError,
    get_saved_audience_detail,
    list_saved_audiences,
    replay_saved_audience_definition,
    save_audience,
    validate_saved_audience_currentness,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "saved-audience-service.db"
    initialize_database(path)
    return path


def _insert_customer(
    database_path: Path,
    *,
    customer_id: str,
    date_of_birth: str,
    state: str,
    income: float,
    family_member_count: int,
    gender: str,
    marital_status: str,
    education: str,
    employment_status: str,
    resident_status: str,
    resident_type: str,
    type_of_employment: str,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                date_of_birth,
                state,
                individual_yearly_income,
                family_member_count,
                gender,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                type_of_employment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                date_of_birth,
                state,
                income,
                family_member_count,
                gender,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                type_of_employment,
            ),
        )


def _insert_campaign_sale(
    database_path: Path,
    *,
    campaign_sales_id: str,
    customer_id: str,
    contact_date: str,
    purchase_flag: int,
    attributed_flag: int,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id,
                customer_id,
                campaign_id,
                product_id,
                campaign_start_date,
                campaign_end_date,
                contact_date,
                contacted_flag,
                engagement_flag,
                response_flag,
                purchase_flag,
                campaign_attributed_sale_flag,
                pu_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_sales_id,
                customer_id,
                "CMP_001",
                "PRD_001",
                "2025-01-01",
                "2025-12-31",
                contact_date,
                1,
                1,
                purchase_flag,
                purchase_flag,
                attributed_flag,
                1 if attributed_flag and purchase_flag else 0,
            ),
        )


def _insert_demographic(
    database_path: Path,
    *,
    person_id: str,
    age: int,
    state: str,
    income: float,
    family_member_count: int,
    gender: str,
    marital_status: str,
    education: str,
    employment_status: str,
    resident_status: str,
    resident_type: str,
    type_of_employment: str,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id,
                age,
                gender,
                state,
                individual_yearly_income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                number_of_children_in_family,
                number_of_adults_in_family,
                type_of_employment,
                family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                age,
                gender,
                state,
                income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                0,
                max(1, family_member_count - 1),
                type_of_employment,
                income + 10_000.0,
            ),
        )


def _seed_fixture(database_path: Path) -> int:
    with get_connection(database_path, write=True) as connection:
        customer_import_id = int(
            connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name, source_path, started_at, completed_at, status,
                    rows_read, rows_inserted, rows_rejected, source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "customers",
                    "customers.csv",
                    "2026-09-10T00:00:00Z",
                    "2026-09-10T00:00:01Z",
                    "COMPLETED",
                    3,
                    3,
                    0,
                    "c" * 64,
                ),
            ).lastrowid
        )
        campaign_import_id = int(
            connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name, source_path, started_at, completed_at, status,
                    rows_read, rows_inserted, rows_rejected, source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign_sales",
                    "campaign_sales.csv",
                    "2026-09-10T00:00:02Z",
                    "2026-09-10T00:00:03Z",
                    "COMPLETED",
                    3,
                    3,
                    0,
                    "d" * 64,
                ),
            ).lastrowid
        )
        demographic_import_id = int(
            connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name, source_path, started_at, completed_at, status,
                    rows_read, rows_inserted, rows_rejected, source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "demographics",
                    "demographics.csv",
                    "2026-09-10T00:00:04Z",
                    "2026-09-10T00:00:05Z",
                    "COMPLETED",
                    6,
                    6,
                    0,
                    "e" * 64,
                ),
            ).lastrowid
        )

    _insert_customer(
        database_path,
        customer_id="CUS_001",
        date_of_birth="1985-01-01",
        state="California",
        income=120000.0,
        family_member_count=2,
        gender="Female",
        marital_status="Married",
        education="Masters",
        employment_status="Employed",
        resident_status="Citizen",
        resident_type="Urban",
        type_of_employment="Private",
    )
    _insert_customer(
        database_path,
        customer_id="CUS_002",
        date_of_birth="1995-01-01",
        state="Texas",
        income=55000.0,
        family_member_count=1,
        gender="Male",
        marital_status="Single",
        education="Bachelors",
        employment_status="Employed",
        resident_status="Resident",
        resident_type="Suburban",
        type_of_employment="Government",
    )
    _insert_customer(
        database_path,
        customer_id="CUS_003",
        date_of_birth="1975-01-01",
        state="California",
        income=210000.0,
        family_member_count=4,
        gender="Female",
        marital_status="Married",
        education="PhD",
        employment_status="Self-employed",
        resident_status="Citizen",
        resident_type="Urban",
        type_of_employment="Private",
    )

    _insert_campaign_sale(
        database_path,
        campaign_sales_id="CS_001",
        customer_id="CUS_001",
        contact_date="2025-06-01",
        purchase_flag=1,
        attributed_flag=1,
    )
    _insert_campaign_sale(
        database_path,
        campaign_sales_id="CS_002",
        customer_id="CUS_002",
        contact_date="2025-06-01",
        purchase_flag=0,
        attributed_flag=0,
    )
    _insert_campaign_sale(
        database_path,
        campaign_sales_id="CS_003",
        customer_id="CUS_003",
        contact_date="2025-06-01",
        purchase_flag=1,
        attributed_flag=1,
    )

    with get_connection(database_path, write=True) as connection:
        analysis_run_id = int(
            connection.execute(
                """
                INSERT INTO historical_analysis_runs (
                    analysis_name, created_at, completed_at, status,
                    conversion_definition, filters_json, results_json,
                    customer_import_id, customer_source_checksum,
                    campaign_sales_import_id, campaign_sales_source_checksum,
                    observation_count, selected_customer_count,
                    positive_customer_count, unlabeled_customer_count,
                    positive_customer_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Saved audience fixture analysis",
                    "2026-09-10T00:00:06Z",
                    "2026-09-10T00:00:10Z",
                    "COMPLETED",
                    "ATTRIBUTED_PURCHASE",
                    json.dumps(
                        {
                            "campaign_ids": [],
                            "product_ids": [],
                            "product_categories": [],
                            "campaign_channels": [],
                            "campaign_types": [],
                            "contact_date_from": "2025-01-01",
                            "contact_date_to": "2025-12-31",
                            "contacted_only": True,
                            "conversion_definition": "ATTRIBUTED_PURCHASE",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "{}",
                    customer_import_id,
                    "c" * 64,
                    campaign_import_id,
                    "d" * 64,
                    3,
                    3,
                    2,
                    1,
                    2 / 3,
                ),
            ).lastrowid
        )

        model_run_id = int(
            connection.execute(
                """
                INSERT INTO model_runs (
                    analysis_run_id,
                    model_name,
                    created_at,
                    completed_at,
                    status,
                    random_seed,
                    validation_fraction,
                    selected_candidate,
                    artifact_sha256,
                    metrics_json,
                    feature_contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_run_id,
                    "Saved audience model",
                    "2026-09-10T00:10:00Z",
                    "2026-09-10T00:10:20Z",
                    "COMPLETED",
                    42,
                    0.2,
                    "BAGGING_PU",
                    "a" * 64,
                    "{}",
                    "{}",
                ),
            ).lastrowid
        )

        job_id = int(
            connection.execute(
                """
                INSERT INTO jobs (
                    job_type,
                    status,
                    progress_percent,
                    stage,
                    analysis_run_id,
                    model_run_id,
                    created_at,
                    started_at,
                    finished_at,
                    request_json,
                    result_json,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "PROSPECT_SCORING",
                    "COMPLETED",
                    100,
                    "COMPLETED",
                    None,
                    model_run_id,
                    "2026-09-10T00:30:00Z",
                    "2026-09-10T00:30:00Z",
                    "2026-09-10T00:30:15Z",
                    json.dumps({"model_run_id": model_run_id}, sort_keys=True, separators=(",", ":")),
                    json.dumps({"model_run_id": model_run_id}, sort_keys=True, separators=(",", ":")),
                    None,
                ),
            ).lastrowid
        )

    prospect_rows = [
        ("PER_000001", 35, "California", 120000.0, 2, "Female", "Married", "Masters", "Employed", "Citizen", "Urban", "Private", 0.97),
        ("PER_000002", 29, "Texas", 60000.0, 1, "Male", "Single", "Bachelors", "Employed", "Resident", "Suburban", "Government", 0.94),
        ("PER_000003", 41, "California", 210000.0, 4, "Female", "Married", "PhD", "Self-employed", "Citizen", "Urban", "Private", 0.91),
        ("PER_000004", 54, "Ohio", 45000.0, 3, "Female", "Divorced", "High School", "Unemployed", "Resident", "Rural", "Contract", 0.84),
        ("PER_000005", 33, "Florida", 80000.0, 5, "Male", "Married", "Bachelors", "Employed", "Citizen", "Suburban", "Private", 0.76),
        ("PER_000006", 67, "California", 160000.0, 2, "Female", "Widowed", "Masters", "Retired", "Citizen", "Urban", "Retired", 0.55),
    ]

    for (
        person_id,
        age,
        state,
        income,
        family_member_count,
        gender,
        marital_status,
        education,
        employment_status,
        resident_status,
        resident_type,
        type_of_employment,
        score,
    ) in prospect_rows:
        _insert_demographic(
            database_path,
            person_id=person_id,
            age=age,
            state=state,
            income=income,
            family_member_count=family_member_count,
            gender=gender,
            marital_status=marital_status,
            education=education,
            employment_status=employment_status,
            resident_status=resident_status,
            resident_type=resident_type,
            type_of_employment=type_of_employment,
        )

    with get_connection(database_path, write=True) as connection:
        min_person_id = "PER_000001"
        max_person_id = "PER_000006"
        scores = [row[-1] for row in prospect_rows]
        scoring_run_id = int(
            connection.execute(
                """
                INSERT INTO scoring_runs (
                    job_id,
                    model_run_id,
                    created_at,
                    completed_at,
                    status,
                    demographic_snapshot_count,
                    demographic_min_person_id,
                    demographic_max_person_id,
                    scored_person_count,
                    chunk_size,
                    last_person_id,
                    selected_candidate,
                    model_role_policy_version,
                    feature_contract_version,
                    feature_contract_sha256,
                    artifact_sha256,
                    score_min,
                    score_max,
                    score_mean,
                    score_summary_json,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    model_run_id,
                    "2026-09-10T00:30:01Z",
                    "2026-09-10T00:30:15Z",
                    "COMPLETED",
                    6,
                    min_person_id,
                    max_person_id,
                    6,
                    1000,
                    max_person_id,
                    "BAGGING_PU",
                    "2",
                    "1",
                    "a" * 64,
                    "a" * 64,
                    min(scores),
                    max(scores),
                    sum(scores) / len(scores),
                    json.dumps(
                        {
                            "demographic_import_id": demographic_import_id,
                            "demographic_source_checksum": "e" * 64,
                            "demographic_snapshot_count": 6,
                            "demographic_min_person_id": min_person_id,
                            "demographic_max_person_id": max_person_id,
                            "model_run_id": model_run_id,
                            "analysis_run_id": analysis_run_id,
                            "customer_import_id": customer_import_id,
                            "customer_source_checksum": "c" * 64,
                            "campaign_sales_import_id": campaign_import_id,
                            "campaign_sales_source_checksum": "d" * 64,
                            "selected_candidate": "BAGGING_PU",
                            "feature_contract_version": "1",
                            "feature_contract_sha256": "a" * 64,
                            "artifact_sha256": "a" * 64,
                            "chunk_size": 1000,
                            "chunk_count": 1,
                            "score_count": 6,
                            "score_min": min(scores),
                            "score_mean": sum(scores) / len(scores),
                            "score_max": max(scores),
                            "total_seconds": 0.1,
                            "rows_per_second": 60.0,
                            "age_semantics_note": "fixture",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    None,
                ),
            ).lastrowid
        )

        connection.executemany(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            [(scoring_run_id, model_run_id, row[0], row[-1]) for row in prospect_rows],
        )

    return scoring_run_id


def test_save_and_replay_and_detail(database_path: Path) -> None:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    saved = save_audience(
        database_path,
        {
            "audience_name": "  California Prospects  ",
            "description": "  Saved for phase 7 replay  ",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "selection": {"mode": "TOP_N", "target_count": 2},
            "include_profile_snapshot": True,
        },
    )

    assert saved["audience_name"] == "California Prospects"
    assert saved["description"] == "Saved for phase 7 replay"
    assert saved["definition"]["selection_mode"] == "TOP_N"
    assert saved["definition"]["target_count"] == 2
    assert saved["definition"]["resolved_count"] == 2
    assert saved["currentness"]["is_current"] is True
    assert saved["profile_snapshot"] is not None

    replay = replay_saved_audience_definition(
        database_path,
        audience_id=saved["audience_id"],
    )
    assert replay == {
        "scoring_run_id": scoring_run_id,
        "filters": {"age_max": None, "age_min": None, "deciles": [], "education": [], "employment_status": [], "family_member_count_max": None, "family_member_count_min": None, "gender": [], "individual_yearly_income_max": None, "individual_yearly_income_min": None, "marital_status": [], "rank_bands": [], "resident_status": [], "resident_type": [], "score_max": None, "score_min": None, "state": ["California"], "top_percentile_max": None, "type_of_employment": []},
        "selection": {"mode": "TOP_N", "target_count": 2},
    }

    detail = get_saved_audience_detail(database_path, audience_id=saved["audience_id"])
    assert detail["replay_request"] == replay
    assert detail["currentness"]["is_current"] is True


def test_save_rejects_empty_selected_count(database_path: Path) -> None:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    with pytest.raises(SavedAudienceServiceValidationError, match=SAVED_AUDIENCE_EMPTY_MESSAGE):
        save_audience(
            database_path,
            {
                "audience_name": "Empty Audience",
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["NoMatchState"]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )


def test_saved_audience_currentness_stale_on_new_demographics_import(database_path: Path) -> None:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    saved = save_audience(
        database_path,
        {
            "audience_name": "Current now",
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "demographics",
                "demographics_v2.csv",
                "2026-09-11T00:00:00Z",
                "2026-09-11T00:00:01Z",
                "COMPLETED",
                6,
                6,
                0,
                "f" * 64,
            ),
        )

    currentness = validate_saved_audience_currentness(database_path, audience_id=saved["audience_id"])
    assert currentness["is_current"] is False
    assert currentness["issues"]


def test_list_saved_audiences_pagination(database_path: Path) -> None:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    first = save_audience(
        database_path,
        {
            "audience_name": "Audience A",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "selection": {"mode": "TOP_N", "target_count": 1},
        },
    )
    second = save_audience(
        database_path,
        {
            "audience_name": "Audience B",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["Texas"]},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )

    page_1 = list_saved_audiences(database_path, limit=1, offset=0)
    page_2 = list_saved_audiences(database_path, limit=1, offset=1)

    assert len(page_1) == 1
    assert len(page_2) == 1
    assert {page_1[0]["audience_id"], page_2[0]["audience_id"]} == {first["audience_id"], second["audience_id"]}


def test_missing_saved_audience_not_found(database_path: Path) -> None:
    with pytest.raises(SavedAudienceServiceNotFoundError):
        get_saved_audience_detail(database_path, audience_id=999)
