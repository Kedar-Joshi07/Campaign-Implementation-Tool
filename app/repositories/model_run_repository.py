"""Governed SQLite lifecycle persistence for Phase 3 model runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.connection import get_connection


class ModelRunRepository:
    """Persist model-run state transitions without storing model BLOBs."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_run(
        self,
        *,
        analysis_run_id: int,
        model_name: str,
        created_at: str,
        random_seed: int,
        validation_fraction: float,
    ) -> int:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO model_runs (
                    analysis_run_id,
                    model_name,
                    created_at,
                    status,
                    random_seed,
                    validation_fraction
                ) VALUES (?, ?, ?, 'RUNNING', ?, ?)
                """,
                (
                    analysis_run_id,
                    model_name,
                    created_at,
                    random_seed,
                    validation_fraction,
                ),
            )
            return int(cursor.lastrowid)

    def complete_run(
        self,
        *,
        model_run_id: int,
        completed_at: str,
        algorithm: str,
        selected_candidate: str,
        counts: dict[str, int],
        feature_contract_json: str,
        preprocessing_json: str,
        hyperparameters_json: str,
        metrics_json: str,
        library_versions_json: str,
        artifact_path: str,
        artifact_sha256: str,
    ) -> None:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE model_runs
                SET
                    completed_at = ?,
                    status = 'COMPLETED',
                    algorithm = ?,
                    selected_candidate = ?,
                    reconstructed_observation_count = ?,
                    selected_customer_count = ?,
                    positive_customer_count = ?,
                    unlabeled_customer_count = ?,
                    train_customer_count = ?,
                    validation_customer_count = ?,
                    train_positive_count = ?,
                    validation_positive_count = ?,
                    feature_contract_json = ?,
                    preprocessing_json = ?,
                    hyperparameters_json = ?,
                    metrics_json = ?,
                    library_versions_json = ?,
                    artifact_path = ?,
                    artifact_sha256 = ?,
                    error_message = NULL
                WHERE model_run_id = ? AND status = 'RUNNING'
                """,
                (
                    completed_at,
                    algorithm,
                    selected_candidate,
                    counts["reconstructed_observation_count"],
                    counts["selected_customer_count"],
                    counts["positive_customer_count"],
                    counts["unlabeled_customer_count"],
                    counts["train_customer_count"],
                    counts["validation_customer_count"],
                    counts["train_positive_count"],
                    counts["validation_positive_count"],
                    feature_contract_json,
                    preprocessing_json,
                    hyperparameters_json,
                    metrics_json,
                    library_versions_json,
                    artifact_path,
                    artifact_sha256,
                    model_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Model run was not in RUNNING state during completion."
                )

    def fail_run(
        self,
        *,
        model_run_id: int,
        completed_at: str,
        error_message: str,
    ) -> None:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE model_runs
                SET
                    completed_at = ?,
                    status = 'FAILED',
                    artifact_path = NULL,
                    artifact_sha256 = NULL,
                    error_message = ?
                WHERE model_run_id = ? AND status = 'RUNNING'
                """,
                (completed_at, error_message, model_run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Model run was not in RUNNING state during failure."
                )

    def fetch_run(self, model_run_id: int) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM model_runs WHERE model_run_id = ?",
                (model_run_id,),
            ).fetchone()
        return dict(row) if row is not None else None


__all__ = ("ModelRunRepository",)
