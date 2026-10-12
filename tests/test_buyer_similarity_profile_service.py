from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, ORDERED_FEATURES
from app.services.buyer_similarity_cohort_service import (
    BuyerCohortBuild,
    BuyerCohortManifest,
    BuyerCohortSourceIdentity,
    ProductBuyerSupport,
)
from app.services.buyer_similarity_profile_service import (
    BuyerSimilarityArtifactError,
    _profile_identity,
    _updated_prototypes,
    describe_profile_holdout,
    fit_buyer_similarity_profile,
    load_profile_artifact,
    score_buyer_similarity_frame,
    score_buyer_similarity_record,
    serialize_profile_artifact,
    write_profile_artifact,
)
from app.repositories.buyer_similarity_profile_repository import (
    BuyerSimilarityProfileFenceLost,
    BuyerSimilarityProfileLeaseBusy,
    BuyerSimilarityProfileRepository,
    BuyerSimilarityProfileSourceStale,
    publish_buyer_similarity_profile,
)


BASE_FEATURES = {
    "age": 50,
    "gender": "Female",
    "state": "MH",
    "individual_yearly_income": 100_000.0,
    "marital_status": "Married",
    "education": "Graduate",
    "employment_status": "Employed",
    "resident_status": "Owner",
    "resident_type": "Urban",
    "family_member_count": 4,
    "type_of_employment": "Salaried",
}


def _cohort(
    fit_rows: list[dict[str, object]],
    *,
    holdout_rows: list[dict[str, object]] | None = None,
    unrelated_rows: list[dict[str, object]] | None = None,
) -> BuyerCohortBuild:
    holdout = holdout_rows or [dict(BASE_FEATURES) for _ in range(40)]
    records: list[dict[str, object]] = []
    for index, features in enumerate(fit_rows):
        records.append(
            {
                "product_id": "PRD001",
                "customer_id": f"C{index:06d}",
                "split": "FIT",
                **features,
            }
        )
    for index, features in enumerate(holdout):
        records.append(
            {
                "product_id": "PRD001",
                "customer_id": f"H{index:06d}",
                "split": "HOLDOUT",
                **features,
            }
        )
    for index, features in enumerate(unrelated_rows or []):
        records.append(
            {
                "product_id": "PRD999",
                "customer_id": f"U{index:06d}",
                "split": "FIT",
                **features,
            }
        )
    support = ProductBuyerSupport(
        product_id="PRD001",
        distinct_attributed_buyers=len(fit_rows) + len(holdout),
        fit_buyers=len(fit_rows),
        holdout_buyers=len(holdout),
        fit_identity_sha256="a" * 64,
        holdout_identity_sha256="b" * 64,
        status="ELIGIBLE",
        reason_code="ELIGIBLE",
    )
    manifest = BuyerCohortManifest(
        cohort_contract_version="1",
        conversion_definition="ATTRIBUTED_PURCHASE",
        product_match_policy="ANY_SELECTED_PRODUCT_MAX_V1",
        product_ids=("PRD001",),
        historical_context={
            "campaign_types": (),
            "campaign_categories": (),
            "offer_types": (),
            "historical_campaign_channels": (),
        },
        window_start="2024-01-01",
        window_end="2025-12-31",
        demographic_reference_date="2025-12-31",
        split_strategy_version="CUSTOMER_UNION_HASH_ORDER_80_20_V1",
        split_seed=20261005,
        fit_fraction=0.8,
        source_identity=BuyerCohortSourceIdentity(
            customer_import_id=1,
            customer_source_checksum="1" * 64,
            campaign_sales_import_id=2,
            campaign_sales_source_checksum="2" * 64,
            product_catalog_sha256="3" * 64,
        ),
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        union_buyer_count=len(fit_rows) + len(holdout),
        union_fit_count=len(fit_rows),
        union_holdout_count=len(holdout),
        union_fit_identity_sha256="a" * 64,
        union_holdout_identity_sha256="b" * 64,
        context_identity_sha256="c" * 64,
        product_support=(support,),
        eligible=True,
        reason_codes=(),
        historical_age_semantics="completed years at reference date",
        prospect_age_semantics="completed years at source snapshot",
        comparison_label_semantics="UNLABELED_NOT_VERIFIED_NONBUYER",
    )
    return BuyerCohortBuild(manifest=manifest, frame=pd.DataFrame(records))


def _single_profile() -> dict[str, object]:
    return fit_buyer_similarity_profile(
        _cohort([dict(BASE_FEATURES) for _ in range(160)]),
        product_id="PRD001",
        assignment_chunk_size=17,
    )


def _reidentify(profile: dict[str, object]) -> dict[str, object]:
    profile["immutable_identity_sha256"] = _profile_identity(
        profile, include_existing=False
    )
    return profile


def _registry_database(tmp_path: Path) -> Path:
    database = tmp_path / "registry.db"
    initialize_database(database)
    with get_connection(database, write=True) as connection:
        connection.executemany(
            """INSERT INTO data_import_runs (
                import_id,dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES (?,?,?,?,?,'COMPLETED',0,0,0,?)""",
            (
                (1, "customers", "customers.csv", "2026-10-06T00:00:00Z", "2026-10-06T00:00:01Z", "1" * 64),
                (2, "campaign_sales", "sales.csv", "2026-10-06T00:00:00Z", "2026-10-06T00:00:01Z", "2" * 64),
            ),
        )
    return database


def test_independent_known_prototype_score_math_and_contributions() -> None:
    profile = copy.deepcopy(_single_profile())
    profile["categorical_vocabulary"]["gender"] = ["Female", "Male"]
    profile["categorical_vocabulary"]["state"] = ["KA", "MH"]
    profile["numeric_scales"]["age"] = {
        "q05": 40.0,
        "q95": 60.0,
        "distance_range": 20.0,
        "used_zero_range_fallback": False,
    }
    _reidentify(profile)

    exact = score_buyer_similarity_record(BASE_FEATURES, profile)
    assert exact.is_valid and exact.buyer_similarity_score == pytest.approx(1.0)
    assert sum(term.weighted_contribution for term in exact.feature_distances) == 0

    one_mismatch = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": "Male"}, profile
    )
    assert one_mismatch.buyer_similarity_score == pytest.approx(10 / 11)
    assert sum(
        term.weighted_contribution for term in one_mismatch.feature_distances
    ) == pytest.approx(1 / 11)

    two_mismatches = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": "Male", "state": "KA"}, profile
    )
    assert two_mismatches.buyer_similarity_score == pytest.approx(9 / 11)

    mismatch_and_half_range = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": "Male", "age": 60}, profile
    )
    assert mismatch_and_half_range.buyer_similarity_score == pytest.approx(1 - 1.5 / 11)


def test_missing_unknown_coverage_and_score_one_rules() -> None:
    profile = copy.deepcopy(_single_profile())
    profile["categorical_vocabulary"]["gender"] = ["Female", "Male"]
    _reidentify(profile)

    missing = {feature: None for feature in ORDERED_FEATURES}
    result = score_buyer_similarity_record(missing, profile)
    assert not result.is_valid
    assert result.buyer_similarity_score is None
    assert result.feature_coverage == 0
    assert result.invalid_reason_code == "INSUFFICIENT_FEATURE_COVERAGE"

    unknown = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": "Never Seen"}, profile
    )
    assert unknown.is_valid
    assert unknown.feature_coverage == pytest.approx(10 / 11)
    assert unknown.buyer_similarity_score == pytest.approx(10 / 11)

    missing_one = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": None}, profile
    )
    assert missing_one.is_valid
    assert missing_one.buyer_similarity_score < 1
    assert score_buyer_similarity_record(BASE_FEATURES, profile).buyer_similarity_score == 1


def test_numeric_distance_is_monotonic_and_saturates_without_clipping() -> None:
    profile = copy.deepcopy(_single_profile())
    profile["numeric_scales"]["age"] = {
        "q05": 40.0,
        "q95": 60.0,
        "distance_range": 20.0,
        "used_zero_range_fallback": False,
    }
    _reidentify(profile)
    near = score_buyer_similarity_record({**BASE_FEATURES, "age": 55}, profile)
    far = score_buyer_similarity_record({**BASE_FEATURES, "age": 60}, profile)
    saturated = score_buyer_similarity_record({**BASE_FEATURES, "age": 100}, profile)
    assert 1 > near.buyer_similarity_score > far.buyer_similarity_score > saturated.buyer_similarity_score
    assert saturated.feature_distances[0].distance == 1


def test_mode_and_nearest_ties_are_deterministic() -> None:
    frame = pd.DataFrame(
        [
            {**BASE_FEATURES, "gender": "Male"},
            {**BASE_FEATURES, "gender": "Female"},
        ]
    ).loc[:, ORDERED_FEATURES]
    mode = _updated_prototypes(frame, np.array([0, 0]), 1)[0]
    assert mode["gender"] == "Female"

    profile = copy.deepcopy(_single_profile())
    profile["categorical_vocabulary"]["gender"] = ["Female", "Male", "Other"]
    second = copy.deepcopy(profile["prototypes"][0])
    second["prototype_key"] = "P002"
    second["tie_order"] = 1
    second["values"]["gender"] = "Male"
    second["support"] = 80
    profile["prototypes"][0]["support"] = 80
    profile["prototypes"].append(second)
    profile["realized_k"] = 2
    _reidentify(profile)
    tied = score_buyer_similarity_record(
        {**BASE_FEATURES, "gender": "Other"}, profile
    )
    assert tied.prototype_key == "P001"


def test_multimodal_groups_survive_and_singleton_anchor_is_rejected() -> None:
    groups: list[dict[str, object]] = []
    for gender, state in (
        ("Female", "MH"),
        ("Male", "KA"),
        ("Female", "DL"),
        ("Male", "GJ"),
    ):
        groups.extend([{**BASE_FEATURES, "gender": gender, "state": state}] * 40)
    multimodal = fit_buyer_similarity_profile(
        _cohort(groups), product_id="PRD001", assignment_chunk_size=13
    )
    assert multimodal["realized_k"] == 4
    assert [prototype["support"] for prototype in multimodal["prototypes"]] == [40] * 4

    singleton_rows = [dict(BASE_FEATURES) for _ in range(159)]
    singleton_rows.append({**BASE_FEATURES, "state": "ZZ", "gender": "Male"})
    singleton = fit_buyer_similarity_profile(
        _cohort(singleton_rows), product_id="PRD001", assignment_chunk_size=19
    )
    assert singleton["realized_k"] == 1
    candidate_two = next(
        item for item in singleton["candidate_diagnostics"] if item["k"] == 2
    )
    assert not candidate_two["valid"]
    assert candidate_two["reason"] == "UNDERSUPPORTED_CLUSTER"


def test_fit_is_order_and_chunk_invariant_and_excludes_holdout_and_other_products() -> None:
    rows = [
        {
            **BASE_FEATURES,
            "age": 30 + index % 30,
            "state": ("MH", "KA", "DL", "GJ")[index % 4],
            "gender": ("Female", "Male")[index % 2],
        }
        for index in range(160)
    ]
    base = _cohort(rows)
    reordered = BuyerCohortBuild(
        manifest=base.manifest,
        frame=base.frame.sample(frac=1, random_state=99).reset_index(drop=True),
    )
    first = fit_buyer_similarity_profile(base, product_id="PRD001", assignment_chunk_size=7)
    second = fit_buyer_similarity_profile(
        reordered, product_id="PRD001", assignment_chunk_size=31
    )
    assert serialize_profile_artifact(first) == serialize_profile_artifact(second)
    scoring_frame = base.frame.loc[:32, ORDERED_FEATURES]
    assert score_buyer_similarity_frame(
        scoring_frame, first, chunk_size=3
    ) == score_buyer_similarity_frame(scoring_frame, first, chunk_size=19)

    changed_holdout = _cohort(
        rows,
        holdout_rows=[{**BASE_FEATURES, "state": "ZZ"} for _ in range(40)],
        unrelated_rows=[{**BASE_FEATURES, "state": "XX"} for _ in range(60)],
    )
    third = fit_buyer_similarity_profile(changed_holdout, product_id="PRD001")
    assert serialize_profile_artifact(first) == serialize_profile_artifact(third)
    first_holdout = describe_profile_holdout(base, first)
    changed_description = describe_profile_holdout(changed_holdout, third)
    assert first_holdout["predictive_validation"] is False
    assert first_holdout["score_mean"] != changed_description["score_mean"]


def test_relevant_fit_change_changes_profile_and_score() -> None:
    baseline = [dict(BASE_FEATURES) for _ in range(160)]
    changed = [
        {**BASE_FEATURES, "age": 80, "state": "KA"} for _ in range(160)
    ]
    first = fit_buyer_similarity_profile(_cohort(baseline), product_id="PRD001")
    second = fit_buyer_similarity_profile(_cohort(changed), product_id="PRD001")
    assert serialize_profile_artifact(first) != serialize_profile_artifact(second)
    first_score = score_buyer_similarity_record(BASE_FEATURES, first)
    second_score = score_buyer_similarity_record(BASE_FEATURES, second)
    assert first_score.buyer_similarity_score > second_score.buyer_similarity_score


def test_safe_json_artifact_round_trip_and_refusals(tmp_path: Path) -> None:
    profile = _single_profile()
    stored = write_profile_artifact(profile, project_root=tmp_path)
    loaded = load_profile_artifact(
        project_root=tmp_path,
        storage_uri=stored.storage_uri,
        expected_artifact_sha256=stored.artifact_sha256,
        expected_product_id="PRD001",
        expected_lineage={
            "customer_source_checksum": "1" * 64,
            "campaign_sales_source_checksum": "2" * 64,
        },
    )
    assert loaded == profile
    assert serialize_profile_artifact(loaded)[1] == stored.artifact_sha256
    assert write_profile_artifact(profile, project_root=tmp_path) == stored

    conflicting = copy.deepcopy(profile)
    conflicting["prototypes"][0]["values"]["age"] = 51.0
    with pytest.raises(BuyerSimilarityArtifactError, match="different content"):
        write_profile_artifact(conflicting, project_root=tmp_path)

    with pytest.raises(BuyerSimilarityArtifactError, match="stale"):
        load_profile_artifact(
            project_root=tmp_path,
            storage_uri=stored.storage_uri,
            expected_artifact_sha256=stored.artifact_sha256,
            expected_lineage={"customer_source_checksum": "f" * 64},
        )

    artifact_path = tmp_path / stored.storage_uri
    artifact_path.write_bytes(artifact_path.read_bytes() + b"corrupt")
    with pytest.raises(BuyerSimilarityArtifactError, match="checksum"):
        load_profile_artifact(
            project_root=tmp_path,
            storage_uri=stored.storage_uri,
            expected_artifact_sha256=stored.artifact_sha256,
        )
    with pytest.raises(BuyerSimilarityArtifactError, match="governed"):
        load_profile_artifact(
            project_root=tmp_path,
            storage_uri="../../profile.pkl",
            expected_artifact_sha256="0" * 64,
        )

    partial = copy.deepcopy(profile)
    del partial["numeric_scales"]
    partial_bytes = (json.dumps(partial, sort_keys=True, separators=(",", ":")) + "\n").encode()
    artifact_path.write_bytes(partial_bytes)
    with pytest.raises(BuyerSimilarityArtifactError, match="partial"):
        load_profile_artifact(
            project_root=tmp_path,
            storage_uri=stored.storage_uri,
            expected_artifact_sha256=hashlib.sha256(partial_bytes).hexdigest(),
        )


def test_fenced_profile_publication_is_transactional_and_reusable(tmp_path: Path) -> None:
    database = _registry_database(tmp_path)
    artifact = _single_profile()
    first = publish_buyer_similarity_profile(
        database,
        artifact,
        project_root=tmp_path,
        execution_owner="profile-worker-1",
        execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    assert not first.reused
    with get_connection(database) as connection:
        profile = dict(connection.execute(
            "SELECT * FROM buyer_similarity_profiles WHERE profile_id=?",
            (first.profile_id,),
        ).fetchone())
        stored = dict(connection.execute(
            "SELECT * FROM buyer_similarity_profile_artifacts WHERE profile_id=?",
            (first.profile_id,),
        ).fetchone())
    assert profile["publication_state"] == "PUBLISHED"
    assert profile["execution_owner"] is None and profile["execution_token"] is None
    assert stored["artifact_state"] == "PUBLISHED"
    assert stored["artifact_sha256"] == first.storage.artifact_sha256

    second = publish_buyer_similarity_profile(
        database,
        artifact,
        project_root=tmp_path,
        execution_owner="profile-worker-2",
        execution_token="b" * 64,
        now="2026-10-06T01:01:00Z",
    )
    assert second.reused and second.profile_id == first.profile_id
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profiles"
        ).fetchone()[0] == 1


def test_profile_lease_fencing_recovery_and_safe_cancellation(tmp_path: Path) -> None:
    database = _registry_database(tmp_path)
    artifact = _single_profile()
    repository = BuyerSimilarityProfileRepository(database)
    claim = repository.claim_build(
        artifact,
        execution_owner="worker-a",
        execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    with pytest.raises(BuyerSimilarityProfileLeaseBusy):
        repository.claim_build(
            artifact,
            execution_owner="worker-b",
            execution_token="b" * 64,
            now="2026-10-06T01:01:00Z",
            stale_before="2026-10-06T00:59:00Z",
        )
    recovered = repository.claim_build(
        artifact,
        execution_owner="worker-b",
        execution_token="b" * 64,
        now="2026-10-06T02:00:00Z",
        stale_before="2026-10-06T01:30:00Z",
    )
    assert recovered.profile_id == claim.profile_id
    with pytest.raises(BuyerSimilarityProfileFenceLost):
        repository.heartbeat(
            claim.profile_id,
            execution_owner="worker-a",
            execution_token="a" * 64,
            now="2026-10-06T02:01:00Z",
        )
    repository.cancel(
        recovered.profile_id,
        execution_owner="worker-b",
        execution_token="b" * 64,
    )
    with get_connection(database) as connection:
        row = connection.execute(
            "SELECT publication_state,safe_error_code FROM buyer_similarity_profiles WHERE profile_id=?",
            (recovered.profile_id,),
        ).fetchone()
    assert tuple(row) == ("FAILED", "CANCELLED")


def test_source_replacement_before_publication_fails_closed(tmp_path: Path) -> None:
    database = _registry_database(tmp_path)
    artifact = _single_profile()
    repository = BuyerSimilarityProfileRepository(database)
    claim = repository.claim_build(
        artifact,
        execution_owner="worker-a",
        execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    storage = write_profile_artifact(artifact, project_root=tmp_path)
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                import_id,dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES (3,'customers','replacement.csv',?,?,'COMPLETED',0,0,0,?)""",
            ("2026-10-06T01:01:00Z", "2026-10-06T01:01:01Z", "f" * 64),
        )
    with pytest.raises(BuyerSimilarityProfileSourceStale):
        repository.publish(
            claim.profile_id,
            artifact,
            storage,
            project_root=tmp_path,
            execution_owner="worker-a",
            execution_token="a" * 64,
            now="2026-10-06T01:02:00Z",
        )
    with get_connection(database) as connection:
        profile = connection.execute(
            "SELECT publication_state,safe_error_code FROM buyer_similarity_profiles WHERE profile_id=?",
            (claim.profile_id,),
        ).fetchone()
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts WHERE profile_id=?",
            (claim.profile_id,),
        ).fetchone()[0]
    assert tuple(profile) == ("STALE", "SOURCE_REPLACED")
    assert artifact_count == 0
