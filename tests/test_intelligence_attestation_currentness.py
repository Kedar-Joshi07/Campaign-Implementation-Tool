from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from time import perf_counter

import pytest

from app.database.connection import get_connection
from app.database.schema import MIGRATIONS
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.repositories.scoring_repository import ScoringRepository
from app.services.intelligence_attestation_service import (
    ATTESTATION_INTEGRITY_CONTRACT_VERSION,
    ATTESTATION_VERIFICATION_CONTRACT_VERSION,
    has_current_attestation,
    record_deep_verification_attestation,
)
from app.services.phase11_export_service import (
    Phase11ExportConflictError,
    stream_phase11_result_export_csv,
)
from app.services.phase10_orchestration_service import (
    prepare_phase10_orchestration,
    run_phase10_orchestration,
)
from app.services.phase11_search_orchestration_service import execute_phase11_search
from app.services.potential_customer_preflight_service import exact_preflight
from app.services.source_currentness_service import reconcile_source_currentness
from app.services.targeting_option_catalog_service import get_or_build_targeting_catalog
from tests.test_phase10_orchestration_service import (
    _create_context,
    _seed_orchestration_database,
)
from tests.test_phase11_smart_reuse_engine import (
    DeterministicMaterializer,
    fixed_membership_source,
)


@pytest.fixture(scope="module")
def verified_generation_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("attestation-currentness")
    database_path, project_root = _seed_orchestration_database(root)
    context_id = _create_context(database_path)
    started = prepare_phase10_orchestration(
        database_path, context_id, submitter=lambda *_args: None
    )
    ready = run_phase10_orchestration(
        database_path,
        int(started.orchestration["orchestration_id"]),
        project_root=project_root,
        artifact_root=Path("artifacts/models"),
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert ready["status"] == "READY"
    generation = Phase10IntelligenceRepository(database_path).fetch_generation(
        int(ready["generation_id"])
    )
    assert generation is not None
    return database_path, project_root, context_id, generation


@pytest.fixture
def attestation_case(tmp_path, verified_generation_source):
    source, project_root, context_id, generation = verified_generation_source
    database_path = tmp_path / "attestation.db"
    shutil.copy2(source, database_path)
    return database_path, project_root, context_id, dict(generation)


def test_verified_attestation_binds_full_identity_and_fast_path_avoids_deep_scan(
    attestation_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, _root, _context_id, generation = attestation_case
    recorded = record_deep_verification_attestation(database_path, generation)
    assert recorded["status"] == "VERIFIED"
    assert recorded["verified_row_count"] == 60

    def forbidden_deep(*_args, **_kwargs):
        raise AssertionError("current-attestation lookup must not deep-scan scores")

    monkeypatch.setattr(
        "app.services.intelligence_attestation_service.validate_completed_scoring_run_integrity_deep",
        forbidden_deep,
    )
    started = perf_counter()
    assert has_current_attestation(database_path, generation) is True
    elapsed = perf_counter() - started
    assert elapsed < 2.0
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM intelligence_verification_attestations"
        ).fetchone()
    assert row["verification_contract_version"] == ATTESTATION_VERIFICATION_CONTRACT_VERSION
    assert row["integrity_contract_version"] == ATTESTATION_INTEGRITY_CONTRACT_VERSION
    assert len(row["verified_facts_sha256"]) == 64
    assert row["customer_import_id"] == generation["customer_import_id"]
    assert row["campaign_sales_import_id"] == generation["campaign_sales_import_id"]
    assert row["demographic_import_id"] == generation["demographic_import_id"]


@pytest.mark.parametrize(
    ("field", "value", "failure_code"),
    (
        ("duplicate_person_count", 1, "SCORING_DEEP_INTEGRITY_FAILED"),
        ("missing_person_count", 1, "SCORING_DEEP_INTEGRITY_FAILED"),
        ("invalid_score_count", 1, "SCORING_DEEP_INTEGRITY_FAILED"),
    ),
)
def test_deep_integrity_failure_never_creates_verified_attestation(
    attestation_case,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int,
    failure_code: str,
) -> None:
    database_path, _root, _context_id, generation = attestation_case
    original = ScoringRepository.fetch_phase10_score_integrity

    def corrupted(repository, scoring_run_id):
        facts = original(repository, scoring_run_id)
        facts[field] = value
        if field == "duplicate_person_count":
            facts["distinct_person_count"] -= 1
        return facts

    monkeypatch.setattr(ScoringRepository, "fetch_phase10_score_integrity", corrupted)
    recorded = record_deep_verification_attestation(database_path, generation)
    assert recorded["status"] == "FAILED"
    assert failure_code in recorded["failure_codes"]
    assert has_current_attestation(database_path, generation) is False


def test_missing_model_identity_never_creates_verified_attestation(
    attestation_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, _root, _context_id, generation = attestation_case
    monkeypatch.setattr(
        "app.services.intelligence_attestation_service.ModelRunRepository.fetch_run",
        lambda *_args: None,
    )
    recorded = record_deep_verification_attestation(database_path, generation)
    assert recorded["status"] == "FAILED"
    assert "MODEL_RUN_MISSING" in recorded["failure_codes"]


def test_new_authoritative_source_invalidates_old_attestation(attestation_case) -> None:
    database_path, _root, _context_id, generation = attestation_case
    assert record_deep_verification_attestation(database_path, generation)["status"] == "VERIFIED"
    assert has_current_attestation(database_path, generation) is True
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','data/new-demographics.csv.gz',
                   '2026-09-29T10:00:00Z','2026-09-29T10:00:01Z',
                   'COMPLETED',60,60,0,?)""",
            ("f" * 64,),
        )
    assert has_current_attestation(database_path, generation) is False


def test_old_verification_or_integrity_contract_is_not_reused(attestation_case) -> None:
    database_path, _root, _context_id, generation = attestation_case
    recorded = record_deep_verification_attestation(database_path, generation)
    assert recorded["status"] == "VERIFIED"
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """UPDATE intelligence_verification_attestations
               SET verification_contract_version='1',integrity_contract_version='1'"""
        )
    assert has_current_attestation(database_path, generation) is False


def test_schema_24_marks_legacy_count_only_attestation_stale(attestation_case) -> None:
    database_path, _root, _context_id, generation = attestation_case
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT INTO intelligence_verification_attestations (
                   attestation_key_sha256,generation_id,scoring_run_id,
                   source_checksums_json,artifact_sha256,schema_version,
                   verified_at,verification_status,verified_row_count
               ) VALUES (?,?,?,?,?,'23','2026-09-28T00:00:00Z','VERIFIED',60)""",
            (
                "a" * 64,
                generation["generation_id"],
                generation["scoring_run_id"],
                "{}",
                generation["artifact_sha256"],
            ),
        )
        MIGRATIONS[24](connection)
        MIGRATIONS[24](connection)
    with get_connection(database_path) as connection:
        status = connection.execute(
            """SELECT verification_status
               FROM intelligence_verification_attestations
               WHERE attestation_key_sha256=?""",
            ("a" * 64,),
        ).fetchone()[0]
    assert status == "STALE"


def test_phase11_direct_reuse_does_not_call_deep_validator(
    attestation_case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root, context_id, generation = attestation_case
    assert record_deep_verification_attestation(database_path, generation)["status"] == "VERIFIED"
    repository = CampaignResultRegistryRepository(database_path)
    search_run_id = repository.create_search_run(
        campaign_name="Attested direct reuse",
        targeting_context_id=context_id,
        modeling_context_sha256=generation["modeling_context_sha256"],
        targeting_criteria={"selection_mode": "ALL_MATCHING", "target_count": None},
        filter_branches=[{}],
        delivery_channel="EMAIL",
    )
    fence = repository.claim_search_attempt(
        search_run_id, lease_owner="attestation-direct-reuse-test"
    )
    monkeypatch.setattr(
        "app.services.intelligence_attestation_service.validate_completed_scoring_run_integrity_deep",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("direct reuse must not deep-scan")
        ),
    )
    outcome = execute_phase11_search(
        database_path,
        search_run_id,
        **fence.as_kwargs(),
        materializer=DeterministicMaterializer(project_root, repository),
        project_root=project_root,
        membership_source=fixed_membership_source,
        phase10_reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("current attested generation should bypass Phase 10 API")
        ),
        phase10_preparer=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("current attested generation should bypass Phase 10 build")
        ),
    )
    assert outcome.status == "COMPLETED"


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


def _governed_calibration_lineage(database_path: Path, model_run_id: int) -> str:
    with get_connection(database_path) as connection:
        model_lineage = json.loads(connection.execute(
            "SELECT split_lineage_json FROM model_runs WHERE model_run_id=?",
            (model_run_id,),
        ).fetchone()[0])
    partitions = model_lineage["partitions"]
    payload = {
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
        payload[f"{field}_sha256"] = hashlib.sha256(
            json.dumps(sorted(payload[field]), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize(
    ("dataset_name", "row_count"),
    (("customers", 40), ("campaign_sales", 40), ("demographics", 60)),
)
def test_authoritative_replacement_stales_every_dependent_currentness_layer(
    attestation_case,
    dataset_name: str,
    row_count: int,
) -> None:
    database_path, project_root, context_id, generation = attestation_case
    assert record_deep_verification_attestation(database_path, generation)["status"] == "VERIFIED"
    catalog = get_or_build_targeting_catalog(database_path)
    with get_connection(database_path, write=True) as connection:
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
                _governed_calibration_lineage(
                    database_path, int(generation["model_run_id"])
                ),
                "b" * 64, "c" * 64, "2026-09-29T09:00:00Z",
                "2026-09-29T09:00:00Z",
            ),
        ).lastrowid)
        context = connection.execute(
            "SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?",
            (context_id,),
        ).fetchone()[0]
    raw_context = json.loads(context)
    raw_context.pop("campaign_targeting_context_contract_version", None)
    before = exact_preflight(
        database_path,
        context=raw_context,
        criteria={},
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    assert before["calibration_currentness"] == "CURRENT"
    assert before["calibration_artifact_id"] == calibration_id

    repository = CampaignResultRegistryRepository(database_path)
    run_id = repository.create_search_run(
        campaign_name="Source invalidation export",
        targeting_context_id=context_id,
        modeling_context_sha256=generation["modeling_context_sha256"],
        targeting_criteria={"selection_mode": "ALL_MATCHING", "target_count": None},
        filter_branches=[{}],
        delivery_channel="EMAIL",
    )
    fence = repository.claim_search_attempt(run_id, lease_owner="source-invalidation-test")
    outcome = execute_phase11_search(
        database_path,
        run_id,
        **fence.as_kwargs(),
        materializer=DeterministicMaterializer(project_root, repository),
        project_root=project_root,
        membership_source=fixed_membership_source,
        phase10_reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified generation should be reused")
        ),
        phase10_preparer=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified generation should be reused")
        ),
    )
    assert outcome.status == "COMPLETED"
    run = repository.fetch_search_run(run_id)
    snapshot_id = int(run["result_snapshot_id"])

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES (?,?,'2026-09-29T10:00:00Z','2026-09-29T10:00:01Z',
                         'COMPLETED',?,?,0,?)""",
            (dataset_name, f"data/replaced-{dataset_name}.csv", row_count, row_count, "f" * 64),
        )
    reconciled = reconcile_source_currentness(database_path)
    assert reconciled["stale_attestations"] == 1
    assert reconciled["stale_calibrations"] == 1
    assert reconciled["stale_preflight_entries"] == 1
    assert reconciled["stale_snapshots"] == 1
    repaired_again = reconcile_source_currentness(database_path)
    assert repaired_again["catalog_version"] == reconciled["catalog_version"]
    assert all(
        repaired_again[key] == 0
        for key in (
            "stale_attestations", "stale_calibrations",
            "stale_preflight_entries", "stale_snapshots",
        )
    )
    assert has_current_attestation(database_path, generation) is False
    repeated = exact_preflight(
        database_path,
        context=raw_context,
        criteria={},
        propensity_bucket="0.70",
        catalog_version=catalog["catalog_version"],
    )
    assert repeated["calibration_currentness"] == "STALE"
    assert repeated["bucket_count"] == repeated["intersection_count"] == 0
    assert repeated["demo_ready"] is False
    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT status FROM score_calibration_artifacts WHERE calibration_artifact_id=?",
            (calibration_id,),
        ).fetchone()[0] == "STALE"
        assert connection.execute(
            "SELECT currentness_state FROM search_preflight_cache"
        ).fetchone()[0] == "STALE"
    assert repository.fetch_snapshot(snapshot_id)["currentness_state"] == "STALE"
    with pytest.raises(Phase11ExportConflictError):
        stream_phase11_result_export_csv(
            database_path,
            search_run_id=run_id,
            request=_NeverDisconnected(),
            project_root=project_root,
        )


def test_catalog_checksum_identity_is_repromoted_when_sources_return(
    attestation_case,
) -> None:
    database_path, _project_root, _context_id, _generation = attestation_case
    first = get_or_build_targeting_catalog(database_path)
    with get_connection(database_path, write=True) as connection:
        original = connection.execute(
            """SELECT source_checksum FROM data_import_runs
               WHERE dataset_name='demographics' AND status='COMPLETED'
               ORDER BY import_id DESC LIMIT 1"""
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','data/replacement.csv','2026-09-29T10:00:00Z',
                         '2026-09-29T10:00:01Z','COMPLETED',60,60,0,?)""",
            ("f" * 64,),
        )
    second = get_or_build_targeting_catalog(database_path)
    assert second["catalog_version"] != first["catalog_version"]
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','data/original-again.csv','2026-09-29T11:00:00Z',
                         '2026-09-29T11:00:01Z','COMPLETED',60,60,0,?)""",
            (original,),
        )
    returned = get_or_build_targeting_catalog(database_path)
    assert returned["catalog_version"] == first["catalog_version"]
    with get_connection(database_path) as connection:
        current = connection.execute(
            "SELECT catalog_version FROM targeting_option_catalogs WHERE is_current=1"
        ).fetchall()
    assert [row[0] for row in current] == [first["catalog_version"]]
