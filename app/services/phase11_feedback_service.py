"""Governed purchase-outcome ingestion and adaptive retraining eligibility."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Iterable, Mapping

from app.database.connection import get_connection
from app.database.schema import initialize_database


MAX_FEEDBACK_ROWS = 100_000
FEEDBACK_CSV_TEMPLATE = (
    "person_id,outcome,outcome_at,outcome_value\n"
    "REPLACE_WITH_PERSON_ID,1,2026-01-31T23:59:59Z,125.50\n"
    "REPLACE_WITH_ANOTHER_PERSON_ID,0,2026-01-31T23:59:59Z,\n"
)
FEEDBACK_JSON_TEMPLATE = {
    "source_name": "replace-with-source-name",
    "rows": [
        {
            "person_id": "REPLACE_WITH_PERSON_ID",
            "outcome": 1,
            "outcome_at": "2026-01-31T23:59:59Z",
            "outcome_value": 125.50,
        },
        {
            "person_id": "REPLACE_WITH_ANOTHER_PERSON_ID",
            "outcome": 0,
            "outcome_at": "2026-01-31T23:59:59Z",
        },
    ],
}
FeedbackRetrainingExecutor = Callable[[Path, int], None]
FEEDBACK_RETRAINING_EXECUTOR: FeedbackRetrainingExecutor | None = None


def configure_feedback_retraining_executor(executor: FeedbackRetrainingExecutor | None) -> None:
    global FEEDBACK_RETRAINING_EXECUTOR
    FEEDBACK_RETRAINING_EXECUTOR = executor


class FeedbackValidationError(ValueError):
    pass


class FeedbackConflictError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_feedback_csv(payload: bytes) -> list[dict[str, Any]]:
    if len(payload) > 10 * 1024 * 1024:
        raise FeedbackValidationError("Feedback CSV exceeds the 10 MB limit.")
    try:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
    except UnicodeError as exc:
        raise FeedbackValidationError("Feedback CSV must be UTF-8.") from exc
    required = {"person_id", "outcome", "outcome_at"}
    if not required.issubset(reader.fieldnames or ()):
        raise FeedbackValidationError("Feedback CSV requires person_id, outcome, and outcome_at columns.")
    return [dict(row) for row in reader]


def _normalize_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if index > MAX_FEEDBACK_ROWS:
            raise FeedbackValidationError("Feedback batches are limited to 100,000 rows.")
        if not isinstance(row, Mapping):
            raise FeedbackValidationError("Every feedback row must be an object.")
        person_id = str(row.get("person_id", "")).strip()
        if not person_id or len(person_id) > 200 or person_id in seen:
            raise FeedbackValidationError("Feedback person identifiers must be unique and bounded.")
        raw_outcome = row.get("outcome")
        if isinstance(raw_outcome, str):
            raw_outcome = raw_outcome.strip().lower()
            raw_outcome = {"1": 1, "true": 1, "yes": 1, "0": 0, "false": 0, "no": 0}.get(raw_outcome)
        if raw_outcome not in {0, 1, False, True}:
            raise FeedbackValidationError("Feedback outcomes must be boolean or 0/1.")
        raw_timestamp = row.get("outcome_at")
        try:
            parsed = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise FeedbackValidationError("Feedback timestamps cannot be in the future.")
            outcome_at = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except FeedbackValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise FeedbackValidationError("Feedback timestamps must include a timezone.") from exc
        raw_value = row.get("outcome_value")
        if raw_value in {None, ""}:
            outcome_value = None
        else:
            try:
                outcome_value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise FeedbackValidationError("Outcome values must be finite numbers.") from exc
            if not math.isfinite(outcome_value):
                raise FeedbackValidationError("Outcome values must be finite numbers.")
        normalized.append({
            "person_id": person_id, "outcome": int(bool(raw_outcome)),
            "outcome_at": outcome_at, "outcome_value": outcome_value,
        })
        seen.add(person_id)
    if not normalized:
        raise FeedbackValidationError("Feedback requires at least one row.")
    return normalized


def _snapshot_members(project_root: Path, storage_uri: str, requested: set[str]) -> set[str]:
    artifact = (project_root / storage_uri).resolve()
    if not artifact.is_relative_to(project_root) or not artifact.is_file():
        raise FeedbackConflictError("The immutable result membership is unavailable.")
    found: set[str] = set()
    with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            person_id = row.get("person_id")
            if person_id in requested:
                found.add(str(person_id))
                if len(found) == len(requested):
                    break
    return found


def evaluate_adaptive_feedback_gate(
    *,
    labels: int,
    positives: int,
    negatives: int,
    runs: int,
    new_label_ratio: float,
    population_stability_index: float,
) -> tuple[str, str]:
    """Apply the version-one governed threshold without database side effects."""

    floor_met = labels >= 1_000 and positives >= 100 and negatives >= 100 and runs >= 2
    adaptive_met = new_label_ratio >= .10 or population_stability_index >= .20
    if floor_met and adaptive_met:
        return "QUEUED", "Adaptive feedback threshold reached; challenger preparation queued."
    return (
        "WAITING_FOR_DATA",
        "Waiting for 1,000 labels, both outcome classes, two runs, and sufficient new information.",
    )


def _adaptive_gate(connection, scoring_run_id: int) -> tuple[str, str, dict[str, float | int]]:
    counts = connection.execute(
        """SELECT COUNT(*) AS labels,
                  SUM(o.outcome) AS positives,
                  COUNT(*)-SUM(o.outcome) AS negatives,
                  COUNT(DISTINCT b.search_run_id) AS runs
           FROM campaign_feedback_outcomes AS o
           JOIN campaign_feedback_batches AS b ON b.feedback_batch_id=o.feedback_batch_id
           JOIN campaign_search_runs AS r ON r.search_run_id=b.search_run_id
           WHERE b.status='ACCEPTED' AND r.scoring_run_id=?""",
        (scoring_run_id,),
    ).fetchone()
    labels = int(counts["labels"] or 0)
    positives = int(counts["positives"] or 0)
    negatives = int(counts["negatives"] or 0)
    runs = int(counts["runs"] or 0)
    previous = connection.execute(
        """SELECT label_count FROM feedback_retraining_decisions
           WHERE scoring_run_id=? AND status='PROMOTED'
           ORDER BY retraining_decision_id DESC LIMIT 1""",
        (scoring_run_id,),
    ).fetchone()
    previous_labels = int(previous["label_count"]) if previous else 0
    new_ratio = 1.0 if previous_labels == 0 else max(0.0, (labels - previous_labels) / previous_labels)
    calibration = connection.execute(
        """SELECT calibration_artifact_id FROM score_calibration_artifacts
           WHERE scoring_run_id=? AND status='PROMOTED' ORDER BY promoted_at DESC LIMIT 1""",
        (scoring_run_id,),
    ).fetchone()
    psi = 0.0
    if calibration is not None and labels:
        calibration_id = int(calibration["calibration_artifact_id"])
        base_rows = connection.execute(
            "SELECT bin_number,population_count FROM calibration_distribution_bins WHERE calibration_artifact_id=?",
            (calibration_id,),
        ).fetchall()
        sample_rows = connection.execute(
            """SELECT MIN(9,CAST(p.calibrated_probability*10 AS INTEGER)) AS bin_number,COUNT(*) AS count
               FROM campaign_feedback_outcomes AS o
               JOIN campaign_feedback_batches AS b ON b.feedback_batch_id=o.feedback_batch_id
               JOIN campaign_search_runs AS r ON r.search_run_id=b.search_run_id
               JOIN calibrated_propensity_scores AS p
                 ON p.calibration_artifact_id=? AND p.person_id=o.person_id
               WHERE b.status='ACCEPTED' AND r.scoring_run_id=? GROUP BY bin_number""",
            (calibration_id, scoring_run_id),
        ).fetchall()
        base = {int(row["bin_number"]): int(row["population_count"]) for row in base_rows}
        sample = {int(row["bin_number"]): int(row["count"]) for row in sample_rows}
        base_total = max(1, sum(base.values()))
        sample_total = max(1, sum(sample.values()))
        for bin_number in range(10):
            base_share = max(1e-6, base.get(bin_number, 0) / base_total)
            sample_share = max(1e-6, sample.get(bin_number, 0) / sample_total)
            psi += (sample_share - base_share) * math.log(sample_share / base_share)
    facts = {
        "labels": labels, "positives": positives, "negatives": negatives,
        "runs": runs, "new_label_ratio": new_ratio, "population_stability_index": psi,
    }
    status, reason = evaluate_adaptive_feedback_gate(
        labels=labels,
        positives=positives,
        negatives=negatives,
        runs=runs,
        new_label_ratio=new_ratio,
        population_stability_index=psi,
    )
    return status, reason, facts


def ingest_feedback(
    database_path: str | Path,
    search_run_id: int,
    *,
    rows: Iterable[Mapping[str, Any]],
    source_name: str,
    idempotency_key: str,
    project_root: str | Path,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    root = Path(project_root).resolve()
    if not source_name.strip() or len(source_name.strip()) > 120:
        raise FeedbackValidationError("Feedback source name is required.")
    if not idempotency_key.strip() or len(idempotency_key.strip()) > 200:
        raise FeedbackValidationError("A bounded idempotency key is required.")
    normalized = _normalize_rows(rows)
    canonical = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with get_connection(path) as connection:
        run = connection.execute(
            """SELECT r.*,s.storage_uri FROM campaign_search_runs AS r
               JOIN campaign_result_snapshots AS s ON s.result_snapshot_id=r.result_snapshot_id
               WHERE r.search_run_id=?""",
            (search_run_id,),
        ).fetchone()
        existing = connection.execute(
            "SELECT * FROM campaign_feedback_batches WHERE search_run_id=? AND idempotency_key=?",
            (search_run_id, idempotency_key.strip()),
        ).fetchone()
    if run is None or run["status"] != "COMPLETED":
        raise FeedbackConflictError("Feedback is accepted only for a completed immutable result.")
    if existing is not None:
        if existing["payload_sha256"] != checksum:
            raise FeedbackConflictError("The idempotency key was already used for different feedback.")
        return _project_batch(path, dict(existing))
    requested = {row["person_id"] for row in normalized}
    found = _snapshot_members(root, str(run["storage_uri"]), requested)
    if found != requested:
        raise FeedbackValidationError("Every feedback person must belong to the immutable result snapshot.")
    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        marks = ",".join("?" for _ in requested)
        duplicate = connection.execute(
            f"""SELECT 1 FROM campaign_feedback_outcomes AS o
                 JOIN campaign_feedback_batches AS b ON b.feedback_batch_id=o.feedback_batch_id
                 WHERE b.search_run_id=? AND o.person_id IN ({marks}) LIMIT 1""",
            (search_run_id, *sorted(requested)),
        ).fetchone()
        if duplicate is not None:
            raise FeedbackConflictError("Feedback for one or more members was already recorded for this search.")
        now = _now()
        positives = sum(row["outcome"] for row in normalized)
        batch_id = int(connection.execute(
            """INSERT INTO campaign_feedback_batches (
                   search_run_id,attempt_number,outcome_definition,source_name,
                   idempotency_key,payload_sha256,row_count,positive_count,
                   negative_count,status,created_at
               ) VALUES (?,?,'ATTRIBUTED_PURCHASE',?,?,?,?,?,?, 'ACCEPTED',?)""",
            (search_run_id, int(run["current_attempt_number"]), source_name.strip(),
             idempotency_key.strip(), checksum, len(normalized), positives,
             len(normalized)-positives, now),
        ).lastrowid)
        connection.executemany(
            """INSERT INTO campaign_feedback_outcomes (
                   feedback_batch_id,person_id,outcome,outcome_at,outcome_value
               ) VALUES (?,?,?,?,?)""",
            ((batch_id, row["person_id"], row["outcome"], row["outcome_at"], row["outcome_value"])
             for row in normalized),
        )
        connection.execute(
            """UPDATE campaign_search_future_lineage
               SET feedback_batch_id=COALESCE(feedback_batch_id,?),
                   outcome_dataset_id=COALESCE(outcome_dataset_id,?),updated_at=?
               WHERE search_run_id=?""",
            (str(batch_id), f"feedback:{batch_id}:{checksum}", now, search_run_id),
        )
        gate_status, gate_reason, facts = _adaptive_gate(connection, int(run["scoring_run_id"]))
        decision_id = int(connection.execute(
            """INSERT INTO feedback_retraining_decisions (
                   decision_contract_version,scoring_run_id,status,label_count,positive_count,
                   negative_count,distinct_run_count,new_label_ratio,
                   population_stability_index,trigger_reason,created_at
               ) VALUES ('1',?,?,?,?,?,?,?,?,?,?)""",
            (int(run["scoring_run_id"]), gate_status, facts["labels"], facts["positives"], facts["negatives"],
             facts["runs"], facts["new_label_ratio"], facts["population_stability_index"],
             gate_reason, now),
        ).lastrowid)
        row = dict(connection.execute(
            "SELECT * FROM campaign_feedback_batches WHERE feedback_batch_id=?", (batch_id,)
        ).fetchone())
    if gate_status == "QUEUED" and FEEDBACK_RETRAINING_EXECUTOR is not None:
        FEEDBACK_RETRAINING_EXECUTOR(path, decision_id)
    return _project_batch(path, row)


def _project_batch(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    with get_connection(path) as connection:
        scoring = connection.execute(
            "SELECT scoring_run_id FROM campaign_search_runs WHERE search_run_id=?",
            (int(row["search_run_id"]),),
        ).fetchone()
        decision = connection.execute(
            """SELECT status,trigger_reason FROM feedback_retraining_decisions
               WHERE scoring_run_id=? ORDER BY retraining_decision_id DESC LIMIT 1""",
            (int(scoring["scoring_run_id"]),),
        ).fetchone() if scoring is not None and scoring["scoring_run_id"] is not None else None
    return {
        "feedback_batch_id": int(row["feedback_batch_id"]),
        "search_run_id": int(row["search_run_id"]),
        "attempt_number": int(row["attempt_number"]), "status": str(row["status"]),
        "row_count": int(row["row_count"]), "positive_count": int(row["positive_count"]),
        "negative_count": int(row["negative_count"]), "created_at": str(row["created_at"]),
        "retraining_status": str(decision["status"]) if decision else "WAITING_FOR_DATA",
        "retraining_reason": str(decision["trigger_reason"]) if decision else "Waiting for governed feedback.",
    }


def list_feedback(database_path: str | Path, search_run_id: int) -> list[dict[str, Any]]:
    path = initialize_database(database_path)
    with get_connection(path) as connection:
        rows = connection.execute(
            "SELECT * FROM campaign_feedback_batches WHERE search_run_id=? ORDER BY feedback_batch_id",
            (search_run_id,),
        ).fetchall()
    return [_project_batch(path, dict(row)) for row in rows]


__all__ = (
    "FEEDBACK_CSV_TEMPLATE", "FEEDBACK_JSON_TEMPLATE",
    "FeedbackConflictError", "FeedbackValidationError",
    "configure_feedback_retraining_executor", "evaluate_adaptive_feedback_gate",
    "ingest_feedback", "list_feedback", "parse_feedback_csv",
)
