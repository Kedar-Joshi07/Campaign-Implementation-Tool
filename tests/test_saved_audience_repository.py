from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.saved_audience_repository import (
    SELECTION_MODE_ALL_MATCHING,
    SELECTION_MODE_TOP_N,
    SavedAudienceNotFoundError,
    SavedAudienceRepository,
    SavedAudienceValidationError,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "saved-audience-repository.db"
    initialize_database(path)
    return path


def _insert_completed_analysis(database_path: Path) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
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
                "Saved audience fixture",
                "2026-09-01T00:00:00Z",
                "2026-09-01T00:00:03Z",
                "COMPLETED",
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}",
                100,
                20,
                5,
                15,
                0.25,
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
                status,
                random_seed,
                validation_fraction
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Saved audience model",
                "2026-09-01T00:00:05Z",
                "RUNNING",
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_job(database_path: Path, model_run_id: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
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
                request_json,
                result_json,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROSPECT_SCORING",
                "RUNNING",
                1,
                "VALIDATING_MODEL",
                None,
                model_run_id,
                "2026-09-01T00:00:10Z",
                "2026-09-01T00:00:10Z",
                "{}",
                None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_run(database_path: Path, job_id: int, model_run_id: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                model_run_id,
                "2026-09-01T00:00:11Z",
                "2026-09-01T00:00:20Z",
                "COMPLETED",
                100,
                "PER_001",
                "PER_100",
                100,
                1000,
                "BAGGING_PU",
                "2",
                "1",
                "a" * 64,
                "b" * 64,
                0.1,
                0.9,
                0.5,
                "{}",
                None,
            ),
        )
        return int(cursor.lastrowid)


def _insert_data_import_run(database_path: Path, dataset_name: str, checksum_char: str) -> int:
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
                dataset_name,
                f"{dataset_name}.csv.gz",
                "2026-09-01T00:00:00Z",
                "2026-09-01T00:00:01Z",
                "COMPLETED",
                1,
                1,
                0,
                checksum_char * 64,
            ),
        )
        return int(cursor.lastrowid)


def _create_repository_fixture(database_path: Path) -> tuple[int, int, int, int, int, int]:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id)
    scoring_run_id = _insert_scoring_run(database_path, job_id, model_run_id)
    customer_import_id = _insert_data_import_run(database_path, "customers", "c")
    campaign_import_id = _insert_data_import_run(database_path, "campaign_sales", "d")
    demographic_import_id = _insert_data_import_run(database_path, "demographics", "e")
    return (
        scoring_run_id,
        model_run_id,
        analysis_run_id,
        customer_import_id,
        campaign_import_id,
        demographic_import_id,
    )


def test_create_fetch_and_list_saved_audience(database_path: Path) -> None:
    (
        scoring_run_id,
        model_run_id,
        analysis_run_id,
        customer_import_id,
        campaign_import_id,
        demographic_import_id,
    ) = _create_repository_fixture(database_path)

    repository = SavedAudienceRepository(database_path)
    audience_id = repository.create_saved_audience(
        audience_name="  Top 100 Ohio Prospects  ",
        description="  Immutable audience snapshot  ",
        created_at="2026-09-01T01:00:00Z",
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        analysis_run_id=analysis_run_id,
        selection_mode=SELECTION_MODE_TOP_N,
        target_count=100,
        resolved_count=100,
        filter_contract_version="1",
        rank_contract_version="1",
        selection_contract_version="1",
        filters_payload={"states": ["Ohio"]},
        selection_payload={"sort": "score_desc", "take": 100},
        profile_summary_payload={"rows": 100},
        customer_import_id=customer_import_id,
        customer_source_checksum="c" * 64,
        campaign_sales_import_id=campaign_import_id,
        campaign_sales_source_checksum="d" * 64,
        demographic_import_id=demographic_import_id,
        demographic_source_checksum="e" * 64,
        feature_contract_version="1",
        feature_contract_sha256="f" * 64,
        artifact_sha256="a" * 64,
    )

    saved = repository.fetch_saved_audience(audience_id)
    assert saved["audience_id"] == audience_id
    assert saved["audience_name"] == "Top 100 Ohio Prospects"
    assert saved["description"] == "Immutable audience snapshot"
    assert saved["selection_mode"] == SELECTION_MODE_TOP_N
    assert saved["target_count"] == 100

    listed = repository.list_saved_audiences(limit=10, offset=0)
    assert len(listed) == 1
    assert listed[0]["audience_id"] == audience_id


def test_saved_audience_selection_mode_validation(database_path: Path) -> None:
    (
        scoring_run_id,
        model_run_id,
        analysis_run_id,
        customer_import_id,
        campaign_import_id,
        demographic_import_id,
    ) = _create_repository_fixture(database_path)
    repository = SavedAudienceRepository(database_path)

    with pytest.raises(SavedAudienceValidationError, match="target_count is required"):
        repository.create_saved_audience(
            audience_name="A",
            description=None,
            created_at="2026-09-01T01:05:00Z",
            scoring_run_id=scoring_run_id,
            model_run_id=model_run_id,
            analysis_run_id=analysis_run_id,
            selection_mode=SELECTION_MODE_TOP_N,
            target_count=None,
            resolved_count=1,
            filter_contract_version="1",
            rank_contract_version="1",
            selection_contract_version="1",
            filters_payload={"states": ["Ohio"]},
            selection_payload={"sort": "score_desc"},
            profile_summary_payload=None,
            customer_import_id=customer_import_id,
            customer_source_checksum="c" * 64,
            campaign_sales_import_id=campaign_import_id,
            campaign_sales_source_checksum="d" * 64,
            demographic_import_id=demographic_import_id,
            demographic_source_checksum="e" * 64,
            feature_contract_version="1",
            feature_contract_sha256="f" * 64,
            artifact_sha256="a" * 64,
        )

    with pytest.raises(SavedAudienceValidationError, match="must be null"):
        repository.create_saved_audience(
            audience_name="B",
            description=None,
            created_at="2026-09-01T01:06:00Z",
            scoring_run_id=scoring_run_id,
            model_run_id=model_run_id,
            analysis_run_id=analysis_run_id,
            selection_mode=SELECTION_MODE_ALL_MATCHING,
            target_count=10,
            resolved_count=10,
            filter_contract_version="1",
            rank_contract_version="1",
            selection_contract_version="1",
            filters_payload={"states": ["Ohio"]},
            selection_payload={"sort": "score_desc"},
            profile_summary_payload=None,
            customer_import_id=customer_import_id,
            customer_source_checksum="c" * 64,
            campaign_sales_import_id=campaign_import_id,
            campaign_sales_source_checksum="d" * 64,
            demographic_import_id=demographic_import_id,
            demographic_source_checksum="e" * 64,
            feature_contract_version="1",
            feature_contract_sha256="f" * 64,
            artifact_sha256="a" * 64,
        )


def test_fetch_missing_saved_audience_raises(database_path: Path) -> None:
    repository = SavedAudienceRepository(database_path)
    with pytest.raises(SavedAudienceNotFoundError):
        repository.fetch_saved_audience(999)
