"""Adversarial durable-attempt execution fencing and migration coverage."""

# ruff: noqa: F401, F811 - imported pytest fixture is intentionally injected.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS, initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from tests.test_phase10_schema_registry_repository import (
    NOW,
    _create_version_fourteen_database,
)
from tests.test_phase11_search_result_registry import _fence, _search, _snapshot, case


@pytest.mark.parametrize(
    "method_name",
    (
        "mark_processing",
        "update_search_progress",
        "bind_current_attempt_lineage",
        "complete_search_run",
        "fail_search_run",
    ),
)
def test_every_worker_mutation_requires_an_explicit_execution_fence(
    method_name: str,
) -> None:
    signature = inspect.signature(
        getattr(CampaignResultRegistryRepository, method_name)
    )
    for parameter_name in ("attempt_number", "execution_lease_token"):
        parameter = signature.parameters[parameter_name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def _retry_stale_processing(case):
    path, _ids, _values, repository = case
    search_run_id = _search(case, campaign_name="Stale worker fencing")
    snapshot_id = _snapshot(case, search_run_id)
    attempt_one = _fence(case, search_run_id, owner="attempt-one-worker")
    repository.mark_processing(search_run_id, **attempt_one, timestamp=NOW)
    with get_connection(path, write=True) as connection:
        connection.execute(
            """UPDATE campaign_search_run_runtime
               SET heartbeat_at='2026-09-13T10:00:00Z',
                   updated_at='2026-09-13T10:00:00Z'
               WHERE search_run_id=?""",
            (search_run_id,),
        )
    repository.retry_search_run(
        search_run_id,
        idempotency_key="stale-attempt-retry",
        timestamp="2026-09-13T10:03:00Z",
    )
    attempt_two = repository.claim_search_attempt(
        search_run_id, lease_owner="attempt-two-worker"
    ).as_kwargs()
    return search_run_id, snapshot_id, attempt_one, attempt_two


def test_stale_attempt_cannot_progress_fail_complete_or_bind_new_attempt(case) -> None:
    path, ids, _values, repository = case
    search_run_id, snapshot_id, attempt_one, attempt_two = _retry_stale_processing(case)

    with pytest.raises(Phase11RegistryStateError):
        repository.update_search_progress(
            search_run_id,
            **attempt_one,
            stage_code="STALE_PROGRESS",
            stage_label="Stale progress",
            progress_percent=40,
            status_message="A stale worker must not record this event.",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.fail_search_run(search_run_id, **attempt_one)
    with pytest.raises(Phase11RegistryStateError):
        repository.complete_search_run(
            search_run_id,
            **attempt_one,
            result_snapshot_id=snapshot_id,
            result_source="INTELLIGENCE_REUSE",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.bind_current_attempt_lineage(
            search_run_id,
            **attempt_one,
            generation_id=ids["generation_id"],
            scoring_run_id=ids["scoring_run_id"],
            calibration_artifact_id=None,
        )

    run = repository.fetch_search_run(search_run_id)
    runtime = repository.fetch_search_runtime(search_run_id)
    assert run["current_attempt_number"] == 2
    assert run["status"] == runtime["lifecycle_status"] == "QUEUED"
    with get_connection(path) as connection:
        stale_events = connection.execute(
            """SELECT COUNT(*) FROM campaign_search_progress_events
               WHERE search_run_id=? AND attempt_number=2
                 AND stage_code='STALE_PROGRESS'""",
            (search_run_id,),
        ).fetchone()[0]
    assert stale_events == 0

    repository.mark_processing(search_run_id, **attempt_two)
    repository.update_search_progress(
        search_run_id,
        **attempt_two,
        stage_code="ATTEMPT_TWO_HEALTHY",
        stage_label="Attempt two is healthy",
        progress_percent=10,
        status_message="The current attempt still owns its state.",
    )
    assert repository.fetch_search_run(search_run_id)["status"] == "PROCESSING"
    assert repository.fetch_search_runtime(search_run_id)["stage_code"] == "ATTEMPT_TWO_HEALTHY"


def test_different_retry_keys_cannot_create_multiple_active_attempts(case) -> None:
    path, _ids, _values, repository = case
    search_run_id = _search(case)
    repository.fail_search_run(
        search_run_id,
        **_fence(case, search_run_id),
        blocked=True,
        timestamp="2026-09-13T10:00:10Z",
    )

    def retry(index: int) -> str:
        try:
            row = repository.retry_search_run(
                search_run_id,
                idempotency_key=f"different-retry-key-{index}",
                timestamp="2026-09-13T10:00:20Z",
            )
            return f"created-{row['current_attempt_number']}"
        except Phase11RegistryStateError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(retry, range(8)))

    assert outcomes.count("created-2") == 1
    assert outcomes.count("rejected") == 7
    with get_connection(path) as connection:
        attempts = connection.execute(
            """SELECT attempt_number,status FROM campaign_search_attempts
               WHERE search_run_id=? ORDER BY attempt_number""",
            (search_run_id,),
        ).fetchall()
    assert [tuple(row) for row in attempts] == [(1, "BLOCKED"), (2, "QUEUED")]


def test_restart_recovery_requires_stale_lease_and_rotates_fence(case) -> None:
    path, _ids, _values, repository = case
    search_run_id = _search(case)
    before = repository.claim_search_attempt(
        search_run_id, lease_owner="process-before-restart"
    )
    repository.mark_processing(search_run_id, **before.as_kwargs())

    restarted_repository = CampaignResultRegistryRepository(path)
    with pytest.raises(Phase11RegistryStateError, match="live worker"):
        restarted_repository.claim_search_attempt(
            search_run_id, lease_owner="process-after-restart"
        )
    with get_connection(path, write=True) as connection:
        connection.execute(
            """UPDATE campaign_search_attempts
               SET lease_heartbeat_at='2026-01-01T00:00:00Z'
               WHERE search_run_id=? AND attempt_number=1""",
            (search_run_id,),
        )
    after = restarted_repository.claim_search_attempt(
        search_run_id, lease_owner="process-after-restart"
    )

    assert before.attempt_number == after.attempt_number == 1
    assert before.execution_lease_token != after.execution_lease_token
    with get_connection(path) as connection:
        attempts = connection.execute(
            "SELECT COUNT(*) FROM campaign_search_attempts WHERE search_run_id=?",
            (search_run_id,),
        ).fetchone()[0]
    assert attempts == 1


def test_same_attempt_takeover_fences_every_old_owner_write(case) -> None:
    path, ids, _values, repository = case
    search_run_id = _search(case, campaign_name="Same-attempt takeover")
    snapshot_id = _snapshot(case, search_run_id)
    owner_a = repository.claim_search_attempt(
        search_run_id,
        lease_owner="owner-a",
        timestamp="2026-09-13T10:00:00Z",
    )
    repository.mark_processing(search_run_id, **owner_a.as_kwargs())
    owner_a_reclaim = repository.claim_search_attempt(
        search_run_id,
        lease_owner="owner-a",
        timestamp="2026-09-13T10:00:30Z",
    )
    assert owner_a_reclaim.execution_lease_token == owner_a.execution_lease_token
    with pytest.raises(Phase11RegistryStateError, match="live worker"):
        repository.claim_search_attempt(
            search_run_id,
            lease_owner="owner-b",
            timestamp="2026-09-13T10:01:00Z",
        )

    owner_b = repository.claim_search_attempt(
        search_run_id,
        lease_owner="owner-b",
        timestamp="2026-09-13T10:03:00Z",
    )
    assert owner_b.execution_lease_token != owner_a.execution_lease_token
    old_fence = owner_a.as_kwargs()
    with pytest.raises(Phase11RegistryStateError):
        repository.update_search_progress(
            search_run_id,
            **old_fence,
            stage_code="STALE_OWNER",
            stage_label="Stale owner",
            progress_percent=50,
            status_message="This write must be fenced.",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.fail_search_run(search_run_id, **old_fence)
    with pytest.raises(Phase11RegistryStateError):
        repository.complete_search_run(
            search_run_id,
            **old_fence,
            result_snapshot_id=snapshot_id,
            result_source="INTELLIGENCE_REUSE",
        )
    with pytest.raises(Phase11RegistryStateError):
        repository.bind_current_attempt_lineage(
            search_run_id,
            **old_fence,
            generation_id=ids["generation_id"],
            scoring_run_id=ids["scoring_run_id"],
            calibration_artifact_id=None,
        )

    repository.update_search_progress(
        search_run_id,
        **owner_b.as_kwargs(),
        stage_code="TAKEOVER_HEALTHY",
        stage_label="Takeover is healthy",
        progress_percent=55,
        status_message="The new owner has the only valid fence.",
    )
    assert repository.fetch_search_runtime(search_run_id)["stage_code"] == (
        "TAKEOVER_HEALTHY"
    )


def test_terminal_attempt_history_is_immutable_after_retry(case) -> None:
    path, _ids, _values, repository = case
    search_run_id, _snapshot_id, _attempt_one, _attempt_two = _retry_stale_processing(case)
    with get_connection(path) as connection:
        before = tuple(connection.execute(
            """SELECT status,completed_at,failure_code,failure_stage_code,
                      failure_summary,retryable,execution_lease_token
               FROM campaign_search_attempts
               WHERE search_run_id=? AND attempt_number=1""",
            (search_run_id,),
        ).fetchone())
    with pytest.raises(sqlite3.IntegrityError, match="terminal search attempt is immutable"):
        with get_connection(path, write=True) as connection:
            connection.execute(
                """UPDATE campaign_search_attempts SET failure_summary='rewritten'
                   WHERE search_run_id=? AND attempt_number=1""",
                (search_run_id,),
            )
    with get_connection(path) as connection:
        after = tuple(connection.execute(
            """SELECT status,completed_at,failure_code,failure_stage_code,
                      failure_summary,retryable,execution_lease_token
               FROM campaign_search_attempts
               WHERE search_run_id=? AND attempt_number=1""",
            (search_run_id,),
        ).fetchone())
    assert after == before


def test_graceful_claim_release_rotates_fence_before_handoff(case) -> None:
    _path, _ids, _values, repository = case
    search_run_id = _search(case, campaign_name="Graceful owner handoff")
    owner_a = repository.claim_search_attempt(
        search_run_id, lease_owner="owner-a"
    )

    repository.release_search_attempt_claim(
        search_run_id, **owner_a.as_kwargs()
    )
    with pytest.raises(Phase11RegistryStateError):
        repository.mark_processing(search_run_id, **owner_a.as_kwargs())

    owner_b = repository.claim_search_attempt(
        search_run_id, lease_owner="owner-b"
    )
    assert owner_b.attempt_number == owner_a.attempt_number
    assert owner_b.execution_lease_token != owner_a.execution_lease_token
    repository.mark_processing(search_run_id, **owner_b.as_kwargs())
    assert repository.fetch_search_run(search_run_id)["status"] == "PROCESSING"


@pytest.mark.parametrize("baseline", (17, 18, 19, 20, 21))
def test_schema_22_upgrades_and_backfills_attempt_fences_from_supported_baselines(
    tmp_path, baseline: int
) -> None:
    path = tmp_path / f"upgrade-v{baseline}.db"
    _create_version_fourteen_database(path)
    with get_connection(path, write=True) as connection:
        for version in range(15, 18):
            MIGRATIONS[version](connection)
        connection.execute(
            """INSERT INTO campaign_search_runs (
                   search_run_contract_version,campaign_name,targeting_context_id,
                   modeling_context_sha256,targeting_criteria_json,
                   targeting_criteria_sha256,filter_branches_json,
                   filter_branches_sha256,selection_mode,delivery_channel,
                   export_profile,status,created_at,started_at,completed_at,
                   processing_seconds,safe_error_message
               ) VALUES ('1','Preserved terminal search',1,?,'{}',?,'[{}]',?,
                   'ALL_MATCHING','EMAIL','EMAIL_CONTACT_V1','BLOCKED',?,?,?,0,?)""",
            (
                "a" * 64,
                "b" * 64,
                "c" * 64,
                NOW,
                NOW,
                NOW,
                "Preserved safe message",
            ),
        )
        for version in range(18, baseline + 1):
            MIGRATIONS[version](connection)
        connection.execute(
            "UPDATE app_metadata SET value=? WHERE key='schema_version'",
            (str(baseline),),
        )

    initialize_database(path)
    initialize_database(path)
    with get_connection(path, write=True) as connection:
        MIGRATIONS[22](connection)
        MIGRATIONS[22](connection)
    with get_connection(path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0]
        attempt = connection.execute(
            """SELECT attempt_number,status,execution_lease_token,lease_owner,
                      lease_claimed_at,lease_heartbeat_at
               FROM campaign_search_attempts"""
        ).fetchone()
        indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(campaign_search_attempts)")
        }
    assert version == str(CURRENT_SCHEMA_VERSION)
    assert tuple(attempt)[:2] == (1, "BLOCKED")
    assert len(attempt["execution_lease_token"]) == 64
    assert set(attempt["execution_lease_token"]) <= set("0123456789abcdef")
    assert attempt["lease_owner"] is None
    assert attempt["lease_claimed_at"] is None
    assert attempt["lease_heartbeat_at"] is None
    assert "idx_search_attempt_execution_lease" in indexes


def test_execution_lease_is_absent_from_public_api_openapi_and_safe_repr(case) -> None:
    path, _ids, _values, repository = case
    search_run_id = _search(case)
    fence = repository.claim_search_attempt(
        search_run_id, lease_owner="public-boundary-test"
    )
    token = fence.execution_lease_token

    app.dependency_overrides[get_database_path] = lambda: path
    try:
        client = TestClient(app)
        payload = client.get(
            f"/api/potential-customer-search/runs/{search_run_id}"
        ).json()
        serialized = json.dumps(payload, sort_keys=True)
        openapi = json.dumps(app.openapi(), sort_keys=True)
    finally:
        app.dependency_overrides.clear()

    assert token not in serialized
    assert "execution_lease_token" not in serialized
    assert "execution_lease_token" not in openapi
    assert token not in repr(fence)
