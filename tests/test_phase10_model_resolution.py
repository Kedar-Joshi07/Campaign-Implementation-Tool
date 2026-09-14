from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
)
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
)
from app.services.historical_analysis_service import create_historical_analysis
from app.services.historical_source_provenance_service import (
    resolve_current_historical_source_provenance,
)
from app.services.model_training_service import train_and_persist_model
from app.services.phase10_context_identity_service import (
    build_historical_compatibility_fingerprint,
    normalize_modeling_context,
)
from app.services.phase10_historical_resolution_service import (
    resolve_or_create_phase10_historical_analysis,
)
from app.services.phase10_model_resolution_service import (
    Phase10ModelValidationError,
    resolve_or_train_phase10_model,
    validate_phase10_model_before_scoring,
)


@pytest.fixture
def phase10_case(tmp_path: Path):
    database_path = tmp_path / "phase10-model-resolution.db"
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
    observations = [
        (
            f"S{index:03d}",
            f"C{index:03d}",
            f"2025-01-{1 + ((index - 1) % 28):02d}",
            1 if index <= 20 else 0,
        )
        for index in range(1, 41)
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
                (*row, row[3], row[3])
                for row in observations
            ],
        )
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, '2026-09-14T00:00:00Z',
                      '2026-09-14T00:00:01Z', 'COMPLETED', 40, 40, 0, ?)
            """,
            (
                ("customers", "data/customers.csv", "c" * 64),
                ("campaign_sales", "data/campaign_sales.csv", "d" * 64),
            ),
        )
    context = normalize_modeling_context({"product_ids": ["P1"]})
    historical = resolve_or_create_phase10_historical_analysis(database_path, context)
    assert historical.status == "READY"
    return database_path, tmp_path, context, historical


def _fresh_model(phase10_case):
    database_path, project_root, context, historical = phase10_case
    resolution = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    return database_path, project_root, context, historical, resolution


def _historical_fingerprint(database_path, context, historical):
    source = resolve_current_historical_source_provenance(database_path)
    return build_historical_compatibility_fingerprint(
        modeling_context=context,
        resolved_historical_filters=historical.resolved_filters,
        customer_source_checksum=source.customer_source_checksum,
        campaign_sales_source_checksum=source.campaign_sales_source_checksum,
    )


def _assert_validation_reason(
    database_path: Path,
    project_root: Path,
    historical,
    fingerprint,
    model_run_id: int,
    reason: str,
) -> None:
    with pytest.raises(Phase10ModelValidationError) as captured:
        validate_phase10_model_before_scoring(
            database_path,
            model_run_id,
            analysis_run_id=historical.analysis_run_id,
            historical_fingerprint=fingerprint,
            project_root=project_root,
        )
    assert reason in captured.value.reason_codes


def test_fresh_training_uses_synchronous_child_job_then_exactly_reuses(
    phase10_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_pool_submission(*args, **kwargs):
        raise AssertionError("the shared worker pool must not be used")

    monkeypatch.setattr(
        "app.jobs.executor.submit_model_training_job",
        forbidden_pool_submission,
    )
    database_path, project_root, context, historical, first = _fresh_model(
        phase10_case
    )

    assert first.status == "READY"
    assert first.trained is True and first.reused is False
    assert first.training_job_id is not None
    assert first.model_run_id is not None
    with get_connection(database_path) as connection:
        job = connection.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (first.training_job_id,)
        ).fetchone()
    assert job is not None
    assert job["status"] == "COMPLETED"
    request = json.loads(job["request_json"])
    assert request == {
        "analysis_run_id": historical.analysis_run_id,
        "model_name": f"Phase 10 model for analysis {historical.analysis_run_id}",
        "random_seed": 42,
        "run_elkan_challenger": True,
        "validation_fraction": 0.2,
    }
    row = ModelRunRepository(database_path).fetch_run(first.model_run_id)
    assert row["selected_candidate"] == PRIMARY_MODEL_NAME

    second = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    assert second.status == "READY"
    assert second.reused is True and second.trained is False
    assert second.training_job_id is None
    assert second.model_run_id == first.model_run_id
    assert [item.model_run_id for item in second.compatible_candidates] == [
        first.model_run_id
    ]
    assert second.compatible_candidates[0].discovery_source == "LEGACY_MODEL_RUN"


def test_pre_scoring_gate_rejects_all_required_model_integrity_failures(
    phase10_case,
) -> None:
    database_path, project_root, context, historical, resolution = _fresh_model(
        phase10_case
    )
    model_run_id = resolution.model_run_id
    assert model_run_id is not None
    row = ModelRunRepository(database_path).fetch_run(model_run_id)
    assert row is not None
    fingerprint = _historical_fingerprint(database_path, context, historical)

    validated = validate_phase10_model_before_scoring(
        database_path,
        model_run_id,
        analysis_run_id=historical.analysis_run_id,
        historical_fingerprint=fingerprint,
        project_root=project_root,
    )
    assert validated.model_run_id == model_run_id

    alternate = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET analysis_run_id = ? WHERE model_run_id = ?",
            (alternate["analysis_run_id"], model_run_id),
        )
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "ANALYSIS_LINK_MISMATCH",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET analysis_run_id = ? WHERE model_run_id = ?",
            (historical.analysis_run_id, model_run_id),
        )

    mutations = (
        ("feature_contract_json", json.dumps({"version": "wrong"}), "FEATURE_CONTRACT_MISMATCH"),
        (
            "preprocessing_json",
            json.dumps({**json.loads(row["preprocessing_json"]), "customer_id": "forbidden"}),
            "PROHIBITED_MODEL_INPUT",
        ),
        (
            "hyperparameters_json",
            json.dumps({**json.loads(row["hyperparameters_json"]), "model_role_policy_version": "wrong"}),
            "HYPERPARAMETER_METADATA_INVALID",
        ),
        (
            "metrics_json",
            json.dumps({**json.loads(row["metrics_json"]), "model_role_policy_version": "wrong"}),
            "MODEL_ROLE_POLICY_MISMATCH",
        ),
        (
            "metrics_json",
            json.dumps({**json.loads(row["metrics_json"]), "evaluation_contract_version": "wrong"}),
            "EVALUATION_CONTRACT_MISMATCH",
        ),
    )
    for column, replacement, reason in mutations:
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                f"UPDATE model_runs SET {column} = ? WHERE model_run_id = ?",
                (replacement, model_run_id),
            )
        _assert_validation_reason(
            database_path, project_root, historical, fingerprint,
            model_run_id, reason,
        )
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                f"UPDATE model_runs SET {column} = ? WHERE model_run_id = ?",
                (row[column], model_run_id),
            )

    disabled_metrics = json.loads(row["metrics_json"])
    disabled_metrics["candidate_results"][CHALLENGER_1_MODEL_NAME]["status"] = (
        "SKIPPED_DISABLED"
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET metrics_json = ? WHERE model_run_id = ?",
            (json.dumps(disabled_metrics), model_run_id),
        )
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "AUTOMATED_TRAINING_POLICY_MISMATCH",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET metrics_json = ? WHERE model_run_id = ?",
            (row["metrics_json"], model_run_id),
        )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET random_seed = 43 WHERE model_run_id = ?",
            (model_run_id,),
        )
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "AUTOMATED_TRAINING_POLICY_MISMATCH",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET random_seed = 42 WHERE model_run_id = ?",
            (model_run_id,),
        )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET selected_candidate = ? WHERE model_run_id = ?",
            (CHALLENGER_1_MODEL_NAME, model_run_id),
        )
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "PRIMARY_NOT_SELECTED",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET selected_candidate = ? WHERE model_run_id = ?",
            (PRIMARY_MODEL_NAME, model_run_id),
        )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET status = 'FAILED' WHERE model_run_id = ?",
            (model_run_id,),
        )
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "STATUS_NOT_COMPLETED",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET status = 'COMPLETED' WHERE model_run_id = ?",
            (model_run_id,),
        )

    artifact_path = project_root / row["artifact_path"]
    original_artifact = artifact_path.read_bytes()
    artifact_path.unlink()
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "ARTIFACT_INVALID",
    )
    artifact_path.write_bytes(b"corrupt artifact")
    _assert_validation_reason(
        database_path, project_root, historical, fingerprint,
        model_run_id, "ARTIFACT_INVALID",
    )
    artifact_path.write_bytes(original_artifact)


def test_filters_all_candidates_then_selects_deterministically_and_prefers_generation(
    phase10_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root, context, historical, first = _fresh_model(
        phase10_case
    )
    second = train_and_persist_model(
        database_path,
        historical.analysis_run_id,
        run_elkan_challenger=True,
        project_root=project_root,
    )
    legacy = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    assert legacy.model_run_id == second["model_run_id"]
    assert [item.model_run_id for item in legacy.compatible_candidates] == [
        second["model_run_id"],
        first.model_run_id,
    ]

    source = resolve_current_historical_source_provenance(database_path)
    filters_payload = historical.resolved_filters.model_dump(mode="json")
    filters_json = json.dumps(
        filters_payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    filters_sha = hashlib.sha256(filters_json.encode("utf-8")).hexdigest()

    def generation(model_run_id: int, generation_id: int, *, valid: bool):
        model = ModelRunRepository(database_path).fetch_run(model_run_id)
        return {
            "generation_id": generation_id,
            "lifecycle_state": "CURRENT",
            "model_run_id": model_run_id,
            "compatibility_contract_version": PHASE10_COMPATIBILITY_CONTRACT_VERSION,
            "historical_filters_sha256": filters_sha,
            "historical_window_policy_version": PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
            "multi_product_positive_policy_version": PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
            "training_eligibility_policy_version": PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
            "customer_import_id": source.customer_import_id,
            "customer_source_checksum": source.customer_source_checksum,
            "campaign_sales_import_id": source.campaign_sales_import_id,
            "campaign_sales_source_checksum": source.campaign_sales_source_checksum,
            "feature_contract_version": FEATURE_CONTRACT_VERSION if valid else "wrong",
            "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
            "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
            "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
            "automated_training_policy_version": PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
            "analysis_run_id": historical.analysis_run_id,
            "artifact_sha256": model["artifact_sha256"],
        }

    monkeypatch.setattr(
        Phase10IntelligenceRepository,
        "list_reusable_model_generations",
        lambda self, sha: [
            generation(second["model_run_id"], 100, valid=False),
            generation(first.model_run_id, 99, valid=True),
        ],
    )
    resolved = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    assert resolved.model_run_id == first.model_run_id
    assert resolved.compatible_candidates == (
        resolved.compatible_candidates[0],
    )
    assert resolved.compatible_candidates[0].generation_id == 99
    assert resolved.compatible_candidates[0].discovery_source == (
        "PHASE10_CURRENT_GENERATION"
    )
    assert resolved.rejected_candidates[0].generation_id == 100
    assert "GENERATION_COMPATIBILITY_MISMATCH" in (
        resolved.rejected_candidates[0].reason_codes
    )


def test_blocked_history_never_creates_model_or_scoring(phase10_case) -> None:
    database_path, project_root, _, _ = phase10_case
    context = normalize_modeling_context({"product_ids": ["MISSING"]})
    historical = resolve_or_create_phase10_historical_analysis(database_path, context)
    resolved = resolve_or_train_phase10_model(
        database_path,
        context,
        historical,
        project_root=project_root,
    )
    assert resolved.status == "BLOCKED"
    assert resolved.model_run_id is None
    assert resolved.training_job_id is None
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0] == 0
