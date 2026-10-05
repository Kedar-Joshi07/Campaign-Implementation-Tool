from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from app.services import potential_customer_preflight_service as preflight_service
from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.services.intelligence_attestation_service import (
    record_deep_verification_attestation,
)
from app.services.phase11_result_snapshot_service import materialize_result_snapshot
from app.services.phase11_result_contracts import RESULT_MEMBERSHIP_V2_COLUMNS
from app.services.phase11_search_orchestration_service import (
    build_result_cache_key,
    iter_selected_members,
)
from app.services.phase11_results_service import (
    get_result_detail,
    list_result_history,
)
from app.services.potential_customer_preflight_service import (
    build_preflight_cache_key,
    count_calibrated_members,
    exact_preflight,
)
from app.services.potential_customer_search_submission_service import (
    normalize_search_definition,
)
from app.services.propensity_calibration_service import (
    FittedCalibration,
    publish_fitted_calibration,
)
from app.services.source_currentness_service import (
    reconcile_source_currentness,
    resolve_governed_calibration_eligibility,
)
from app.services.targeting_option_catalog_service import get_or_build_targeting_catalog
from tests.test_intelligence_attestation_currentness import (
    attestation_case,
    verified_generation_source,
)


def _bucket(probability: float) -> str | None:
    if probability >= 0.90:
        return "0.90"
    if probability >= 0.80:
        return "0.80"
    if probability >= 0.70:
        return "0.70"
    if probability >= 0.60:
        return "0.60"
    if probability >= 0.50:
        return "0.50"
    return None


def _rank_band(percentile: int) -> str:
    if percentile == 1:
        return "ELITE"
    if percentile <= 5:
        return "VERY_HIGH"
    if percentile <= 10:
        return "HIGH"
    if percentile <= 25:
        return "MEDIUM"
    if percentile <= 50:
        return "LOW"
    return "VERY_LOW"


def _publish_controlled_calibration(path: Path, generation: dict) -> int:
    probabilities = [
        0.49, 0.50, math.nextafter(0.60, 0.0), 0.60,
        math.nextafter(0.70, 0.0), 0.70, math.nextafter(0.80, 0.0),
        0.80, math.nextafter(0.90, 0.0), 0.90, 1.00,
    ]
    with get_connection(path) as connection:
        raw_rows = connection.execute(
            """SELECT person_id,propensity_score FROM propensity_scores
               WHERE scoring_run_id=? ORDER BY person_id""",
            (generation["scoring_run_id"],),
        ).fetchall()
        artifact_ordinal = int(connection.execute(
            "SELECT COUNT(*) FROM score_calibration_artifacts WHERE scoring_run_id=?",
            (generation["scoring_run_id"],),
        ).fetchone()[0]) + 1
        model_lineage = json.loads(connection.execute(
            "SELECT split_lineage_json FROM model_runs WHERE model_run_id=?",
            (generation["model_run_id"],),
        ).fetchone()[0])
    partitions = model_lineage["partitions"]
    calibration_lineage = {
        "seed": 1729,
        "strategy": model_lineage["strategy_version"],
        "strategy_version": model_lineage["strategy_version"],
        "model_training_group_ids": partitions["model_training"]["group_ids"],
        "calibration_fit_group_ids": partitions["calibration_fit"]["group_ids"],
        "calibration_evaluation_group_ids": partitions["calibration_evaluation"]["group_ids"],
        "overlap_counts": model_lineage["overlap_counts"],
        "calibration_fit_class_balance": {
            "positive": partitions["calibration_fit"]["positive_count"],
            "negative": partitions["calibration_fit"]["negative_count"],
        },
        "calibration_evaluation_class_balance": {
            "positive": partitions["calibration_evaluation"]["positive_count"],
            "negative": partitions["calibration_evaluation"]["negative_count"],
        },
        "candidate_selection_partition": "calibration_evaluation",
        "evaluation_records_used_for_fit": 0,
        "three_way_isolated": True,
        "model_partition_seed": model_lineage["seed"],
        "model_validation_fraction": model_lineage["validation_fraction"],
    }
    for field in (
        "model_training_group_ids",
        "calibration_fit_group_ids",
        "calibration_evaluation_group_ids",
    ):
        calibration_lineage[f"{field}_sha256"] = hashlib.sha256(
            json.dumps(
                sorted(calibration_lineage[field]), separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    while len(probabilities) < len(raw_rows):
        probabilities.append(0.75)
    ordered = sorted(
        zip(raw_rows, probabilities, strict=True),
        key=lambda item: (-item[1], str(item[0]["person_id"])),
    )
    with get_connection(path, write=True) as connection:
        calibration_id = int(connection.execute(
            """INSERT INTO score_calibration_artifacts (
                   calibration_contract_version,scoring_run_id,model_run_id,
                   outcome_definition,method,split_seed,split_lineage_json,
                   artifact_json,metrics_json,artifact_sha256,source_checksum,
                   status,created_at,promoted_at
               ) VALUES ('2',?,?,'ATTRIBUTED_PURCHASE','SIGMOID',1729,
                         ?,'{}','{}',?,?,'PROMOTED',?,?)""",
            (
                generation["scoring_run_id"], generation["model_run_id"],
                json.dumps(calibration_lineage, sort_keys=True, separators=(",", ":")),
                f"{artifact_ordinal:064x}", "e" * 64, "2026-09-29T12:00:00Z",
                "2026-09-29T12:00:00Z",
            ),
        ).lastrowid)
        total = len(ordered)
        connection.executemany(
            """INSERT INTO calibrated_propensity_scores (
                   calibration_artifact_id,scoring_run_id,person_id,raw_score,
                   calibrated_probability,propensity_bucket,rank_position,
                   total_population,percentile_bucket,decile,rank_band
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    calibration_id,
                    generation["scoring_run_id"],
                    str(row["person_id"]),
                    float(row["propensity_score"]),
                    probability,
                    _bucket(probability),
                    rank,
                    total,
                    percentile := int(((rank - 1) * 100) / total) + 1,
                    int((percentile + 9) / 10),
                    _rank_band(percentile),
                )
                for rank, (row, probability) in enumerate(ordered, start=1)
            ),
        )
    return calibration_id


def _context(path: Path, context_id: int) -> dict:
    with get_connection(path) as connection:
        payload = json.loads(connection.execute(
            "SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?",
            (context_id,),
        ).fetchone()[0])
    payload.pop("campaign_targeting_context_contract_version", None)
    return payload


def _criteria(*, mode: str = "ALL_MATCHING", target_count: int | None = None) -> dict:
    return {"selection_mode": mode, "target_count": target_count}


def _run_for(
    path: Path,
    context_id: int,
    generation: dict,
    calibration_id: int,
    *,
    bucket: str,
    criteria: dict,
) -> tuple[dict, list[dict]]:
    catalog = get_or_build_targeting_catalog(path)
    context, normalized, _ = normalize_search_definition(
        path,
        raw_context=_context(path, context_id),
        raw_criteria=criteria,
        propensity_bucket=bucket,
        catalog_version=catalog["catalog_version"],
    )
    repository = CampaignResultRegistryRepository(path)
    run_id = repository.create_search_run(
        campaign_name=f"Parity {bucket} {criteria['selection_mode']}",
        targeting_context_id=context_id,
        modeling_context_sha256=generation["modeling_context_sha256"],
        targeting_criteria=normalized.payload,
        filter_branches=list(normalized.audience_filter_branches),
        selection_mode=normalized.audience_selection["mode"],
        target_count=normalized.audience_selection.get("target_count"),
        delivery_channel=context["campaign_channel"],
        selection_contract_version="2",
        propensity_bucket=bucket,
        catalog_version=catalog["catalog_version"],
    )
    run = repository.fetch_search_run(run_id) | {
        "calibration_artifact_id": calibration_id,
    }
    return run, [dict(item) for item in normalized.audience_filter_branches]


def _materialized_count(
    path: Path,
    run: dict,
    generation: dict,
    *,
    project_root: Path,
) -> int:
    repository = CampaignResultRegistryRepository(path)
    cache_key = build_result_cache_key(run, generation)
    snapshot_id = materialize_result_snapshot(
        path,
        run,
        generation,
        cache_key,
        None,
        iter_selected_members(path, run, generation),
        project_root=project_root,
    )
    return int(repository.fetch_snapshot(snapshot_id)["resolved_count"])


@pytest.fixture
def parity_case(attestation_case):
    path, project_root, context_id, generation = attestation_case
    assert record_deep_verification_attestation(path, generation)["status"] == "VERIFIED"
    calibration_id = _publish_controlled_calibration(path, generation)
    return path, project_root, context_id, generation, calibration_id


def test_governed_calibration_consumption_gate_accepts_exact_current_lineage(
    parity_case,
) -> None:
    path, _root, _context_id, generation, calibration_id = parity_case
    decision = resolve_governed_calibration_eligibility(
        path, generation, calibration_id
    )
    assert decision.eligible is True
    assert decision.reason_code == "ELIGIBLE"


def test_legacy_promoted_calibration_remains_historical_but_is_not_v2_eligible(
    parity_case,
) -> None:
    path, _root, _context_id, generation, calibration_id = parity_case
    with get_connection(path, write=True) as connection:
        connection.execute(
            """UPDATE score_calibration_artifacts
               SET calibration_contract_version='1'
               WHERE calibration_artifact_id=?""",
            (calibration_id,),
        )
    decision = resolve_governed_calibration_eligibility(
        path, generation, calibration_id
    )
    assert decision.eligible is False
    assert decision.reason_code == "CALIBRATION_GOVERNANCE_INCOMPATIBLE"
    with get_connection(path) as connection:
        persisted = connection.execute(
            """SELECT calibration_contract_version,status
               FROM score_calibration_artifacts WHERE calibration_artifact_id=?""",
            (calibration_id,),
        ).fetchone()
    assert tuple(persisted) == ("1", "PROMOTED")


def test_malformed_governed_calibration_lineage_is_not_consumable(
    parity_case,
) -> None:
    path, _root, _context_id, generation, calibration_id = parity_case
    with get_connection(path, write=True) as connection:
        connection.execute(
            """UPDATE score_calibration_artifacts SET split_lineage_json='{}'
               WHERE calibration_artifact_id=?""",
            (calibration_id,),
        )
    decision = resolve_governed_calibration_eligibility(
        path, generation, calibration_id
    )
    assert decision.eligible is False
    assert decision.reason_code == "CALIBRATION_LINEAGE_INVALID"


@pytest.mark.parametrize(
    ("bucket", "expected"),
    (("0.90", 2), ("0.80", 2), ("0.70", 51), ("0.60", 2), ("0.50", 2)),
)
def test_exact_bucket_boundaries_and_all_matching_materialization_parity(
    parity_case, bucket: str, expected: int,
) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    catalog = get_or_build_targeting_catalog(path)
    preflight = exact_preflight(
        path,
        context=_context(path, context_id),
        criteria=_criteria(),
        propensity_bucket=bucket,
        catalog_version=catalog["catalog_version"],
    )
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket=bucket, criteria=_criteria(),
    )
    assert preflight["qualifying_count"] == expected
    assert preflight["selected_count"] == expected
    assert preflight["intersection_count"] == expected
    assert _materialized_count(
        path, run, generation, project_root=project_root
    ) == expected


@pytest.mark.parametrize(("target", "expected"), ((7, 7), (100, 51)))
def test_top_n_reports_qualifying_and_selected_and_matches_snapshot(
    parity_case, target: int, expected: int,
) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    criteria = _criteria(mode="TOP_N", target_count=target)
    catalog = get_or_build_targeting_catalog(path)
    preflight = exact_preflight(
        path,
        context=_context(path, context_id),
        criteria=criteria,
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.70", criteria=criteria,
    )
    assert preflight["qualifying_count"] == 51
    assert preflight["selected_count"] == expected
    assert _materialized_count(
        path, run, generation, project_root=project_root
    ) == expected


def test_overlapping_or_branches_deduplicate_identically(parity_case) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    score_max = math.nextafter(0.80, 0.0)
    branches = [
        {"score_min": 0.70, "score_max": score_max, "state": ["Ohio"]},
        {"score_min": 0.70, "score_max": score_max, "gender": ["Female"]},
    ]
    qualifying = count_calibrated_members(
        path,
        branches,
        calibration_artifact_id=calibration_id,
        propensity_bucket="0.70",
    )
    repository = CampaignResultRegistryRepository(path)
    catalog = get_or_build_targeting_catalog(path)
    run_id = repository.create_search_run(
        campaign_name="Overlapping OR parity",
        targeting_context_id=context_id,
        modeling_context_sha256=generation["modeling_context_sha256"],
        targeting_criteria={"selection_mode": "ALL_MATCHING", "target_count": None},
        filter_branches=branches,
        delivery_channel="EMAIL",
        selection_contract_version="2",
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    run = repository.fetch_search_run(run_id) | {
        "calibration_artifact_id": calibration_id,
    }
    assert qualifying > 0
    assert _materialized_count(
        path, run, generation, project_root=project_root
    ) == qualifying


def test_empty_filtered_bucket_matches_empty_snapshot(parity_case) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    criteria = _criteria() | {"states": ["Texas"]}
    catalog = get_or_build_targeting_catalog(path)
    preflight = exact_preflight(
        path,
        context=_context(path, context_id),
        criteria=criteria,
        propensity_bucket="0.90",
        catalog_version=catalog["catalog_version"],
    )
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.90", criteria=criteria,
    )
    expected = _materialized_count(path, run, generation, project_root=project_root)
    assert preflight["selected_count"] == expected
    # The fixture's two top-boundary identities are deliberately outside Texas.
    assert expected == 0


def test_materialization_uses_exact_discrete_bucket_not_only_lower_bound(
    parity_case,
) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    with get_connection(path, write=True) as connection:
        moved = connection.execute(
            """UPDATE calibrated_propensity_scores SET propensity_bucket='0.60'
               WHERE calibration_artifact_id=? AND person_id='P0012'
                 AND calibrated_probability=0.75""",
            (calibration_id,),
        )
    assert moved.rowcount == 1
    catalog = get_or_build_targeting_catalog(path)
    preflight = exact_preflight(
        path,
        context=_context(path, context_id),
        criteria=_criteria(),
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.70", criteria=_criteria(),
    )
    assert preflight["selected_count"] == 50
    assert _materialized_count(
        path, run, generation, project_root=project_root
    ) == 50


def test_cache_identity_binds_bucket_selection_catalog_sources_and_calibration(
    parity_case,
) -> None:
    path, _root, context_id, generation, calibration_id = parity_case
    catalog = get_or_build_targeting_catalog(path)
    common = dict(
        context=_context(path, context_id), criteria=_criteria(),
        catalog_version=catalog["catalog_version"],
    )
    exact_preflight(path, propensity_bucket="0.70", **common)
    exact_preflight(path, propensity_bucket="0.60", **common)
    with get_connection(path) as connection:
        first_keys = {
            str(row[0]) for row in connection.execute(
                "SELECT cache_key_sha256 FROM search_preflight_cache"
            )
        }
    assert len(first_keys) == 2

    with get_connection(path, write=True) as connection:
        connection.execute(
            "UPDATE score_calibration_artifacts SET status='STALE' WHERE calibration_artifact_id=?",
            (calibration_id,),
        )
    reconcile_source_currentness(path)
    second_id = _publish_controlled_calibration(path, generation)
    assert second_id != calibration_id
    exact_preflight(path, propensity_bucket="0.70", **common)
    with get_connection(path) as connection:
        rows = connection.execute(
            "SELECT cache_key_sha256,currentness_state FROM search_preflight_cache"
        ).fetchall()
    assert len({str(row[0]) for row in rows}) == 3
    assert sum(row["currentness_state"] == "CURRENT" for row in rows) == 1


def test_calibration_replacement_stales_preflight_cache_and_preserves_snapshot_identity(
    parity_case,
) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    catalog = get_or_build_targeting_catalog(path)
    exact_preflight(
        path,
        context=_context(path, context_id),
        criteria=_criteria(),
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    run, _branches = _run_for(
        path,
        context_id,
        generation,
        calibration_id,
        bucket="0.70",
        criteria=_criteria(),
    )
    repository = CampaignResultRegistryRepository(path)
    result_cache_key = build_result_cache_key(run, generation)
    snapshot_id = materialize_result_snapshot(
        path,
        run,
        generation,
        result_cache_key,
        None,
        iter_selected_members(path, run, generation),
        project_root=project_root,
    )
    snapshot_before = repository.fetch_snapshot(snapshot_id)
    with get_connection(path) as connection:
        lineage = json.loads(
            connection.execute(
                """SELECT split_lineage_json FROM score_calibration_artifacts
                   WHERE calibration_artifact_id=?""",
                (calibration_id,),
            ).fetchone()[0]
        )
    replacement = FittedCalibration(
        method="ISOTONIC",
        artifact={
            "method": "ISOTONIC",
            "x_thresholds": [0.0, 1.0],
            "y_thresholds": [0.0, 1.0],
        },
        metrics={
            "brier_score": 0.1,
            "log_loss": 0.2,
            "expected_calibration_error": 0.03,
            "roc_auc": 0.8,
            "average_precision": 0.7,
            "top_decile_lift": 2.0,
        },
        split_lineage=lineage,
    )
    published = publish_fitted_calibration(
        path,
        int(generation["scoring_run_id"]),
        replacement,
        source_checksum="f" * 64,
        promote=True,
        batch_size=10,
    )

    assert published["calibration_artifact_id"] != calibration_id
    with get_connection(path) as connection:
        statuses = {
            int(row["calibration_artifact_id"]): str(row["status"])
            for row in connection.execute(
                """SELECT calibration_artifact_id,status
                   FROM score_calibration_artifacts
                   WHERE scoring_run_id=?""",
                (generation["scoring_run_id"],),
            )
        }
        cache_states = {
            str(row["currentness_state"])
            for row in connection.execute(
                "SELECT currentness_state FROM search_preflight_cache"
            )
        }
    assert statuses[calibration_id] == "STALE"
    assert statuses[int(published["calibration_artifact_id"])] == "PROMOTED"
    assert cache_states == {"STALE"}
    snapshot_after = repository.fetch_snapshot(snapshot_id)
    assert snapshot_after["calibration_artifact_id"] == calibration_id
    assert snapshot_after["snapshot_sha256"] == snapshot_before["snapshot_sha256"]


def test_result_cache_identity_binds_v2_catalog_bucket_and_calibration(parity_case) -> None:
    path, _root, context_id, generation, calibration_id = parity_case
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.70", criteria=_criteria(),
    )
    key = build_result_cache_key(run, generation)
    assert build_result_cache_key(run | {"propensity_bucket": "0.60"}, generation) != key
    assert build_result_cache_key(run | {"calibration_artifact_id": calibration_id + 1}, generation) != key
    assert build_result_cache_key(run | {"catalog_version": "f" * 64}, generation) != key
    legacy_key = build_result_cache_key(
        run | {
            "selection_contract_version": "1",
            "propensity_bucket": None,
            "calibration_artifact_id": None,
        },
        generation,
    )
    assert legacy_key != key


def test_v2_snapshot_uses_explicit_calibrated_membership_and_manifest(parity_case) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    run, _branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.50", criteria=_criteria(),
    )
    repository = CampaignResultRegistryRepository(path)
    cache_key = build_result_cache_key(run, generation)
    snapshot_id = materialize_result_snapshot(
        path,
        run,
        generation,
        cache_key,
        None,
        iter_selected_members(path, run, generation),
        project_root=project_root,
    )
    snapshot = repository.fetch_snapshot(snapshot_id)
    assert snapshot["result_membership_contract_version"] == "2"
    artifact = project_root / snapshot["storage_uri"]
    with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == RESULT_MEMBERSHIP_V2_COLUMNS
    assert rows
    assert "propensity_score" not in rows[0]
    assert all(row["probability_bucket"] == "0.50" for row in rows)
    assert all(0.50 <= float(row["calibrated_purchase_probability"]) < 0.60 for row in rows)
    assert all(row["raw_propensity_score"] for row in rows)
    manifest = json.loads((artifact.parent / "manifest.json").read_text("utf-8"))
    assert manifest["result_snapshot_manifest_contract_version"] == "2"
    assert manifest["result_membership_contract_version"] == "2"
    assert manifest["selection_contract_version"] == "2"
    assert manifest["propensity_bucket"] == "0.50"
    assert tuple(field["name"] for field in manifest["storage_schema"]) == (
        RESULT_MEMBERSHIP_V2_COLUMNS
    )


def test_v2_results_distinguish_buckets_and_summarize_calibrated_scores(
    parity_case,
) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    run_50, _ = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.50", criteria=_criteria(),
    )
    run_60, _ = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.60", criteria=_criteria(),
    )
    history = list_result_history(path)
    selections = {
        row["propensity_bucket"]: (
            row["selection_label"], row["selection_value"],
            row["selection_semantics"],
        )
        for row in history
        if row["search_run_id"] in {
            run_50["search_run_id"], run_60["search_run_id"],
        }
    }
    assert selections == {
        "0.50": (
            "Purchase Propensity", "50% to <60%",
            "CALIBRATED_PURCHASE_PROBABILITY",
        ),
        "0.60": (
            "Purchase Propensity", "60% to <70%",
            "CALIBRATED_PURCHASE_PROBABILITY",
        ),
    }

    repository = CampaignResultRegistryRepository(path)
    fence = repository.claim_search_attempt(
        int(run_50["search_run_id"]), lease_owner="v2-result-semantics-test"
    )
    repository.mark_processing(int(run_50["search_run_id"]), **fence.as_kwargs())
    repository.bind_current_attempt_lineage(
        int(run_50["search_run_id"]),
        **fence.as_kwargs(),
        generation_id=int(generation["generation_id"]),
        scoring_run_id=int(generation["scoring_run_id"]),
        calibration_artifact_id=calibration_id,
    )
    bound_run = repository.fetch_search_run(int(run_50["search_run_id"]))
    cache_key = build_result_cache_key(bound_run, generation)
    snapshot_id = materialize_result_snapshot(
        path,
        bound_run,
        generation,
        cache_key,
        None,
        iter_selected_members(path, bound_run, generation),
        project_root=project_root,
    )
    repository.complete_search_run(
        int(run_50["search_run_id"]),
        **fence.as_kwargs(),
        result_snapshot_id=snapshot_id,
        result_source="INTELLIGENCE_REUSE",
    )
    detail = get_result_detail(
        path, int(run_50["search_run_id"]), project_root=project_root
    )
    with get_connection(path) as connection:
        expected = connection.execute(
            """SELECT COUNT(*) AS count,MIN(calibrated_probability) AS minimum,
                      MAX(calibrated_probability) AS maximum,
                      AVG(calibrated_probability) AS mean
               FROM calibrated_propensity_scores
               WHERE calibration_artifact_id=?""",
            (calibration_id,),
        ).fetchone()
        raw = connection.execute(
            """SELECT score_min,score_max,score_mean FROM scoring_runs
               WHERE scoring_run_id=?""",
            (generation["scoring_run_id"],),
        ).fetchone()
    assert detail["selection_label"] == "Purchase Propensity"
    assert detail["selection_value"] == "50% to <60%"
    assert detail["snapshot_provenance"]["membership_contract_version"] == "2"
    assert detail["score_summary"] == {
        "scope": "Calibrated potential-customer universe",
        "metric_label": "Calibrated purchase probability",
        "semantics": "CALIBRATED_PURCHASE_PROBABILITY",
        "probability_bucket": "0.50",
        "population_count": int(expected["count"]),
        "minimum": float(expected["minimum"]),
        "maximum": float(expected["maximum"]),
        "mean": float(expected["mean"]),
    }
    assert (
        detail["score_summary"]["minimum"],
        detail["score_summary"]["maximum"],
        detail["score_summary"]["mean"],
    ) != (float(raw["score_min"]), float(raw["score_max"]), float(raw["score_mean"]))


def test_preflight_cache_key_changes_for_every_semantic_identity_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {
        "criteria_sha256": "1" * 64,
        "filter_branches_sha256": "2" * 64,
        "catalog_version": "3" * 64,
        "source_identity": {
            "customers": {"import_id": 1, "source_checksum": "4" * 64},
            "campaign_sales": {"import_id": 2, "source_checksum": "5" * 64},
            "demographics": {"import_id": 3, "source_checksum": "6" * 64},
        },
        "generation_id": 4,
        "scoring_run_id": 5,
        "calibration_artifact_id": 6,
        "propensity_bucket": "0.70",
        "selection_mode": "ALL_MATCHING",
        "target_count": None,
    }
    key = build_preflight_cache_key(**base)
    changes = (
        {"criteria_sha256": "a" * 64},
        {"filter_branches_sha256": "b" * 64},
        {"catalog_version": "c" * 64},
        {"source_identity": base["source_identity"] | {
            "demographics": {"import_id": 7, "source_checksum": "d" * 64}
        }},
        {"generation_id": 8},
        {"scoring_run_id": 9},
        {"calibration_artifact_id": 10},
        {"propensity_bucket": "0.60"},
        {"selection_mode": "TOP_N", "target_count": 11},
    )
    for change in changes:
        assert build_preflight_cache_key(**(base | change)) != key
    monkeypatch.setattr(preflight_service, "PREFLIGHT_CACHE_CONTRACT_VERSION", "3")
    assert build_preflight_cache_key(**base) != key


def test_larger_controlled_fixture_preflight_core_matches_materialization(parity_case) -> None:
    path, project_root, context_id, generation, calibration_id = parity_case
    additional = 10_000
    with get_connection(path, write=True) as connection:
        connection.executemany(
            """INSERT INTO demographics (
                   person_id,age,gender,state,individual_yearly_income,
                   marital_status,education,employment_status,resident_status,
                   resident_type,family_member_count,number_of_children_in_family,
                   number_of_adults_in_family,type_of_employment,family_yearly_income
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    f"L{index:06d}", 40, "Female" if index % 2 else "Male",
                    "Ohio", 75_000, "Married", "College", "Employed",
                    "Resident", "House", 3, 1, 2, "Salaried", 100_000,
                )
                for index in range(additional)
            ),
        )
        connection.executemany(
            """INSERT INTO calibrated_propensity_scores (
                   calibration_artifact_id,scoring_run_id,person_id,raw_score,
                   calibrated_probability,propensity_bucket,rank_position,
                   total_population,percentile_bucket,decile,rank_band
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    calibration_id, generation["scoring_run_id"], f"L{index:06d}",
                    0.75, 0.75, "0.70", 61 + index, 60 + additional,
                    50, 5, "LOW",
                )
                for index in range(additional)
            ),
        )
    run, branches = _run_for(
        path, context_id, generation, calibration_id,
        bucket="0.70", criteria=_criteria(),
    )
    qualifying = count_calibrated_members(
        path,
        branches,
        calibration_artifact_id=calibration_id,
        propensity_bucket="0.70",
    )
    assert qualifying == 10_051
    assert _materialized_count(
        path, run, generation, project_root=project_root
    ) == qualifying
