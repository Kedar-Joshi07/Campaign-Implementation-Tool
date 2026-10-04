"""Single-slot automatic feedback recalibration challenger worker."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread

import numpy as np

from app.database.connection import get_connection
from app.services.feedback_grouping import (
    FEEDBACK_GROUPING_CONTRACT_VERSION,
    build_feedback_grouping,
)
from app.services.phase11_feedback_service import _adaptive_gate
from app.services.phase11_run_lifecycle_service import STALE_HEARTBEAT_SECONDS
from app.services.propensity_calibration_service import (
    PropensityCalibrationError,
    apply_calibration,
    calibration_metrics,
    fit_held_out_calibration,
    publish_fitted_calibration,
)


logger = logging.getLogger(__name__)
FEEDBACK_WORKER_HEARTBEAT_SECONDS = 15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


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
        return False
    if any(key not in incumbent or not math.isfinite(float(incumbent[key])) for key in required):
        return False
    return bool(
        candidate["brier_score"] < incumbent["brier_score"]
        and candidate["roc_auc"] >= incumbent["roc_auc"] - .01
        and candidate["average_precision"] >= incumbent["average_precision"] - .01
        and candidate["top_decile_lift"] >= incumbent["top_decile_lift"]
    )


def compare_calibrations_on_evaluation_window(
    candidate_artifact: dict,
    incumbent_artifact: dict,
    raw_scores: np.ndarray,
    labels: np.ndarray,
) -> tuple[dict[str, float], dict[str, float], bool]:
    """Evaluate both transforms on one immutable record window."""

    candidate_metrics = calibration_metrics(
        labels, apply_calibration(candidate_artifact, raw_scores)
    )
    incumbent_metrics = calibration_metrics(
        labels, apply_calibration(incumbent_artifact, raw_scores)
    )
    return (
        candidate_metrics,
        incumbent_metrics,
        challenger_meets_promotion_gates(candidate_metrics, incumbent_metrics),
    )


def evaluation_population_sha256(records: list[dict]) -> str:
    """Return the immutable identity of one ordered evaluation population."""

    return hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class FeedbackRecalibrationWorker:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="feedback-recalibration"
        )
        self._lock = Lock()
        self._lease_owner = f"feedback-recalibration-{secrets.token_hex(12)}"
        self._active: set[int] = set()
        self._futures: dict[int, Future[None]] = {}

    def submit(self, database_path: str | Path, decision_id: int) -> None:
        with self._lock:
            if decision_id in self._active:
                return
            self._active.add(decision_id)
            future = self._executor.submit(self._run, Path(database_path), decision_id)
            self._futures[decision_id] = future

    def _claim(self, path: Path, decision_id: int) -> str | None:
        moment = _now()
        stale_before = (
            datetime.now(timezone.utc)
            - timedelta(seconds=STALE_HEARTBEAT_SECONDS)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        token = secrets.token_hex(32)
        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT status,lease_owner,execution_lease_token,
                          lease_heartbeat_at,lease_claimed_at
                   FROM feedback_retraining_decisions
                   WHERE retraining_decision_id=?""",
                (decision_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "QUEUED":
                claimed = connection.execute(
                    """UPDATE feedback_retraining_decisions
                       SET status='TRAINING',execution_lease_token=?,lease_owner=?,
                           lease_claimed_at=?,lease_heartbeat_at=?
                       WHERE retraining_decision_id=? AND status='QUEUED'""",
                    (token, self._lease_owner, moment, moment, decision_id),
                )
                return token if claimed.rowcount == 1 else None
            if row["status"] != "TRAINING":
                return None
            heartbeat = row["lease_heartbeat_at"] or row["lease_claimed_at"]
            if row["lease_owner"] == self._lease_owner:
                token = str(row["execution_lease_token"])
            elif heartbeat is not None and str(heartbeat) > stale_before:
                return None
            claimed = connection.execute(
                """UPDATE feedback_retraining_decisions
                   SET execution_lease_token=?,lease_owner=?,lease_claimed_at=?,
                       lease_heartbeat_at=?,
                       trigger_reason=CASE WHEN lease_owner<>? THEN
                           'Interrupted recalibration recovered after its lease expired.'
                           ELSE trigger_reason END
                   WHERE retraining_decision_id=? AND status='TRAINING'
                     AND COALESCE(execution_lease_token,'')=COALESCE(?, '')""",
                (
                    token,
                    self._lease_owner,
                    moment,
                    moment,
                    self._lease_owner,
                    decision_id,
                    row["execution_lease_token"],
                ),
            )
            return token if claimed.rowcount == 1 else None

    def _heartbeat(self, path: Path, decision_id: int, token: str) -> bool:
        with get_connection(path, write=True) as connection:
            updated = connection.execute(
                """UPDATE feedback_retraining_decisions SET lease_heartbeat_at=?
                   WHERE retraining_decision_id=? AND status='TRAINING'
                     AND lease_owner=? AND execution_lease_token=?""",
                (_now(), decision_id, self._lease_owner, token),
            )
        return updated.rowcount == 1

    def _heartbeat_loop(
        self, path: Path, decision_id: int, token: str, stop: Event
    ) -> None:
        while not stop.wait(FEEDBACK_WORKER_HEARTBEAT_SECONDS):
            try:
                if not self._heartbeat(path, decision_id, token):
                    return
            except Exception:
                logger.exception(
                    "Feedback recalibration heartbeat failed | decision_id=%s",
                    decision_id,
                )

    def resume_durable_decisions(self, database_path: str | Path) -> int:
        """Schedule queued and genuinely stale work without stealing fresh leases."""

        path = Path(database_path)
        stale_before = (
            datetime.now(timezone.utc)
            - timedelta(seconds=STALE_HEARTBEAT_SECONDS)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        with get_connection(path) as connection:
            identifiers = [
                int(row["retraining_decision_id"])
                for row in connection.execute(
                    """SELECT retraining_decision_id FROM feedback_retraining_decisions
                       WHERE status='QUEUED'
                          OR (status='TRAINING' AND
                              COALESCE(lease_heartbeat_at,lease_claimed_at,'')<=?)
                       ORDER BY retraining_decision_id""",
                    (stale_before,),
                ).fetchall()
            ]
        for identifier in identifiers:
            self.submit(path, identifier)
        return len(identifiers)

    def _record_terminal_without_candidate(
        self,
        path: Path,
        decision_id: int,
        token: str,
        status: str,
        reason: str,
    ) -> None:
        with get_connection(path, write=True) as connection:
            connection.execute(
                """UPDATE feedback_retraining_decisions
                   SET status=?,trigger_reason=?,completed_at=?
                   WHERE retraining_decision_id=? AND status='TRAINING'
                     AND lease_owner=? AND execution_lease_token=?""",
                (status, reason, _now(), decision_id, self._lease_owner, token),
            )

    def _record_insufficient_topology(
        self,
        path: Path,
        decision_id: int,
        scoring_run_id: int,
        token: str,
        detail: str,
    ) -> None:
        safe_reason = (
            "Feedback remains waiting because its connected components cannot "
            "yet form leakage-safe fit and evaluation groups with both outcomes."
        )
        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            successor = connection.execute(
                """SELECT 1 FROM feedback_retraining_decisions
                   WHERE scoring_run_id=? AND status='WAITING_FOR_DATA'
                     AND retraining_decision_id<>? LIMIT 1""",
                (scoring_run_id, decision_id),
            ).fetchone()
            status = "REJECTED" if successor is not None else "WAITING_FOR_DATA"
            reason = safe_reason + (
                " Newer feedback is already reserved in the successor decision."
                if successor is not None
                else ""
            )
            connection.execute(
                """UPDATE feedback_retraining_decisions
                   SET status=?,trigger_reason=?,completed_at=?,
                       metrics_json=?
                   WHERE retraining_decision_id=? AND status='TRAINING'
                     AND lease_owner=? AND execution_lease_token=?""",
                (
                    status,
                    reason,
                    _now() if status == "REJECTED" else None,
                    json.dumps(
                        {
                            "operation": "RECALIBRATION",
                            "promotion_checks_passed": False,
                            "statistical_status": "INSUFFICIENT_FEEDBACK_TOPOLOGY",
                            "bounded_detail": detail[:500],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    decision_id,
                    self._lease_owner,
                    token,
                ),
            )

    def _run(self, path: Path, decision_id: int) -> None:
        token = self._claim(path, decision_id)
        if token is None:
            with self._lock:
                self._active.discard(decision_id)
                self._futures.pop(decision_id, None)
            return
        heartbeat_stop = Event()
        heartbeat_thread = Thread(
            target=self._heartbeat_loop,
            args=(path, decision_id, token, heartbeat_stop),
            name=f"feedback-heartbeat-{decision_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            with get_connection(path) as connection:
                decision = connection.execute(
                    """SELECT * FROM feedback_retraining_decisions
                       WHERE retraining_decision_id=? AND status='TRAINING'
                         AND lease_owner=? AND execution_lease_token=?""",
                    (decision_id, self._lease_owner, token),
                ).fetchone()
            if decision is None:
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
                             AND lease_owner=? AND execution_lease_token=?
                             AND latest_feedback_batch_id IS NULL""",
                        (
                            int(batch_cutoff), decision_id,
                            self._lease_owner, token,
                        ),
                    )
            batch_cutoff = int(batch_cutoff)
            with get_connection(path) as connection:
                rows = connection.execute(
                    """SELECT b.search_run_id,b.feedback_batch_id,o.person_id,
                              p.propensity_score,o.outcome,
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
                    """SELECT calibration_artifact_id,artifact_json
                       FROM score_calibration_artifacts
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
            partitions = model_lineage.get("partitions", {})
            model_groups = partitions.get("model_training", {}).get("group_ids", [])
            model_fit_groups = partitions.get("calibration_fit", {}).get(
                "group_ids", []
            )
            model_evaluation_groups = partitions.get(
                "calibration_evaluation", {}
            ).get("group_ids", [])
            if not model_groups or not model_fit_groups or not model_evaluation_groups:
                raise RuntimeError(
                    "Feedback recalibration requires complete model partition lineage."
                )
            grouping = build_feedback_grouping([dict(row) for row in rows])
            if (
                decision["feedback_grouping_contract_version"]
                not in (None, FEEDBACK_GROUPING_CONTRACT_VERSION)
                or decision["feedback_grouping_sha256"]
                not in (None, grouping.grouping_sha256)
            ):
                raise RuntimeError(
                    "The immutable feedback grouping boundary changed unexpectedly."
                )
            try:
                fitted = fit_held_out_calibration(
                    np.asarray([row["propensity_score"] for row in rows]),
                    np.asarray([row["outcome"] for row in rows]),
                    np.asarray(grouping.row_group_ids),
                    model_training_group_ids=tuple(str(value) for value in model_groups),
                    model_calibration_fit_group_ids=tuple(
                        str(value) for value in model_fit_groups
                    ),
                    model_calibration_evaluation_group_ids=tuple(
                        str(value) for value in model_evaluation_groups
                    ),
                    model_partition_seed=model_lineage.get("seed"),
                    model_validation_fraction=model_lineage.get(
                        "validation_fraction"
                    ),
                )
            except PropensityCalibrationError as exc:
                self._record_insufficient_topology(
                    path, decision_id, scoring_run_id, token, str(exc)
                )
                return
            evaluation_groups = set(
                fitted.split_lineage[
                    "statistical_calibration_evaluation_group_ids"
                ]
            )
            evaluation_indexes = [
                index
                for index, group_id in enumerate(grouping.row_group_ids)
                if group_id in evaluation_groups
            ]
            evaluation_scores = np.asarray(
                [rows[index]["propensity_score"] for index in evaluation_indexes],
                dtype=np.float64,
            )
            evaluation_labels = np.asarray(
                [rows[index]["outcome"] for index in evaluation_indexes],
                dtype=np.int8,
            )
            population_identity = [
                {
                    "feedback_batch_id": int(rows[index]["feedback_batch_id"]),
                    "search_run_id": int(rows[index]["search_run_id"]),
                    "person_id": str(rows[index]["person_id"]),
                    "outcome": int(rows[index]["outcome"]),
                    "raw_score": float(rows[index]["propensity_score"]),
                }
                for index in evaluation_indexes
            ]
            evaluation_population_identity = evaluation_population_sha256(
                population_identity
            )
            evaluation_group_ids_sha256 = hashlib.sha256(
                json.dumps(
                    sorted(evaluation_groups), separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            fitted = replace(
                fitted,
                split_lineage={
                    **fitted.split_lineage,
                    "feedback_grouping_contract_version": FEEDBACK_GROUPING_CONTRACT_VERSION,
                    "feedback_grouping_sha256": grouping.grouping_sha256,
                    "feedback_batch_cutoff": batch_cutoff,
                    "evaluation_population_sha256": evaluation_population_identity,
                    "evaluation_group_ids_sha256": evaluation_group_ids_sha256,
                },
            )
            if incumbent is None:
                self._record_terminal_without_candidate(
                    path,
                    decision_id,
                    token,
                    "REJECTED",
                    "A promoted incumbent calibration is required for governed recalibration.",
                )
                return
            incumbent_artifact = json.loads(str(incumbent["artifact_json"]))
            candidate, incumbent_metrics, promote = (
                compare_calibrations_on_evaluation_window(
                    fitted.artifact,
                    incumbent_artifact,
                    evaluation_scores,
                    evaluation_labels,
                )
            )
            source_checksum = hashlib.sha256("".join(sorted({str(row["payload_sha256"]) for row in rows})).encode()).hexdigest()
            if not self._heartbeat(path, decision_id, token):
                return
            published = publish_fitted_calibration(
                path, scoring_run_id, fitted, source_checksum=source_checksum, promote=promote,
            )
            outcome = "PROMOTED" if promote else "REJECTED"
            comparison = {
                "candidate": candidate, "incumbent": incumbent_metrics,
                "promotion_checks_passed": promote,
                "promotion_checks": {
                    "brier_improved": (
                        candidate["brier_score"] < incumbent_metrics["brier_score"]
                    ),
                    "roc_auc_non_regression": (
                        candidate["roc_auc"] >= incumbent_metrics["roc_auc"] - 0.01
                    ),
                    "average_precision_non_regression": (
                        candidate["average_precision"]
                        >= incumbent_metrics["average_precision"] - 0.01
                    ),
                    "top_decile_lift_non_regression": (
                        candidate["top_decile_lift"]
                        >= incumbent_metrics["top_decile_lift"]
                    ),
                },
                "operation": "RECALIBRATION",
                "model_run_id": int(model["model_run_id"]),
                "model_created": False,
                "raw_scores_reused": True,
                "feedback_batch_cutoff": batch_cutoff,
                "evaluation_record_count": len(evaluation_indexes),
                "evaluation_positive_count": int(evaluation_labels.sum()),
                "evaluation_negative_count": int(
                    evaluation_labels.size - evaluation_labels.sum()
                ),
                "evaluation_group_ids_sha256": evaluation_group_ids_sha256,
                "evaluation_population_sha256": evaluation_population_identity,
                "feedback_grouping_contract_version": FEEDBACK_GROUPING_CONTRACT_VERSION,
                "feedback_grouping_sha256": grouping.grouping_sha256,
                "candidate_calibration_artifact_id": int(
                    published["calibration_artifact_id"]
                ),
                "incumbent_calibration_artifact_id": int(
                    incumbent["calibration_artifact_id"]
                ),
            }
            with get_connection(path, write=True) as connection:
                completed = connection.execute(
                    """UPDATE feedback_retraining_decisions
                       SET status=?,incumbent_calibration_artifact_id=?,
                           candidate_calibration_artifact_id=?,metrics_json=?,completed_at=datetime('now')
                       WHERE retraining_decision_id=? AND status='TRAINING'
                         AND lease_owner=? AND execution_lease_token=?""",
                    (outcome, int(incumbent["calibration_artifact_id"]) if incumbent else None,
                     int(published["calibration_artifact_id"]),
                      json.dumps(comparison, sort_keys=True, separators=(",", ":")),
                      decision_id, self._lease_owner, token),
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
                       WHERE retraining_decision_id=? AND status='TRAINING'
                         AND lease_owner=? AND execution_lease_token=?""",
                    (decision_id, self._lease_owner, token),
                )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
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
                       distinct_run_count=?,independent_feedback_group_count=?,
                       feedback_grouping_contract_version=?,feedback_grouping_sha256=?,
                       new_label_ratio=?,
                       population_stability_index=?,trigger_reason=?,
                       reference_decision_id=?,drift_lineage_json=?,completed_at=NULL
                   WHERE retraining_decision_id=? AND status='WAITING_FOR_DATA'""",
                (
                    status,
                    facts["labels"],
                    facts["positives"],
                    facts["negatives"],
                    facts["runs"],
                    facts["independent_groups"],
                    facts["feedback_grouping_contract_version"],
                    facts["feedback_grouping_sha256"],
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
    "compare_calibrations_on_evaluation_window",
    "evaluation_population_sha256",
)
