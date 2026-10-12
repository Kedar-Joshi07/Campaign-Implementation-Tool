"""Independent support, isolation, determinism, and partition-publication checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.connection import get_connection
from app.repositories.buyer_similarity_profile_repository import (
    BuyerSimilarityProfileFenceLost, BuyerSimilarityProfileRepository,
    publish_buyer_similarity_profile,
)
from app.services import buyer_similarity_split_service as split
from app.services.buyer_similarity_cohort_service import (
    BUYER_SPLIT_SEED,
    LEGACY_BUYER_SPLIT_STRATEGY_VERSION,
    _split_assignments,
    build_product_buyer_cohorts,
)
from app.services.buyer_similarity_partition_service import (
    BuyerPartitionError,
    PARTITION_ROOT,
    freeze_partition_manifest,
    load_partition_manifest,
)
from app.services.buyer_similarity_profile_service import (
    BuyerSimilarityArtifactError, fit_buyer_similarity_profile,
    load_profile_artifact, write_profile_artifact,
)
from app.services.buyer_similarity_scoring_service import (
    has_current_similarity_attestation, run_similarity_generation,
)
from tests.test_buyer_similarity_cohort_service import _catalog, _seed


def _overlapping_members() -> dict[str, list[str]]:
    return {
        "A": [f"C{index:04d}" for index in range(200)],
        "B": [f"C{index:04d}" for index in range(50, 250)],
        "C": [f"C{index:04d}" for index in range(100, 300)],
    }


def _hash(values: set[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(values), separators=(",", ":")).encode()).hexdigest()


def test_three_overlapping_200_buyer_products_have_one_shared_exact_split() -> None:
    members = _overlapping_members()
    baseline = _split_assignments(set().union(*map(set, members.values())))
    result = split.solve_support_aware_split(members, baseline, seed=BUYER_SPLIT_SEED)
    assert result.status == "FEASIBLE"
    assert result.product_holdout_deviation == 0
    assert result.assignments is not None
    for product, identities in members.items():
        fit = {cid for cid in identities if result.assignments[cid] == "FIT"}
        holdout = {cid for cid in identities if result.assignments[cid] == "HOLDOUT"}
        assert (len(identities), len(fit), len(holdout)) == (200, 160, 40)
        assert fit.isdisjoint(holdout), product
    assert len(result.assignments) == 300


def test_product_and_row_order_and_restart_do_not_change_identity_hashes() -> None:
    members = _overlapping_members()
    baseline = _split_assignments(set().union(*map(set, members.values())))
    first = split.solve_support_aware_split(members, baseline, seed=BUYER_SPLIT_SEED)
    reversed_members = {product: list(reversed(members[product])) for product in reversed(members)}
    second = split.solve_support_aware_split(reversed_members, baseline, seed=BUYER_SPLIT_SEED)
    assert first.status == second.status == "FEASIBLE"
    assert first.assignments == second.assignments
    assert first.assignments is not None
    expected = _hash({cid for cid, value in first.assignments.items() if value == "HOLDOUT"})
    child = subprocess.run(
        [sys.executable, "-c", (
            "import hashlib,json,sys; "
            "from app.services.buyer_similarity_cohort_service import _split_assignments; "
            "from app.services.buyer_similarity_split_service import solve_support_aware_split; "
            "m=json.loads(sys.stdin.read()); b=_split_assignments(set().union(*map(set,m.values()))); "
            "a=solve_support_aware_split(m,b,seed=20261005).assignments; "
            "print(hashlib.sha256(json.dumps(sorted(k for k,v in a.items() if v=='HOLDOUT'),"
            "separators=(',',':')).encode()).hexdigest())"
        )],
        input=json.dumps(reversed_members), text=True, capture_output=True,
        timeout=90, check=False,
    )
    assert child.returncode == 0, child.stderr[-500:]
    assert child.stdout.strip() == expected


def test_insufficient_history_and_small_exact_infeasible_overlap_are_distinct() -> None:
    below = {"A": [f"C{index:04d}" for index in range(199)]}
    baseline = _split_assignments(below["A"])
    result = split.solve_support_aware_split(below, baseline, seed=BUYER_SPLIT_SEED)
    assert result.status == "INFEASIBLE"
    assert result.reason_code == "INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT"
    assert result.assignments is None

    triangle = {"A": {"x", "y"}, "B": {"y", "z"}, "C": {"x", "z"}}
    baseline = {cid: "FIT" for cid in {"x", "y", "z"}}
    impossible = split.solve_support_aware_split(
        triangle, baseline, seed=BUYER_SPLIT_SEED,
        minimum_buyers=2, minimum_fit=1, minimum_holdout=1,
    )
    assert impossible.status == "INFEASIBLE"
    assert impossible.reason_code == "SPLIT_CONSTRAINTS_INFEASIBLE"
    assert impossible.assignments is None


def test_timeout_is_unresolved_not_infeasible(monkeypatch: pytest.MonkeyPatch) -> None:
    members = _overlapping_members()
    baseline = _split_assignments(set().union(*map(set, members.values())))
    monkeypatch.setattr(split, "milp", lambda *_args, **_kwargs: SimpleNamespace(status=1, x=None))
    result = split.solve_support_aware_split(members, baseline, seed=BUYER_SPLIT_SEED)
    assert result.status == "UNRESOLVED"
    assert result.reason_code == "SPLIT_SOLVER_UNRESOLVED"
    assert result.assignments is None
    bounded = split.solve_support_aware_split(
        members, baseline, seed=BUYER_SPLIT_SEED, max_signatures=1,
    )
    assert bounded.status == "UNRESOLVED"
    assert bounded.reason_code == "SPLIT_SOLVER_CAPACITY"


def test_assignments_accept_no_features_scores_or_metrics() -> None:
    members = _overlapping_members()
    baseline = _split_assignments(set().union(*map(set, members.values())))
    first = split.solve_support_aware_split(members, baseline, seed=BUYER_SPLIT_SEED)
    unrelated_demographics = {cid: {"income": -999, "outcome": 1, "score": .99}
                              for cid in baseline}
    unrelated_demographics.clear()
    second = split.solve_support_aware_split(members, baseline, seed=BUYER_SPLIT_SEED)
    assert first.assignments == second.assignments
    assert set(split.solve_support_aware_split.__code__.co_varnames[:2]) == {
        "product_members", "baseline",
    }


def _cohort(tmp_path: Path):
    database = _seed(tmp_path / "partition.db")
    catalog = _catalog(tmp_path / "products.csv")
    cohort = build_product_buyer_cohorts(
        database, product_ids=["P1"], window_start="2025-01-01",
        window_end="2025-12-31", product_catalog_path=catalog,
    )
    assert cohort.manifest.split_status == "FEASIBLE"
    return database, catalog, cohort


def test_atomic_partition_freeze_competition_and_corruption_fails_closed(tmp_path: Path) -> None:
    database, _, cohort = _cohort(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: freeze_partition_manifest(
                cohort, project_root=tmp_path, database_path=database,
            ), range(2),
        ))
    assert results[0] == results[1] == cohort.manifest.partition_payload()
    artifacts = list((tmp_path / PARTITION_ROOT).glob("partition_*.json"))
    assert len(artifacts) == 1
    assert "CUS0000" not in artifacts[0].read_text(encoding="utf-8")
    artifacts[0].write_text("{}\n", encoding="utf-8")
    with pytest.raises(BuyerPartitionError, match="does not match"):
        load_partition_manifest(
            project_root=tmp_path,
            context_sha256=cohort.manifest.context_identity_sha256,
            partition_sha256=cohort.manifest.partition_manifest_sha256,
        )


def test_true_process_death_after_partition_link_reuses_exact_manifest(tmp_path: Path) -> None:
    database, catalog, cohort = _cohort(tmp_path)
    code = (
        "import os,sys; from pathlib import Path; "
        "from app.services.buyer_similarity_cohort_service import build_product_buyer_cohorts; "
        "from app.services import buyer_similarity_partition_service as p; "
        "db,cat,root=map(Path,sys.argv[1:]); "
        "c=build_product_buyer_cohorts(db,product_ids=['P1'],window_start='2025-01-01',"
        "window_end='2025-12-31',product_catalog_path=cat); "
        "real=p.os.link; "
        "def_link=lambda a,b:(real(a,b),os._exit(77)); "
        "p.os.link=def_link; p.freeze_partition_manifest(c,project_root=root,database_path=db)"
    )
    child = subprocess.run(
        [sys.executable, "-c", code, str(database), str(catalog), str(tmp_path)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert child.returncode == 77, child.stderr[-500:]
    recovered = freeze_partition_manifest(
        cohort, project_root=tmp_path, database_path=database,
    )
    assert recovered == cohort.manifest.partition_payload()
    assert len(list((tmp_path / PARTITION_ROOT).glob("partition_*.json"))) == 1


def test_historical_split_remains_reproducible(tmp_path: Path) -> None:
    database, catalog, current = _cohort(tmp_path)
    legacy = build_product_buyer_cohorts(
        database, product_ids=["P1"], window_start="2025-01-01",
        window_end="2025-12-31", product_catalog_path=catalog,
        split_strategy_version=LEGACY_BUYER_SPLIT_STRATEGY_VERSION,
    )
    assert legacy.manifest.split_strategy_version == LEGACY_BUYER_SPLIT_STRATEGY_VERSION
    assert legacy.manifest.context_identity_sha256 != current.manifest.context_identity_sha256
    assert legacy.manifest.partition_manifest_sha256 is None
    old_profile = fit_buyer_similarity_profile(legacy, product_id="P1")
    new_profile = fit_buyer_similarity_profile(current, product_id="P1")
    assert old_profile["immutable_identity_sha256"] != new_profile["immutable_identity_sha256"]
    old_storage = write_profile_artifact(old_profile, project_root=tmp_path)
    assert load_profile_artifact(
        project_root=tmp_path, storage_uri=old_storage.storage_uri,
        expected_artifact_sha256=old_storage.artifact_sha256,
    )["lineage"]["split_strategy_version"] == LEGACY_BUYER_SPLIT_STRATEGY_VERSION
    new_storage = write_profile_artifact(new_profile, project_root=tmp_path)
    with pytest.raises(BuyerSimilarityArtifactError, match="partition"):
        load_profile_artifact(
            project_root=tmp_path, storage_uri=new_storage.storage_uri,
            expected_artifact_sha256=new_storage.artifact_sha256,
        )
    freeze_partition_manifest(current, project_root=tmp_path, database_path=database)
    assert load_profile_artifact(
        project_root=tmp_path, storage_uri=new_storage.storage_uri,
        expected_artifact_sha256=new_storage.artifact_sha256,
    )["lineage"]["partition_manifest_sha256"] == current.manifest.partition_manifest_sha256


def test_stale_owner_cannot_publish_new_policy_profile(tmp_path: Path) -> None:
    database, _, cohort = _cohort(tmp_path)
    freeze_partition_manifest(cohort, project_root=tmp_path, database_path=database)
    artifact = fit_buyer_similarity_profile(cohort, product_id="P1")
    repository = BuyerSimilarityProfileRepository(database)
    first = repository.claim_build(
        artifact, execution_owner="old-worker", execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    successor = repository.claim_build(
        artifact, execution_owner="new-worker", execution_token="b" * 64,
        now="2026-10-06T02:00:00Z", stale_before="2026-10-06T01:30:00Z",
    )
    assert first.profile_id == successor.profile_id
    storage = write_profile_artifact(artifact, project_root=tmp_path)
    with pytest.raises(BuyerSimilarityProfileFenceLost):
        repository.publish(
            first.profile_id, artifact, storage, project_root=tmp_path,
            execution_owner="old-worker", execution_token="a" * 64,
            now="2026-10-06T02:01:00Z",
        )
    repository.publish(
        successor.profile_id, artifact, storage, project_root=tmp_path,
        execution_owner="new-worker", execution_token="b" * 64,
        now="2026-10-06T02:02:00Z",
    )


def test_new_policy_fit_does_not_read_holdout_features(tmp_path: Path) -> None:
    _, _, cohort = _cohort(tmp_path)
    baseline = fit_buyer_similarity_profile(cohort, product_id="P1")
    altered = cohort.frame.copy(deep=True)
    altered.loc[altered["split"] == "HOLDOUT", "individual_yearly_income"] = 999999
    altered.loc[altered["split"] == "HOLDOUT", "gender"] = "Male"
    modified = fit_buyer_similarity_profile(
        replace(cohort, frame=altered), product_id="P1",
    )
    assert baseline == modified


def test_missing_partition_cannot_leave_new_generation_current(tmp_path: Path) -> None:
    database, _, cohort = _cohort(tmp_path)
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
    freeze_partition_manifest(cohort, project_root=tmp_path, database_path=database)
    artifact = fit_buyer_similarity_profile(cohort, product_id="P1")
    profile = publish_buyer_similarity_profile(
        database, artifact, project_root=tmp_path,
        execution_owner="profile-new-policy", execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    generation = run_similarity_generation(
        database, profile.profile_id, project_root=tmp_path,
        execution_owner="score-new-policy", execution_token="b" * 64,
        chunk_size=3,
    )
    generation_id = generation["similarity_generation_id"]
    assert has_current_similarity_attestation(
        database, generation_id, project_root=tmp_path,
    )
    partition_file = next((tmp_path / PARTITION_ROOT).glob("partition_*.json"))
    hidden = partition_file.with_suffix(".held")
    partition_file.rename(hidden)
    try:
        assert not has_current_similarity_attestation(
            database, generation_id, project_root=tmp_path,
        )
    finally:
        hidden.rename(partition_file)
    assert has_current_similarity_attestation(
        database, generation_id, project_root=tmp_path,
    )


def test_source_replacement_prevents_partition_publication(tmp_path: Path) -> None:
    database, _, cohort = _cohort(tmp_path)
    with get_connection(database, write=True) as connection:
        count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('customers','replacement.csv',?,?, 'COMPLETED',?,?,0,?)""",
            ("2026-10-06T01:00:00Z", "2026-10-06T01:00:00Z", count, count,
             "f" * 64),
        )
    with pytest.raises(BuyerPartitionError, match="source changed"):
        freeze_partition_manifest(cohort, project_root=tmp_path, database_path=database)
    assert not list((tmp_path / PARTITION_ROOT).glob("partition_*.json"))
