"""Single-slot automatic feedback recalibration challenger worker."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import numpy as np

from app.database.connection import get_connection
from app.services.phase11_feedback_service import _adaptive_gate
from app.services.propensity_calibration_service import (
    fit_held_out_calibration, publish_fitted_calibration,
)


logger = logging.getLogger(__name__)


def challenger_meets_promotion_gates(
    candidate: dict[str, float],
    incumbent: dict[str, float] | None,
) -> bool:
    """Require calibration improvement and bounded ranking non-regression."""

    required = (
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "roc_auc",
        "average_precision",
        "top_decile_lift",
    )
    if any(key not in candidate or not math.isfinite(float(candidate[key])) for key in required):
        return False
    if incumbent is None:
        return True
    if any(key not in incumbent or not math.isfinite(float(incumbent[key])) for key in required):
        return False
    return bool(
        candidate["brier_score"] < incumbent["brier_score"]
        and candidate["roc_auc"] >= incumbent["roc_auc"] - .01
        and candidate["average_precision"] >= incumbent["average_precision"] - .01
        and candidate["top_decile_lift"] >= incumbent["top_decile_lift"]
    )


class FeedbackRecalibrationWorker:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="feedback-recalibration"
        )
        self._lock = Lock()
        self._active: set[int] = set()
        self._futures: dict[int, Future[None]] = {}

    def submit(self, database_path: str | Path, decision_id: int) -> None:
        with self._lock:
            if decision_id in self._active:
                return
            self._active.add(decision_id)
            future = self._executor.submit(self._run, Path(database_path), decision_id)
            self._futures[decision_id] = future

    def resume_durable_decisions(self, database_path: str | Path) -> int:
        """Recover queued or interrupted recalibrations without duplicating workers."""

        path = Path(database_path)
        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE feedback_retraining_decisions
                   SET status='QUEUED',
                       trigger_reason='Interrupted recalibration recovered at application startup.'
                   WHERE status='TRAINING'"""
            )
            identifiers = [
                int(row["retraining_decision_id"])
                for row in connection.execute(
                    """SELECT retraining_decision_id FROM feedback_retraining_decisions
                       WHERE status='QUEUED' ORDER BY retraining_decision_id"""
                ).fetchall()
            ]
        for identifier in identifiers:
            self.submit(path, identifier)
        return len(identifiers)

    def _run(self, path: Path, decision_id: int) -> None:
        try:
            with get_connection(path, write=True) as connection:
                claimed = connection.execute(
                    "UPDATE feedback_retraining_decisions SET status='TRAINING' WHERE retraining_decision_id=? AND status='QUEUED'",
                    (decision_id,),
                )
                if claimed.rowcount != 1:
                    return
                decision = connection.execute(
                    "SELECT * FROM feedback_retraining_decisions WHERE retraining_decision_id=?",
                    (decision_id,),
                ).fetchone()
            if decision is None or decision["status"] != "TRAINING":
                return
            scoring_run_id = int(decision["scoring_run_id"])
            batch_cutoff = decision["latest_feedback_batch_id"]
            if batch_cutoff is None:
                with get_connection(path, write=True) as connection:
                    cutoff_row = connection.execute(
                        """SELECT MAX(b.feedback_batch_id) AS batch_cutoff
                           FROM campaign_feedback_batches AS b
                           JOIN campaign_search_runs AS r
                             ON r.search_run_id=b.search_run_id
                           WHERE b.status='ACCEPTED' AND r.scoring_run_id=?""",
                        (scoring_run_id,),
                    ).fetchone()
                    batch_cutoff = cutoff_row["batch_cutoff"]
                    if batch_cutoff is None:
                        raise RuntimeError(
                            "Feedback recalibration has no accepted feedback boundary."
                        )
                    connection.execute(
                        """UPDATE feedback_retraining_decisions
                           SET latest_feedback_batch_id=?
                           WHERE retraining_decision_id=? AND status='TRAINING'
                             AND latest_feedback_batch_id IS NULL""",
                        (int(batch_cutoff), decision_id),
                    )
            batch_cutoff = int(batch_cutoff)
            with get_connection(path) as connection:
                rows = connection.execute(
                    """SELECT p.propensity_score,o.outcome,
                              'feedback-search-run:' || CAST(b.search_run_id AS TEXT) AS group_id,
                              b.payload_sha256
                       FROM campaign_feedback_outcomes AS o
                       JOIN campaign_feedback_batches AS b ON b.feedback_batch_id=o.feedback_batch_id
                       JOIN campaign_search_runs AS r ON r.search_run_id=b.search_run_id
                       JOIN propensity_scores AS p ON p.scoring_run_id=r.scoring_run_id AND p.person_id=o.person_id
                       WHERE b.status='ACCEPTED' AND r.scoring_run_id=?
                         AND b.feedback_batch_id<=?
                       ORDER BY b.search_run_id,o.person_id""",
                    (scoring_run_id, batch_cutoff),
                ).fetchall()
                incumbent = connection.execute(
                    """SELECT calibration_artifact_id,metrics_json FROM score_calibration_artifacts
                       WHERE scoring_run_id=? AND status='PROMOTED'
                       ORDER BY promoted_at DESC LIMIT 1""",
                    (scoring_run_id,),
                ).fetchone()
                model = connection.execute(
                    """SELECT m.model_run_id,m.split_lineage_json
                       FROM scoring_runs AS s
                       JOIN model_runs AS m ON m.model_run_id=s.model_run_id
                       WHERE s.scoring_run_id=? AND s.status='COMPLETED'
                         AND m.status='COMPLETED'""",
                    (scoring_run_id,),
                ).fetchone()
            if model is None or model["split_lineage_json"] is None:
                raise RuntimeError(
                    "Feedback recalibration requires governed model split lineage."
                )
            model_lineage = json.loads(str(model["split_lineage_json"]))
            model_groups = model_lineage.get("partitions", {}).get(
                "model_training", {}
            ).get("group_ids", [])
            if not model_groups:
                raise RuntimeError(
                    "Feedback recalibration requires model-training group lineage."
                )
            fitted = fit_held_out_calibration(
                np.asarray([row["propensity_score"] for row in rows]),
                np.asarray([row["outcome"] for row in rows]),
                np.asarray([row["group_id"] for row in rows]),
                model_training_group_ids=tuple(str(value) for value in model_groups),
            )
            incumbent_metrics = json.loads(incumbent["metrics_json"]) if incumbent else None
            candidate = fitted.metrics
            promote = challenger_meets_promotion_gates(candidate, incumbent_metrics)
            source_checksum = hashlib.sha256("".join(sorted({str(row["payload_sha256"]) for row in rows})).encode()).hexdigest()
            published = publish_fitted_calibration(
                path, scoring_run_id, fitted, source_checksum=source_checksum, promote=promote,
            )
            outcome = "PROMOTED" if promote else "REJECTED"
            comparison = {
                "candidate": candidate, "incumbent": incumbent_metrics,
                "promotion_checks_passed": promote,
                "operation": "RECALIBRATION",
                "model_run_id": int(model["model_run_id"]),
                "model_created": False,
                "raw_scores_reused": True,
                "feedback_batch_cutoff": batch_cutoff,
            }
            with get_connection(path, write=True) as connection:
                completed = connection.execute(
                    """UPDATE feedback_retraining_decisions
                       SET status=?,incumbent_calibration_artifact_id=?,
                           candidate_calibration_artifact_id=?,metrics_json=?,completed_at=datetime('now')
                       WHERE retraining_decision_id=? AND status='TRAINING'""",
                    (outcome, int(incumbent["calibration_artifact_id"]) if incumbent else None,
                     int(published["calibration_artifact_id"]),
                     json.dumps(comparison, sort_keys=True, separators=(",", ":")), decision_id),
                )
            if completed.rowcount == 1:
                try:
                    self._reevaluate_waiting_successor(path, scoring_run_id)
                except Exception:
                    logger.exception(
                        "Waiting feedback reevaluation failed | scoring_run_id=%s",
                        scoring_run_id,
                    )
        except Exception:
            logger.exception("Feedback recalibration failed | decision_id=%s", decision_id)
            with get_connection(path, write=True) as connection:
                connection.execute(
                    """UPDATE feedback_retraining_decisions SET status='FAILED',
                       trigger_reason='Automatic feedback recalibration could not be completed safely.',
                       completed_at=datetime('now')
                       WHERE retraining_decision_id=? AND status='TRAINING'""",
                    (decision_id,),
                )
        finally:
            with self._lock:
                self._active.discard(decision_id)
                self._futures.pop(decision_id, None)

    def _reevaluate_waiting_successor(
        self, path: Path, scoring_run_id: int
    ) -> None:
        """Evaluate feedback accepted after the active decision's fixed cutoff."""

        queued_id: int | None = None
        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            waiting = connection.execute(
                """SELECT retraining_decision_id,latest_feedback_batch_id
                   FROM feedback_retraining_decisions
                   WHERE scoring_run_id=? AND status='WAITING_FOR_DATA'
                   ORDER BY retraining_decision_id DESC LIMIT 1""",
                (scoring_run_id,),
            ).fetchone()
            if waiting is None or waiting["latest_feedback_batch_id"] is None:
                return
            status, reason, facts = _adaptive_gate(
                connection,
                scoring_run_id,
                int(waiting["latest_feedback_batch_id"]),
            )
            updated = connection.execute(
                """UPDATE feedback_retraining_decisions
                   SET status=?,label_count=?,positive_count=?,negative_count=?,
                       distinct_run_count=?,new_label_ratio=?,
                       population_stability_index=?,trigger_reason=?,
                       reference_decision_id=?,drift_lineage_json=?,completed_at=NULL
                   WHERE retraining_decision_id=? AND status='WAITING_FOR_DATA'""",
                (
                    status,
                    facts["labels"],
                    facts["positives"],
                    facts["negatives"],
                    facts["runs"],
                    facts["new_label_ratio"],
                    facts["population_stability_index"],
                    reason,
                    facts["reference_decision_id"],
                    json.dumps(
                        facts["drift_lineage"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    int(waiting["retraining_decision_id"]),
                ),
            )
            if updated.rowcount == 1 and status == "QUEUED":
                queued_id = int(waiting["retraining_decision_id"])
        if queued_id is not None:
            self.submit(path, queued_id)

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


FeedbackRetrainingWorker = FeedbackRecalibrationWorker


__all__ = (
    "FeedbackRecalibrationWorker",
    "FeedbackRetrainingWorker",
    "challenger_meets_promotion_gates",
)
