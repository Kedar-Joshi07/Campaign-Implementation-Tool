from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CREATE_TABLE_STATEMENTS,
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    PHASE10_CONTEXT_BINDING_COLUMNS,
    PHASE10_INTELLIGENCE_GENERATION_COLUMNS,
    PHASE10_ORCHESTRATION_RUN_COLUMNS,
    PHASE_TEN_REQUIRED_INDEX_STATEMENTS,
    initialize_database,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
    Phase10RepositoryStateError,
    Phase10RepositoryValidationError,
)


NOW = "2026-09-13T10:00:00Z"


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row["name"] for row in connection.execute(f"PRAGMA table_info({table})"))


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _create_version_fourteen_database(path: Path) -> None:
    with get_connection(path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (
                ("schema_version", "1", NOW),
                ("application_version", "0.1.0", NOW),
                ("database_initialized_at", NOW, NOW),
                ("phase10_migration_sentinel", "preserve-me", NOW),
            ),
        )
        for version in range(2, 15):
            MIGRATIONS[version](connection)
            connection.execute(
                "UPDATE app_metadata SET value = ? WHERE key = 'schema_version'",
                (str(version),),
            )
        connection.execute(
            """
            INSERT INTO campaign_targeting_contexts (
                campaign_targeting_context_contract_version,
                targeting_segment_contract_version,
                business_match_strength_contract_version,
                campaign_context_json, campaign_context_sha256,
                targeting_criteria_json, targeting_criteria_sha256,
                created_at, updated_at
            ) VALUES ('1', '1', '1', '{}', ?, '{}', ?, ?, ?)
            """,
            ("a" * 64, "b" * 64, NOW, NOW),
        )


def _seed_lineage(path: Path) -> dict[str, int]:
    initialize_database(path)
    with get_connection(path, write=True) as connection:
        import_ids: list[int] = []
        for index, dataset in enumerate(("customers", "campaign_sales", "demographics"), 1):
            cursor = connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name, source_path, started_at, completed_at, status,
                    rows_read, rows_inserted, rows_rejected, source_checksum
                ) VALUES (?, ?, ?, ?, 'COMPLETED', 1, 1, 0, ?)
                """,
                (dataset, f"data/{dataset}.csv", NOW, NOW, f"{index}" * 64),
            )
            import_ids.append(int(cursor.lastrowid))
        analysis_id = int(
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
                ) VALUES ('Phase 10', ?, ?, 'COMPLETED',
                          'ATTRIBUTED_PURCHASE', '{}', '{}', ?, ?, ?, ?,
                          2, 2, 1, 1, 0.5)
                """,
                (
                    NOW,
                    NOW,
                    import_ids[0],
                    "1" * 64,
                    import_ids[1],
                    "2" * 64,
                ),
            ).lastrowid
        )
        model_id = int(
            connection.execute(
                """
                INSERT INTO model_runs (
                    analysis_run_id, model_name, created_at, completed_at,
                    status, algorithm, selected_candidate,
                    random_seed, validation_fraction, artifact_path, artifact_sha256
                ) VALUES (?, 'Phase 10 model', ?, ?, 'COMPLETED',
                          'BAGGING_PU', 'BAGGING_PU', 42, 0.2,
                          'artifacts/model.joblib', ?)
                """,
                (analysis_id, NOW, NOW, "7" * 64),
            ).lastrowid
        )
        job_id = int(
            connection.execute(
                """
                INSERT INTO jobs (
                    job_type, status, progress_percent, stage, model_run_id,
                    created_at, started_at, finished_at, request_json, result_json
                ) VALUES ('PROSPECT_SCORING', 'COMPLETED', 100, 'COMPLETED', ?,
                          ?, ?, ?, '{}', '{}')
                """,
                (model_id, NOW, NOW, NOW),
            ).lastrowid
        )
        scoring_id = int(
            connection.execute(
                """
                INSERT INTO scoring_runs (
                    job_id, model_run_id, created_at, completed_at, status,
                    demographic_snapshot_count, demographic_min_person_id,
                    demographic_max_person_id, scored_person_count, chunk_size,
                    selected_candidate, model_role_policy_version,
                    feature_contract_version, feature_contract_sha256,
                    artifact_sha256, score_min, score_max, score_mean,
                    score_summary_json
                ) VALUES (?, ?, ?, ?, 'COMPLETED', 1, 'P1', 'P1', 1, 1000,
                          'BAGGING_PU', '2', '1', ?, ?, 0.5, 0.5, 0.5, '{}')
                """,
                (job_id, model_id, NOW, NOW, "6" * 64, "7" * 64),
            ).lastrowid
        )
        context_ids: list[int] = []
        for suffix in ("a", "c"):
            context_ids.append(
                int(
                    connection.execute(
                        """
                        INSERT INTO campaign_targeting_contexts (
                            campaign_targeting_context_contract_version,
                            targeting_segment_contract_version,
                            business_match_strength_contract_version,
                            campaign_context_json, campaign_context_sha256,
                            targeting_criteria_json, targeting_criteria_sha256,
                            created_at, updated_at
                        ) VALUES ('1', '1', '1', '{}', ?, '{}', ?, ?, ?)
                        """,
                        (suffix * 64, "b" * 64, NOW, NOW),
                    ).lastrowid
                )
            )
    return {
        "customer_import_id": import_ids[0],
        "campaign_sales_import_id": import_ids[1],
        "demographic_import_id": import_ids[2],
        "analysis_run_id": analysis_id,
        "model_run_id": model_id,
        "job_id": job_id,
        "scoring_run_id": scoring_id,
        "targeting_context_id": context_ids[0],
        "second_targeting_context_id": context_ids[1],
    }


def _generation_values(ids: dict[str, int]) -> dict[str, object]:
    modeling_json = _canonical({"product_ids": ["P1"]})
    filters_json = _canonical(
        {"product_ids": ["P1"], "contact_date_from": "2025-01-01", "contact_date_to": "2025-12-31"}
    )
    score_json = _canonical({"minimum_score": 0.0, "maximum_score": 1.0})
    return {
        "intelligence_generation_contract_version": "1",
        "compatibility_contract_version": "1",
        "intelligence_key_sha256": "8" * 64,
        "modeling_context_json": modeling_json,
        "modeling_context_sha256": _digest(modeling_json),
        "historical_filters_json": filters_json,
        "historical_filters_sha256": _digest(filters_json),
        "historical_window_policy_version": "1",
        "multi_product_positive_policy_version": "1",
        "training_eligibility_policy_version": "1",
        "customer_import_id": ids["customer_import_id"],
        "customer_source_checksum": "1" * 64,
        "campaign_sales_import_id": ids["campaign_sales_import_id"],
        "campaign_sales_source_checksum": "2" * 64,
        "demographic_import_id": ids["demographic_import_id"],
        "demographic_source_checksum": "3" * 64,
        "feature_contract_version": "1",
        "feature_contract_sha256": "6" * 64,
        "model_role_policy_version": "2",
        "evaluation_contract_version": "2",
        "automated_training_policy_version": "1",
        "analysis_run_id": ids["analysis_run_id"],
        "model_run_id": ids["model_run_id"],
        "scoring_run_id": ids["scoring_run_id"],
        "artifact_sha256": "7" * 64,
        "score_semantics_json": score_json,
        "score_semantics_sha256": _digest(score_json),
        "rank_contract_version": "1",
        "analytics_contract_version": "1",
        "lifecycle_policy_version": "1",
        "generation_status": "READY",
        "lifecycle_state": "CURRENT",
        "created_at": NOW,
        "last_verified_at": NOW,
        "last_used_at": NOW,
    }


def test_fresh_v15_schema_has_exact_tables_columns_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    initialize_database(path)
    with get_connection(path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert _columns(connection, "phase10_intelligence_generations") == (
            PHASE10_INTELLIGENCE_GENERATION_COLUMNS
        )
        assert _columns(connection, "phase10_orchestration_runs") == (
            PHASE10_ORCHESTRATION_RUN_COLUMNS
        )
        assert _columns(connection, "phase10_context_bindings") == (
            PHASE10_CONTEXT_BINDING_COLUMNS
        )
    assert version == str(CURRENT_SCHEMA_VERSION) == "15"
    assert set(PHASE_TEN_REQUIRED_INDEX_STATEMENTS) <= indexes


def test_v14_upgrade_is_additive_idempotent_and_preserves_phase9_rows(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.db"
    _create_version_fourteen_database(path)

    initialize_database(path)
    initialize_database(path)

    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "15"
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'phase10_migration_sentinel'"
        ).fetchone()[0] == "preserve-me"
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_targeting_contexts"
        ).fetchone()[0] == 1
        for table in (
            "phase10_intelligence_generations",
            "phase10_orchestration_runs",
            "phase10_context_bindings",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_failed_v15_migration_rolls_back_tables_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "failed-upgrade.db"
    _create_version_fourteen_database(path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback_v15 (id INTEGER)")
        raise RuntimeError("forced v15 migration failure")

    monkeypatch.setitem(MIGRATIONS, 15, fail_migration)
    with pytest.raises(RuntimeError, match="forced v15 migration failure"):
        initialize_database(path)

    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "14"
        assert connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'migration_should_rollback_v15'
            """
        ).fetchone() is None


def test_registry_repository_ready_lookup_lifecycle_and_constraints(tmp_path: Path) -> None:
    path = tmp_path / "registry.db"
    ids = _seed_lineage(path)
    repository = Phase10IntelligenceRepository(path)
    values = _generation_values(ids)

    generation_id = repository.insert_ready_generation(values)
    assert repository.fetch_generation(generation_id)["generation_status"] == "READY"
    assert repository.verify_generation_record(generation_id)["generation_id"] == generation_id
    assert repository.find_generation_by_intelligence_key("8" * 64)["generation_id"] == generation_id
    assert len(repository.find_generations_by_modeling_context(values["modeling_context_sha256"])) == 1
    second_generation_id = repository.insert_ready_generation(values)
    assert second_generation_id > generation_id
    assert repository.find_generation_by_intelligence_key("8" * 64)[
        "generation_id"
    ] == second_generation_id
    with pytest.raises(Phase10RepositoryValidationError):
        repository.insert_ready_generation({**values, "modeling_context_sha256": "9" * 64})
    pii_json = _canonical({"person_id": "P1"})
    with pytest.raises(Phase10RepositoryValidationError, match="prohibited"):
        repository.insert_ready_generation(
            {
                **values,
                "intelligence_key_sha256": "9" * 64,
                "modeling_context_json": pii_json,
                "modeling_context_sha256": _digest(pii_json),
            }
        )

    repository.record_generation_verification(
        generation_id, verified_at="2026-09-13T10:01:00Z"
    )
    repository.touch_generation_usage(generation_id, used_at="2026-09-13T10:02:00Z")
    repository.update_generation_lifecycle(
        generation_id,
        lifecycle_state="REUSABLE",
        verified_at="2026-09-13T10:03:00Z",
    )
    assert repository.list_generations_by_lifecycle(["REUSABLE"])[0][
        "generation_id"
    ] == generation_id

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(path, write=True) as connection:
            connection.execute(
                """
                UPDATE phase10_intelligence_generations
                SET modeling_context_json = 'not-json'
                WHERE generation_id = ?
                """,
                (generation_id,),
            )


def test_orchestration_updates_are_atomic_idempotent_and_monotonic(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.db"
    ids = _seed_lineage(path)
    repository = Phase10IntelligenceRepository(path)
    context_sha = str(_generation_values(ids)["modeling_context_sha256"])

    queued, created = repository.create_or_get_active_orchestration(
        orchestration_contract_version="1",
        targeting_context_id=ids["targeting_context_id"],
        modeling_context_sha256=context_sha,
        intelligence_key_sha256="8" * 64,
        business_message="Checking available targeting intelligence",
        reuse_plan={},
        created_at=NOW,
    )
    duplicate, duplicate_created = repository.create_or_get_active_orchestration(
        orchestration_contract_version="1",
        targeting_context_id=ids["second_targeting_context_id"],
        modeling_context_sha256=context_sha,
        intelligence_key_sha256="8" * 64,
        business_message="Checking available targeting intelligence",
        reuse_plan={},
        created_at=NOW,
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate["orchestration_id"] == queued["orchestration_id"]

    orchestration_id = queued["orchestration_id"]
    repository.mark_orchestration_running(
        orchestration_id,
        stage="CHECKING_COMPATIBILITY",
        progress_percent=5,
        business_message="Checking available targeting intelligence",
        started_at="2026-09-13T10:00:01Z",
    )
    repository.update_orchestration_stage(
        orchestration_id,
        stage="RESOLVING_SCORING",
        progress_percent=50,
        business_message="Checking potential-customer coverage",
        updated_at="2026-09-13T10:00:02Z",
        reuse_plan={"analysis": "REUSE", "model": "REUSE", "scoring": "REUSE", "rank": "REUSE"},
        analysis_run_id=ids["analysis_run_id"],
        model_run_id=ids["model_run_id"],
        scoring_run_id=ids["scoring_run_id"],
        scoring_job_id=ids["job_id"],
    )
    with pytest.raises(Phase10RepositoryStateError, match="monotonic"):
        repository.update_orchestration_stage(
            orchestration_id,
            stage="RESOLVING_MODEL",
            progress_percent=40,
            business_message="Preparing targeting intelligence",
            updated_at="2026-09-13T10:00:03Z",
        )

    generation_id = repository.insert_ready_generation(_generation_values(ids))
    repository.mark_orchestration_ready(
        orchestration_id,
        generation_id=generation_id,
        analysis_run_id=ids["analysis_run_id"],
        model_run_id=ids["model_run_id"],
        scoring_run_id=ids["scoring_run_id"],
        business_message="Targeting intelligence ready",
        completed_at="2026-09-13T10:00:04Z",
    )
    ready = repository.fetch_orchestration(orchestration_id)
    assert (ready["status"], ready["stage"], ready["progress_percent"]) == (
        "READY",
        "READY",
        100,
    )
    with pytest.raises(Phase10RepositoryStateError):
        repository.mark_orchestration_terminal(
            orchestration_id,
            status="FAILED",
            business_message="Could not prepare targeting intelligence",
            safe_error_message="Safe failure",
            completed_at="2026-09-13T10:00:05Z",
        )


def test_bindings_share_generation_and_reference_queries_are_no_pii(tmp_path: Path) -> None:
    path = tmp_path / "bindings.db"
    ids = _seed_lineage(path)
    repository = Phase10IntelligenceRepository(path)
    context_sha = str(_generation_values(ids)["modeling_context_sha256"])
    orchestration, _ = repository.create_or_get_active_orchestration(
        orchestration_contract_version="1",
        targeting_context_id=ids["targeting_context_id"],
        modeling_context_sha256=context_sha,
        intelligence_key_sha256="8" * 64,
        business_message="Checking available targeting intelligence",
        reuse_plan={},
        created_at=NOW,
    )
    generation_id = repository.insert_ready_generation(_generation_values(ids))
    repository.mark_orchestration_running(
        orchestration["orchestration_id"],
        stage="CHECKING_COMPATIBILITY",
        progress_percent=5,
        business_message="Checking available targeting intelligence",
        started_at="2026-09-13T10:00:01Z",
    )
    repository.mark_orchestration_ready(
        orchestration["orchestration_id"],
        generation_id=generation_id,
        analysis_run_id=ids["analysis_run_id"],
        model_run_id=ids["model_run_id"],
        scoring_run_id=ids["scoring_run_id"],
        business_message="Targeting intelligence ready",
        completed_at="2026-09-13T10:00:02Z",
    )
    for context_id in (
        ids["targeting_context_id"],
        ids["second_targeting_context_id"],
    ):
        repository.upsert_context_binding(
            targeting_context_id=context_id,
            modeling_context_sha256=context_sha,
            orchestration_id=orchestration["orchestration_id"],
            generation_id=generation_id,
            binding_status="READY",
            timestamp=NOW,
        )
    repository.touch_context_binding(
        ids["targeting_context_id"], used_at="2026-09-13T10:01:00Z"
    )
    assert repository.fetch_context_binding(ids["targeting_context_id"])[
        "generation_id"
    ] == generation_id
    references = repository.fetch_generation_reference_counts(generation_id)
    assert references == {
        "context_binding_count": 2,
        "ready_context_binding_count": 2,
        "orchestration_count": 0,
        "saved_audience_count": 0,
        "saved_target_group_count": 0,
        "campaign_count": 0,
        "finalized_campaign_count": 0,
        "export_event_count": 0,
    }
    assert all("person" not in key and "customer" not in key for key in references)


def test_blocked_and_failed_terminal_state_constraints(tmp_path: Path) -> None:
    path = tmp_path / "terminal.db"
    ids = _seed_lineage(path)
    repository = Phase10IntelligenceRepository(path)
    for hash_character, status in zip(("9", "a"), ("BLOCKED", "FAILED"), strict=True):
        queued, _ = repository.create_or_get_active_orchestration(
            orchestration_contract_version="1",
            targeting_context_id=ids["targeting_context_id"],
            modeling_context_sha256=hash_character * 64,
            intelligence_key_sha256=hash_character * 64,
            business_message="Checking available targeting intelligence",
            reuse_plan={},
            created_at=NOW,
        )
        repository.mark_orchestration_terminal(
            queued["orchestration_id"],
            status=status,
            business_message="There is not enough verified past campaign history.",
            safe_error_message="Safe technical failure" if status == "FAILED" else None,
            completed_at="2026-09-13T10:05:00Z",
        )
        assert repository.fetch_orchestration(queued["orchestration_id"])["status"] == status
