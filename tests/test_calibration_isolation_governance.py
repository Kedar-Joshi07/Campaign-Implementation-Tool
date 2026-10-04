"""Recovery Prompt 11 campaign-group calibration isolation tests."""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database
from app.ml.campaign_group_split import (
    CALIBRATION_EVALUATION,
    CALIBRATION_FIT,
    MODEL_TRAINING,
    SPLIT_STRATEGY_VERSION,
    CampaignGroupSplitError,
    build_campaign_group_partition,
    validate_calibration_model_lineage_identity,
)
from app.ml.feature_contract import RAW_TRAINING_COLUMNS
from app.services import propensity_calibration_service as calibration
from app.services.propensity_calibration_service import PropensityCalibrationError


def _cohort(group_count: int = 9, rows_per_group: int = 40):
    rows: list[dict[str, object]] = []
    memberships: dict[str, tuple[str, ...]] = {}
    for group_index in range(group_count):
        for row_index in range(rows_per_group):
            customer_id = f"C{group_index:02d}-{row_index:03d}"
            rows.append(
                {
                    "customer_id": customer_id,
                    "pu_label": row_index % 2,
                    "age": 25 + row_index % 40,
                    "gender": "Female" if row_index % 2 else "Male",
                    "state": "Ohio",
                    "individual_yearly_income": 50_000.0 + row_index,
                    "marital_status": "Single",
                    "education": "College",
                    "employment_status": "Employed",
                    "resident_status": "Citizen",
                    "resident_type": "Owner",
                    "family_member_count": 2,
                    "type_of_employment": "Salaried",
                }
            )
            memberships[customer_id] = (f"CMP-{group_index:02d}",)
    return pd.DataFrame(rows).loc[:, RAW_TRAINING_COLUMNS], memberships


def test_three_way_campaign_partition_is_deterministic_balanced_and_disjoint() -> None:
    frame, memberships = _cohort()
    first = build_campaign_group_partition(
        frame, memberships, seed=1729, validation_fraction=0.4
    )
    repeated = build_campaign_group_partition(
        frame.sample(frac=1, random_state=91).sort_values("customer_id"),
        memberships,
        seed=1729,
        validation_fraction=0.4,
    )

    assert first.lineage == repeated.lineage
    assert first.lineage["strategy_version"] == SPLIT_STRATEGY_VERSION
    assert set(first.lineage["overlap_counts"].values()) == {0}
    partitions = first.lineage["partitions"]
    all_groups: set[str] = set()
    for name in (MODEL_TRAINING, CALIBRATION_FIT, CALIBRATION_EVALUATION):
        details = partitions[name]
        assert details["positive_count"] > 0
        assert details["negative_count"] > 0
        groups = set(details["group_ids"])
        assert not all_groups.intersection(groups)
        all_groups.update(groups)


def test_multi_campaign_customer_connects_campaigns_deterministically() -> None:
    frame, memberships = _cohort()
    memberships["C00-000"] = ("CMP-00", "CMP-01")
    first = build_campaign_group_partition(
        frame, memberships, seed=42, validation_fraction=0.4
    )
    memberships["C00-000"] = ("CMP-01", "CMP-00")
    second = build_campaign_group_partition(
        frame, memberships, seed=42, validation_fraction=0.4
    )
    by_customer = dict(zip(frame["customer_id"], first.customer_group_ids, strict=True))

    assert first.lineage == second.lineage
    assert by_customer["C00-000"] == by_customer["C01-001"]
    assert first.lineage["multi_campaign_customer_count"] == 1


@pytest.mark.parametrize("group_count", [1, 2])
def test_impossible_three_way_partition_fails_without_relaxing(group_count: int) -> None:
    frame, memberships = _cohort(group_count=group_count)
    with pytest.raises(CampaignGroupSplitError, match="three independent"):
        build_campaign_group_partition(
            frame, memberships, seed=1729, validation_fraction=0.4
        )


def test_calibrator_selection_metrics_only_receive_evaluation_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scores = np.tile(np.linspace(0.05, 0.95, 100), 4)
    outcomes = np.tile(np.asarray([0, 1] * 50), 4)
    groups = np.repeat(np.asarray(["fit-a", "fit-b", "eval-a", "eval-b"]), 100)
    observed_sizes: list[int] = []
    real_metrics = calibration._metrics

    def recording_metrics(labels: np.ndarray, probabilities: np.ndarray):
        observed_sizes.append(labels.size)
        assert set(labels) == {0, 1}
        return real_metrics(labels, probabilities)

    monkeypatch.setattr(calibration, "_metrics", recording_metrics)
    fitted = calibration.fit_held_out_calibration(
        scores,
        outcomes,
        groups,
        calibration_fit_group_ids=("fit-a", "fit-b"),
        calibration_evaluation_group_ids=("eval-a", "eval-b"),
        model_training_group_ids=("train-a", "train-b"),
    )

    assert observed_sizes == [200, 200]
    assert fitted.split_lineage["evaluation_records_used_for_fit"] == 0
    assert fitted.split_lineage["candidate_selection_partition"] == (
        "calibration_evaluation"
    )
    assert fitted.split_lineage["three_way_isolated"] is True


def test_calibration_rejects_overlap_and_missing_classes() -> None:
    scores = np.tile(np.linspace(0.05, 0.95, 100), 3)
    outcomes = np.tile(np.asarray([0, 1] * 50), 3)
    groups = np.repeat(np.asarray(["fit", "eval", "other"]), 100)
    with pytest.raises(PropensityCalibrationError, match="must not overlap"):
        calibration.fit_held_out_calibration(
            scores,
            outcomes,
            groups,
            calibration_fit_group_ids=("fit",),
            calibration_evaluation_group_ids=("eval", "other"),
            model_training_group_ids=("fit",),
        )

    bad_outcomes = outcomes.copy()
    bad_outcomes[groups == "eval"] = 0
    bad_outcomes[groups == "other"] = 0
    with pytest.raises(PropensityCalibrationError, match="lacks both outcome classes"):
        calibration.fit_held_out_calibration(
            scores,
            bad_outcomes,
            groups,
            calibration_fit_group_ids=("fit",),
            calibration_evaluation_group_ids=("eval", "other"),
            model_training_group_ids=("train",),
        )


def test_cross_artifact_lineage_requires_exact_partition_identity() -> None:
    frame, memberships = _cohort()
    partition = build_campaign_group_partition(
        frame, memberships, seed=42, validation_fraction=0.20
    )
    model_lineage = partition.lineage
    parts = model_lineage["partitions"]
    calibration_lineage = {
        "strategy_version": model_lineage["strategy_version"],
        "model_training_group_ids": list(parts[MODEL_TRAINING]["group_ids"]),
        "model_training_group_ids_sha256": parts[MODEL_TRAINING][
            "group_ids_sha256"
        ],
        "calibration_fit_group_ids": list(parts[CALIBRATION_FIT]["group_ids"]),
        "calibration_fit_group_ids_sha256": parts[CALIBRATION_FIT][
            "group_ids_sha256"
        ],
        "calibration_evaluation_group_ids": list(
            parts[CALIBRATION_EVALUATION]["group_ids"]
        ),
        "calibration_evaluation_group_ids_sha256": parts[
            CALIBRATION_EVALUATION
        ]["group_ids_sha256"],
        "model_partition_seed": model_lineage["seed"],
        "model_validation_fraction": model_lineage["validation_fraction"],
    }
    assert validate_calibration_model_lineage_identity(
        calibration_lineage, model_lineage
    )

    missing_seed = copy.deepcopy(calibration_lineage)
    missing_seed.pop("model_partition_seed")
    assert not validate_calibration_model_lineage_identity(missing_seed, model_lineage)

    wrong_fraction = copy.deepcopy(calibration_lineage)
    wrong_fraction["model_validation_fraction"] = 0.25
    assert not validate_calibration_model_lineage_identity(wrong_fraction, model_lineage)

    reordered = copy.deepcopy(calibration_lineage)
    reordered["model_training_group_ids"].reverse()
    assert validate_calibration_model_lineage_identity(reordered, model_lineage)

    missing = copy.deepcopy(calibration_lineage)
    missing["model_training_group_ids"] = missing[
        "model_training_group_ids"
    ][:-1]
    missing["model_training_group_ids_sha256"] = hashlib.sha256(
        json.dumps(
            sorted(missing["model_training_group_ids"]), separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert not validate_calibration_model_lineage_identity(missing, model_lineage)

    extra = copy.deepcopy(calibration_lineage)
    extra["calibration_fit_group_ids"].append("extra-group")
    extra["calibration_fit_group_ids_sha256"] = hashlib.sha256(
        json.dumps(
            sorted(extra["calibration_fit_group_ids"]), separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert not validate_calibration_model_lineage_identity(extra, model_lineage)

    hash_mismatch = copy.deepcopy(calibration_lineage)
    hash_mismatch["calibration_evaluation_group_ids_sha256"] = "f" * 64
    assert not validate_calibration_model_lineage_identity(
        hash_mismatch, model_lineage
    )

    swapped = copy.deepcopy(calibration_lineage)
    swapped["calibration_fit_group_ids"], swapped[
        "calibration_evaluation_group_ids"
    ] = (
        swapped["calibration_evaluation_group_ids"],
        swapped["calibration_fit_group_ids"],
    )
    swapped["calibration_fit_group_ids_sha256"], swapped[
        "calibration_evaluation_group_ids_sha256"
    ] = (
        swapped["calibration_evaluation_group_ids_sha256"],
        swapped["calibration_fit_group_ids_sha256"],
    )
    assert not validate_calibration_model_lineage_identity(swapped, model_lineage)

def test_schema_30_preserves_model_lineage_and_calibration_v2(tmp_path) -> None:
    path = initialize_database(tmp_path / "calibration-isolation.db")
    with get_connection(path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0]
        model_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(model_runs)")
        }
        feedback_batch_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(campaign_feedback_batches)"
            )
        }
        feedback_decision_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(feedback_retraining_decisions)"
            )
        }
        feedback_indexes = {
            row["name"]
            for row in connection.execute(
                "PRAGMA index_list(feedback_retraining_decisions)"
            )
        }
        definition = connection.execute(
            """SELECT sql FROM sqlite_master
               WHERE type='table' AND name='score_calibration_artifacts'"""
        ).fetchone()[0]

    assert version == str(CURRENT_SCHEMA_VERSION)
    assert "split_lineage_json" in model_columns
    assert "selection_basis_sha256" in feedback_batch_columns
    assert {
        "decision_kind",
        "latest_feedback_batch_id",
        "reference_decision_id",
        "drift_lineage_json",
    } <= feedback_decision_columns
    assert "idx_feedback_recalibration_waiting" in feedback_indexes
    assert "calibration_contract_version IN ('1','2')" in definition
    assert json.loads(json.dumps({"strategy": SPLIT_STRATEGY_VERSION}))
