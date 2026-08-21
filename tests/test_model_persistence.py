from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import joblib
import pytest
from pulearn import BaggingPuClassifier

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, ORDERED_FEATURES
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    DIAGNOSTIC_CONTROL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.repositories.model_run_repository import ModelRunRepository
from app.services.historical_analysis_service import create_historical_analysis
from app.services.model_training_service import (
    ModelArtifactError,
    ModelTrainingExecutionError,
    load_verified_model_artifact,
    train_and_persist_model,
)


@pytest.fixture
def completed_analysis(tmp_path: Path) -> tuple[Path, int]:
    database_path = tmp_path / "model-persistence.db"
    initialize_database(database_path)
    customers = []
    observations = []
    for index in range(60):
        customer_id = f"CUS_FIXTURE_{index:03d}"
        positive = int(index % 2 == 0)
        customers.append(
            (
                customer_id,
                f"{1970 + index % 30:04d}-06-15",
                "Female" if index % 2 == 0 else "Male",
                ("Ohio", "Texas", "California")[index % 3],
                30_000 + index * 1_000,
                1 + index % 5,
                "Citizen",
                "Owner" if index % 2 == 0 else "Renter",
                ("College", "Graduate", "Postgraduate")[index % 3],
                "Employed",
                "Salaried" if index % 2 == 0 else "Contract",
                "Married" if index % 3 else "Single",
            )
        )
        observations.append(
            (
                f"CS_FIXTURE_{index:03d}",
                customer_id,
                "CMP_MODEL",
                "PRD_MODEL",
                "2025-06-15",
                1,
                positive,
                positive,
                positive,
                positive,
            )
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
                ?, ?, ?, ?, 'Model Campaign', 'Acquisition', 'Email',
                'Model Product', 'Electronics',
                '2025-01-01', '2025-12-31', ?, ?, 0, ?, ?, ?, ?
            )
            """,
            observations,
        )
    analysis = create_historical_analysis(database_path, {})
    return database_path, int(analysis["analysis_run_id"])


def _train(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
) -> dict[str, Any]:
    database_path, analysis_run_id = completed_analysis
    return train_and_persist_model(
        database_path,
        analysis_run_id,
        model_name="Persistence fixture",
        run_elkan_challenger=False,
        project_root=tmp_path,
    )


def _assert_no_forbidden_metadata_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = {
            "customer_id",
            "person_id",
            "email",
            "phone_number",
            "address_line_1",
            "train_matrix",
            "validation_matrix",
            "validation_scores",
        }
        assert not forbidden.intersection(value)
        for nested in value.values():
            _assert_no_forbidden_metadata_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_metadata_keys(nested)


def test_successful_lifecycle_persists_reloadable_checksummed_artifact(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
) -> None:
    database_path, analysis_run_id = completed_analysis
    summary = _train(completed_analysis, tmp_path)
    row = ModelRunRepository(database_path).fetch_run(summary["model_run_id"])

    assert row is not None
    assert row["status"] == "COMPLETED"
    assert row["selected_candidate"] == PRIMARY_MODEL_NAME
    assert summary["model_role_policy_version"] == MODEL_ROLE_POLICY_VERSION
    assert summary["primary_candidate"] == PRIMARY_MODEL_NAME
    assert summary["challenger_1"] == CHALLENGER_1_MODEL_NAME
    assert summary["challenger_1_status"] == "SKIPPED_DISABLED"
    assert summary["diagnostic_control"] == DIAGNOSTIC_CONTROL_NAME
    assert summary["selection_policy"] == PRIMARY_ROLE_GOVERNED_SELECTION
    assert row["analysis_run_id"] == analysis_run_id
    assert row["selected_candidate"] == summary["selected_candidate"]
    assert row["completed_at"] is not None
    assert row["error_message"] is None
    assert row["selected_customer_count"] == 60
    assert row["positive_customer_count"] == 30
    assert row["unlabeled_customer_count"] == 30
    assert row["train_customer_count"] + row["validation_customer_count"] == 60
    assert row["train_positive_count"] + row["validation_positive_count"] == 30
    assert summary["transformed_feature_count"] > len(ORDERED_FEATURES)
    assert set(summary["stage_seconds"]) == {
        "reconstruction",
        "split",
        "preprocessing",
        "candidate_training",
        "evaluation_selection",
        "persistence_reload_checksum",
    }
    assert all(value >= 0 for value in summary["stage_seconds"].values())
    assert summary["total_seconds"] >= sum(summary["stage_seconds"].values())
    assert all(value > 0 for value in summary["approximate_memory_bytes"].values())

    relative_path = Path(row["artifact_path"])
    assert not relative_path.is_absolute()
    assert ".." not in relative_path.parts
    assert str(tmp_path) not in summary["artifact_path"]
    artifact_path = tmp_path / relative_path
    assert artifact_path.is_file()
    expected_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert expected_sha == row["artifact_sha256"] == summary["artifact_sha256"]

    payload = load_verified_model_artifact(
        database_path,
        summary["model_run_id"],
        project_root=tmp_path,
    )
    assert payload["selected_candidate"] == row["selected_candidate"]
    assert payload["feature_contract_sha256"] == FEATURE_CONTRACT_SHA256
    assert tuple(payload["raw_feature_order"]) == ORDERED_FEATURES
    assert isinstance(payload["estimator"], BaggingPuClassifier)
    assert set(payload) == {
        "artifact_version",
        "feature_contract_version",
        "feature_contract_sha256",
        "raw_feature_order",
        "preprocessor",
        "estimator",
        "selected_candidate",
    }
    artifact_bytes = artifact_path.read_bytes()
    assert b"CUS_FIXTURE_" not in artifact_bytes

    for field in (
        "feature_contract_json",
        "preprocessing_json",
        "hyperparameters_json",
        "metrics_json",
        "library_versions_json",
    ):
        decoded = json.loads(row[field])
        _assert_no_forbidden_metadata_keys(decoded)
    assert json.loads(row["feature_contract_json"])["ordered_features"] == list(
        ORDERED_FEATURES
    )
    assert json.loads(row["metrics_json"])["selected_candidate"] == row[
        "selected_candidate"
    ]
    assert json.loads(row["metrics_json"])["model_role_policy_version"] == "2"
    assert json.loads(row["hyperparameters_json"])[
        "model_role_policy_version"
    ] == "2"
    assert json.loads(row["library_versions_json"])["joblib"] == joblib.__version__


def test_missing_and_corrupted_artifacts_are_detected(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
) -> None:
    database_path, _ = completed_analysis
    missing_summary = _train(completed_analysis, tmp_path)
    missing_path = tmp_path / missing_summary["artifact_path"]
    missing_path.unlink()

    with pytest.raises(ModelArtifactError, match="missing"):
        load_verified_model_artifact(
            database_path,
            missing_summary["model_run_id"],
            project_root=tmp_path,
        )

    corrupt_summary = _train(completed_analysis, tmp_path)
    corrupt_path = tmp_path / corrupt_summary["artifact_path"]
    corrupt_path.write_bytes(b"corrupted-local-artifact")

    with pytest.raises(ModelArtifactError, match="checksum"):
        load_verified_model_artifact(
            database_path,
            corrupt_summary["model_run_id"],
            project_root=tmp_path,
        )


def test_pipeline_failure_transitions_running_row_to_failed(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, analysis_run_id = completed_analysis

    def fail_reconstruction(*args: object, **kwargs: object) -> object:
        raise RuntimeError("forced internal pipeline diagnostic")

    monkeypatch.setattr(
        "app.services.model_training_service.reconstruct_training_cohort",
        fail_reconstruction,
    )

    with pytest.raises(ModelTrainingExecutionError) as captured:
        train_and_persist_model(
            database_path,
            analysis_run_id,
            project_root=tmp_path,
        )

    row = ModelRunRepository(database_path).fetch_run(captured.value.model_run_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["analysis_run_id"] == analysis_run_id
    assert row["completed_at"] is not None
    assert "forced internal pipeline diagnostic" in row["error_message"]
    assert row["artifact_path"] is None
    assert row["artifact_sha256"] is None
    assert not (tmp_path / "artifacts" / "models").exists()


def test_completion_failure_removes_artifact_and_persists_failed_status(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, analysis_run_id = completed_analysis

    def fail_completion(self: object, **kwargs: object) -> None:
        raise RuntimeError("forced completion transaction failure")

    monkeypatch.setattr(ModelRunRepository, "complete_run", fail_completion)

    with pytest.raises(ModelTrainingExecutionError) as captured:
        train_and_persist_model(
            database_path,
            analysis_run_id,
            run_elkan_challenger=False,
            project_root=tmp_path,
        )

    row = ModelRunRepository(database_path).fetch_run(captured.value.model_run_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert "forced completion transaction failure" in row["error_message"]
    run_directory = (
        tmp_path
        / "artifacts"
        / "models"
        / f"model_run_{captured.value.model_run_id:06d}"
    )
    assert not run_directory.exists()


def test_cli_json_success_and_failure_exit_codes(
    completed_analysis: tuple[Path, int],
    tmp_path: Path,
) -> None:
    database_path, analysis_run_id = completed_analysis
    script = Path(__file__).resolve().parents[1] / "scripts" / "train_pu_model.py"
    success = subprocess.run(
        (
            sys.executable,
            str(script),
            "--analysis-run-id",
            str(analysis_run_id),
            "--model-name",
            "CLI fixture",
            "--no-run-elkan-challenger",
            "--database-path",
            str(database_path),
            "--json",
        ),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert success.returncode == 0, success.stderr
    success_json = json.loads(success.stdout)
    assert success_json["status"] == "COMPLETED"
    assert success_json["analysis_run_id"] == analysis_run_id
    assert not Path(success_json["artifact_path"]).is_absolute()
    assert (tmp_path / success_json["artifact_path"]).is_file()

    failure = subprocess.run(
        (
            sys.executable,
            str(script),
            "--analysis-run-id",
            "999999",
            "--database-path",
            str(database_path),
            "--json",
        ),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert failure.returncode == 1
    failure_json = json.loads(failure.stdout)
    assert failure_json["status"] == "FAILED"
    assert "artifact_path" not in failure_json
    assert str(tmp_path) not in failure.stdout
