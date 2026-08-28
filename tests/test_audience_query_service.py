from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.audience_query_service import (
    CURSOR_MISMATCH_MESSAGE,
    RANK_BOUNDARIES_NOT_READY_MESSAGE,
    AudienceQueryConflictError,
    AudienceQueryValidationError,
    SEARCH_QUERY_AFTER,
    SEARCH_QUERY_INITIAL,
    estimate_audience,
    get_audience_filter_options,
    normalize_audience_filters,
    search_audience,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "audience-query-service.db"
    initialize_database(path)
    return path


def _insert_analysis_run(database_path: Path) -> int:
    with get_connection(database_path, write=True) as connection:
        customer_import_id = int(
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
                    "2026-09-05T00:00:00Z",
                    "2026-09-05T00:00:01Z",
                    "COMPLETED",
                    0,
                    0,
                    0,
                    "c" * 64,
                ),
            ).lastrowid
        )
        campaign_import_id = int(
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
                    "data/campaign_fixture.csv",
                    "2026-09-05T00:00:02Z",
                    "2026-09-05T00:00:03Z",
                    "COMPLETED",
                    0,
                    0,
                    0,
                    "d" * 64,
                ),
            ).lastrowid
        )
        cursor = connection.execute(
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
                "Audience query fixture",
                "2026-09-05T00:00:04Z",
                "2026-09-05T00:00:10Z",
                "COMPLETED",
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}",
                customer_import_id,
                "c" * 64,
                campaign_import_id,
                "d" * 64,
                10,
                5,
                3,
                2,
                0.6,
            ),
        )
        return int(cursor.lastrowid)


def _insert_model_run(database_path: Path, analysis_run_id: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
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
                "Audience query model",
                "2026-09-05T00:10:00Z",
                "2026-09-05T00:10:20Z",
                "COMPLETED",
                42,
                0.2,
                "BAGGING_PU",
                "a" * 64,
                "{}",
                "{}",
            ),
        )
        return int(cursor.lastrowid)


def _insert_demographic_person(
    database_path: Path,
    *,
    person_id: str,
    age: int,
    gender: str,
    state: str,
    income: float,
    marital_status: str,
    education: str,
    employment_status: str,
    resident_status: str,
    resident_type: str,
    family_member_count: int,
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
                income + 20_000.0,
            ),
        )


def _insert_completed_demographic_import(database_path: Path, *, rows_inserted: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
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
                "demographics",
                "data/demographics_fixture.csv",
                "2026-09-05T00:20:00Z",
                "2026-09-05T00:20:10Z",
                "COMPLETED",
                rows_inserted,
                rows_inserted,
                0,
                "e" * 64,
            ),
        )
        return int(cursor.lastrowid)


def _create_completed_scoring_run(
    database_path: Path,
    *,
    model_run_id: int,
    analysis_run_id: int,
    scores: list[tuple[str, float]],
) -> int:
    demographic_import_id = _insert_completed_demographic_import(
        database_path,
        rows_inserted=len(scores),
    )

    with get_connection(database_path, write=True) as connection:
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
                    "2026-09-05T00:30:00Z",
                    "2026-09-05T00:30:00Z",
                    "2026-09-05T00:30:15Z",
                    json.dumps({"model_run_id": model_run_id}, sort_keys=True, separators=(",", ":")),
                    json.dumps(
                        {
                            "scoring_run_id": 0,
                            "model_run_id": model_run_id,
                            "scored_person_count": len(scores),
                            "score_min": min(score for _, score in scores),
                            "score_max": max(score for _, score in scores),
                            "score_mean": sum(score for _, score in scores) / len(scores),
                            "total_seconds": 1.0,
                            "rows_per_second": float(len(scores)),
                            "chunk_size": 1000,
                            "chunk_count": 1,
                            "largest_chunk_rows": len(scores),
                            "largest_transformed_matrix_bytes": 128,
                            "selected_candidate": "BAGGING_PU",
                            "model_role_policy_version": "2",
                            "feature_contract_version": "1",
                            "feature_contract_sha256": "a" * 64,
                            "artifact_sha256": "a" * 64,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    None,
                ),
            ).lastrowid
        )

        sorted_rows = sorted(scores, key=lambda item: (-item[1], item[0]))
        min_person_id = min(person_id for person_id, _ in sorted_rows)
        max_person_id = max(person_id for person_id, _ in sorted_rows)
        score_min = min(score for _, score in sorted_rows)
        score_max = max(score for _, score in sorted_rows)
        score_mean = sum(score for _, score in sorted_rows) / len(sorted_rows)

        summary_json = json.dumps(
            {
                "demographic_import_id": demographic_import_id,
                "demographic_source_checksum": "e" * 64,
                "demographic_snapshot_count": len(sorted_rows),
                "demographic_min_person_id": min_person_id,
                "demographic_max_person_id": max_person_id,
                "model_run_id": model_run_id,
                "analysis_run_id": analysis_run_id,
                "customer_import_id": 1,
                "customer_source_checksum": "c" * 64,
                "campaign_sales_import_id": 2,
                "campaign_sales_source_checksum": "d" * 64,
                "selected_candidate": "BAGGING_PU",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "a" * 64,
                "chunk_size": 1000,
                "chunk_count": 1,
                "score_count": len(sorted_rows),
                "score_min": score_min,
                "score_mean": score_mean,
                "score_max": score_max,
                "total_seconds": 0.1,
                "rows_per_second": 10.0,
                "age_semantics_note": "fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        )

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
                    "2026-09-05T00:30:01Z",
                    "2026-09-05T00:30:15Z",
                    "COMPLETED",
                    len(sorted_rows),
                    min_person_id,
                    max_person_id,
                    len(sorted_rows),
                    1000,
                    max_person_id,
                    "BAGGING_PU",
                    "2",
                    "1",
                    "a" * 64,
                    "a" * 64,
                    score_min,
                    score_max,
                    score_mean,
                    summary_json,
                    None,
                ),
            ).lastrowid
        )

        connection.execute(
            "UPDATE jobs SET result_json = ? WHERE job_id = ?",
            (
                json.dumps(
                    {
                        "scoring_run_id": scoring_run_id,
                        "model_run_id": model_run_id,
                        "scored_person_count": len(sorted_rows),
                        "score_min": score_min,
                        "score_max": score_max,
                        "score_mean": score_mean,
                        "total_seconds": 1.0,
                        "rows_per_second": float(len(sorted_rows)),
                        "chunk_size": 1000,
                        "chunk_count": 1,
                        "largest_chunk_rows": len(sorted_rows),
                        "largest_transformed_matrix_bytes": 128,
                        "selected_candidate": "BAGGING_PU",
                        "model_role_policy_version": "2",
                        "feature_contract_version": "1",
                        "feature_contract_sha256": "a" * 64,
                        "artifact_sha256": "a" * 64,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                job_id,
            ),
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
            [(scoring_run_id, model_run_id, person_id, score) for person_id, score in sorted_rows],
        )

    return scoring_run_id


def _seed_query_fixture(database_path: Path) -> int:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    rows = [
        ("PER_000001", 0.98, 29, "Female", "California", 120_000.0, "Single", "Masters", "Employed", "Citizen", "Urban", 1, "Private"),
        ("PER_000002", 0.95, 35, "Male", "California", 85_000.0, "Married", "Bachelors", "Employed", "Citizen", "Urban", 3, "Private"),
        ("PER_000003", 0.95, 41, "Female", "Nevada", 65_000.0, "Married", "Bachelors", "Employed", "Resident", "Suburban", 4, "Government"),
        ("PER_000004", 0.88, 52, "Female", "Texas", 70_000.0, "Divorced", "High School", "Self-employed", "Citizen", "Rural", 2, "Self-employed"),
        ("PER_000005", 0.80, 24, "Male", "Texas", 40_000.0, "Single", "Bachelors", "Unemployed", "Resident", "Urban", 1, "Contract"),
        ("PER_000006", 0.73, 33, "Female", "Florida", 52_000.0, "Single", "Bachelors", "Employed", "Citizen", "Suburban", 2, "Private"),
        ("PER_000007", 0.61, 47, "Male", "Florida", 110_000.0, "Married", "Masters", "Employed", "Citizen", "Suburban", 5, "Private"),
        ("PER_000008", 0.55, 39, "Female", "Ohio", 72_000.0, "Married", "Bachelors", "Employed", "Citizen", "Urban", 3, "Government"),
        ("PER_000009", 0.50, 58, "Male", "Ohio", 48_000.0, "Widowed", "High School", "Retired", "Citizen", "Rural", 2, "Retired"),
        ("PER_000010", 0.42, 30, "Female", "Nevada", 36_000.0, "Single", "High School", "Unemployed", "Resident", "Urban", 1, "Contract"),
    ]

    scores: list[tuple[str, float]] = []
    for (
        person_id,
        score,
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
        type_of_employment,
    ) in rows:
        _insert_demographic_person(
            database_path,
            person_id=person_id,
            age=age,
            gender=gender,
            state=state,
            income=income,
            marital_status=marital_status,
            education=education,
            employment_status=employment_status,
            resident_status=resident_status,
            resident_type=resident_type,
            family_member_count=family_member_count,
            type_of_employment=type_of_employment,
        )
        scores.append((person_id, score))

    scoring_run_id = _create_completed_scoring_run(
        database_path,
        model_run_id=model_run_id,
        analysis_run_id=analysis_run_id,
        scores=scores,
    )
    return scoring_run_id


def test_options_and_estimate_and_search_happy_path(database_path: Path) -> None:
    scoring_run_id = _seed_query_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    options = get_audience_filter_options(database_path, scoring_run_id=scoring_run_id)
    assert options["scoring_run_id"] == scoring_run_id
    assert options["population_count"] == 10
    assert "person_level_pii_exposed" in options["pii_policy"]
    assert options["score_summary"]["score_min"] == pytest.approx(0.42)
    assert options["score_summary"]["score_max"] == pytest.approx(0.98)

    estimate = estimate_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {
                "score_min": 0.8,
                "gender": ["Female"],
                "state": ["California", "Texas"],
            },
            "selection": {"mode": "TOP_N", "target_count": 5},
        },
    )
    assert estimate["matching_count"] == 2
    assert estimate["selected_count"] == 2
    assert len(estimate["filter_hash"]) == 64

    search_page_1 = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {
                "state": ["California", "Nevada"],
                "deciles": [1, 2, 3],
            },
            "page_size": 2,
        },
    )
    assert len(search_page_1["rows"]) == 2
    assert search_page_1["has_more"] is True
    assert search_page_1["next_cursor"] is not None

    # Highest score first; ties broken by person_id asc.
    assert search_page_1["rows"][0]["person_id"] == "PER_000001"
    assert search_page_1["rows"][1]["person_id"] == "PER_000002"

    search_page_2 = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {
                "state": ["California", "Nevada"],
                "deciles": [1, 2, 3],
            },
            "page_size": 2,
            "cursor": search_page_1["next_cursor"],
        },
    )
    assert len(search_page_2["rows"]) >= 1
    assert search_page_2["rows"][0]["person_id"] == "PER_000003"


def test_filter_normalizer_determinism_and_unknown_key_rejection() -> None:
    normalized_a = normalize_audience_filters(
        {
            "state": ["Texas", "California", "Texas"],
            "deciles": [2, 1, 2],
            "score_min": 0.4,
            "score_max": 0.9,
        }
    )
    normalized_b = normalize_audience_filters(
        {
            "score_max": 0.9,
            "score_min": 0.4,
            "deciles": [1, 2],
            "state": ["California", "Texas"],
        }
    )
    assert normalized_a.canonical_json == normalized_b.canonical_json
    assert normalized_a.filter_hash == normalized_b.filter_hash

    with pytest.raises(AudienceQueryValidationError, match="unknown keys"):
        normalize_audience_filters({"ethnicity": ["A"]})


def test_unprepared_rank_boundaries_rejected(database_path: Path) -> None:
    scoring_run_id = _seed_query_fixture(database_path)

    with pytest.raises(AudienceQueryConflictError, match=RANK_BOUNDARIES_NOT_READY_MESSAGE):
        get_audience_filter_options(database_path, scoring_run_id=scoring_run_id)


def test_cursor_tampering_or_mismatch_rejected(database_path: Path) -> None:
    scoring_run_id = _seed_query_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    first_page = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 3,
        },
    )
    cursor = str(first_page["next_cursor"])
    assert cursor

    # Filter mismatch should be rejected.
    with pytest.raises(AudienceQueryConflictError, match=CURSOR_MISMATCH_MESSAGE):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["Ohio"]},
                "page_size": 3,
                "cursor": cursor,
            },
        )

    # Corrupted cursor bytes should be rejected.
    with pytest.raises(AudienceQueryValidationError):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 3,
                "cursor": cursor[:-2] + "@@",
            },
        )

    # Scoring run mismatch encoded in cursor should be rejected.
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * ((4 - len(cursor) % 4) % 4)).decode("utf-8"))
    payload["scoring_run_id"] = scoring_run_id + 1
    forged = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    with pytest.raises(AudienceQueryConflictError, match=CURSOR_MISMATCH_MESSAGE):
        search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 3,
                "cursor": forged,
            },
        )


def test_search_query_constants_do_not_use_offset() -> None:
    assert "OFFSET" not in SEARCH_QUERY_INITIAL.upper()
    assert "OFFSET" not in SEARCH_QUERY_AFTER.upper()


def test_search_response_allowlist_fields_only(database_path: Path) -> None:
    scoring_run_id = _seed_query_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    response = search_audience(
        database_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 1,
        },
    )
    row = response["rows"][0]
    assert set(row) == {
        "person_id",
        "propensity_score",
        "age",
        "gender",
        "state",
        "individual_yearly_income",
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "family_member_count",
        "type_of_employment",
        "percentile_bucket",
        "decile",
        "rank_band",
    }
