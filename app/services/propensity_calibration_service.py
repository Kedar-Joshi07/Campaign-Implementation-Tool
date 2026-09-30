"""Held-out propensity calibration and immutable calibrated score publication."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.phase10_intelligence_repository import Phase10IntelligenceRepository
from app.services.intelligence_attestation_service import (
    has_current_attestation,
    record_deep_verification_attestation,
)
from app.services.model_scoring_compatibility import (
    transform_and_score_prospect_chunk,
    validate_scoreable_model,
)
from app.services.training_cohort_service import reconstruct_training_cohort
from app.services.calibrated_selection_contract_service import PROPENSITY_BUCKETS
from app.ml.preprocessing import split_customer_cohort
from app.ml.campaign_group_split import (
    CALIBRATION_EVALUATION,
    CALIBRATION_FIT,
    MODEL_TRAINING,
    SPLIT_STRATEGY_VERSION,
    build_campaign_group_partition,
)


CALIBRATION_CONTRACT_VERSION = "2"
CALIBRATION_SPLIT_SEED = 1729
class PropensityCalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class FittedCalibration:
    method: str
    artifact: dict[str, Any]
    metrics: dict[str, Any]
    split_lineage: dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ece(labels: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    value = 0.0
    for lower in np.linspace(0.0, 1.0, bins, endpoint=False):
        upper = lower + 1.0 / bins
        mask = (probabilities >= lower) & (probabilities < upper if upper < 1 else probabilities <= upper)
        if mask.any():
            value += float(mask.mean()) * abs(float(probabilities[mask].mean()) - float(labels[mask].mean()))
    return value


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    clipped = np.clip(probabilities, 1e-9, 1 - 1e-9)
    order = np.lexsort((np.arange(labels.size), -clipped))
    top_n = max(1, math.ceil(labels.size * .10))
    prevalence = float(labels.mean())
    lift = float(labels[order[:top_n]].mean() / prevalence) if prevalence > 0 else 0.0
    return {
        "brier_score": float(brier_score_loss(labels, clipped)),
        "log_loss": float(log_loss(labels, clipped, labels=[0, 1])),
        "expected_calibration_error": _ece(labels, clipped),
        "roc_auc": float(roc_auc_score(labels, clipped)),
        "average_precision": float(average_precision_score(labels, clipped)),
        "top_decile_lift": lift,
    }


def has_governed_calibration_lineage(lineage: dict[str, Any]) -> bool:
    overlaps = lineage.get("overlap_counts")
    partitions = (
        set(lineage.get("model_training_group_ids", ())),
        set(lineage.get("calibration_fit_group_ids", ())),
        set(lineage.get("calibration_evaluation_group_ids", ())),
    )
    balances = (
        lineage.get("calibration_fit_class_balance"),
        lineage.get("calibration_evaluation_class_balance"),
    )
    return bool(
        lineage.get("three_way_isolated") is True
        and lineage.get("strategy_version") == SPLIT_STRATEGY_VERSION
        and lineage.get("candidate_selection_partition")
        == "calibration_evaluation"
        and lineage.get("evaluation_records_used_for_fit") == 0
        and isinstance(overlaps, dict)
        and overlaps
        and all(value == 0 for value in overlaps.values())
        and all(partitions)
        and not partitions[0].intersection(partitions[1] | partitions[2])
        and not partitions[1].intersection(partitions[2])
        and all(
            isinstance(balance, dict)
            and int(balance.get("positive", 0)) > 0
            and int(balance.get("negative", 0)) > 0
            for balance in balances
        )
    )


def apply_calibration(artifact: dict[str, Any], raw_scores: np.ndarray) -> np.ndarray:
    scores = np.asarray(raw_scores, dtype=np.float64)
    if artifact.get("method") == "SIGMOID":
        linear = float(artifact["coefficient"]) * scores + float(artifact["intercept"])
        return 1.0 / (1.0 + np.exp(-np.clip(linear, -700, 700)))
    if artifact.get("method") == "ISOTONIC":
        return np.interp(
            scores,
            np.asarray(artifact["x_thresholds"], dtype=np.float64),
            np.asarray(artifact["y_thresholds"], dtype=np.float64),
        )
    raise PropensityCalibrationError("Unsupported calibration artifact.")


def fit_held_out_calibration(
    raw_scores: list[float] | np.ndarray,
    outcomes: list[int] | np.ndarray,
    group_ids: list[str] | np.ndarray,
    *,
    seed: int = CALIBRATION_SPLIT_SEED,
    calibration_fit_group_ids: list[str] | tuple[str, ...] | None = None,
    calibration_evaluation_group_ids: list[str] | tuple[str, ...] | None = None,
    model_training_group_ids: list[str] | tuple[str, ...] = (),
) -> FittedCalibration:
    scores = np.asarray(raw_scores, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.int8)
    groups = np.asarray(group_ids, dtype=str)
    if scores.ndim != 1 or labels.shape != scores.shape or groups.shape != scores.shape:
        raise PropensityCalibrationError("Calibration inputs must have matching one-dimensional shapes.")
    if scores.size < 200 or not np.isfinite(scores).all() or (scores < 0).any() or (scores > 1).any():
        raise PropensityCalibrationError("Calibration requires at least 200 finite unit-interval scores.")
    if set(np.unique(labels)) != {0, 1}:
        raise PropensityCalibrationError("Calibration requires positive and negative outcomes.")
    unique_groups = np.unique(groups)
    if unique_groups.size < 2:
        raise PropensityCalibrationError("Calibration requires at least two independent campaign groups.")
    if (calibration_fit_group_ids is None) != (
        calibration_evaluation_group_ids is None
    ):
        raise PropensityCalibrationError(
            "Both calibration partition group lists must be supplied together."
        )
    if calibration_fit_group_ids is None:
        shuffled = unique_groups.copy()
        np.random.default_rng(seed).shuffle(shuffled)
        calibration_groups = set(shuffled[: max(1, shuffled.size // 2)])
        evaluation_groups = set(shuffled) - calibration_groups
    else:
        calibration_groups = set(calibration_fit_group_ids)
        evaluation_groups = set(calibration_evaluation_group_ids or ())
        if calibration_groups | evaluation_groups != set(unique_groups):
            raise PropensityCalibrationError(
                "Persisted calibration partitions do not exactly cover held-out groups."
            )
    model_groups = set(model_training_group_ids)
    overlap_counts = {
        "model_training_calibration_fit": len(model_groups & calibration_groups),
        "model_training_calibration_evaluation": len(model_groups & evaluation_groups),
        "calibration_fit_calibration_evaluation": len(
            calibration_groups & evaluation_groups
        ),
    }
    if any(overlap_counts.values()):
        raise PropensityCalibrationError(
            "Model, calibration-fit, and calibration-evaluation groups must not overlap."
        )
    calibration_mask = np.asarray([value in calibration_groups for value in groups])
    test_mask = np.asarray([value in evaluation_groups for value in groups])
    if not calibration_mask.all() and not (calibration_mask | test_mask).all():
        raise PropensityCalibrationError("A held-out record has no governed partition.")
    if len(np.unique(labels[calibration_mask])) < 2 or len(np.unique(labels[test_mask])) < 2:
        raise PropensityCalibrationError("The deterministic grouped split lacks both outcome classes.")

    sigmoid = LogisticRegression(random_state=seed, solver="lbfgs")
    sigmoid.fit(scores[calibration_mask].reshape(-1, 1), labels[calibration_mask])
    sigmoid_artifact = {
        "method": "SIGMOID",
        "coefficient": float(sigmoid.coef_[0, 0]),
        "intercept": float(sigmoid.intercept_[0]),
    }
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    isotonic.fit(scores[calibration_mask], labels[calibration_mask])
    isotonic_artifact = {
        "method": "ISOTONIC",
        "x_thresholds": [float(value) for value in isotonic.X_thresholds_],
        "y_thresholds": [float(value) for value in isotonic.y_thresholds_],
    }
    candidates = []
    for artifact in (sigmoid_artifact, isotonic_artifact):
        probabilities = apply_calibration(artifact, scores[test_mask])
        candidates.append((artifact, _metrics(labels[test_mask], probabilities)))
    artifact, metrics = min(
        candidates,
        key=lambda item: (item[1]["brier_score"], item[1]["log_loss"], item[0]["method"]),
    )
    return FittedCalibration(
        method=str(artifact["method"]), artifact=artifact, metrics=metrics,
        split_lineage={
            "seed": seed,
            "strategy": SPLIT_STRATEGY_VERSION,
            "strategy_version": SPLIT_STRATEGY_VERSION,
            "calibration_count": int(calibration_mask.sum()),
            "test_count": int(test_mask.sum()),
            "calibration_group_count": len(calibration_groups),
            "test_group_count": len(evaluation_groups),
            "model_training_group_count": len(model_groups),
            "model_training_group_ids": sorted(model_groups),
            "calibration_fit_group_ids": sorted(calibration_groups),
            "calibration_evaluation_group_ids": sorted(evaluation_groups),
            "model_training_group_ids_sha256": hashlib.sha256(
                json.dumps(sorted(model_groups), separators=(",", ":")).encode()
            ).hexdigest(),
            "calibration_fit_group_ids_sha256": hashlib.sha256(
                json.dumps(sorted(calibration_groups), separators=(",", ":")).encode()
            ).hexdigest(),
            "calibration_evaluation_group_ids_sha256": hashlib.sha256(
                json.dumps(sorted(evaluation_groups), separators=(",", ":")).encode()
            ).hexdigest(),
            "overlap_counts": overlap_counts,
            "group_overlap_count": sum(overlap_counts.values()),
            "calibration_fit_class_balance": {
                "positive": int(labels[calibration_mask].sum()),
                "negative": int(calibration_mask.sum() - labels[calibration_mask].sum()),
            },
            "calibration_evaluation_class_balance": {
                "positive": int(labels[test_mask].sum()),
                "negative": int(test_mask.sum() - labels[test_mask].sum()),
            },
            "candidate_selection_partition": "calibration_evaluation",
            "evaluation_records_used_for_fit": 0,
            "three_way_isolated": bool(model_groups),
        },
    )


def _load_observed_outcomes(
    path: Path, scoring_run_id: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Score only the model's held-out historical customers for calibration.

    Prospect identifiers and historical customer identifiers are deliberately
    different namespaces. Calibration therefore reconstructs the exact governed
    historical cohort, reproduces the model's persisted train/validation split,
    and uses only that untouched validation partition. It never joins outcomes
    to the five-million-row prospect score table by identifier.
    """

    with get_connection(path) as connection:
        scoring = connection.execute(
            """SELECT s.model_run_id,m.analysis_run_id,m.random_seed,
                      m.validation_fraction,m.split_lineage_json
               FROM scoring_runs AS s
               JOIN model_runs AS m ON m.model_run_id=s.model_run_id
               WHERE s.scoring_run_id=? AND s.status='COMPLETED'
                 AND m.status='COMPLETED'""",
            (scoring_run_id,),
        ).fetchone()
    if scoring is None:
        raise PropensityCalibrationError("Completed scoring and model lineage are required.")
    cohort = reconstruct_training_cohort(path, int(scoring["analysis_run_id"]))
    if cohort.conversion_definition != "ATTRIBUTED_PURCHASE":
        raise PropensityCalibrationError(
            "Calibration requires an attributed-purchase historical outcome."
        )
    split = split_customer_cohort(
        cohort.frame,
        validation_fraction=float(scoring["validation_fraction"]),
        random_seed=int(scoring["random_seed"]),
        campaign_memberships=cohort.campaign_memberships,
    )
    if scoring["split_lineage_json"] is None:
        raise PropensityCalibrationError(
            "The model predates campaign-group isolation and cannot be calibrated safely."
        )
    persisted_lineage = json.loads(str(scoring["split_lineage_json"]))
    if persisted_lineage != split.split_lineage:
        raise PropensityCalibrationError(
            "Reconstructed campaign-group lineage does not match the model run."
        )
    model = validate_scoreable_model(path, int(scoring["model_run_id"]))
    scores = transform_and_score_prospect_chunk(
        artifact_payload=model.artifact_payload,
        raw_features=split.validation_features,
    )
    grouped = build_campaign_group_partition(
        cohort.frame,
        cohort.campaign_memberships,
        seed=int(scoring["random_seed"]),
        validation_fraction=float(scoring["validation_fraction"]),
    )
    groups_by_customer = dict(
        zip(
            cohort.frame["customer_id"].astype(str),
            grouped.customer_group_ids.astype(str),
            strict=True,
        )
    )
    validation_ids = [str(value) for value in split.validation_customer_ids]
    if any(identifier not in groups_by_customer for identifier in validation_ids):
        raise PropensityCalibrationError(
            "Held-out outcomes do not have complete campaign-group lineage."
        )
    labels = np.asarray(split.validation_labels, dtype=np.int8)
    if scores.shape != labels.shape:
        raise PropensityCalibrationError("Held-out model scores do not match outcomes.")
    return (
        scores,
        labels,
        np.asarray(
            [groups_by_customer[identifier] for identifier in validation_ids],
            dtype=str,
        ),
        persisted_lineage,
    )


def publish_fitted_calibration(
    database_path: str | Path,
    scoring_run_id: int,
    fitted: FittedCalibration,
    *,
    source_checksum: str,
    promote: bool,
    batch_size: int = 50_000,
) -> dict[str, Any]:
    """Persist a fitted candidate and, when approved, publish all calibrated scores."""

    path = initialize_database(database_path)
    if promote and not has_governed_calibration_lineage(fitted.split_lineage):
        raise PropensityCalibrationError(
            "Calibration promotion requires isolated model, fit, and evaluation groups."
        )
    artifact_json = json.dumps(fitted.artifact, sort_keys=True, separators=(",", ":"))
    metrics_json = json.dumps(fitted.metrics, sort_keys=True, separators=(",", ":"))
    split_json = json.dumps(fitted.split_lineage, sort_keys=True, separators=(",", ":"))
    with get_connection(path) as connection:
        scoring = connection.execute(
            "SELECT model_run_id,scored_person_count,artifact_sha256 FROM scoring_runs WHERE scoring_run_id=? AND status='COMPLETED'",
            (scoring_run_id,),
        ).fetchone()
    if scoring is None or len(source_checksum) != 64:
        raise PropensityCalibrationError("Completed scoring and a governed source checksum are required.")
    generation = next(
        (
            item
            for item in Phase10IntelligenceRepository(path).list_all_generations()
            if item.get("scoring_run_id") == scoring_run_id
            and item.get("generation_status") == "READY"
        ),
        None,
    )
    if promote:
        if generation is None:
            raise PropensityCalibrationError(
                "A ready intelligence generation is required before calibration promotion."
            )
        if not has_current_attestation(path, generation):
            attestation = record_deep_verification_attestation(path, generation)
            if attestation["status"] != "VERIFIED":
                raise PropensityCalibrationError(
                    "The scoring generation failed deep verification."
                )
    artifact_sha = hashlib.sha256(
        (artifact_json + metrics_json + split_json + str(scoring["artifact_sha256"]) + source_checksum).encode("utf-8")
    ).hexdigest()
    now = _now()
    with get_connection(path, write=True) as connection:
        existing = connection.execute(
            """SELECT calibration_artifact_id,status FROM score_calibration_artifacts
               WHERE scoring_run_id=? AND artifact_sha256=?""",
            (scoring_run_id, artifact_sha),
        ).fetchone()
        if existing is None:
            calibration_id = int(connection.execute(
                """INSERT INTO score_calibration_artifacts (
                       calibration_contract_version,scoring_run_id,model_run_id,outcome_definition,
                       method,split_seed,split_lineage_json,artifact_json,metrics_json,
                       artifact_sha256,source_checksum,status,created_at
                   ) VALUES (?, ?,?,?,?,?,?,?,?,?,?,?,?)""",
                (CALIBRATION_CONTRACT_VERSION, scoring_run_id, int(scoring["model_run_id"]), "ATTRIBUTED_PURCHASE",
                 fitted.method, int(fitted.split_lineage.get("seed", CALIBRATION_SPLIT_SEED)), split_json, artifact_json,
                 metrics_json, artifact_sha, source_checksum,
                 "CANDIDATE" if promote else "REJECTED", now),
            ).lastrowid)
            existing_status = "CANDIDATE" if promote else "REJECTED"
        else:
            calibration_id = int(existing["calibration_artifact_id"])
            existing_status = str(existing["status"])
            if existing_status == "REJECTED" and not promote:
                return {
                    "calibration_artifact_id": calibration_id,
                    "status": "REJECTED", "metrics": fitted.metrics,
                    "artifact_sha256": artifact_sha,
                }
            if existing_status not in {"CANDIDATE", "PROMOTED"}:
                raise PropensityCalibrationError(
                    "This exact calibration candidate was already rejected or superseded."
                )
            if existing_status == "CANDIDATE" and not promote:
                raise PropensityCalibrationError(
                    "This exact calibration candidate is already being published."
                )
    if existing_status == "PROMOTED":
        with get_connection(path) as connection:
            count = int(connection.execute(
                "SELECT COUNT(*) FROM calibrated_propensity_scores WHERE calibration_artifact_id=?",
                (calibration_id,),
            ).fetchone()[0])
        return {
            "calibration_artifact_id": calibration_id, "status": "PROMOTED",
            "metrics": fitted.metrics, "artifact_sha256": artifact_sha,
            "calibrated_person_count": count,
        }
    if not promote:
        return {
            "calibration_artifact_id": calibration_id, "status": "REJECTED",
            "metrics": fitted.metrics, "artifact_sha256": artifact_sha,
        }

    with get_connection(path) as connection:
        cursor = connection.execute(
            "SELECT person_id,propensity_score FROM propensity_scores WHERE scoring_run_id=? ORDER BY person_id",
            (scoring_run_id,),
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            raw = np.asarray([row["propensity_score"] for row in rows], dtype=np.float64)
            calibrated = apply_calibration(fitted.artifact, raw)
            with get_connection(path, write=True) as writer:
                writer.executemany(
                    "INSERT OR REPLACE INTO calibration_score_stage (calibration_artifact_id,person_id,raw_score,calibrated_probability) VALUES (?,?,?,?)",
                    ((calibration_id, str(row["person_id"]), float(row["propensity_score"]), float(probability))
                     for row, probability in zip(rows, calibrated, strict=True)),
                )
    total = int(scoring["scored_person_count"])
    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO calibrated_propensity_scores (
                   calibration_artifact_id,scoring_run_id,person_id,raw_score,
                   calibrated_probability,propensity_bucket,rank_position,total_population,
                   percentile_bucket,decile,rank_band
               )
               SELECT ?,?,person_id,raw_score,calibrated_probability,
                      CASE WHEN calibrated_probability>=.9 THEN '0.90'
                           WHEN calibrated_probability>=.8 THEN '0.80'
                           WHEN calibrated_probability>=.7 THEN '0.70'
                           WHEN calibrated_probability>=.6 THEN '0.60'
                           WHEN calibrated_probability>=.5 THEN '0.50' END,
                      position,?,percentile,CAST((percentile+9)/10 AS INTEGER),
                      CASE WHEN percentile=1 THEN 'ELITE'
                           WHEN percentile<=5 THEN 'VERY_HIGH'
                           WHEN percentile<=10 THEN 'HIGH'
                           WHEN percentile<=25 THEN 'MEDIUM'
                           WHEN percentile<=50 THEN 'LOW' ELSE 'VERY_LOW' END
               FROM (
                   SELECT person_id,raw_score,calibrated_probability,
                          ROW_NUMBER() OVER (ORDER BY calibrated_probability DESC,person_id) AS position,
                          CAST(((ROW_NUMBER() OVER (ORDER BY calibrated_probability DESC,person_id)-1)*100)/? AS INTEGER)+1 AS percentile
                   FROM calibration_score_stage WHERE calibration_artifact_id=?
               )""",
            (calibration_id, scoring_run_id, total, total, calibration_id),
        )
        actual = int(connection.execute(
            "SELECT COUNT(*) FROM calibrated_propensity_scores WHERE calibration_artifact_id=?",
            (calibration_id,),
        ).fetchone()[0])
        if actual != total:
            raise PropensityCalibrationError("Calibrated score publication is incomplete.")
        connection.execute("DELETE FROM calibration_score_stage WHERE calibration_artifact_id=?", (calibration_id,))
        connection.execute(
            """INSERT INTO calibration_distribution_bins (calibration_artifact_id,bin_number,population_count)
               SELECT ?, MIN(9,CAST(calibrated_probability*10 AS INTEGER)),COUNT(*)
               FROM calibrated_propensity_scores WHERE calibration_artifact_id=?
               GROUP BY MIN(9,CAST(calibrated_probability*10 AS INTEGER))""",
            (calibration_id, calibration_id),
        )
        connection.execute(
            "UPDATE score_calibration_artifacts SET status='STALE' WHERE scoring_run_id=? AND status='PROMOTED'",
            (scoring_run_id,),
        )
        connection.execute(
            "UPDATE score_calibration_artifacts SET status='PROMOTED',promoted_at=? WHERE calibration_artifact_id=?",
            (now, calibration_id),
        )
        connection.execute("UPDATE search_preflight_cache SET currentness_state='STALE' WHERE generation_id IN (SELECT generation_id FROM phase10_intelligence_generations WHERE scoring_run_id=?)", (scoring_run_id,))
    return {
        "calibration_artifact_id": calibration_id, "status": "PROMOTED",
        "metrics": fitted.metrics, "artifact_sha256": artifact_sha,
        "calibrated_person_count": total,
    }


def publish_calibrated_generation(
    database_path: str | Path,
    scoring_run_id: int,
    *,
    batch_size: int = 50_000,
) -> dict[str, Any]:
    """Fit on held-out outcomes and publish a separate calibrated score generation."""

    path = initialize_database(database_path)
    scores, labels, groups, model_lineage = _load_observed_outcomes(
        path, scoring_run_id
    )
    partitions = model_lineage["partitions"]
    fitted = fit_held_out_calibration(
        scores,
        labels,
        groups,
        calibration_fit_group_ids=partitions[CALIBRATION_FIT]["group_ids"],
        calibration_evaluation_group_ids=partitions[CALIBRATION_EVALUATION][
            "group_ids"
        ],
        model_training_group_ids=partitions[MODEL_TRAINING]["group_ids"],
    )
    with get_connection(path) as connection:
        source = connection.execute(
            """SELECT source_checksum FROM data_import_runs
               WHERE dataset_name='campaign_sales' AND status='COMPLETED'
               ORDER BY import_id DESC LIMIT 1"""
        ).fetchone()
    if source is None or source["source_checksum"] is None:
        raise PropensityCalibrationError("Completed scoring and outcome lineage are required.")
    published = publish_fitted_calibration(
        path,
        scoring_run_id,
        fitted,
        source_checksum=str(source["source_checksum"]),
        promote=True,
        batch_size=batch_size,
    )
    return {"scoring_run_id": scoring_run_id, "method": fitted.method, **published}


__all__ = (
    "CALIBRATION_CONTRACT_VERSION", "PROPENSITY_BUCKETS", "FittedCalibration",
    "PropensityCalibrationError", "apply_calibration", "fit_held_out_calibration",
    "has_governed_calibration_lineage",
    "publish_calibrated_generation", "publish_fitted_calibration",
)
