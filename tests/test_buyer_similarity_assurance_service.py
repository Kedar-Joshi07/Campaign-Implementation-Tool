"""Independent descriptive assurance and explanation guards for Stage 14B_08."""

from __future__ import annotations

import copy
import csv
import gzip
import sqlite3

import pandas as pd
import pytest

from app.ml.feature_contract import ORDERED_FEATURES
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256
from app.services.buyer_similarity_cohort_service import (
    BuyerCohortBuild, BuyerCohortManifest, BuyerCohortSourceIdentity,
    ProductBuyerSupport,
)
from app.services.buyer_similarity_assurance_service import (
    BuyerSimilarityAssuranceError,
    _distribution,
    evaluate_bounded_similarity_assurance,
    explain_buyer_similarity_record,
    summarize_result_explanations,
)
from app.services.buyer_similarity_profile_service import (
    fit_buyer_similarity_profile, score_buyer_similarity_record,
    write_profile_artifact,
)

BASE_FEATURES = {
    "age": 50, "gender": "Female", "state": "MH",
    "individual_yearly_income": 100_000.0, "marital_status": "Married",
    "education": "Graduate", "employment_status": "Employed",
    "resident_status": "Owner", "resident_type": "Urban",
    "family_member_count": 4, "type_of_employment": "Salaried",
}


def _cohort(fit_rows):
    rows = [
        {"product_id": "PRD001", "customer_id": f"F{index:06d}",
         "split": "FIT", **record}
        for index, record in enumerate(fit_rows)
    ] + [
        {"product_id": "PRD001", "customer_id": f"H{index:06d}",
         "split": "HOLDOUT", **BASE_FEATURES}
        for index in range(40)
    ]
    support = ProductBuyerSupport("PRD001", 200, 160, 40,
                                  "a" * 64, "b" * 64, "ELIGIBLE", "ELIGIBLE")
    manifest = BuyerCohortManifest(
        cohort_contract_version="1", conversion_definition="ATTRIBUTED_PURCHASE",
        product_match_policy="ANY_SELECTED_PRODUCT_MAX_V1",
        product_ids=("PRD001",),
        historical_context={key: () for key in (
            "campaign_types", "campaign_categories", "offer_types",
            "historical_campaign_channels")},
        window_start="2024-01-01", window_end="2025-12-31",
        demographic_reference_date="2025-12-31",
        split_strategy_version="CUSTOMER_UNION_HASH_ORDER_80_20_V1",
        split_seed=20261005, fit_fraction=0.8,
        source_identity=BuyerCohortSourceIdentity(1, "1" * 64, 2, "2" * 64,
                                                   "3" * 64),
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        union_buyer_count=200, union_fit_count=160, union_holdout_count=40,
        union_fit_identity_sha256="a" * 64,
        union_holdout_identity_sha256="b" * 64,
        context_identity_sha256="c" * 64, product_support=(support,),
        eligible=True, reason_codes=(),
        historical_age_semantics="completed years at reference date",
        prospect_age_semantics="completed years at source snapshot",
        comparison_label_semantics="UNLABELED_NOT_VERIFIED_NONBUYER",
    )
    return BuyerCohortBuild(manifest=manifest, frame=pd.DataFrame(rows))


@pytest.fixture(scope="module")
def sources():
    fit = [dict(BASE_FEATURES) for _ in range(160)]
    cohort = _cohort(fit)
    profile = fit_buyer_similarity_profile(cohort, product_id="PRD001")
    broad = pd.DataFrame([dict(BASE_FEATURES) for _ in range(24)]).loc[:, ORDERED_FEATURES]
    prospect = broad.copy()
    prospect.loc[0:5, "age"] = 60
    return cohort, profile, broad, prospect


def _evaluate(sources):
    cohort, profile, broad, prospect = sources
    return evaluate_bounded_similarity_assurance(
        broad_training=broad, prospects=prospect, cohort=cohort, artifact=profile,
        broad_training_source_checksum="1" * 64,
        prospect_source_checksum="4" * 64,
        expected_prospect_source_checksum="4" * 64,
        current_sources=True,
    )


def test_training_defined_bins_missingness_ks_psi_and_variation():
    train = pd.DataFrame([dict(BASE_FEATURES) for _ in range(4)]).loc[:, ORDERED_FEATURES]
    other = train.copy()
    other.loc[0:1, "age"] = 60
    other.loc[0:1, "gender"] = "Male"
    other.loc[2, "age"] = None
    summary = _distribution(train, other)
    assert summary["numeric"]["age"]["training_defined_bin_edges"] == [50.0]
    assert summary["numeric"]["age"]["comparison_missing_count"] == 1
    assert summary["numeric"]["age"]["ks_nonmissing"] == pytest.approx(2 / 3)
    assert summary["numeric"]["age"]["psi_including_missing"] > 0
    assert summary["categorical"]["gender"]["total_variation"] == pytest.approx(0.5)
    assert summary["categorical"]["gender"]["comparison_counts"] == [2, 2, 0]


def test_source_and_split_identity_fail_closed(sources):
    cohort, profile, broad, prospect = sources
    arguments = dict(broad_training=broad, prospects=prospect, cohort=cohort,
                     artifact=profile, broad_training_source_checksum="1" * 64,
                     prospect_source_checksum="4" * 64,
                     expected_prospect_source_checksum="4" * 64,
                     current_sources=True)
    for changed in ({"current_sources": False},
                    {"prospect_source_checksum": "5" * 64},
                    {"broad_training_source_checksum": "6" * 64}):
        with pytest.raises(BuyerSimilarityAssuranceError):
            evaluate_bounded_similarity_assurance(**(arguments | changed))
    different = copy.deepcopy(profile)
    different["lineage"]["fit_identity_sha256"] = "f" * 64
    with pytest.raises(Exception):
        evaluate_bounded_similarity_assurance(**(arguments | {"artifact": different}))


def test_bounded_assurance_is_descriptive_and_selection_independent(sources):
    report = _evaluate(sources)
    assert report["scope"] == "BOUNDED_DESCRIPTIVE_SAMPLE"
    assert report["independent_descriptive_holdout"]["population_count"] == 40
    assert report["independent_descriptive_holdout"]["all_valid_scores_tied"] is True
    assert report["predictive_validation"].startswith("UNAVAILABLE")
    assert report["response_lift_validation"] == "UNAVAILABLE"
    assert len(report["bootstrap_fit_stability"]["repetitions"]) == 3
    assert len(report["perturbation_sensitivity"]["by_feature"]) == 11
    assert "threshold" not in str(report).lower()
    assert "target_count" not in str(report).lower()
    assert _evaluate(sources) == report


def test_explanation_exact_contributions_and_no_identity_or_claims(sources):
    _cohort_value, profile, _broad, _prospects = sources
    record = dict(BASE_FEATURES)
    record["age"] = 51
    explained = explain_buyer_similarity_record(record, profile)
    assert explained["distance"] == pytest.approx(1 / 11)
    assert explained["similarity_score"] == pytest.approx(10 / 11)
    assert sum(term["weighted_contribution"] for term in explained["feature_terms"]) == pytest.approx(explained["distance"])
    assert explained["fit_buyer_support"] == 160
    assert "prototype_key" not in explained
    assert "customer_id" not in str(explained)
    assert "purchase probability" in explained["meaning"]
    assert "90 percent" not in str(explained).lower()
    assert "causes" not in str(explained).lower()


def test_aggregate_result_explanation_contains_only_bounded_facts(tmp_path, sources):
    _cohort_value, profile, _broad, _prospects = sources
    stored = write_profile_artifact(profile, project_root=tmp_path)
    database = tmp_path / "test.db"
    connection = sqlite3.connect(database)
    feature_definitions = ",".join(f'"{feature}" TEXT' for feature in ORDERED_FEATURES)
    connection.execute(f"CREATE TABLE demographics (person_id TEXT PRIMARY KEY,{feature_definitions})")
    connection.executemany(
        f"INSERT INTO demographics VALUES ({','.join('?' for _ in range(12))})",
        [(f"PRIVATE-{index}", *[BASE_FEATURES[feature] for feature in ORDERED_FEATURES])
         for index in range(5)],
    )
    connection.commit()
    connection.close()
    directory = tmp_path / "artifacts" / "similarity_results" / "snapshot_000001"
    directory.mkdir(parents=True)
    score = score_buyer_similarity_record(BASE_FEATURES, profile)
    with gzip.open(directory / "members.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "person_id", "buyer_similarity_score", "matched_product_id"))
        writer.writeheader()
        for index in range(5):
            writer.writerow({"person_id": f"PRIVATE-{index}",
                             "buyer_similarity_score": score.buyer_similarity_score,
                             "matched_product_id": "PRD001"})
    report = summarize_result_explanations(
        database, project_root=tmp_path,
        snapshot={"storage_uri": "artifacts/similarity_results/snapshot_000001/members.csv.gz",
                  "resolved_count": 5},
        profile_rows=({"product_id": "PRD001", "storage_uri": stored.storage_uri,
                       "artifact_sha256": stored.artifact_sha256},),
    )
    assert report["sample_count"] == 5
    assert report["selected_product_counts_in_sample"] == {"PRD001": 5}
    assert sum(term["mean_weighted_distance"] for term in report["feature_drivers"]) == pytest.approx(0)
    assert "PRIVATE-" not in str(report)
    assert "prototype_key" not in str(report)
    with gzip.open(directory / "members.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "person_id", "buyer_similarity_score", "matched_product_id"))
        writer.writeheader()
        writer.writerow({"person_id": "PRIVATE-0", "buyer_similarity_score": score.buyer_similarity_score,
                         "matched_product_id": "PRD001"})
    suppressed = summarize_result_explanations(
        database, project_root=tmp_path,
        snapshot={"storage_uri": "artifacts/similarity_results/snapshot_000001/members.csv.gz",
                  "resolved_count": 1},
        profile_rows=(),
    )
    assert suppressed["scope"] == "INSUFFICIENT_AGGREGATE_SUPPORT"
    assert suppressed["feature_drivers"] == []
