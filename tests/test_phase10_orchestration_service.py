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
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.schemas.phase10_intelligence import PHASE10_INSUFFICIENT_HISTORY_MESSAGE
from app.services.phase10_orchestration_service import (
    BUSINESS_LABELS,
    SAFE_FAILURE_MESSAGE,
    prepare_phase10_orchestration,
    reconcile_phase10_orchestrations,
    run_phase10_orchestration,
)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_context(
    database_path: Path,
    *,
    product_id: str = "P1",
    delivery_channel: str = "EMAIL",
) -> int:
    campaign_json = _canonical(
        {
            "campaign_targeting_context_contract_version": "1",
            "product_ids": [product_id],
            "campaign_types": ["Retention"],
            "campaign_categories": ["Retention"],
            "offer_types": ["Loyalty"],
            "historical_campaign_channels": ["Email"],
            "campaign_channel": delivery_channel,
        }
    )
    targeting_json = "{}"
    return CampaignTargetingContextRepository(database_path).create_context(
        campaign_context_contract_version="1",
        targeting_segment_contract_version="1",
        business_match_strength_contract_version="1",
        campaign_context_json=campaign_json,
        campaign_context_sha256=_digest(campaign_json),
        targeting_criteria_json=targeting_json,
        targeting_criteria_sha256=_digest(targeting_json),
        timestamp="2026-09-14T00:01:00Z",
    )


def _seed_orchestration_database(tmp_path: Path) -> tuple[Path, Path]:
    database_path = tmp_path / "phase10-orchestration.db"
    initialize_database(database_path)
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
            [
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
            ],
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
            [
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
                for index in range(1, 61)
            ],
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
                    60,
                    60,
                    "e" * 64,
                ),
            ),
        )
    return database_path, tmp_path


@pytest.fixture
def orchestration_database(tmp_path: Path) -> tuple[Path, Path]:
    return _seed_orchestration_database(tmp_path)


def test_durable_build_active_dedup_sharing_reuse_and_verified_resume(
    orchestration_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root = orchestration_database
    repository = Phase10IntelligenceRepository(database_path)
    email_context = _create_context(database_path, delivery_channel="EMAIL")
    sms_context = _create_context(database_path, delivery_channel="SMS")

    for submission_name in (
        "submit_model_training_job",
        "submit_prospect_scoring_job",
        "submit_audience_preparation_job",
    ):
        monkeypatch.setattr(
            f"app.jobs.executor.{submission_name}",
            lambda *_args, name=submission_name, **_kwargs: (_ for _ in ()).throw(
                AssertionError(f"nested executor submission is forbidden: {name}")
            ),
        )

    queued = prepare_phase10_orchestration(
        database_path,
        email_context,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    assert queued.created is True and queued.submitted is True
    assert queued.orchestration["status"] == "QUEUED"
    assert json.loads(queued.orchestration["reuse_plan_json"]) == {
        "analysis": "BUILD",
        "model": "BUILD",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    joined = prepare_phase10_orchestration(
        database_path,
        sms_context,
        project_root=project_root,
        submitter=lambda *_args: (_ for _ in ()).throw(
            AssertionError("an exact active orchestration must not be resubmitted")
        ),
    )
    assert joined.orchestration["orchestration_id"] == queued.orchestration[
        "orchestration_id"
    ]
    assert joined.created is False and joined.submitted is False

    recorded: list[tuple[str, int, str]] = []
    original_start = Phase10IntelligenceRepository.mark_orchestration_running
    original_update = Phase10IntelligenceRepository.update_orchestration_stage

    def recording_start(self, orchestration_id, **kwargs):
        recorded.append(
            (kwargs["stage"], kwargs["progress_percent"], kwargs["business_message"])
        )
        return original_start(self, orchestration_id, **kwargs)

    def recording_update(self, orchestration_id, **kwargs):
        recorded.append(
            (kwargs["stage"], kwargs["progress_percent"], kwargs["business_message"])
        )
        return original_update(self, orchestration_id, **kwargs)

    monkeypatch.setattr(
        Phase10IntelligenceRepository,
        "mark_orchestration_running",
        recording_start,
    )
    monkeypatch.setattr(
        Phase10IntelligenceRepository,
        "update_orchestration_stage",
        recording_update,
    )
    first_ready = run_phase10_orchestration(
        database_path,
        queued.orchestration["orchestration_id"],
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert first_ready["status"] == "READY"
    assert first_ready["stage"] == "READY" and first_ready["progress_percent"] == 100
    assert first_ready["business_message"] == BUSINESS_LABELS["READY"]
    assert json.loads(first_ready["reuse_plan_json"]) == {
        "analysis": "BUILD",
        "model": "BUILD",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    progress = [item[1] for item in recorded]
    assert progress == sorted(progress)
    stages = [item[0] for item in recorded]
    for expected in (
        "CHECKING_COMPATIBILITY",
        "RESOLVING_HISTORICAL_CONTEXT",
        "CHECKING_TRAINING_ELIGIBILITY",
        "RESOLVING_MODEL",
        "VALIDATING_MODEL",
        "RESOLVING_SCORING",
        "SCORING_POTENTIAL_CUSTOMERS",
        "PREPARING_TARGET_GROUP",
        "VERIFYING_FINAL_CURRENTNESS",
    ):
        assert expected in stages
    assert all(message == BUSINESS_LABELS[stage] for stage, _, message in recorded)
    assert all(
        50 <= value <= 89
        for stage, value, _ in recorded
        if stage == "SCORING_POTENTIAL_CUSTOMERS"
    )

    for context_id in (email_context, sms_context):
        binding = repository.fetch_context_binding(context_id)
        assert binding["binding_status"] == "READY"
        assert binding["generation_id"] == first_ready["generation_id"]
        with get_connection(database_path) as connection:
            source = connection.execute(
                """
                SELECT source_scoring_run_id FROM campaign_targeting_contexts
                WHERE targeting_context_id = ?
                """,
                (context_id,),
            ).fetchone()[0]
        assert source == first_ready["scoring_run_id"]

    repeated = prepare_phase10_orchestration(
        database_path,
        email_context,
        project_root=project_root,
        submitter=lambda *_args: (_ for _ in ()).throw(
            AssertionError("READY preparation must not be submitted")
        ),
    )
    assert repeated.already_ready is True
    assert repeated.orchestration["orchestration_id"] == first_ready["orchestration_id"]

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "DELETE FROM audience_analytics_snapshots WHERE scoring_run_id = ?",
            (first_ready["scoring_run_id"],),
        )
    repaired = prepare_phase10_orchestration(
        database_path,
        email_context,
        project_root=project_root,
        submitter=lambda db, oid, root: run_phase10_orchestration(
            db,
            oid,
            project_root=root,
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        ),
    )
    assert repaired.created is True
    assert repaired.orchestration["status"] == "READY"
    assert repaired.orchestration["generation_id"] == first_ready["generation_id"]
    assert repaired.orchestration["scoring_run_id"] == first_ready["scoring_run_id"]
    assert json.loads(repaired.orchestration["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "REUSE",
        "rank": "BUILD",
        "scoring": "REUSE",
    }

    with get_connection(database_path) as connection:
        initial_model_count = connection.execute(
            "SELECT COUNT(*) FROM model_runs"
        ).fetchone()[0]
        initial_scoring_count = connection.execute(
            "SELECT COUNT(*) FROM scoring_runs"
        ).fetchone()[0]

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
                'P0061', 41, 'Female', 'Ohio', 72000, 'Married', 'College',
                'Employed', 'Resident', 'House', 3, 1, 2, 'Salaried', 94000
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
                'COMPLETED', 61, 61, 0, ?
            )
            """,
            ("9" * 64,),
        )
    drift_context = _create_context(database_path, delivery_channel="PUSH")
    drift = prepare_phase10_orchestration(
        database_path,
        drift_context,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    assert json.loads(drift.orchestration["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "REUSE",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    repository.mark_orchestration_running(
        drift.orchestration["orchestration_id"],
        stage="CHECKING_COMPATIBILITY",
        progress_percent=2,
        business_message=BUSINESS_LABELS["CHECKING_COMPATIBILITY"],
        started_at="2026-09-14T01:01:00Z",
    )
    repository.update_orchestration_stage(
        drift.orchestration["orchestration_id"],
        stage="VALIDATING_MODEL",
        progress_percent=47,
        business_message=BUSINESS_LABELS["VALIDATING_MODEL"],
        updated_at="2026-09-14T01:01:01Z",
        analysis_run_id=first_ready["analysis_run_id"],
        model_run_id=first_ready["model_run_id"],
    )
    resumed = run_phase10_orchestration(
        database_path,
        drift.orchestration["orchestration_id"],
        project_root=project_root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert resumed["status"] == "READY"
    assert resumed["analysis_run_id"] == first_ready["analysis_run_id"]
    assert resumed["model_run_id"] == first_ready["model_run_id"]
    assert resumed["scoring_run_id"] != first_ready["scoring_run_id"]
    assert json.loads(resumed["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "REUSE",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == (
            initial_model_count
        )
        assert connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0] == (
            initial_scoring_count + 1
        )

    reusable_context = _create_context(database_path, delivery_channel="PHONE")
    generation_reuse = prepare_phase10_orchestration(
        database_path,
        reusable_context,
        project_root=project_root,
        submitter=lambda db, oid, root: run_phase10_orchestration(
            db,
            oid,
            project_root=root,
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        ),
    )
    assert generation_reuse.orchestration["status"] == "READY"
    assert generation_reuse.orchestration["generation_id"] == resumed["generation_id"]
    assert json.loads(generation_reuse.orchestration["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "REUSE",
        "rank": "REUSE",
        "scoring": "REUSE",
    }
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0] == (
            initial_scoring_count + 1
        )


def test_insufficient_history_is_blocked_not_failed(
    orchestration_database,
) -> None:
    database_path, project_root = orchestration_database
    context_id = _create_context(database_path, product_id="NO-HISTORY")
    started = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda db, oid, root: run_phase10_orchestration(
            db,
            oid,
            project_root=root,
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        ),
    )
    assert started.orchestration["status"] == "BLOCKED"
    assert started.orchestration["business_message"] == (
        PHASE10_INSUFFICIENT_HISTORY_MESSAGE
    )
    assert started.orchestration["safe_error_message"] is None
    assert started.orchestration["generation_id"] is None
    binding = Phase10IntelligenceRepository(database_path).fetch_context_binding(
        context_id
    )
    assert binding["binding_status"] == "BLOCKED"
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM phase10_intelligence_generations"
        ).fetchone()[0] == 0


def test_model_and_scoring_failures_retry_from_highest_verified_stage(
    orchestration_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root = orchestration_database
    context_id = _create_context(database_path)

    model_attempt = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(
            "app.services.phase10_orchestration_service.resolve_or_train_phase10_model",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("synthetic model failure")
            ),
        )
        model_failed = run_phase10_orchestration(
            database_path,
            int(model_attempt.orchestration["orchestration_id"]),
            project_root=project_root,
        )
    assert model_failed["status"] == "FAILED"
    assert model_failed["technical_message"] == "RuntimeError"
    assert model_failed["generation_id"] is None

    scoring_attempt = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    assert json.loads(scoring_attempt.orchestration["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "BUILD",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    with monkeypatch.context() as scoped:
        scoped.setattr(
            "app.services.phase10_orchestration_service.resolve_or_build_phase10_scoring_rank",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("synthetic scoring failure")
            ),
        )
        scoring_failed = run_phase10_orchestration(
            database_path,
            int(scoring_attempt.orchestration["orchestration_id"]),
            project_root=project_root,
        )
    assert scoring_failed["status"] == "FAILED"
    assert scoring_failed["technical_message"] == "RuntimeError"
    assert scoring_failed["model_run_id"] is not None
    assert scoring_failed["scoring_run_id"] is None
    assert scoring_failed["generation_id"] is None

    retried = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda db, oid, root: run_phase10_orchestration(
            db,
            oid,
            project_root=root,
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        ),
    )
    assert retried.orchestration["status"] == "READY"
    assert json.loads(retried.orchestration["reuse_plan_json"]) == {
        "analysis": "REUSE",
        "model": "REUSE",
        "rank": "BUILD",
        "scoring": "BUILD",
    }
    assert retried.orchestration["model_run_id"] == scoring_failed["model_run_id"]
    assert retried.orchestration["scoring_run_id"] is not None


def test_startup_reconciliation_and_changed_identity_fail_safely(
    orchestration_database,
) -> None:
    database_path, project_root = orchestration_database
    context_id = _create_context(database_path)
    started = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    submissions: list[int] = []
    reconciled = reconcile_phase10_orchestrations(
        database_path,
        project_root=project_root,
        submitter=lambda _db, oid, _root: submissions.append(oid),
    )
    assert reconciled == 1
    assert submissions == [started.orchestration["orchestration_id"]]

    changed_json = _canonical(
        {
            "product_ids": ["OTHER"],
            "campaign_types": ["Retention"],
            "campaign_categories": ["Retention"],
            "offer_types": ["Loyalty"],
            "historical_campaign_channels": ["Email"],
            "campaign_channel": "EMAIL",
        }
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE campaign_targeting_contexts
            SET campaign_context_json = ?, campaign_context_sha256 = ?
            WHERE targeting_context_id = ?
            """,
            (changed_json, _digest(changed_json), context_id),
        )
    failed = run_phase10_orchestration(
        database_path,
        started.orchestration["orchestration_id"],
        project_root=project_root,
    )
    assert failed["status"] == "FAILED"
    assert failed["business_message"] == SAFE_FAILURE_MESSAGE
    assert failed["safe_error_message"] == SAFE_FAILURE_MESSAGE
    assert failed["technical_message"] == "Phase10OrchestrationError"
    assert failed["generation_id"] is None
    binding = Phase10IntelligenceRepository(database_path).fetch_context_binding(
        context_id
    )
    assert binding["binding_status"] == "FAILED"
    assert binding["generation_id"] is None
