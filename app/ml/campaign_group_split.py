"""Deterministic campaign-connected train/calibrate/evaluate partitioning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


SPLIT_STRATEGY_VERSION = "CAMPAIGN_CONNECTED_THREE_WAY_V1"
CALIBRATION_FIT = "calibration_fit"
CALIBRATION_EVALUATION = "calibration_evaluation"
MODEL_TRAINING = "model_training"
_PARTITIONS = (MODEL_TRAINING, CALIBRATION_FIT, CALIBRATION_EVALUATION)


class CampaignGroupSplitError(ValueError):
    """Raised when campaign lineage cannot support an isolated split."""


def validate_campaign_group_split_lineage(
    lineage: Mapping[str, Any] | None,
    *,
    expected_seed: int | None = None,
    expected_validation_fraction: float | None = None,
) -> bool:
    """Return whether persisted lineage proves the governed isolated split.

    This intentionally validates persisted facts rather than accepting a strategy
    label alone. Historical rows remain readable, but cannot satisfy governed
    automated reuse unless their three partitions are complete and disjoint.
    """

    if not isinstance(lineage, Mapping):
        return False
    if lineage.get("strategy_version") != SPLIT_STRATEGY_VERSION:
        return False
    if expected_seed is not None and lineage.get("seed") != expected_seed:
        return False
    if expected_validation_fraction is not None and lineage.get(
        "validation_fraction"
    ) != expected_validation_fraction:
        return False
    partitions = lineage.get("partitions")
    if not isinstance(partitions, Mapping) or set(partitions) != set(_PARTITIONS):
        return False
    all_groups: set[str] = set()
    customer_count = 0
    for partition in _PARTITIONS:
        facts = partitions.get(partition)
        if not isinstance(facts, Mapping):
            return False
        groups = facts.get("group_ids")
        if (
            not isinstance(groups, list)
            or not groups
            or any(not isinstance(group, str) or not group for group in groups)
            or len(groups) != len(set(groups))
            or all_groups.intersection(groups)
            or facts.get("group_count") != len(groups)
            or facts.get("group_ids_sha256") != _sha(groups)
        ):
            return False
        positive_count = facts.get("positive_count")
        negative_count = facts.get("negative_count")
        partition_customer_count = facts.get("customer_count")
        if (
            not isinstance(positive_count, int)
            or isinstance(positive_count, bool)
            or positive_count <= 0
            or not isinstance(negative_count, int)
            or isinstance(negative_count, bool)
            or negative_count <= 0
            or partition_customer_count != positive_count + negative_count
        ):
            return False
        all_groups.update(groups)
        customer_count += partition_customer_count
    overlap_counts = lineage.get("overlap_counts")
    if not isinstance(overlap_counts, Mapping) or set(overlap_counts.values()) != {0}:
        return False
    return (
        lineage.get("group_count") == len(all_groups)
        and lineage.get("all_group_ids_sha256") == _sha(sorted(all_groups))
        and lineage.get("customer_count") == customer_count
    )


@dataclass(frozen=True)
class CampaignGroupPartition:
    customer_group_ids: pd.Series
    customer_partitions: pd.Series
    lineage: dict[str, object]


def _sha(values: Sequence[str]) -> str:
    payload = json.dumps(sorted(values), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_calibration_model_lineage_identity(
    calibration_lineage: Mapping[str, Any] | None,
    model_lineage: Mapping[str, Any] | None,
) -> bool:
    """Prove a calibration names the exact partitions recorded by its model.

    Calibration fitting has its own deterministic estimator seed, so that seed
    is not compared with the model partition seed. The model lineage is still
    required to carry the governed partition strategy, seed, and validation
    policy; exact partition membership and canonical hashes are then compared.
    """

    if not isinstance(calibration_lineage, Mapping) or not isinstance(
        model_lineage, Mapping
    ):
        return False
    if calibration_lineage.get("strategy_version") != model_lineage.get(
        "strategy_version"
    ):
        return False
    partitions = model_lineage.get("partitions")
    if not isinstance(partitions, Mapping):
        return False
    calibration_fields = {
        MODEL_TRAINING: "model_training_group_ids",
        CALIBRATION_FIT: "calibration_fit_group_ids",
        CALIBRATION_EVALUATION: "calibration_evaluation_group_ids",
    }
    for partition, calibration_field in calibration_fields.items():
        model_facts = partitions.get(partition)
        calibration_groups = calibration_lineage.get(calibration_field)
        if not isinstance(model_facts, Mapping) or not isinstance(
            calibration_groups, list
        ):
            return False
        model_groups = model_facts.get("group_ids")
        if not isinstance(model_groups, list):
            return False
        if sorted(calibration_groups) != sorted(model_groups):
            return False
        canonical_hash = _sha(calibration_groups)
        if calibration_lineage.get(
            f"{calibration_field}_sha256"
        ) != canonical_hash or model_facts.get("group_ids_sha256") != canonical_hash:
            return False
    recorded_partition_seed = calibration_lineage.get("model_partition_seed")
    if recorded_partition_seed is None or recorded_partition_seed != model_lineage.get("seed"):
        return False
    recorded_validation_fraction = calibration_lineage.get(
        "model_validation_fraction"
    )
    if recorded_validation_fraction is None or recorded_validation_fraction != model_lineage.get(
        "validation_fraction"
    ):
        return False
    return True


def _connected_group_ids(
    customer_ids: Sequence[str],
    memberships: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        parent[second] = first

    normalized: dict[str, tuple[str, ...]] = {}
    for customer_id in customer_ids:
        campaigns = tuple(sorted({str(value) for value in memberships.get(customer_id, ()) if str(value)}))
        if not campaigns:
            raise CampaignGroupSplitError(
                f"Customer {customer_id!r} has no campaign-group lineage."
            )
        normalized[customer_id] = campaigns
        for campaign_id in campaigns[1:]:
            union(campaigns[0], campaign_id)
        find(campaigns[0])

    components: dict[str, list[str]] = {}
    for campaign_id in sorted(parent):
        components.setdefault(find(campaign_id), []).append(campaign_id)
    component_ids = {
        root: "campaign-component:" + _sha(campaign_ids)
        for root, campaign_ids in components.items()
    }
    return {
        customer_id: component_ids[find(campaigns[0])]
        for customer_id, campaigns in normalized.items()
    }


def _partition_lineage(
    *,
    customer_ids: np.ndarray,
    labels: np.ndarray,
    group_ids: np.ndarray,
    assignments: Mapping[str, str],
    seed: int,
    validation_fraction: float,
    memberships: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    partitions: dict[str, object] = {}
    partition_groups: dict[str, set[str]] = {}
    for partition in _PARTITIONS:
        groups = {group for group, value in assignments.items() if value == partition}
        mask = np.asarray([group in groups for group in group_ids])
        partition_groups[partition] = groups
        partitions[partition] = {
            "group_ids": sorted(groups),
            "group_ids_sha256": _sha(sorted(groups)),
            "group_count": len(groups),
            "customer_count": int(mask.sum()),
            "positive_count": int(labels[mask].sum()),
            "negative_count": int(mask.sum() - labels[mask].sum()),
        }
    multiplicities = [len(set(memberships[str(customer_id)])) for customer_id in customer_ids]
    return {
        "strategy_version": SPLIT_STRATEGY_VERSION,
        "seed": seed,
        "unit_of_observation": "unique_customer",
        "group_boundary": "connected_component_of_campaign_membership",
        "validation_fraction": validation_fraction,
        "calibration_fit_fraction": validation_fraction / 2.0,
        "calibration_evaluation_fraction": validation_fraction / 2.0,
        "customer_count": int(customer_ids.size),
        "group_count": len(assignments),
        "all_group_ids_sha256": _sha(sorted(assignments)),
        "multi_campaign_customer_count": sum(value > 1 for value in multiplicities),
        "maximum_campaigns_per_customer": max(multiplicities, default=0),
        "partitions": partitions,
        "overlap_counts": {
            "model_training_calibration_fit": len(
                partition_groups[MODEL_TRAINING] & partition_groups[CALIBRATION_FIT]
            ),
            "model_training_calibration_evaluation": len(
                partition_groups[MODEL_TRAINING]
                & partition_groups[CALIBRATION_EVALUATION]
            ),
            "calibration_fit_calibration_evaluation": len(
                partition_groups[CALIBRATION_FIT]
                & partition_groups[CALIBRATION_EVALUATION]
            ),
        },
    }


def build_campaign_group_partition(
    frame: pd.DataFrame,
    memberships: Mapping[str, Sequence[str]],
    *,
    seed: int,
    validation_fraction: float,
) -> CampaignGroupPartition:
    """Create deterministic model/calibration partitions at campaign-component grain."""

    if not 0 < validation_fraction < 1:
        raise CampaignGroupSplitError("validation_fraction must be between 0 and 1.")
    customer_ids = frame["customer_id"].astype(str).to_numpy()
    labels = frame["pu_label"].astype(int).to_numpy()
    by_customer = _connected_group_ids(customer_ids, memberships)
    group_ids = np.asarray([by_customer[value] for value in customer_ids], dtype=str)
    unique_groups = sorted(set(group_ids))
    if len(unique_groups) < 3:
        raise CampaignGroupSplitError(
            "At least three independent campaign-connected groups are required."
        )

    summaries = {
        group: (
            int((group_ids == group).sum()),
            int(labels[group_ids == group].sum()),
        )
        for group in unique_groups
    }
    for class_value, label in ((1, "positive"), (0, "negative")):
        containing = sum(
            1
            for count, positives in summaries.values()
            if (positives if class_value else count - positives) > 0
        )
        if containing < 3:
            raise CampaignGroupSplitError(
                f"Three-way isolation requires {label} outcomes in at least three independent groups."
            )

    targets = {
        MODEL_TRAINING: len(frame) * (1.0 - validation_fraction),
        CALIBRATION_FIT: len(frame) * validation_fraction / 2.0,
        CALIBRATION_EVALUATION: len(frame) * validation_fraction / 2.0,
    }
    rng = np.random.default_rng(seed)
    best: tuple[tuple[float, str], dict[str, str]] | None = None
    trial_count = min(2048, max(256, len(unique_groups) * 16))
    for _ in range(trial_count):
        shuffled = list(unique_groups)
        rng.shuffle(shuffled)
        assigned: dict[str, str] = {}
        counts = {partition: 0 for partition in _PARTITIONS}
        partition_order = list(_PARTITIONS)
        rng.shuffle(partition_order)
        for index, group in enumerate(shuffled):
            if index < len(_PARTITIONS):
                selected = partition_order[index]
            else:
                selected = min(
                    _PARTITIONS,
                    key=lambda partition: (
                        counts[partition] / max(targets[partition], 1.0),
                        partition,
                    ),
                )
            assigned[group] = selected
            counts[selected] += summaries[group][0]

        class_counts = {
            partition: {"positive": 0, "negative": 0}
            for partition in _PARTITIONS
        }
        for group, partition in assigned.items():
            count, positives = summaries[group]
            class_counts[partition]["positive"] += positives
            class_counts[partition]["negative"] += count - positives
        valid = all(
            values["positive"] > 0 and values["negative"] > 0
            for values in class_counts.values()
        )
        if not valid:
            continue
        deviation = sum(
            abs(counts[partition] - targets[partition]) / len(frame)
            for partition in _PARTITIONS
        )
        canonical = json.dumps(assigned, sort_keys=True, separators=(",", ":"))
        score = (deviation, canonical)
        if best is None or score < best[0]:
            best = (score, assigned)

    if best is None:
        raise CampaignGroupSplitError(
            "The campaign-connected cohort cannot produce three isolated partitions with both classes."
        )
    assignments = best[1]
    customer_partitions = pd.Series(
        [assignments[group] for group in group_ids],
        index=frame.index,
        dtype="string",
    )
    customer_groups = pd.Series(group_ids, index=frame.index, dtype="string")
    lineage = _partition_lineage(
        customer_ids=customer_ids,
        labels=labels,
        group_ids=group_ids,
        assignments=assignments,
        seed=seed,
        validation_fraction=validation_fraction,
        memberships=memberships,
    )
    return CampaignGroupPartition(customer_groups, customer_partitions, lineage)


__all__ = (
    "CALIBRATION_EVALUATION",
    "CALIBRATION_FIT",
    "CampaignGroupPartition",
    "CampaignGroupSplitError",
    "MODEL_TRAINING",
    "SPLIT_STRATEGY_VERSION",
    "build_campaign_group_partition",
    "validate_calibration_model_lineage_identity",
    "validate_campaign_group_split_lineage",
)
