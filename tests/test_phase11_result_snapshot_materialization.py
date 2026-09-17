from __future__ import annotations

import csv
import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.phase11_result_contracts import RESULT_MEMBERSHIP_COLUMNS
from app.services.phase11_result_snapshot_service import (
    RESULT_MEMBERSHIP_SCHEMA,
    RESULT_SNAPSHOT_STORAGE_FORMAT,
    ResultSnapshotMaterializer,
    ResultSnapshotPublicationError,
    ResultSnapshotValidationError,
    materialize_result_snapshot,
    recover_orphan_result_artifacts,
    validate_result_snapshot,
)
from app.services.phase11_search_orchestration_service import (
    build_result_cache_key,
    execute_phase11_search,
)
from tests.test_phase11_search_result_registry import _search, case
from tests.test_phase11_smart_reuse_engine import fixed_reader, ready_response


def _generation(case):
    return Phase10IntelligenceRepository(case[0]).fetch_generation(
        case[1]["generation_id"]
    )


def _members():
    return iter(
        (
            {
                "person_id": "P1",
                "propensity_score": 0.9,
                "percentile_bucket": 1,
                "decile": 1,
                "rank_band": "ELITE",
            },
            {
                "person_id": "P2",
                "propensity_score": 0.8,
                "percentile_bucket": 2,
                "decile": 1,
                "rank_band": "VERY_HIGH",
            },
        )
    )


def _materialize(case, search_run_id: int):
    path, _, _, repository = case
    run = repository.fetch_search_run(search_run_id)
    generation = _generation(case)
    cache_key = build_result_cache_key(run, generation)
    snapshot_id = materialize_result_snapshot(
        path,
        run,
        generation,
        cache_key,
        None,
        _members(),
        project_root=path.parent,
    )
    return snapshot_id, run, generation, cache_key


def test_streams_deterministic_no_pii_snapshot_and_exact_manifest(case):
    path, _, _, repository = case
    snapshot_id, run, generation, cache_key = _materialize(case, _search(case))
    snapshot = repository.fetch_snapshot(snapshot_id)
    artifact = path.parent / snapshot["storage_uri"]
    manifest_path = artifact.parent / "manifest.json"

    assert snapshot["storage_format"] == RESULT_SNAPSHOT_STORAGE_FORMAT
    assert artifact.is_file() and manifest_path.is_file()
    with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == RESULT_MEMBERSHIP_COLUMNS
    assert [row["person_id"] for row in rows] == ["P1", "P2"]
    assert not {
        "name", "email", "phone", "phone_number", "postal_code",
        "street", "address",
    }.intersection(reader.fieldnames or ())

    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["snapshot_id"] == snapshot_id
    assert manifest["row_count"] == 2
    assert manifest["generation_id"] == generation["generation_id"]
    assert manifest["scoring_run_id"] == generation["scoring_run_id"]
    assert manifest["model_run_id"] == generation["model_run_id"]
    assert manifest["analysis_run_id"] == generation["analysis_run_id"]
    assert manifest["targeting_criteria_sha256"] == run["targeting_criteria_sha256"]
    assert manifest["filter_branches_sha256"] == run["filter_branches_sha256"]
    assert manifest["storage_schema"] == list(RESULT_MEMBERSHIP_SCHEMA)
    assert validate_result_snapshot(
        snapshot, run, generation, cache_key, project_root=path.parent
    ).is_valid


def test_same_membership_bytes_are_reproducible(case):
    path, _, _, repository = case
    first_id, *_ = _materialize(case, _search(case))
    second_id, *_ = _materialize(
        case,
        _search(
            case,
            targeting_criteria={"states": ["Texas"]},
            filter_branches=[{"state": ["Texas"]}],
        ),
    )
    first = repository.fetch_snapshot(first_id)
    second = repository.fetch_snapshot(second_id)
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert (path.parent / first["storage_uri"]).read_bytes() == (
        path.parent / second["storage_uri"]
    ).read_bytes()


def test_invalid_membership_leaves_no_registry_row_or_orphan(case):
    path, _, _, repository = case
    run = repository.fetch_search_run(_search(case))
    generation = _generation(case)
    bad = list(_members())
    bad[0] = bad[0] | {"email": "person@example.test"}
    with pytest.raises(ResultSnapshotValidationError):
        materialize_result_snapshot(
            path, run, generation, build_result_cache_key(run, generation),
            None, bad, project_root=path.parent,
        )
    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_result_snapshots"
        ).fetchone()[0] == 0
    results = path.parent / "artifacts" / "results"
    assert not list(results.iterdir())


def test_database_insert_failure_cleans_published_orphan(case, monkeypatch):
    path, _, _, repository = case
    run = repository.fetch_search_run(_search(case))
    generation = _generation(case)

    def fail(*args, **kwargs):
        raise sqlite3.IntegrityError("forced registry failure")

    monkeypatch.setattr(
        CampaignResultRegistryRepository,
        "register_snapshot_in_transaction",
        fail,
    )
    with pytest.raises(sqlite3.IntegrityError):
        materialize_result_snapshot(
            path, run, generation, build_result_cache_key(run, generation),
            None, _members(), project_root=path.parent,
        )
    assert repository.find_snapshot_by_cache_key(
        build_result_cache_key(run, generation)
    ) is None
    assert not list((path.parent / "artifacts" / "results").iterdir())


def test_corrupt_existing_snapshot_is_repaired_only_to_original_identity(case):
    path, _, _, repository = case
    snapshot_id, run, generation, cache_key = _materialize(case, _search(case))
    snapshot = repository.fetch_snapshot(snapshot_id)
    artifact = path.parent / snapshot["storage_uri"]
    artifact.write_bytes(b"corrupt")
    repository.update_snapshot_currentness(snapshot_id, state="STALE")

    repaired_id = materialize_result_snapshot(
        path, run, generation, cache_key, snapshot, _members(),
        project_root=path.parent,
    )
    repaired = repository.fetch_snapshot(repaired_id)
    assert repaired_id == snapshot_id
    assert validate_result_snapshot(
        repaired, run, generation, cache_key, project_root=path.parent
    ).is_valid
    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_result_snapshots"
        ).fetchone()[0] == 1


def test_immutable_snapshot_refuses_different_regenerated_membership(case):
    path, _, _, repository = case
    snapshot_id, run, generation, cache_key = _materialize(case, _search(case))
    snapshot = repository.fetch_snapshot(snapshot_id)
    artifact = path.parent / snapshot["storage_uri"]
    original = artifact.read_bytes()
    changed = list(_members())
    changed[1] = changed[1] | {"person_id": "P9"}
    repository.update_snapshot_currentness(snapshot_id, state="STALE")

    with pytest.raises(ResultSnapshotPublicationError, match="immutable snapshot"):
        materialize_result_snapshot(
            path, run, generation, cache_key, snapshot, changed,
            project_root=path.parent,
        )
    assert artifact.read_bytes() == original
    assert repository.fetch_snapshot(snapshot_id)["snapshot_sha256"] == snapshot["snapshot_sha256"]


def test_zero_rows_are_valid_and_manifest_drift_is_rejected(case):
    path, _, _, repository = case
    run = repository.fetch_search_run(_search(case))
    generation = _generation(case)
    cache_key = build_result_cache_key(run, generation)
    snapshot_id = materialize_result_snapshot(
        path, run, generation, cache_key, None, (), project_root=path.parent
    )
    snapshot = repository.fetch_snapshot(snapshot_id)
    assert snapshot["resolved_count"] == 0
    assert validate_result_snapshot(
        snapshot, run, generation, cache_key, project_root=path.parent
    ).is_valid

    manifest_path = (
        path.parent / snapshot["storage_uri"]
    ).parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["storage_schema"].append({"name": "email", "type": "string"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    validation = validate_result_snapshot(
        snapshot, run, generation, cache_key, project_root=path.parent
    )
    assert not validation.is_valid and validation.error_code == "MANIFEST_MISMATCH"


def test_orchestrator_reuses_production_snapshot_without_duplicate_file(case):
    path, _, _, repository = case
    generation = _generation(case)
    materializer = ResultSnapshotMaterializer(path.parent)
    first = _search(case)
    first_outcome = execute_phase11_search(
        path,
        first,
        materializer=materializer,
        project_root=path.parent,
        phase10_reader=fixed_reader(ready_response(generation)),
        membership_source=lambda *_: _members(),
    )
    second = _search(case, campaign_name="Repeated exact request")

    def forbidden_scan(*_args):
        raise AssertionError("exact cache reuse must not scan membership")

    second_outcome = execute_phase11_search(
        path,
        second,
        materializer=materializer,
        project_root=path.parent,
        phase10_reader=fixed_reader(ready_response(generation)),
        membership_source=forbidden_scan,
    )
    assert first_outcome.result_snapshot_id == second_outcome.result_snapshot_id
    assert second_outcome.result_source == "EXACT_RESULT_REUSE"
    assert len(list((path.parent / "artifacts" / "results").iterdir())) == 1
    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_result_snapshots"
        ).fetchone()[0] == 1


def test_bounded_restart_recovery_removes_only_recognized_unregistered_orphans(case):
    path, _, _, _repository = case
    results = path.parent / "artifacts" / "results"
    pending = results / ".pending_result_abandoned"
    pending.mkdir(parents=True)
    (pending / "members.csv.gz").write_bytes(b"partial")
    orphan = results / "result_snapshot_000001"
    orphan.mkdir()
    (orphan / "manifest.json").write_text("{}", encoding="utf-8")
    unrelated = results / "operator_notes"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep", encoding="utf-8")

    assert recover_orphan_result_artifacts(
        path, project_root=path.parent, minimum_age_seconds=0
    ) == 2
    assert not pending.exists() and not orphan.exists()
    assert (unrelated / "keep.txt").read_text("utf-8") == "keep"
