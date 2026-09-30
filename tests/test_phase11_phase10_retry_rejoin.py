from __future__ import annotations

from pathlib import Path

import pytest

from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.phase10_orchestration_service import (
    build_phase10_requested_intelligence,
    prepare_phase10_orchestration,
    reconcile_phase10_orchestrations,
    run_phase10_orchestration,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.services.phase11_search_orchestration_service import execute_phase11_search
from app.services.potential_customer_search_submission_service import (
    configure_phase11_search_executor,
    reset_phase11_search_executor,
    retry_potential_customer_search,
)
from tests.test_phase10_orchestration_service import (
    _create_context,
    _seed_orchestration_database,
)
from tests.test_phase11_smart_reuse_engine import (
    DeterministicMaterializer,
    fixed_membership_source,
)


def _search(database_path: Path, targeting_context_id: int) -> int:
    identity = build_phase10_requested_intelligence(
        database_path, targeting_context_id
    ).modeling_context
    return CampaignResultRegistryRepository(database_path).create_search_run(
        campaign_name="Dependency retry",
        targeting_context_id=targeting_context_id,
        modeling_context_sha256=identity.modeling_context_sha256,
        targeting_criteria={
            "selection_mode": "ALL_MATCHING",
            "target_count": None,
        },
        filter_branches=[{}],
        delivery_channel="EMAIL",
    )


def _terminal_phase10(
    database_path: Path,
    targeting_context_id: int,
    *,
    status: str = "FAILED",
    retryable: bool = True,
) -> int:
    start = prepare_phase10_orchestration(
        database_path,
        targeting_context_id,
        submitter=lambda *_args: None,
    )
    orchestration_id = int(start.orchestration["orchestration_id"])
    Phase10IntelligenceRepository(database_path).mark_orchestration_terminal(
        orchestration_id,
        status=status,
        business_message=(
            "Verified campaign history is insufficient."
            if status == "BLOCKED"
            else "Targeting intelligence could not be prepared safely."
        ),
        safe_error_message=(
            None if status == "BLOCKED" else "Targeting intelligence could not be prepared safely."
        ),
        retryable=retryable,
        failure_code=(
            "PHASE10_BUSINESS_BLOCKED"
            if status == "BLOCKED"
            else (
                "PHASE10_TRANSIENT_FAILED"
                if retryable
                else "PHASE10_PERMANENT_VALIDATION_FAILED"
            )
        ),
        failure_category=(
            "BUSINESS_DATA_INSUFFICIENCY"
            if status == "BLOCKED"
            else ("TRANSIENT_DEPENDENCY" if retryable else "PERMANENT_VALIDATION")
        ),
        completed_at="2026-09-28T08:00:00Z",
    )
    return orchestration_id


def _observe_terminal_dependency(database_path: Path, search_run_id: int) -> None:
    repository = CampaignResultRegistryRepository(database_path)
    fence = repository.claim_search_attempt(
        search_run_id, lease_owner="phase11-test"
    )
    execute_phase11_search(
        database_path,
        search_run_id,
        **fence.as_kwargs(),
        materializer=None,
    )


@pytest.fixture(autouse=True)
def _runtime_boundary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.phase10_api_service.PHASE10_API_SUBMITTER",
        lambda *_args: None,
    )
    configure_phase11_search_executor(lambda *_args: None)
    yield
    reset_phase11_search_executor()


def test_phase11_retry_replaces_transient_phase10_failure_and_rejoins_exact_work(
    tmp_path: Path,
) -> None:
    database_path, _ = _seed_orchestration_database(tmp_path)
    context_id = _create_context(database_path)
    failed_id = _terminal_phase10(database_path, context_id)
    first_search = _search(database_path, context_id)
    second_search = _search(database_path, context_id)
    _observe_terminal_dependency(database_path, first_search)
    _observe_terminal_dependency(database_path, second_search)

    first = retry_potential_customer_search(
        database_path, first_search, idempotency_key="first-retry"
    )
    second = retry_potential_customer_search(
        database_path, second_search, idempotency_key="second-retry"
    )

    repository = CampaignResultRegistryRepository(database_path)
    first_attempt = repository.fetch_current_attempt(first_search)
    second_attempt = repository.fetch_current_attempt(second_search)
    assert first["status"] == second["status"] == "QUEUED"
    assert first_attempt["attempt_number"] == second_attempt["attempt_number"] == 2
    assert first_attempt["phase10_orchestration_id"] != failed_id
    assert first_attempt["phase10_orchestration_id"] == second_attempt["phase10_orchestration_id"]
    assert first_attempt["phase10_dependency_rejoined"] == 0
    assert second_attempt["phase10_dependency_rejoined"] == 1
    active = Phase10IntelligenceRepository(database_path).list_active_orchestrations()
    assert [row["orchestration_id"] for row in active] == [
        first_attempt["phase10_orchestration_id"]
    ]

    # Restart reconciliation observes exactly the same durable parent, never a
    # second heavy orchestration for the shared modeling context.
    submitted: list[int] = []
    reconcile_phase10_orchestrations(
        database_path,
        submitter=lambda _db, orchestration_id, _root: submitted.append(orchestration_id),
    )
    assert submitted == [first_attempt["phase10_orchestration_id"]]


def test_transient_dependency_retry_reaches_phase11_completion_without_database_reset(
    tmp_path: Path,
) -> None:
    database_path, project_root = _seed_orchestration_database(tmp_path)
    context_id = _create_context(database_path)
    failed_id = _terminal_phase10(database_path, context_id)
    search_run_id = _search(database_path, context_id)
    _observe_terminal_dependency(database_path, search_run_id)

    retry_potential_customer_search(
        database_path, search_run_id, idempotency_key="complete-retry"
    )
    repository = CampaignResultRegistryRepository(database_path)
    attempt = repository.fetch_current_attempt(search_run_id)
    orchestration_id = int(attempt["phase10_orchestration_id"])
    assert orchestration_id != failed_id

    ready = run_phase10_orchestration(
        database_path,
        orchestration_id,
        project_root=project_root,
        artifact_root=Path("artifacts/models"),
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    assert ready["status"] == "READY"
    fence = repository.claim_search_attempt(
        search_run_id, lease_owner="phase11-completion-test"
    )
    outcome = execute_phase11_search(
        database_path,
        search_run_id,
        **fence.as_kwargs(),
        materializer=DeterministicMaterializer(project_root, repository),
        project_root=project_root,
        membership_source=fixed_membership_source,
    )
    assert outcome.status == "COMPLETED"
    assert repository.fetch_search_run(search_run_id)["status"] == "COMPLETED"
    attempt = repository.fetch_current_attempt(search_run_id)
    assert attempt["phase10_dependency_status"] == "READY"


@pytest.mark.parametrize(
    ("status", "retryable", "expected_code", "category"),
    (
        ("BLOCKED", False, "PHASE10_BUSINESS_BLOCKED", "BUSINESS_DATA_INSUFFICIENCY"),
        ("FAILED", False, "PHASE10_PERMANENT_VALIDATION_FAILED", "PERMANENT_VALIDATION"),
    ),
)
def test_nonretryable_phase10_ownership_does_not_loop(
    tmp_path: Path,
    status: str,
    retryable: bool,
    expected_code: str,
    category: str,
) -> None:
    database_path, _ = _seed_orchestration_database(tmp_path)
    context_id = _create_context(database_path)
    orchestration_id = _terminal_phase10(
        database_path, context_id, status=status, retryable=retryable
    )
    search_run_id = _search(database_path, context_id)
    _observe_terminal_dependency(database_path, search_run_id)

    repository = CampaignResultRegistryRepository(database_path)
    runtime = repository.fetch_search_runtime(search_run_id)
    assert runtime["failure_code"] == expected_code
    assert runtime["failure_category"] == category
    assert runtime["retryable"] == 0
    assert runtime["technical_reference"] == f"P10-{orchestration_id}"
    with pytest.raises(Phase11RegistryStateError):
        retry_potential_customer_search(
            database_path, search_run_id, idempotency_key="forbidden-retry"
        )
    assert repository.fetch_search_run(search_run_id)["current_attempt_number"] == 1
    assert Phase10IntelligenceRepository(database_path).list_active_orchestrations() == []
