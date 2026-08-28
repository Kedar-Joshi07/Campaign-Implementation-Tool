from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import perf_counter

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.scoring_repository import SCORE_SCAN_QUERY_AFTER, SCORE_SCAN_QUERY_INITIAL
from app.services.audience_preparation_service import (
    ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE,
    AudiencePreparationConflictError,
    AudiencePreparationValidationError,
    run_audience_rank_preparation,
    submit_audience_preparation_job_request,
)
from app.services.audience_query_service import (
    CURSOR_INVALID_MESSAGE,
    CURSOR_MISMATCH_MESSAGE,
    RANK_BOUNDARIES_NOT_READY_MESSAGE,
    SCORING_RUN_NOT_CANONICAL_MESSAGE,
    AudienceQueryConflictError,
    AudienceQueryValidationError,
    estimate_audience,
    get_audience_filter_options,
    profile_audience,
    search_audience,
)
from app.services.model_api_service import (
    ModelApiValidationError,
    get_job_detail,
)
from app.services.model_job_service import (
    ACTIVE_JOB_CONFLICT_MESSAGE,
    ModelJobConflictError,
    submit_model_training_job_request,
)
from app.services.saved_audience_service import (
    SavedAudienceServiceConflictError,
    SavedAudienceServiceValidationError,
    get_saved_audience_detail,
    save_audience,
    validate_saved_audience_currentness,
)
from app.services.scoring_job_service import ScoringJobConflictError, submit_prospect_scoring_job_request

FORBIDDEN_PHASE6_FIELDS = (
    "first_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "phone_number",
    "email",
    "ethnicity",
    "religion",
    "occupation_industry",
    "family_yearly_income",
    "number_of_children_in_family",
    "number_of_adults_in_family",
)


def _phase6_seed_fixture(database_path: Path) -> int:
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

    with get_connection(database_path, write=True) as connection:
        connection.executemany(
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
            [
                (
                    "CUS_001",
                    "1985-01-01",
                    "California",
                    120000.0,
                    2,
                    "Female",
                    "Married",
                    "Masters",
                    "Employed",
                    "Citizen",
                    "Urban",
                    "Private",
                ),
                (
                    "CUS_002",
                    "1995-01-01",
                    "Texas",
                    55000.0,
                    1,
                    "Male",
                    "Single",
                    "Bachelors",
                    "Employed",
                    "Resident",
                    "Suburban",
                    "Government",
                ),
                (
                    "CUS_003",
                    "1975-01-01",
                    "California",
                    210000.0,
                    4,
                    "Female",
                    "Married",
                    "PhD",
                    "Self-employed",
                    "Citizen",
                    "Urban",
                    "Private",
                ),
            ],
        )
        connection.executemany(
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
            [
                (
                    "CS_001",
                    "CUS_001",
                    "CMP_001",
                    "PRD_001",
                    "2025-01-01",
                    "2025-12-31",
                    "2025-06-01",
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                ),
                (
                    "CS_002",
                    "CUS_002",
                    "CMP_001",
                    "PRD_001",
                    "2025-01-01",
                    "2025-12-31",
                    "2025-06-01",
                    1,
                    1,
                    0,
                    0,
                    0,
                    0,
                ),
                (
                    "CS_003",
                    "CUS_003",
                    "CMP_001",
                    "PRD_001",
                    "2025-01-01",
                    "2025-12-31",
                    "2025-06-01",
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                ),
            ],
        )

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
                    "Audience profile fixture analysis",
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
                    "Audience profile model",
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
        (
            "PER_000001",
            35,
            "California",
            120000.0,
            2,
            "Female",
            "Married",
            "Masters",
            "Employed",
            "Citizen",
            "Urban",
            "Private",
            0.97,
        ),
        (
            "PER_000002",
            29,
            "Texas",
            60000.0,
            1,
            "Male",
            "Single",
            "Bachelors",
            "Employed",
            "Resident",
            "Suburban",
            "Government",
            0.94,
        ),
        (
            "PER_000003",
            41,
            "California",
            210000.0,
            4,
            "Female",
            "Married",
            "PhD",
            "Self-employed",
            "Citizen",
            "Urban",
            "Private",
            0.91,
        ),
        (
            "PER_000004",
            54,
            "Ohio",
            45000.0,
            3,
            "Female",
            "Divorced",
            "High School",
            "Unemployed",
            "Resident",
            "Rural",
            "Contract",
            0.84,
        ),
        (
            "PER_000005",
            33,
            "Florida",
            80000.0,
            5,
            "Male",
            "Married",
            "Bachelors",
            "Employed",
            "Citizen",
            "Suburban",
            "Private",
            0.76,
        ),
        (
            "PER_000006",
            67,
            "California",
            160000.0,
            2,
            "Female",
            "Widowed",
            "Masters",
            "Retired",
            "Citizen",
            "Urban",
            "Retired",
            0.55,
        ),
    ]

    with get_connection(database_path, write=True) as connection:
        connection.executemany(
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
            [
                (
                    row[0],
                    row[1],
                    row[5],
                    row[2],
                    row[3],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[4],
                    0,
                    max(1, row[4] - 1),
                    row[11],
                    row[3] + 10_000.0,
                )
                for row in prospect_rows
            ],
        )

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


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase6-step8-hardening.db"
    initialize_database(path)
    return path


def _explain_query_plan(database_path: Path, query: str, params: list[object]) -> list[str]:
    with get_connection(database_path) as connection:
        rows = connection.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()
    return [str(row[3]) for row in rows]


def test_no_offset_hot_path_contract_constants() -> None:
    assert "OFFSET" not in SCORE_SCAN_QUERY_INITIAL.upper()
    assert "OFFSET" not in SCORE_SCAN_QUERY_AFTER.upper()


def test_query_plan_uses_rank_index_for_keyset_search(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    initial = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 2,
        },
    )
    assert initial["next_cursor"] is not None

    initial_query = """
        SELECT p.person_id, p.propensity_score
        FROM propensity_scores p
        INNER JOIN demographics d ON d.person_id = p.person_id
        WHERE p.scoring_run_id = ?
        ORDER BY p.propensity_score DESC, p.person_id ASC
        LIMIT ?
    """
    after_query = """
        SELECT p.person_id, p.propensity_score
        FROM propensity_scores p
        INNER JOIN demographics d ON d.person_id = p.person_id
        WHERE p.scoring_run_id = ?
            AND (p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))
        ORDER BY p.propensity_score DESC, p.person_id ASC
        LIMIT ?
    """

    first_row = initial["rows"][-1]
    initial_plan = _explain_query_plan(database_path, initial_query, [scoring_run_id, 3])
    next_plan = _explain_query_plan(
        database_path,
        after_query,
        [
            scoring_run_id,
            float(first_row["propensity_score"]),
            float(first_row["propensity_score"]),
            str(first_row["person_id"]),
            3,
        ],
    )

    combined_plan = "\n".join(initial_plan + next_plan)
    assert "idx_propensity_scores_run_score_person" in combined_plan
    assert "SCAN propensity_scores" not in combined_plan


def test_query_plan_smoke_for_step8_cases(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    cases = [
        {"filters": {}, "selection": {"mode": "ALL_MATCHING"}},
        {"filters": {"top_percentile_max": 1}, "selection": {"mode": "ALL_MATCHING"}},
        {"filters": {"deciles": [1]}, "selection": {"mode": "ALL_MATCHING"}},
        {"filters": {"state": ["California"]}, "selection": {"mode": "ALL_MATCHING"}},
        {
            "filters": {
                "age_min": 30,
                "age_max": 55,
                "individual_yearly_income_min": 50_000.0,
                "individual_yearly_income_max": 150_000.0,
            },
            "selection": {"mode": "ALL_MATCHING"},
        },
        {
            "filters": {
                "rank_bands": ["HIGH", "MEDIUM"],
                "resident_type": ["Urban"],
            },
            "selection": {"mode": "TOP_N", "target_count": 2},
        },
    ]

    for payload in cases:
        t0 = perf_counter()
        estimate = estimate_audience(database_path, {"scoring_run_id": scoring_run_id, **payload})
        elapsed_ms = (perf_counter() - t0) * 1000.0
        assert estimate["source_verified"] is True
        assert estimate["selected_count"] >= 0
        assert elapsed_ms < 5000

    # Search/profile/saved-audience list/detail are exercised with timing bounds.
    t0 = perf_counter()
    search_page = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "page_size": 2,
        },
    )
    assert len(search_page["rows"]) <= 2
    assert (perf_counter() - t0) * 1000.0 < 5000

    t0 = perf_counter()
    profile = profile_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "selection": {"mode": "TOP_N", "target_count": 2},
        },
    )
    assert profile["source_verified"] is True
    assert (perf_counter() - t0) * 1000.0 < 5000

    saved = save_audience(
        database_path,
        {
            "audience_name": "Step8 Perf",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "selection": {"mode": "TOP_N", "target_count": 2},
            "include_profile_snapshot": True,
        },
    )
    assert saved["audience_id"] > 0

    t0 = perf_counter()
    detail = get_saved_audience_detail(database_path, audience_id=int(saved["audience_id"]))
    assert detail["currentness"]["is_current"] is True
    assert (perf_counter() - t0) * 1000.0 < 5000


def test_audience_search_page_size_bound_and_no_large_fetch(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    with pytest.raises(AudienceQueryValidationError, match="page_size must be between"):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 101,
            },
        )


def test_phase6_pii_forbidden_fields_not_exposed_in_public_payloads(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    payloads = [
        get_audience_filter_options(database_path, scoring_run_id=scoring_run_id),
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        ),
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 2,
            },
        ),
        profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        ),
    ]

    saved = save_audience(
        database_path,
        {
            "audience_name": "Step8 PII",
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "selection": {"mode": "TOP_N", "target_count": 2},
        },
    )
    payloads.extend(
        [
            saved,
            get_saved_audience_detail(database_path, audience_id=int(saved["audience_id"])),
            validate_saved_audience_currentness(database_path, audience_id=int(saved["audience_id"])),
        ]
    )

    def _collect_keys(value: object, *, parent_key: str | None = None) -> set[str]:
        collected: set[str] = set()
        if isinstance(value, dict):
            for key, nested in value.items():
                if isinstance(key, str):
                    if not (parent_key == "pii_policy" and key == "blocked_fields"):
                        collected.add(key.casefold())
                collected |= _collect_keys(nested, parent_key=key if isinstance(key, str) else None)
        elif isinstance(value, list):
            for item in value:
                collected |= _collect_keys(item, parent_key=parent_key)
        return collected

    exposed_keys: set[str] = set()
    for payload in payloads:
        exposed_keys |= _collect_keys(payload)

    for forbidden in FORBIDDEN_PHASE6_FIELDS:
        assert forbidden not in exposed_keys


def test_model_api_rejects_forbidden_fields_and_path_like_content_in_result_json(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = int(
            connection.execute(
                """
                INSERT INTO historical_analysis_runs (
                    analysis_name, created_at, completed_at, status,
                    conversion_definition, filters_json, results_json,
                    observation_count, selected_customer_count,
                    positive_customer_count, unlabeled_customer_count,
                    positive_customer_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "x",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:01Z",
                    "COMPLETED",
                    "ATTRIBUTED_PURCHASE",
                    "{}",
                    "{}",
                    1,
                    1,
                    1,
                    0,
                    1.0,
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
                    "x",
                    "2026-01-01T00:00:02Z",
                    "2026-01-01T00:00:03Z",
                    "COMPLETED",
                    1,
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
                    "2026-01-01T00:00:04Z",
                    "2026-01-01T00:00:04Z",
                    "2026-01-01T00:00:05Z",
                    "{}",
                    json.dumps({"city": "Austin"}, sort_keys=True, separators=(",", ":")),
                    None,
                ),
            ).lastrowid
        )

    with pytest.raises(ModelApiValidationError, match="result_json metadata is invalid"):
        get_job_detail(database_path, job_id)

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE jobs SET result_json = ? WHERE job_id = ?",
            (
                json.dumps({"meta": "C:\\private\\db.sqlite"}, sort_keys=True, separators=(",", ":")),
                job_id,
            ),
        )

    with pytest.raises(ModelApiValidationError, match="result_json metadata is invalid"):
        get_job_detail(database_path, job_id)


def test_provenance_drift_marks_saved_audience_stale_across_sources(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    saved = save_audience(
        database_path,
        {
            "audience_name": "Drift",
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    audience_id = int(saved["audience_id"])

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

    demographic_stale = validate_saved_audience_currentness(database_path, audience_id=audience_id)
    assert demographic_stale["is_current"] is False

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "customers",
                "customers_v2.csv",
                "2026-09-11T00:01:00Z",
                "2026-09-11T00:01:01Z",
                "COMPLETED",
                3,
                3,
                0,
                "f" * 64,
            ),
        )
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "campaign_sales",
                "campaign_sales_v2.csv",
                "2026-09-11T00:02:00Z",
                "2026-09-11T00:02:01Z",
                "COMPLETED",
                3,
                3,
                0,
                "f" * 64,
            ),
        )

    source_stale = validate_saved_audience_currentness(database_path, audience_id=audience_id)
    assert source_stale["is_current"] is False
    joined = "\n".join(source_stale["issues"])
    assert "customer" in joined.casefold() or "campaign" in joined.casefold()


def test_rank_boundaries_cannot_override_stale_provenance(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

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

    with pytest.raises(AudienceQueryConflictError, match=SCORING_RUN_NOT_CANONICAL_MESSAGE):
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )

    with pytest.raises(AudiencePreparationConflictError, match=SCORING_RUN_NOT_CANONICAL_MESSAGE):
        run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)


def test_source_restoration_allows_normal_currentness_again(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    saved = save_audience(
        database_path,
        {
            "audience_name": "Restore",
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    audience_id = int(saved["audience_id"])

    with get_connection(database_path, write=True) as connection:
        drift_import_id = int(connection.execute(
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
        ).lastrowid)

    stale = validate_saved_audience_currentness(database_path, audience_id=audience_id)
    assert stale["is_current"] is False

    # Mark the drift import failed so the canonical completed import is latest again.
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE data_import_runs
            SET status = 'FAILED'
            WHERE import_id = ?
            """,
            (drift_import_id,),
        )

    restored = validate_saved_audience_currentness(database_path, audience_id=audience_id)
    assert restored["is_current"] is True


def test_concurrency_conflict_matrix_with_active_audience_preparation(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)

    with get_connection(database_path) as connection:
        model_run_id = int(
            connection.execute(
                "SELECT model_run_id FROM scoring_runs WHERE scoring_run_id = ?",
                (scoring_run_id,),
            ).fetchone()[0]
        )
        analysis_run_id = int(
            connection.execute(
                "SELECT analysis_run_id FROM model_runs WHERE model_run_id = ?",
                (model_run_id,),
            ).fetchone()[0]
        )

    monkeypatch.setattr(
        "app.services.scoring_job_service.validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    with get_connection(database_path, write=True) as connection:
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
                request_json
            ) VALUES (?, 'QUEUED', 0, 'QUEUED', NULL, NULL, ?, ?)
            """,
            (
                "AUDIENCE_PREPARATION",
                "2026-09-11T01:00:00Z",
                json.dumps({"scoring_run_id": scoring_run_id, "rank_contract_version": "1"}),
            ),
        )

    with pytest.raises(AudiencePreparationConflictError, match=ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE):
        submit_audience_preparation_job_request(
            database_path,
            {"scoring_run_id": scoring_run_id, "rank_contract_version": "1"},
            submitter=lambda *_: None,
        )

    with pytest.raises(ModelJobConflictError, match=ACTIVE_JOB_CONFLICT_MESSAGE):
        submit_model_training_job_request(
            database_path,
            {"analysis_run_id": analysis_run_id},
            submitter=lambda *_: None,
        )

    # Use a second model with no completed scoring run so active-compute conflict is evaluated.
    with get_connection(database_path, write=True) as connection:
        second_analysis_id = int(
            connection.execute(
                """
                INSERT INTO historical_analysis_runs (
                    analysis_name, created_at, completed_at, status,
                    conversion_definition, filters_json, results_json,
                    observation_count, selected_customer_count,
                    positive_customer_count, unlabeled_customer_count,
                    positive_customer_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Step8 concurrency analysis",
                    "2026-09-11T01:00:10Z",
                    "2026-09-11T01:00:12Z",
                    "COMPLETED",
                    "ATTRIBUTED_PURCHASE",
                    "{}",
                    "{}",
                    1,
                    1,
                    1,
                    0,
                    1.0,
                ),
            ).lastrowid
        )
        second_model_run_id = int(
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
                    second_analysis_id,
                    "Step8 concurrency model",
                    "2026-09-11T01:00:13Z",
                    "2026-09-11T01:00:14Z",
                    "COMPLETED",
                    7,
                    0.2,
                    "BAGGING_PU",
                    "b" * 64,
                    "{}",
                    "{}",
                ),
            ).lastrowid
        )

    with pytest.raises(ScoringJobConflictError, match=ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE):
        submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": second_model_run_id},
            submitter=lambda *_: None,
        )


def test_read_only_search_profile_requires_prepared_current_run(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)

    with pytest.raises(AudienceQueryConflictError, match=RANK_BOUNDARIES_NOT_READY_MESSAGE):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 2,
            },
        )

    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
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

    with pytest.raises(AudienceQueryConflictError, match=SCORING_RUN_NOT_CANONICAL_MESSAGE):
        profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )


def test_input_hardening_rejects_oversized_arrays_and_text_and_invalid_values(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    too_many_states = [f"S{i:03d}" for i in range(101)]
    with pytest.raises(AudienceQueryValidationError, match="must not contain more than"):
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": too_many_states},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )

    with pytest.raises(AudienceQueryValidationError, match="selection.target_count must not exceed"):
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "TOP_N", "target_count": 1_000_001},
            },
        )

    with pytest.raises(AudienceQueryValidationError, match="finite"):
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"score_min": float("inf")},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )

    with pytest.raises(AudienceQueryValidationError, match="unknown keys"):
        estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"unknown_key": ["x"]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )

    first_page = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 2,
        },
    )
    cursor = str(first_page["next_cursor"])
    with pytest.raises(AudienceQueryValidationError, match=CURSOR_INVALID_MESSAGE):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 2,
                "cursor": cursor[:-2] + "@@",
            },
        )

    with pytest.raises(AudienceQueryConflictError, match=CURSOR_MISMATCH_MESSAGE):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["Ohio"]},
                "page_size": 2,
                "cursor": cursor,
            },
        )


def test_input_hardening_rejects_unsupported_rank_contract_version(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    with pytest.raises(AudiencePreparationValidationError, match="not supported"):
        submit_audience_preparation_job_request(
            database_path,
            {"scoring_run_id": scoring_run_id, "rank_contract_version": "2"},
            submitter=lambda *_: None,
        )


def test_input_hardening_rejects_sql_metacharacter_abuse_without_leakage(database_path: Path) -> None:
    scoring_run_id = _phase6_seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    # SQL-looking content remains plain parameterized string input.
    result = estimate_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California'; DROP TABLE demographics; --"]},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    assert result["matching_count"] == 0

    # Core table still exists.
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'demographics'"
        ).fetchone()
    assert row is not None


def test_phase_boundary_scan_forbidden_surfaces_absent() -> None:
    root = Path(__file__).resolve().parents[1]
    app_source = "\n".join(path.read_text(encoding="utf-8") for path in root.joinpath("app").rglob("*.py")).casefold()
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8") for path in root.joinpath("frontend", "js").glob("*.js")
    ).casefold()

    for forbidden in (
        "/api/campaigns/export",
        "activation adapter",
        "target csv",
        "campaign activation api",
        "contact export api",
        "audience_members",
    ):
        assert forbidden not in app_source
        assert forbidden not in frontend_source
