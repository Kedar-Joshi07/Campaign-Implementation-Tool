from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.repositories.job_repository import JobRepository
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.repositories.scoring_repository import ScoringRepository
from app.schemas.phase10_intelligence import PHASE10_ORCHESTRATION_CONTRACT_VERSION
from app.services.phase10_context_identity_service import normalize_modeling_context
from app.services.phase10_historical_resolution_service import (
    resolve_or_create_phase10_historical_analysis,
)
from app.services.phase10_model_resolution_service import (
    resolve_or_train_phase10_model,
)
from app.services.phase10_scoring_resolution_service import (
    Phase10ScoringValidationError,
    build_phase10_intelligence_key,
    finalize_phase10_ready_context,
    resolve_or_build_phase10_scoring_rank,
    validate_phase10_scoring_candidate,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
def phase10_scoring_case(tmp_path: Path):
    database_path = tmp_path / "phase10-scoring-resolution.db"
    initialize_database(database_path)
    customers = [
        (
            f"C{index:03d}",
            f"19{70 + (index % 25):02d}-01-01",
            "Female" if index % 2 else "Male",
            "Ohio" if index % 3 else "Texas",
            40_000 + (index * 1_000),
            "Married",
            "College",
            "Employed",
            "Resident",
            "House",
            2 + (index % 3),
            "Salaried",
        )
        for index in range(1, 41)
    ]
    demographics = [
        (
            f"P{index:04d}",
            21 + (index % 60),
            "Female" if index % 2 else "Male",
            "Ohio" if index % 3 else "Texas",
            45_000 + (index * 100),
            "Married",
            "College",
            "Employed",
            "Resident",
            "House",
            2 + (index % 3),
            index % 2,
            1 + (index % 3),
            "Salaried",
            70_000 + (index * 100),
        )
        for index in range(1, 121)
    ]
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, gender, state,
                individual_yearly_income, marital_status, education,
                employment_status, resident_status, resident_type,
                family_member_count, type_of_employment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ?, ?, 'CMP1', 'P1', 'Campaign', 'Retention', 'Retention',
                'Email', 'Loyalty', 'Product', 'Category',
                '2025-01-01', '2025-12-31', ?, 1, 0, 0, ?, ?, ?
            )
            """,
            [
                (
                    f"S{index:03d}",
                    f"C{index:03d}",
                    f"2025-01-{1 + ((index - 1) % 28):02d}",
                    1 if index <= 20 else 0,
                    1 if index <= 20 else 0,
                    1 if index <= 20 else 0,
                )
                for index in range(1, 41)
            ],
        )
        connection.executemany(
            """
            INSERT INTO demographics (
                person_id, age, gender, state, individual_yearly_income,
                marital_status, education, employment_status, resident_status,
                resident_type, family_member_count,
                number_of_children_in_family, number_of_adults_in_family,
                type_of_employment, family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            demographics,
        )
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, '2026-09-14T00:00:00Z',
                      '2026-09-14T00:00:01Z', 'COMPLETED', ?, ?, 0, ?)
            """,
            (
                ("customers", "data/customers.csv", 40, 40, "c" * 64),
                (
                    "campaign_sales",
                    "data/campaign_sales.csv",
                    40,
                    40,
                    "d" * 64,
                ),
                (
                    "demographics",
                    "data/demographics.csv.gz",
                    120,
                    120,
                    "e" * 64,
                ),
            ),
        )
    context = normalize_modeling_context({"product_ids": ["P1"]})
    historical = resolve_or_create_phase10_historical_analysis(database_path, context)
    model = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=tmp_path,
    )
    assert historical.status == "READY" and model.status == "READY"
    return database_path, tmp_path, context, historical, model


def _score(phase10_scoring_case):
    database_path, project_root, context, historical, model = phase10_scoring_case
    scoring = resolve_or_build_phase10_scoring_rank(
        database_path,
        model,
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    return database_path, project_root, context, historical, model, scoring


def test_fresh_scoring_and_rank_then_full_reuse_without_pool_submission(
    phase10_scoring_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.jobs.executor.submit_prospect_scoring_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("the shared worker pool must not be used")
        ),
    )
    database_path, project_root, _, _, model, first = _score(
        phase10_scoring_case
    )
    assert first.status == "READY"
    assert first.scoring_built is True and first.scoring_reused is False
    assert first.rank_rebuilt is True and first.rank_reused is False
    assert first.readiness is not None and first.readiness.ready is True
    assert first.readiness.boundary_count == 100
    assert first.scoring_job_id is not None

    with get_connection(database_path) as connection:
        job = connection.execute(
            "SELECT status FROM jobs WHERE job_id = ?", (first.scoring_job_id,)
        ).fetchone()
        counts = connection.execute(
            """
            SELECT COUNT(*) AS score_count, COUNT(DISTINCT person_id) AS people
            FROM propensity_scores WHERE scoring_run_id = ?
            """,
            (first.scoring_run_id,),
        ).fetchone()
    assert job["status"] == "COMPLETED"
    assert tuple(counts) == (120, 120)

    second = resolve_or_build_phase10_scoring_rank(
        database_path,
        model,
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert second.scoring_run_id == first.scoring_run_id
    assert second.scoring_reused is True and second.scoring_built is False
    assert second.rank_reused is True and second.rank_rebuilt is False
    assert second.scoring_job_id is None


def test_scoring_reuse_gate_rejects_corrupt_or_incompatible_candidates(
    phase10_scoring_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root, _, _, model, scoring = _score(
        phase10_scoring_case
    )
    scoring_run_id = scoring.scoring_run_id
    assert scoring_run_id is not None
    validate_phase10_scoring_candidate(
        database_path,
        scoring_run_id,
        model,
        project_root=project_root,
    )

    with get_connection(database_path, write=True) as connection:
        removed = connection.execute(
            """
            SELECT model_run_id, person_id, propensity_score
            FROM propensity_scores WHERE scoring_run_id = ? LIMIT 1
            """,
            (scoring_run_id,),
        ).fetchone()
        connection.execute(
            "DELETE FROM propensity_scores WHERE scoring_run_id = ? AND person_id = ?",
            (scoring_run_id, removed["person_id"]),
        )
    with pytest.raises(Phase10ScoringValidationError) as captured:
        validate_phase10_scoring_candidate(
            database_path,
            scoring_run_id,
            model,
            project_root=project_root,
        )
    assert "INCOMPLETE_FULL_UNIVERSE" in captured.value.reason_codes
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO propensity_scores (
                scoring_run_id, model_run_id, person_id, propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            (
                scoring_run_id,
                removed["model_run_id"],
                removed["person_id"],
                removed["propensity_score"],
            ),
        )

    original_integrity = ScoringRepository.fetch_phase10_score_integrity
    for field, reason in (
        ("duplicate_person_count", "DUPLICATE_PERSON_SCORES"),
        ("invalid_score_count", "INVALID_SCORE_VALUES"),
    ):
        def altered_integrity(self, run_id, *, changed_field=field):
            payload = original_integrity(self, run_id)
            payload[changed_field] = 1
            return payload

        with monkeypatch.context() as scoped:
            scoped.setattr(
                ScoringRepository,
                "fetch_phase10_score_integrity",
                altered_integrity,
            )
            with pytest.raises(Phase10ScoringValidationError) as captured:
                validate_phase10_scoring_candidate(
                    database_path,
                    scoring_run_id,
                    model,
                    project_root=project_root,
                )
        assert reason in captured.value.reason_codes

    row = ScoringRepository(database_path).fetch_scoring_run(scoring_run_id)
    assert row is not None
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE scoring_runs SET artifact_sha256 = ? WHERE scoring_run_id = ?",
            ("f" * 64, scoring_run_id),
        )
    with pytest.raises(Phase10ScoringValidationError) as captured:
        validate_phase10_scoring_candidate(
            database_path,
            scoring_run_id,
            model,
            project_root=project_root,
        )
    assert "ARTIFACT_MISMATCH" in captured.value.reason_codes
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE scoring_runs
            SET artifact_sha256 = ?, score_summary_json = ?
            WHERE scoring_run_id = ?
            """,
            (row["artifact_sha256"], row["score_summary_json"], scoring_run_id),
        )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE scoring_runs SET status = 'FAILED', error_message = 'synthetic'
            WHERE scoring_run_id = ?
            """,
            (scoring_run_id,),
        )
    with pytest.raises(Phase10ScoringValidationError) as captured:
        validate_phase10_scoring_candidate(
            database_path,
            scoring_run_id,
            model,
            project_root=project_root,
        )
    assert "STATUS_NOT_COMPLETED" in captured.value.reason_codes
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE scoring_runs SET status = 'COMPLETED', error_message = NULL
            WHERE scoring_run_id = ?
            """,
            (scoring_run_id,),
        )

    summary = json.loads(row["score_summary_json"])
    summary["score_semantics"] = "OTHER"
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE scoring_runs SET score_summary_json = ? WHERE scoring_run_id = ?",
            (json.dumps(summary), scoring_run_id),
        )
    with pytest.raises(Phase10ScoringValidationError) as captured:
        validate_phase10_scoring_candidate(
            database_path,
            scoring_run_id,
            model,
            project_root=project_root,
        )
    assert "SCORE_SEMANTICS_MISMATCH" in captured.value.reason_codes


def test_demographic_drift_reuses_analysis_and_model_but_rescores_full_universe(
    phase10_scoring_case,
) -> None:
    database_path, project_root, context, historical, model, first = _score(
        phase10_scoring_case
    )
    with get_connection(database_path) as connection:
        model_count = connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0]
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id, age, gender, state, individual_yearly_income,
                marital_status, education, employment_status, resident_status,
                resident_type, family_member_count,
                number_of_children_in_family, number_of_adults_in_family,
                type_of_employment, family_yearly_income
            ) VALUES (
                'P0121', 42, 'Female', 'Ohio', 75000, 'Married', 'College',
                'Employed', 'Resident', 'House', 3, 1, 2, 'Salaried', 95000
            )
            """
        )
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (
                'demographics', 'data/demographics-v2.csv.gz',
                '2026-09-14T01:00:00Z', '2026-09-14T01:00:01Z',
                'COMPLETED', 121, 121, 0, ?
            )
            """,
            ("9" * 64,),
        )

    current_model = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    assert current_model.analysis_run_id == model.analysis_run_id
    assert current_model.model_run_id == model.model_run_id
    assert current_model.reused is True and current_model.trained is False
    second = resolve_or_build_phase10_scoring_rank(
        database_path,
        current_model,
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert second.scoring_run_id != first.scoring_run_id
    assert second.scoring_built is True and second.rank_rebuilt is True
    assert "DEMOGRAPHIC_PROVENANCE_MISMATCH" in (
        second.rejected_candidates[0].reason_codes
    )
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == model_count
        score_count = connection.execute(
            "SELECT COUNT(*) FROM propensity_scores WHERE scoring_run_id = ?",
            (second.scoring_run_id,),
        ).fetchone()[0]
    assert score_count == 121


def test_missing_or_stale_rank_and_analytics_take_rank_only_path(
    phase10_scoring_case,
) -> None:
    database_path, project_root, _, _, model, first = _score(
        phase10_scoring_case
    )
    scoring_run_id = first.scoring_run_id
    with get_connection(database_path) as connection:
        original_counts = tuple(
            connection.execute(
                "SELECT (SELECT COUNT(*) FROM model_runs), (SELECT COUNT(*) FROM scoring_runs), (SELECT COUNT(*) FROM jobs)"
            ).fetchone()
        )

    mutations = (
        "DELETE FROM audience_rank_boundaries WHERE scoring_run_id = ? AND percentile_bucket = 50",
        "DELETE FROM audience_analytics_snapshots WHERE scoring_run_id = ?",
        "UPDATE audience_rank_boundaries SET rank_contract_version = 'wrong' WHERE scoring_run_id = ?",
    )
    for statement in mutations:
        with get_connection(database_path, write=True) as connection:
            connection.execute(statement, (scoring_run_id,))
        resolved = resolve_or_build_phase10_scoring_rank(
            database_path,
            model,
            project_root=project_root,
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        )
        assert resolved.scoring_run_id == scoring_run_id
        assert resolved.scoring_reused is True and resolved.scoring_built is False
        assert resolved.rank_rebuilt is True and resolved.scoring_job_id is None
        assert resolved.readiness is not None and resolved.readiness.ready is True
        with get_connection(database_path) as connection:
            current_counts = tuple(
                connection.execute(
                    "SELECT (SELECT COUNT(*) FROM model_runs), (SELECT COUNT(*) FROM scoring_runs), (SELECT COUNT(*) FROM jobs)"
                ).fetchone()
            )
        assert current_counts == original_counts


def test_ready_generation_reuse_and_existing_phase9_binding_are_exact(
    phase10_scoring_case,
) -> None:
    database_path, project_root, context, historical, model, first = _score(
        phase10_scoring_case
    )
    assert first.scoring_run_id is not None
    job_id = JobRepository(database_path).create_scoring_job(
        created_at="2026-09-14T02:00:00Z",
        request_payload={"model_run_id": model.model_run_id},
        message="Replacement scoring queued.",
    )
    from app.jobs.prospect_scoring_worker import run_prospect_scoring_job

    run_prospect_scoring_job(
        database_path,
        job_id,
        project_root=project_root,
        chunk_size=1_000,
    )
    scoring = resolve_or_build_phase10_scoring_rank(
        database_path,
        model,
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert scoring.scoring_run_id != first.scoring_run_id
    assert scoring.scoring_compatibility is not None

    context_json = "{}"
    context_id = CampaignTargetingContextRepository(database_path).create_context(
        campaign_context_contract_version="1",
        targeting_segment_contract_version="1",
        business_match_strength_contract_version="1",
        campaign_context_json=context_json,
        campaign_context_sha256=_sha256(context_json),
        targeting_criteria_json=context_json,
        targeting_criteria_sha256=_sha256(context_json),
        timestamp="2026-09-14T02:01:00Z",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE campaign_targeting_contexts SET source_scoring_run_id = ?
            WHERE targeting_context_id = ?
            """,
            (first.scoring_run_id, context_id),
        )

    intelligence_key = build_phase10_intelligence_key(
        scoring.scoring_compatibility
    )
    repository = Phase10IntelligenceRepository(database_path)
    orchestration, created = repository.create_or_get_active_orchestration(
        orchestration_contract_version=PHASE10_ORCHESTRATION_CONTRACT_VERSION,
        targeting_context_id=context_id,
        modeling_context_sha256=context.modeling_context_sha256,
        intelligence_key_sha256=intelligence_key,
        business_message="Preparing targeting intelligence.",
        reuse_plan={"scoring": "REUSE", "rank": "REUSE"},
        created_at="2026-09-14T02:02:00Z",
    )
    assert created is True
    repository.mark_orchestration_running(
        orchestration["orchestration_id"],
        stage="FINALIZING",
        progress_percent=95,
        business_message="Finalizing targeting intelligence.",
        started_at="2026-09-14T02:02:01Z",
    )
    generation_id, reused = finalize_phase10_ready_context(
        database_path,
        targeting_context_id=context_id,
        orchestration_id=orchestration["orchestration_id"],
        modeling_context=context,
        historical_resolution=historical,
        model_resolution=model,
        scoring_resolution=scoring,
    )
    assert reused is False
    generation = repository.verify_generation_record(generation_id)
    assert generation["intelligence_key_sha256"] == intelligence_key
    assert generation["scoring_run_id"] == scoring.scoring_run_id
    assert repository.fetch_orchestration(orchestration["orchestration_id"])[
        "status"
    ] == "READY"
    binding = repository.fetch_context_binding(context_id)
    assert binding["binding_status"] == "READY"
    with get_connection(database_path) as connection:
        phase9_source = connection.execute(
            """
            SELECT source_scoring_run_id FROM campaign_targeting_contexts
            WHERE targeting_context_id = ?
            """,
            (context_id,),
        ).fetchone()[0]
    assert phase9_source == scoring.scoring_run_id

    repeated_id, repeated_reuse = finalize_phase10_ready_context(
        database_path,
        targeting_context_id=context_id,
        orchestration_id=orchestration["orchestration_id"],
        modeling_context=context,
        historical_resolution=historical,
        model_resolution=model,
        scoring_resolution=scoring,
    )
    assert repeated_id == generation_id and repeated_reuse is True
    repository.update_generation_lifecycle(
        generation_id,
        lifecycle_state="PROTECTED",
        verified_at="2026-09-14T02:03:00Z",
    )
    protected_id, protected_reuse = finalize_phase10_ready_context(
        database_path,
        targeting_context_id=context_id,
        orchestration_id=orchestration["orchestration_id"],
        modeling_context=context,
        historical_resolution=historical,
        model_resolution=model,
        scoring_resolution=scoring,
    )
    assert protected_id == generation_id and protected_reuse is True
    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM phase10_intelligence_generations"
        ).fetchone()[0] == 1
