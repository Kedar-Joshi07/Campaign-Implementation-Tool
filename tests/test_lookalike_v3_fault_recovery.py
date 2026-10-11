"""Prompt 15: bounded faults through the v3 production repositories and worker."""

# Imported pytest fixture names intentionally reappear as test parameters.
# ruff: noqa: F811

from __future__ import annotations

import sqlite3
import os
import asyncio
import csv
import gzip
import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from app.database.connection import get_connection
from app.repositories.buyer_similarity_profile_repository import (
    BuyerSimilarityProfileFenceLost,
    BuyerSimilarityProfileRepository,
    publish_buyer_similarity_profile,
)
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.buyer_similarity_export_repository import (
    reconcile_similarity_export_events,
)
from app.jobs.phase11_search_coordinator import Phase11SearchCoordinator
from app.schemas.potential_customer_search import PotentialCustomerSearchV3Request
from app.schemas.potential_customer_search import PotentialCustomerSearchRequest
from app.services import potential_customer_search_submission_service as submission
from app.services.buyer_similarity_search_orchestration_service import (
    execute_similarity_search_safely,
)
from app.services.buyer_similarity_result_service import (
    reconcile_similarity_result_publications,
    validate_similarity_result_snapshot,
)
from app.services.buyer_similarity_scoring_service import run_similarity_generation
from app.services.buyer_similarity_selection_service import resolve_similarity_context
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.services.phase11_search_orchestration_service import SearchOrchestrationOutcome
from app.services.phase11_search_orchestration_service import execute_phase11_search_safely
from app.services.phase11_export_service import stream_phase11_result_export_csv
from app.services.phase11_feedback_service import ingest_feedback
from tests.test_buyer_similarity_profile_service import _registry_database, _single_profile
from tests.test_buyer_similarity_scoring_service import _case
from tests.test_buyer_similarity_cohort_service import _seed
from tests.test_lookalike_v3_snapshot_export_feedback import completed  # noqa: F401

# Process startup and disposable SQLite setup are not product latency gates.
# Keep the crash watchdog bounded while allowing slower Windows CI hosts; the
# exact exit-code, publication, fencing and recovery assertions below stay fixed.
CHILD_CRASH_WATCHDOG_SECONDS = 90


def _new_search(
    database: Path, *, minimum: float = .90,
    historical_channels: list[str] | None = None,
    product_ids: list[str] | None = None,
) -> dict:
    options = submission.search_form_options(database)
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3",
        score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=minimum,
        campaign_name="Fault recovery fixture",
        context={
            "product_ids": product_ids or ["P1"], "campaign_types": [],
            "campaign_categories": [], "offer_types": [],
            "historical_campaign_channels": historical_channels or [],
            "campaign_channel": "EMAIL",
        },
        criteria={}, selection_mode="ALL_MATCHING",
        export_profile="EMAIL_CONTACT_V2",
        catalog_version=options["catalog_version"],
    )
    return submission.submit_potential_customer_search(database, request)


def _two_product_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database = _seed(tmp_path / "two_products.db", p3_buyers=200)
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    catalog.write_text(
        "product_id,product_name,product_category\n"
        "P1,Product One,Category A\nP3,Product Three,Category B\n",
        encoding="utf-8",
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','fixture.csv',?,?,'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: True)
    return database


def test_profile_fsync_failure_is_unpublished_and_stale_takeover_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _registry_database(tmp_path)
    artifact = _single_profile()

    with monkeypatch.context() as patch:
        def fail_fsync(_descriptor: int) -> None:
            raise OSError("injected profile fsync failure")

        patch.setattr("app.services.buyer_similarity_profile_service.os.fsync", fail_fsync)
        with pytest.raises(OSError, match="injected profile fsync"):
            publish_buyer_similarity_profile(
                database, artifact, project_root=tmp_path,
                execution_owner="old-builder", execution_token="a" * 64,
                now="2026-10-06T01:00:00Z",
            )

    repository = BuyerSimilarityProfileRepository(database)
    with get_connection(database) as connection:
        row = connection.execute(
            "SELECT profile_id,publication_state FROM buyer_similarity_profiles"
        ).fetchone()
        assert row["publication_state"] == "BUILDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts"
        ).fetchone()[0] == 0
    assert not list((tmp_path / "artifacts").rglob("*.tmp"))

    recovered = publish_buyer_similarity_profile(
        database, artifact, project_root=tmp_path,
        execution_owner="new-builder", execution_token="b" * 64,
        now="2026-10-06T02:00:00Z",
        stale_before="2026-10-06T01:30:00Z",
    )
    assert recovered.profile_id == row["profile_id"]
    with pytest.raises(BuyerSimilarityProfileFenceLost):
        repository.heartbeat(
            recovered.profile_id, execution_owner="old-builder",
            execution_token="a" * 64, now="2026-10-06T02:00:01Z",
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profiles WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts WHERE artifact_state='PUBLISHED'"
        ).fetchone()[0] == 1


def test_profile_rename_interruption_reuses_exact_orphan_after_takeover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _registry_database(tmp_path)
    artifact = _single_profile()
    original_replace = os.replace

    def rename_then_interrupt(source, destination):
        original_replace(source, destination)
        raise OSError("injected profile rename interruption")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.services.buyer_similarity_profile_service.os.replace",
            rename_then_interrupt,
        )
        with pytest.raises(OSError, match="injected profile rename"):
            publish_buyer_similarity_profile(
                database, artifact, project_root=tmp_path,
                execution_owner="old-profile", execution_token="a" * 64,
                now="2026-10-06T01:00:00Z",
            )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT publication_state FROM buyer_similarity_profiles"
        ).fetchone()[0] == "BUILDING"
    recovered = publish_buyer_similarity_profile(
        database, artifact, project_root=tmp_path,
        execution_owner="new-profile", execution_token="b" * 64,
        now="2026-10-06T02:00:00Z",
        stale_before="2026-10-06T01:30:00Z",
    )
    assert recovered.reused is False
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profiles WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts WHERE artifact_state='PUBLISHED'"
        ).fetchone()[0] == 1


def test_score_publication_db_fault_rolls_back_and_same_token_resumes(
    tmp_path: Path,
) -> None:
    database, profile_id = _case(tmp_path)
    with get_connection(database, write=True) as connection:
        connection.execute(
            "CREATE TRIGGER inject_score_publish_failure BEFORE INSERT ON buyer_similarity_scores "
            "BEGIN SELECT RAISE(ABORT,'injected score publication failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected score publication"):
        run_similarity_generation(
            database, profile_id, project_root=tmp_path,
            execution_owner="score-builder", execution_token="c" * 64,
            chunk_size=4, clock=lambda: "2026-10-06T03:00:00Z",
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_generation_attestations"
        ).fetchone()[0] == 0
        row = connection.execute(
            "SELECT similarity_generation_id,publication_state FROM buyer_similarity_score_generations"
        ).fetchone()
        assert row["publication_state"] == "BUILDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 12

    with get_connection(database, write=True) as connection:
        connection.execute("DROP TRIGGER inject_score_publish_failure")
    result = run_similarity_generation(
        database, profile_id, project_root=tmp_path,
        execution_owner="score-builder", execution_token="c" * 64,
        chunk_size=4, clock=lambda: "2026-10-06T03:00:01Z",
    )
    assert result["status"] == "PUBLISHED"
    assert result["similarity_generation_id"] == row["similarity_generation_id"]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_generation_attestations WHERE verification_status='VERIFIED'"
        ).fetchone()[0] == 1


def test_completion_failure_retry_reuses_snapshot_and_preserves_attempt(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(search_id, lease_owner="fault-worker")
    original_complete = CampaignResultRegistryRepository.complete_similarity_search_run

    def fail_completion(*_args, **_kwargs) -> None:
        raise OSError("injected completion failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            CampaignResultRegistryRepository, "complete_similarity_search_run",
            fail_completion,
        )
        outcome = execute_similarity_search_safely(
            database, search_id, **fence.as_kwargs(), project_root=root,
        )
    assert outcome.status == "FAILED"
    assert CampaignResultRegistryRepository.complete_similarity_search_run is original_complete
    with get_connection(database) as connection:
        snapshot = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()
        assert snapshot is not None
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
        attempt = connection.execute(
            "SELECT status,failure_code FROM campaign_search_attempts WHERE search_run_id=? AND attempt_number=1",
            (search_id,),
        ).fetchone()
        assert tuple(attempt) == ("FAILED", "SIMILARITY_PREPARATION_FAILED")
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"

    retry = submission.retry_potential_customer_search(
        database, search_id, idempotency_key="fault-retry-once",
    )
    assert retry["attempt_number"] == 2
    assert submission.retry_potential_customer_search(
        database, search_id, idempotency_key="fault-retry-once",
    )["attempt_number"] == 2
    next_fence = repository.claim_search_attempt(search_id, lease_owner="recovery-worker")
    recovered = execute_similarity_search_safely(
        database, search_id, **next_fence.as_kwargs(), project_root=root,
    )
    assert recovered.status == "COMPLETED"
    assert recovered.result_source == "EXACT_RESULT_REUSE"
    assert recovered.result_snapshot_id == snapshot["similarity_result_snapshot_id"]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
        assert [row["status"] for row in connection.execute(
            "SELECT status FROM campaign_search_attempts WHERE search_run_id=? ORDER BY attempt_number",
            (search_id,),
        )] == ["FAILED", "COMPLETED"]


def test_attempt_takeover_fences_progress_lineage_failure_and_completion(
    completed,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    old = repository.claim_search_attempt(
        search_id, lease_owner="old-worker",
    )
    repository.mark_processing(search_id, **old.as_kwargs())
    with pytest.raises(Phase11RegistryStateError, match="live worker"):
        repository.claim_search_attempt(
            search_id, lease_owner="new-worker",
        )
    # Simulate a process crash: no more heartbeats from the original owner.
    with get_connection(database, write=True) as connection:
        connection.execute(
            "UPDATE campaign_search_attempts SET lease_heartbeat_at='2026-10-06T01:00:00Z' "
            "WHERE search_run_id=? AND attempt_number=1",
            (search_id,),
        )
    new = repository.claim_search_attempt(
        search_id, lease_owner="new-worker",
    )
    assert new.execution_lease_token != old.execution_lease_token
    with pytest.raises(Phase11RegistryStateError):
        repository.update_search_progress(
            search_id, **old.as_kwargs(), stage_code="SCORING_PROSPECTS",
            stage_label="Scoring", progress_percent=30,
            status_message="Old worker cannot report progress.",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.bind_similarity_lineage(
            search_id, **old.as_kwargs(), profile_set_sha256="a" * 64,
            composite_context_sha256="b" * 64, similarity_generation_id=1,
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.fail_search_run(
            search_id, **old.as_kwargs(), failure_code="OLD_WORKER",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.complete_similarity_search_run(
            search_id, **old.as_kwargs(),
            similarity_result_snapshot_id=historical["similarity_result_snapshot_id"],
            result_source="EXACT_RESULT_REUSE",
        )
    outcome = execute_similarity_search_safely(
        database, search_id, **new.as_kwargs(), project_root=root,
    )
    assert outcome.status == "COMPLETED"
    from app.routers.potential_customer_search import _project_search_run

    public_status = json.dumps(_project_search_run(search_id, database))
    assert old.execution_lease_token not in public_status
    assert new.execution_lease_token not in public_status
    assert "lease_owner" not in public_status
    assert "traceback" not in public_status.lower()
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_two_identical_workers_publish_one_snapshot_and_keep_both_runs(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, historical = completed
    first = _new_search(database)
    second = _new_search(database)
    repository = CampaignResultRegistryRepository(database)
    fences = [
        repository.claim_search_attempt(run["search_run_id"], lease_owner=f"worker-{index}")
        for index, run in enumerate((first, second), start=1)
    ]
    from app.services import buyer_similarity_result_service as result_service

    original_write = result_service._write_membership
    both_staged = Barrier(2)

    def meet_at_publication(path, rows, minimum):
        count = original_write(path, rows, minimum)
        both_staged.wait(timeout=20)
        return count

    with monkeypatch.context() as patch:
        patch.setattr(result_service, "_write_membership", meet_at_publication)
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(
                lambda pair: execute_similarity_search_safely(
                    database, pair[0]["search_run_id"], **pair[1].as_kwargs(),
                    project_root=root,
                ),
                zip((first, second), fences, strict=True),
            ))
    assert [outcome.status for outcome in outcomes] == ["COMPLETED", "COMPLETED"]
    assert outcomes[0].result_snapshot_id == outcomes[1].result_snapshot_id
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_concurrent_thresholds_share_generation_but_keep_distinct_memberships(
    completed,
) -> None:
    database, root, historical = completed
    runs = (_new_search(database, minimum=.80), _new_search(database, minimum=.90))
    repository = CampaignResultRegistryRepository(database)
    fences = [
        repository.claim_search_attempt(run["search_run_id"], lease_owner=f"threshold-{index}")
        for index, run in enumerate(runs, start=1)
    ]
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(
            lambda pair: execute_similarity_search_safely(
                database, pair[0]["search_run_id"], **pair[1].as_kwargs(),
                project_root=root,
            ),
            zip(runs, fences, strict=True),
        ))
    assert [outcome.status for outcome in outcomes] == ["COMPLETED", "COMPLETED"]
    assert outcomes[0].generation_id == outcomes[1].generation_id
    assert outcomes[0].result_snapshot_id != outcomes[1].result_snapshot_id
    with get_connection(database) as connection:
        snapshots = connection.execute(
            "SELECT similarity_minimum,resolved_count FROM buyer_similarity_result_snapshots "
            "WHERE similarity_minimum IN (.80,.90) ORDER BY similarity_minimum"
        ).fetchall()
        assert len(snapshots) == 2
        assert float(snapshots[0]["similarity_minimum"]) == .80
        assert float(snapshots[1]["similarity_minimum"]) == .90
        assert int(snapshots[0]["resolved_count"]) >= int(snapshots[1]["resolved_count"])
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_import_during_materialization_prevents_completion_and_invalidates_preflight(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="import-race")
    from app.services import buyer_similarity_result_service as result_service

    original_write = result_service._write_membership
    imported = False

    def import_after_staging(path, rows, minimum):
        nonlocal imported
        count = original_write(path, rows, minimum)
        if not imported:
            imported = True
            with get_connection(database, write=True) as connection:
                connection.execute(
                    """INSERT INTO data_import_runs (
                        dataset_name,source_path,started_at,completed_at,status,
                        rows_read,rows_inserted,rows_rejected,source_checksum
                    ) VALUES ('demographics','replacement.csv',?,?,'COMPLETED',10,10,0,?)""",
                    ("2026-10-08T00:00:00Z", "2026-10-08T00:00:01Z", "f" * 64),
                )
        return count

    with monkeypatch.context() as patch:
        patch.setattr(result_service, "_write_membership", import_after_staging)
        outcome = execute_similarity_search_safely(
            database, created["search_run_id"], **fence.as_kwargs(), project_root=root,
        )
    assert imported
    assert outcome.status == "FAILED"
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 0
    assert not resolve_similarity_context(
        database, {
            "product_ids": ["P1"], "campaign_types": [],
            "campaign_categories": [], "offer_types": [],
            "historical_campaign_channels": [], "campaign_channel": "EMAIL",
        }, project_root=root,
    ).ready
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"
    assert repository.fetch_search_run(created["search_run_id"])["selected_count"] is None


def test_import_during_preflight_count_returns_stale_not_cached_count(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, historical = completed
    options = submission.search_form_options(database)
    from app.services import buyer_similarity_preflight_service as preflight

    original_count = preflight.count_similarity_selection
    imported = False

    def count_then_replace(connection, *args, **kwargs):
        nonlocal imported
        counts = original_count(connection, *args, **kwargs)
        if not imported:
            imported = True
            with get_connection(database, write=True) as writer:
                writer.execute(
                    """INSERT INTO data_import_runs (
                        dataset_name,source_path,started_at,completed_at,status,
                        rows_read,rows_inserted,rows_rejected,source_checksum
                    ) VALUES ('demographics','preflight-replacement.csv',?,?,'COMPLETED',10,10,0,?)""",
                    ("2026-10-08T00:00:00Z", "2026-10-08T00:00:01Z", "f" * 64),
                )
        return counts

    with monkeypatch.context() as patch:
        patch.setattr(preflight, "count_similarity_selection", count_then_replace)
        response = exact_similarity_preflight(
            database, context={
                "product_ids": ["P1"], "campaign_types": [],
                "campaign_categories": [], "offer_types": [],
                "historical_campaign_channels": [], "campaign_channel": "EMAIL",
            }, criteria={}, similarity_minimum=.80, selection_mode="ALL_MATCHING",
            top_n=None, catalog_version=options["catalog_version"], project_root=root,
        )
    assert imported
    assert response["similarity_currentness"] == "STALE"
    assert response["selected_count"] is None
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM similarity_preflight_cache WHERE similarity_minimum=.80"
        ).fetchone()[0] == 0
    assert CampaignResultRegistryRepository(database).fetch_search_run(
        historical["search_run_id"]
    )["status"] == "COMPLETED"


def test_preflight_cache_insert_failure_recomputes_exactly_on_retry(
    completed,
) -> None:
    database, root, historical = completed
    options = submission.search_form_options(database)
    parameters = dict(
        context={
            "product_ids": ["P1"], "campaign_types": [],
            "campaign_categories": [], "offer_types": [],
            "historical_campaign_channels": [], "campaign_channel": "EMAIL",
        },
        criteria={}, similarity_minimum=.80, selection_mode="ALL_MATCHING",
        top_n=None, catalog_version=options["catalog_version"], project_root=root,
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            "CREATE TRIGGER inject_preflight_insert_failure BEFORE INSERT ON similarity_preflight_cache "
            "BEGIN SELECT RAISE(ABORT,'injected preflight cache failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected preflight"):
        exact_similarity_preflight(database, **parameters)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM similarity_preflight_cache WHERE similarity_minimum=.80"
        ).fetchone()[0] == 0
    with get_connection(database, write=True) as connection:
        connection.execute("DROP TRIGGER inject_preflight_insert_failure")
    fresh = exact_similarity_preflight(database, **parameters)
    cached = exact_similarity_preflight(database, **parameters)
    assert fresh["selected_count"] is not None
    assert fresh["cache_hit"] is False
    assert cached["cache_hit"] is True
    assert cached["selected_count"] == fresh["selected_count"]
    assert CampaignResultRegistryRepository(database).fetch_search_run(
        historical["search_run_id"]
    )["status"] == "COMPLETED"


def test_insufficient_historical_buyers_block_once_without_retry_loop(
    completed,
) -> None:
    database, root, historical = completed
    created = _new_search(database, historical_channels=["SMS"])
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(search_id, lease_owner="unsupported-history")
    outcome = execute_similarity_search_safely(
        database, search_id, **fence.as_kwargs(), project_root=root,
    )
    assert outcome.status == "BLOCKED"
    runtime = repository.fetch_search_runtime(search_id)
    assert runtime["failure_code"] == "PROFILE_NOT_ELIGIBLE"
    assert not runtime["retryable"]
    with pytest.raises(Phase11RegistryStateError):
        repository.retry_search_run(search_id, idempotency_key="unsupported-retry")
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_search_attempts WHERE search_run_id=?",
            (search_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_shutdown_rotates_active_v3_lease_and_restart_completes_once(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    entered = Event()

    def paused_worker(_database, run_id, *, cancellation_check, **_kwargs):
        entered.set()
        while not cancellation_check():
            time.sleep(.01)
        return SearchOrchestrationOutcome(run_id, "PROCESSING", waiting_on="CANCELLED")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.jobs.phase11_search_coordinator.execute_similarity_search_safely",
            paused_worker,
        )
        first = Phase11SearchCoordinator(
            database, materializer=lambda *_args, **_kwargs: None,
            project_root=root, max_workers=1, poll_interval_seconds=.05,
        )
        try:
            assert first.submit(database, search_id)
            assert entered.wait(timeout=10)
            with get_connection(database) as connection:
                old_token = connection.execute(
                    "SELECT execution_lease_token FROM campaign_search_attempts WHERE search_run_id=?",
                    (search_id,),
                ).fetchone()[0]
        finally:
            first.shutdown(wait=True)

    with get_connection(database) as connection:
        row = connection.execute(
            "SELECT status,lease_owner,execution_lease_token FROM campaign_search_attempts "
            "WHERE search_run_id=?", (search_id,),
        ).fetchone()
        assert row["status"] in {"QUEUED", "PROCESSING"}
        assert row["lease_owner"] is None
        assert row["execution_lease_token"] != old_token

    second = Phase11SearchCoordinator(
        database, materializer=lambda *_args, **_kwargs: None,
        project_root=root, max_workers=1, poll_interval_seconds=.05,
    )
    try:
        assert second.resume_durable_searches() >= 1
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if repository.fetch_search_run(search_id)["status"] == "COMPLETED":
                break
            time.sleep(.05)
        assert repository.fetch_search_run(search_id)["status"] == "COMPLETED"
    finally:
        second.shutdown(wait=True)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_search_attempts WHERE search_run_id=?",
            (search_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_two_unready_v3_runs_share_one_heavy_generation_after_source_change(
    completed,
) -> None:
    database, root, historical = completed
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','replacement.csv',?,?,'COMPLETED',10,10,0,?)""",
            ("2026-10-08T00:00:00Z", "2026-10-08T00:00:01Z", "f" * 64),
        )
    first = _new_search(database, minimum=.80)
    second = _new_search(database, minimum=.80)
    repository = CampaignResultRegistryRepository(database)
    fences = [
        repository.claim_search_attempt(run["search_run_id"], lease_owner=f"fresh-{index}")
        for index, run in enumerate((first, second), start=1)
    ]
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(
            lambda pair: execute_similarity_search_safely(
                database, pair[0]["search_run_id"], **pair[1].as_kwargs(),
                project_root=root,
            ),
            zip((first, second), fences, strict=True),
        ))
    assert [outcome.status for outcome in outcomes] == ["COMPLETED", "COMPLETED"]
    assert outcomes[0].generation_id == outcomes[1].generation_id
    assert outcomes[0].result_snapshot_id == outcomes[1].result_snapshot_id
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 2  # Old historical generation remains immutable.
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.80"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_v3_heavy_waiter_reports_capacity_and_rejoins_without_duplicate_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _two_product_database(tmp_path, monkeypatch)
    repository = CampaignResultRegistryRepository(database)
    first = _new_search(database, minimum=.70, product_ids=["P1"])
    second = _new_search(database, minimum=.70, product_ids=["P1"])
    first_fence = repository.claim_search_attempt(first["search_run_id"], lease_owner="first-heavy")
    second_fence = repository.claim_search_attempt(second["search_run_id"], lease_owner="waiting-heavy")
    from app.services import buyer_similarity_search_orchestration_service as orchestration
    from app.services import phase11_search_orchestration_service as phase11

    original_score = orchestration.run_similarity_generation
    original_cohort = orchestration.build_product_buyer_cohorts
    entered = Event()
    release = Event()
    cohort_calls = 0
    score_calls = 0

    def counted_cohort(*args, **kwargs):
        nonlocal cohort_calls
        cohort_calls += 1
        return original_cohort(*args, **kwargs)

    def held_score(*args, **kwargs):
        nonlocal score_calls
        score_calls += 1
        entered.set()
        assert release.wait(timeout=20)
        return original_score(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(orchestration, "build_product_buyer_cohorts", counted_cohort)
        patch.setattr(orchestration, "run_similarity_generation", held_score)
        patch.setattr(phase11, "_SEARCH_HEARTBEAT_INTERVAL_SECONDS", .05)
        with ThreadPoolExecutor(max_workers=2) as workers:
            initial = workers.submit(
                execute_similarity_search_safely,
                database, first["search_run_id"], **first_fence.as_kwargs(),
                project_root=tmp_path,
            )
            try:
                assert entered.wait(timeout=20)
                waiting = workers.submit(
                    execute_similarity_search_safely,
                    database, second["search_run_id"], **second_fence.as_kwargs(),
                    project_root=tmp_path,
                )
                deadline = time.monotonic() + 5
                runtime = None
                while time.monotonic() < deadline:
                    runtime = repository.fetch_search_runtime(second["search_run_id"])
                    if runtime and runtime["stage_code"] == "WAITING_FOR_HEAVY_SLOT":
                        break
                    time.sleep(.02)
                assert runtime is not None
                assert runtime["stage_code"] == "WAITING_FOR_HEAVY_SLOT"
                assert "waiting" in runtime["status_message"].lower()
                before = repository.fetch_current_attempt(second["search_run_id"])["lease_heartbeat_at"]
                time.sleep(1.15)
                after = repository.fetch_current_attempt(second["search_run_id"])["lease_heartbeat_at"]
                assert after > before
                assert not waiting.done()
                assert cohort_calls == 1 and score_calls == 1
            finally:
                release.set()
            first_outcome = initial.result(timeout=30)
            second_outcome = waiting.result(timeout=30)
    assert first_outcome.status == second_outcome.status == "COMPLETED"
    assert {first_outcome.result_source, second_outcome.result_source} <= {
        "NEW_INTELLIGENCE_BUILD", "INTELLIGENCE_REUSE", "EXACT_RESULT_REUSE",
    }
    assert cohort_calls == 1 and score_calls == 1
    assert first_outcome.generation_id == second_outcome.generation_id
    assert first_outcome.result_snapshot_id == second_outcome.result_snapshot_id
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.70"
        ).fetchone()[0] == 1


def test_different_product_heavy_score_does_not_hold_verified_cheap_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _two_product_database(tmp_path, monkeypatch)
    repository = CampaignResultRegistryRepository(database)
    p1 = _new_search(database, minimum=.70, product_ids=["P1"])
    p1_fence = repository.claim_search_attempt(p1["search_run_id"], lease_owner="p1-initial")
    assert execute_similarity_search_safely(
        database, p1["search_run_id"], **p1_fence.as_kwargs(), project_root=tmp_path,
    ).status == "COMPLETED"

    p3 = _new_search(database, minimum=.70, product_ids=["P3"])
    p3_fence = repository.claim_search_attempt(p3["search_run_id"], lease_owner="p3-heavy")
    entered = Event()
    release = Event()
    from app.services import buyer_similarity_search_orchestration_service as orchestration

    original_score = orchestration.run_similarity_generation

    def paused_scoring(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=20)
        return original_score(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(orchestration, "run_similarity_generation", paused_scoring)
        with ThreadPoolExecutor(max_workers=2) as workers:
            heavy = workers.submit(
                execute_similarity_search_safely,
                database, p3["search_run_id"], **p3_fence.as_kwargs(),
                project_root=tmp_path,
            )
            try:
                assert entered.wait(timeout=20)
                assert repository.fetch_search_run(p3["search_run_id"])["status"] == "PROCESSING"
                p1_reuse = _new_search(database, minimum=.70, product_ids=["P1"])
                reuse_fence = repository.claim_search_attempt(
                    p1_reuse["search_run_id"], lease_owner="p1-cheap-reuse",
                )
                started = time.perf_counter()
                cheap = workers.submit(
                    execute_similarity_search_safely,
                    database, p1_reuse["search_run_id"], **reuse_fence.as_kwargs(),
                    project_root=tmp_path,
                )
                cheap_outcome = cheap.result(timeout=5)
                cheap_seconds = time.perf_counter() - started
                assert cheap_outcome.status == "COMPLETED"
                assert cheap_outcome.result_source == "EXACT_RESULT_REUSE"
                assert cheap_seconds < 5
                assert not heavy.done()
            finally:
                release.set()
            heavy_outcome = heavy.result(timeout=30)
    assert heavy_outcome.status == "COMPLETED"
    assert heavy_outcome.generation_id != cheap_outcome.generation_id
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 2
        assert {
            row[0] for row in connection.execute(
                "SELECT product_id FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
            )
        } == {"P1", "P3"}
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots"
        ).fetchone()[0] == 2


def test_stale_v2_probability_does_not_block_same_criteria_v3_completion(
    completed,
) -> None:
    database, root, historical = completed
    repository = CampaignResultRegistryRepository(database)
    options = submission.search_form_options(database)
    context = {
        "product_ids": ["P1"], "campaign_types": [],
        "campaign_categories": [], "offer_types": [],
        "historical_campaign_channels": [], "campaign_channel": "EMAIL",
    }
    v2_request = PotentialCustomerSearchRequest(
        campaign_name="Probability alongside similarity",
        context=context, criteria={}, export_profile="EMAIL_CONTACT_V1",
        propensity_bucket="0.70", catalog_version=options["catalog_version"],
    )
    v2 = submission.submit_potential_customer_search(database, v2_request)
    v3 = _new_search(database, minimum=.70)
    v2_fence = repository.claim_search_attempt(v2["search_run_id"], lease_owner="v2-worker")
    v3_fence = repository.claim_search_attempt(v3["search_run_id"], lease_owner="v3-worker")
    entered = Event()
    release = Event()

    def stale_probability(*_args, **_kwargs):
        return {"status": "STALE", "stage": "CHECKING_COMPATIBILITY"}

    def blocked_preparation(*_args, **_kwargs):
        entered.set()
        assert release.wait(timeout=20)
        return {
            "status": "BLOCKED", "stage": "CHECKING_COMPATIBILITY",
            "business_message": "The optional probability generation is stale.",
        }

    with ThreadPoolExecutor(max_workers=2) as workers:
        probability = workers.submit(
            execute_phase11_search_safely,
            database, v2["search_run_id"], **v2_fence.as_kwargs(),
            materializer=None, project_root=root,
            phase10_reader=stale_probability, phase10_preparer=blocked_preparation,
        )
        try:
            assert entered.wait(timeout=20)
            similarity = workers.submit(
                execute_similarity_search_safely,
                database, v3["search_run_id"], **v3_fence.as_kwargs(),
                project_root=root,
            )
            v3_outcome = similarity.result(timeout=10)
            assert v3_outcome.status == "COMPLETED"
            assert not probability.done()
        finally:
            release.set()
        v2_outcome = probability.result(timeout=15)
    assert v2_outcome.status == "BLOCKED"
    assert repository.fetch_search_run(v2["search_run_id"])["selection_contract_version"] == "2"
    assert repository.fetch_search_run(v3["search_run_id"])["selection_contract_version"] == "3"
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM score_calibration_artifacts"
        ).fetchone()[0] == 0


def test_true_process_death_after_result_rename_recovers_without_partial_download(
    completed,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    old = repository.claim_search_attempt(search_id, lease_owner="crashing-process")
    repository.mark_processing(search_id, **old.as_kwargs())
    script = """
import json
import os
import sys
from pathlib import Path
from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.services.buyer_similarity_selection_service import resolve_similarity_context
from app.services import buyer_similarity_result_service as results

database, root, search_id, attempt, token = sys.argv[1:]
run = CampaignResultRegistryRepository(database).fetch_search_run(int(search_id))
with get_connection(database) as connection:
    row = connection.execute(
        'SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?',
        (run['targeting_context_id'],),
    ).fetchone()
context = json.loads(row[0])
resolution = resolve_similarity_context(database, context, project_root=Path(root))
original_replace = os.replace
def die_after_rename(source, destination):
    original_replace(source, destination)
    os._exit(37)
results.os.replace = die_after_rename
results.materialize_similarity_result(
    database, run, context, resolution, project_root=Path(root),
    attempt_number=int(attempt), execution_lease_token=token,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(root), str(search_id),
         str(old.attempt_number), old.execution_lease_token],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 37, child.stderr[:300]
    with get_connection(database) as connection:
        registered = {
            int(row[0]) for row in connection.execute(
                "SELECT similarity_result_snapshot_id FROM buyer_similarity_result_snapshots"
            )
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 0
    results_root = root / "artifacts" / "similarity_results"
    orphaned = [
        path for path in results_root.glob("snapshot_*")
        if int(path.name.removeprefix("snapshot_")) not in registered
    ]
    assert len(orphaned) == 1
    assert repository.fetch_search_run(search_id)["status"] == "PROCESSING"

    old_time = time.time() - 7200
    os.utime(orphaned[0], (old_time, old_time))
    assert reconcile_similarity_result_publications(
        database, project_root=root, minimum_age_seconds=3600,
    ) == 1
    with get_connection(database, write=True) as connection:
        connection.execute(
            "UPDATE campaign_search_attempts SET lease_heartbeat_at='2026-10-06T01:00:00Z' "
            "WHERE search_run_id=? AND attempt_number=1",
            (search_id,),
        )
    current = repository.claim_search_attempt(search_id, lease_owner="restarted-process")
    assert current.execution_lease_token != old.execution_lease_token
    with pytest.raises(Phase11RegistryStateError):
        repository.fail_search_run(search_id, **old.as_kwargs(), failure_code="STALE_WORKER")
    outcome = execute_similarity_search_safely(
        database, search_id, **current.as_kwargs(), project_root=root,
    )
    assert outcome.status == "COMPLETED"
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
        snapshot = dict(connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone())
        saved_run = repository.fetch_search_run(search_id)
        saved_context = json.loads(connection.execute(
            "SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?",
            (saved_run["targeting_context_id"],),
        ).fetchone()[0])
    resolution = resolve_similarity_context(database, saved_context, project_root=root)
    assert validate_similarity_result_snapshot(
        snapshot, saved_run, resolution, project_root=root,
    )
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_true_process_death_after_score_checkpoint_restarts_under_new_fence(
    tmp_path: Path,
) -> None:
    database, profile_id = _case(tmp_path)
    script = """
import os
import sys
from app.services.buyer_similarity_scoring_service import run_similarity_generation
database, root, profile_id = sys.argv[1:]
def crash_after_committed_chunk(stage, processed, total, message):
    if stage == 'SCORING_PROSPECTS' and processed >= 4:
        os._exit(38)
run_similarity_generation(
    database, int(profile_id), project_root=root,
    execution_owner='crashing-scorer', execution_token='a' * 64,
    chunk_size=4, clock=lambda: '2026-10-06T03:00:00Z',
    progress_callback=crash_after_committed_chunk,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(tmp_path), str(profile_id)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 38, child.stderr[:300]
    with get_connection(database) as connection:
        staged = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0]
        generation = connection.execute(
            "SELECT similarity_generation_id,publication_state FROM buyer_similarity_score_generations"
        ).fetchone()
        assert staged == 4
        assert generation["publication_state"] == "BUILDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 0

    recovered = run_similarity_generation(
        database, profile_id, project_root=tmp_path,
        execution_owner="replacement-scorer", execution_token="b" * 64,
        stale_before="2026-10-06T03:30:00Z", chunk_size=4,
        clock=lambda: "2026-10-06T04:00:00Z",
    )
    assert recovered["restarted_from_stale_lease"] is True
    assert recovered["similarity_generation_id"] == generation["similarity_generation_id"]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_generation_attestations WHERE verification_status='VERIFIED'"
        ).fetchone()[0] == 1


def test_true_process_death_after_profile_rename_reclaims_unpublished_artifact(
    tmp_path: Path,
) -> None:
    database = _registry_database(tmp_path)
    script = """
import os
import sys
from tests.test_buyer_similarity_profile_service import _single_profile
from app.repositories.buyer_similarity_profile_repository import publish_buyer_similarity_profile
from app.services import buyer_similarity_profile_service as profiles
database, root = sys.argv[1:]
original = os.replace
def rename_and_die(source, destination):
    original(source, destination)
    os._exit(39)
profiles.os.replace = rename_and_die
publish_buyer_similarity_profile(
    database, _single_profile(), project_root=root,
    execution_owner='dead-profile-worker', execution_token='a' * 64,
    now='2026-10-06T01:00:00Z',
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 39, child.stderr[:300]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT publication_state FROM buyer_similarity_profiles"
        ).fetchone()[0] == "BUILDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts"
        ).fetchone()[0] == 0
    recovered = publish_buyer_similarity_profile(
        database, _single_profile(), project_root=tmp_path,
        execution_owner="new-profile-worker", execution_token="b" * 64,
        now="2026-10-06T02:00:00Z",
        stale_before="2026-10-06T01:30:00Z",
    )
    assert not recovered.reused
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profiles WHERE publication_state='PUBLISHED'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_profile_artifacts WHERE artifact_state='PUBLISHED'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize("boundary,exit_code", [
    ("attestation", 40), ("score_publication", 41),
])
def test_true_process_death_inside_verification_transaction_rolls_back(
    tmp_path: Path, boundary: str, exit_code: int,
) -> None:
    database, profile_id = _case(tmp_path)
    script = """
import os
import sys
from contextlib import contextmanager
from app.repositories import buyer_similarity_scoring_repository as scoring_repo
from app.services.buyer_similarity_scoring_service import run_similarity_generation
database, root, profile_id, boundary, exit_code = sys.argv[1:]
original_connection = scoring_repo.get_connection
class Proxy:
    def __init__(self, connection):
        self.connection = connection
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        normalized = ' '.join(sql.split()).upper()
        if (boundary == 'attestation' and normalized.startswith(
            'INSERT OR REPLACE INTO BUYER_SIMILARITY_GENERATION_ATTESTATIONS'
        )) or (boundary == 'score_publication' and normalized.startswith(
            'INSERT INTO BUYER_SIMILARITY_SCORES'
        )):
            os._exit(int(exit_code))
        return cursor
@contextmanager
def wrapped_connection(*args, **kwargs):
    with original_connection(*args, **kwargs) as connection:
        yield Proxy(connection)
scoring_repo.get_connection = wrapped_connection
run_similarity_generation(
    database, int(profile_id), project_root=root,
    execution_owner='dead-verifier', execution_token='a' * 64,
    chunk_size=4, clock=lambda: '2026-10-06T03:00:00Z',
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(tmp_path),
         str(profile_id), boundary, str(exit_code)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == exit_code, child.stderr[:300]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT publication_state FROM buyer_similarity_score_generations"
        ).fetchone()[0] == "BUILDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_generation_attestations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 0
    recovered = run_similarity_generation(
        database, profile_id, project_root=tmp_path,
        execution_owner="replacement-verifier", execution_token="b" * 64,
        stale_before="2026-10-06T03:30:00Z", chunk_size=4,
        clock=lambda: "2026-10-06T04:00:00Z",
    )
    assert recovered["status"] == "PUBLISHED"
    assert recovered["restarted_from_stale_lease"]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_generation_attestations WHERE verification_status='VERIFIED'"
        ).fetchone()[0] == 1


def test_true_process_death_inside_result_completion_rolls_back_and_rejoins(
    completed,
) -> None:
    database, root, historical = completed
    created = _new_search(database)
    search_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database)
    old = repository.claim_search_attempt(search_id, lease_owner="dead-completer")
    script = """
import os
import sys
from contextlib import contextmanager
from app.repositories import campaign_result_registry_repository as registry
from app.services.buyer_similarity_search_orchestration_service import execute_similarity_search_safely
database, root, search_id, attempt, token = sys.argv[1:]
original_connection = registry.get_connection
class Proxy:
    def __init__(self, connection):
        self.connection = connection
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        if ' '.join(sql.split()).upper().startswith(
            "UPDATE CAMPAIGN_SEARCH_RUNS SET STATUS='COMPLETED'"
        ):
            os._exit(42)
        return cursor
@contextmanager
def wrapped_connection(*args, **kwargs):
    with original_connection(*args, **kwargs) as connection:
        yield Proxy(connection)
registry.get_connection = wrapped_connection
execute_similarity_search_safely(
    database, int(search_id), attempt_number=int(attempt),
    execution_lease_token=token, project_root=root,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(root), str(search_id),
         str(old.attempt_number), old.execution_lease_token],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 42, child.stderr[:300]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT status FROM campaign_search_runs WHERE search_run_id=?",
            (search_id,),
        ).fetchone()[0] == "PROCESSING"
        assert connection.execute(
            "SELECT status FROM campaign_search_attempts WHERE search_run_id=?",
            (search_id,),
        ).fetchone()[0] == "PROCESSING"
    with get_connection(database, write=True) as connection:
        connection.execute(
            "UPDATE campaign_search_attempts SET lease_heartbeat_at='2026-10-06T01:00:00Z' "
            "WHERE search_run_id=?", (search_id,),
        )
    fresh = repository.claim_search_attempt(search_id, lease_owner="new-completer")
    with pytest.raises(Phase11RegistryStateError):
        repository.update_search_progress(
            search_id, **old.as_kwargs(), stage_code="VERIFYING_SIMILARITY",
            stage_label="Verifying", progress_percent=96,
            status_message="A dead worker cannot update progress.",
        )
    outcome = execute_similarity_search_safely(
        database, search_id, **fresh.as_kwargs(), project_root=root,
    )
    assert outcome.status == "COMPLETED"
    assert outcome.result_source == "EXACT_RESULT_REUSE"
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 1
    assert repository.fetch_search_run(historical["search_run_id"])["status"] == "COMPLETED"


def test_true_process_death_during_preflight_cache_insert_recomputes(
    completed,
) -> None:
    database, root, historical = completed
    options = submission.search_form_options(database)
    script = """
import os
import sys
from contextlib import contextmanager
from app.services import buyer_similarity_preflight_service as preflight
database, root, catalog = sys.argv[1:]
original_connection = preflight.get_connection
class Proxy:
    def __init__(self, connection):
        self.connection = connection
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        if ' '.join(sql.split()).upper().startswith(
            'INSERT OR IGNORE INTO SIMILARITY_PREFLIGHT_CACHE'
        ):
            os._exit(43)
        return cursor
@contextmanager
def wrapped_connection(*args, **kwargs):
    with original_connection(*args, **kwargs) as connection:
        yield Proxy(connection)
preflight.get_connection = wrapped_connection
preflight.exact_similarity_preflight(
    database, context={
        'product_ids':['P1'], 'campaign_types':[], 'campaign_categories':[],
        'offer_types':[], 'historical_campaign_channels':[], 'campaign_channel':'EMAIL',
    }, criteria={}, similarity_minimum=.80, selection_mode='ALL_MATCHING',
    top_n=None, catalog_version=catalog, project_root=root,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(root), options["catalog_version"]],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 43, child.stderr[:300]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM similarity_preflight_cache WHERE similarity_minimum=.80"
        ).fetchone()[0] == 0
    parameters = dict(
        context={
            "product_ids": ["P1"], "campaign_types": [],
            "campaign_categories": [], "offer_types": [],
            "historical_campaign_channels": [], "campaign_channel": "EMAIL",
        }, criteria={}, similarity_minimum=.80, selection_mode="ALL_MATCHING",
        top_n=None, catalog_version=options["catalog_version"], project_root=root,
    )
    first = exact_similarity_preflight(database, **parameters)
    second = exact_similarity_preflight(database, **parameters)
    assert first["selected_count"] is not None and not first["cache_hit"]
    assert second["selected_count"] == first["selected_count"] and second["cache_hit"]
    assert CampaignResultRegistryRepository(database).fetch_search_run(
        historical["search_run_id"]
    )["status"] == "COMPLETED"


def test_true_process_death_during_export_is_reconciled_and_retryable(
    completed,
) -> None:
    database, root, run = completed
    script = """
import asyncio
import os
import sys
from app.services.phase11_export_service import stream_phase11_result_export_csv
database, root, search_id = sys.argv[1:]
class Request:
    async def is_disconnected(self):
        return False
async def begin():
    response = stream_phase11_result_export_csv(
        database, search_run_id=int(search_id), request=Request(), project_root=root,
    )
    await response.body_iterator.__anext__()
    os._exit(44)
asyncio.run(begin())
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(root), str(run["search_run_id"])],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 44, child.stderr[:300]
    with get_connection(database) as connection:
        event = connection.execute(
            "SELECT status,csv_sha256 FROM buyer_similarity_export_events"
        ).fetchone()
        assert tuple(event) == ("RUNNING", None)
    assert reconcile_similarity_export_events(
        database, cutoff="2100-01-01T00:00:00Z",
    ) == 1
    retry = stream_phase11_result_export_csv(
        database, search_run_id=run["search_run_id"],
        request=_AlwaysConnected(), project_root=root,
    )
    rows = list(csv.DictReader(io.StringIO(asyncio.run(_download_body(retry)).decode())))
    assert len(rows) == int(retry.headers["X-Exportable-Count"])
    with get_connection(database) as connection:
        assert [row["status"] for row in connection.execute(
            "SELECT status FROM buyer_similarity_export_events ORDER BY export_event_id"
        )] == ["ABORTED", "COMPLETED"]


def test_true_process_death_inside_feedback_transaction_rolls_back_and_retries(
    completed,
) -> None:
    database, root, run = completed
    with get_connection(database) as connection:
        uri = connection.execute(
            "SELECT storage_uri FROM buyer_similarity_result_snapshots "
            "WHERE similarity_result_snapshot_id=?",
            (run["similarity_result_snapshot_id"],),
        ).fetchone()[0]
    with gzip.open(root / uri, "rt", encoding="utf-8", newline="") as source:
        person = next(csv.DictReader(source))["person_id"]
    script = """
import os
import sys
from contextlib import contextmanager
from app.services import phase11_feedback_service as feedback
database, root, search_id, person = sys.argv[1:]
original_connection = feedback.get_connection
class Proxy:
    def __init__(self, connection):
        self.connection = connection
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        if ' '.join(sql.split()).upper().startswith(
            'INSERT INTO CAMPAIGN_FEEDBACK_BATCHES'
        ):
            os._exit(45)
        return cursor
@contextmanager
def wrapped_connection(*args, **kwargs):
    with original_connection(*args, **kwargs) as connection:
        yield Proxy(connection)
feedback.get_connection = wrapped_connection
feedback.ingest_feedback(
    database, int(search_id), rows=[{
        'person_id':person, 'outcome':1, 'outcome_at':'2026-01-01T00:00:00Z',
    }], source_name='crash-test', idempotency_key='crash-feedback-once',
    project_root=root,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(database), str(root),
         str(run["search_run_id"]), person],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=CHILD_CRASH_WATCHDOG_SECONDS, check=False,
    )
    assert child.returncode == 45, child.stderr[:300]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_batches"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_outcomes"
        ).fetchone()[0] == 0
    rows = [{
        "person_id": person, "outcome": 1,
        "outcome_at": "2026-01-01T00:00:00Z",
    }]
    accepted = ingest_feedback(
        database, run["search_run_id"], rows=rows,
        source_name="crash-test", idempotency_key="crash-feedback-once",
        project_root=root,
    )
    assert accepted["status"] == "ACCEPTED"
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_batches"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_outcomes"
        ).fetchone()[0] == 1


class _AlwaysConnected:
    async def is_disconnected(self) -> bool:
        return False


async def _download_body(response) -> bytes:
    return b"".join([chunk async for chunk in response.body_iterator])


def test_v3_export_write_error_is_failed_audit_then_clean_retry(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, run = completed
    from app.services import phase11_export_service as exports

    original_encode = exports._csv_bytes
    calls = 0

    def fail_after_header(values, writer, buffer):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected export write failure")
        return original_encode(values, writer, buffer)

    with monkeypatch.context() as patch:
        patch.setattr(exports, "_csv_bytes", fail_after_header)
        response = stream_phase11_result_export_csv(
            database, search_run_id=run["search_run_id"],
            request=_AlwaysConnected(), project_root=root,
        )
        with pytest.raises(OSError, match="injected export write"):
            asyncio.run(_download_body(response))
    with get_connection(database) as connection:
        event = connection.execute(
            "SELECT status,csv_sha256 FROM buyer_similarity_export_events ORDER BY export_event_id DESC LIMIT 1"
        ).fetchone()
        assert tuple(event) == ("FAILED", None)
    retry = stream_phase11_result_export_csv(
        database, search_run_id=run["search_run_id"],
        request=_AlwaysConnected(), project_root=root,
    )
    rows = list(csv.DictReader(io.StringIO(asyncio.run(_download_body(retry)).decode())))
    assert len(rows) == int(retry.headers["X-Exportable-Count"])
    with get_connection(database) as connection:
        assert [row["status"] for row in connection.execute(
            "SELECT status FROM buyer_similarity_export_events ORDER BY export_event_id"
        )] == ["FAILED", "COMPLETED"]
    assert repository_history_unchanged(database, run["search_run_id"])


def repository_history_unchanged(database: Path, search_run_id: int) -> bool:
    run = CampaignResultRegistryRepository(database).fetch_search_run(search_run_id)
    return run is not None and run["status"] == "COMPLETED" and run["similarity_result_snapshot_id"] is not None


def test_v3_feedback_insert_error_rolls_back_batch_and_idempotent_retry(
    completed,
) -> None:
    database, root, run = completed
    with get_connection(database) as connection:
        uri = connection.execute(
            "SELECT storage_uri FROM buyer_similarity_result_snapshots "
            "WHERE similarity_result_snapshot_id=?",
            (run["similarity_result_snapshot_id"],),
        ).fetchone()[0]
    with gzip.open(root / uri, "rt", encoding="utf-8", newline="") as source:
        person = next(csv.DictReader(source))["person_id"]
    rows = [{
        "person_id": person, "outcome": 1,
        "outcome_at": "2026-01-01T00:00:00Z",
    }]
    with get_connection(database, write=True) as connection:
        connection.execute(
            "CREATE TRIGGER inject_feedback_insert_failure BEFORE INSERT ON campaign_feedback_outcomes "
            "BEGIN SELECT RAISE(ABORT,'injected feedback insertion failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected feedback insertion"):
        ingest_feedback(
            database, run["search_run_id"], rows=rows,
            source_name="fault-test", idempotency_key="fault-feedback-once",
            project_root=root,
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_batches"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_outcomes"
        ).fetchone()[0] == 0
    with get_connection(database, write=True) as connection:
        connection.execute("DROP TRIGGER inject_feedback_insert_failure")
    accepted = ingest_feedback(
        database, run["search_run_id"], rows=rows,
        source_name="fault-test", idempotency_key="fault-feedback-once",
        project_root=root,
    )
    assert accepted["status"] == "ACCEPTED"
    assert ingest_feedback(
        database, run["search_run_id"], rows=rows,
        source_name="fault-test", idempotency_key="fault-feedback-once",
        project_root=root,
    )["feedback_batch_id"] == accepted["feedback_batch_id"]
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_batches"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_feedback_outcomes"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM feedback_retraining_decisions"
        ).fetchone()[0] == 0
