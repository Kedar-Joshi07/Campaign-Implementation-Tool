from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs import executor as executor_module


class _FakeExecutor:
    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers
        self.submit_calls: list[tuple[object, tuple[object, ...]]] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, fn: object, *args: object) -> object:
        self.submit_calls.append((fn, args))
        return {"submitted": True, "args": args}

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


@pytest.fixture(autouse=True)
def _reset_executor_state() -> None:
    executor_module.shutdown_model_training_executor(wait=False)
    yield
    executor_module.shutdown_model_training_executor(wait=False)


def test_executor_is_lazy_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeExecutor] = []

    def fake_factory(*, max_workers: int) -> _FakeExecutor:
        instance = _FakeExecutor(max_workers=max_workers)
        created.append(instance)
        return instance

    monkeypatch.setattr(executor_module, "ProcessPoolExecutor", fake_factory)

    assert not executor_module.is_model_training_executor_initialized()

    first = executor_module.get_model_training_executor()
    second = executor_module.get_model_training_executor()

    assert first is second
    assert len(created) == 1
    assert created[0].max_workers == executor_module.EXECUTOR_MAX_WORKERS == 1
    assert executor_module.is_model_training_executor_initialized()


def test_submit_forwards_worker_and_job_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_executor = _FakeExecutor(max_workers=1)
    monkeypatch.setattr(executor_module, "get_model_training_executor", lambda: fake_executor)

    future = executor_module.submit_model_training_job(Path("relative.db"), 7)

    assert future == {"submitted": True, "args": ("relative.db", 7)}
    assert len(fake_executor.submit_calls) == 1
    fn, args = fake_executor.submit_calls[0]
    assert fn is executor_module.run_model_training_job
    assert args == ("relative.db", 7)


def test_submit_scoring_forwards_worker_and_job_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_executor = _FakeExecutor(max_workers=1)
    monkeypatch.setattr(executor_module, "get_model_training_executor", lambda: fake_executor)

    future = executor_module.submit_prospect_scoring_job(Path("relative.db"), 9)

    assert future == {"submitted": True, "args": ("relative.db", 9)}
    assert len(fake_executor.submit_calls) == 1
    fn, args = fake_executor.submit_calls[0]
    assert fn is executor_module.run_prospect_scoring_job
    assert args == ("relative.db", 9)


def test_submit_rejects_invalid_job_id() -> None:
    with pytest.raises(ValueError):
        executor_module.submit_model_training_job("db.sqlite", 0)
    with pytest.raises(ValueError):
        executor_module.submit_prospect_scoring_job("db.sqlite", -1)


def test_shutdown_is_idempotent_and_clears_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_executor = _FakeExecutor(max_workers=1)
    monkeypatch.setattr(executor_module, "ProcessPoolExecutor", lambda *, max_workers: fake_executor)

    executor_module.get_model_training_executor()
    executor_module.shutdown_model_training_executor(wait=False)
    executor_module.shutdown_model_training_executor(wait=False)

    assert fake_executor.shutdown_calls == [(False, True)]
    assert not executor_module.is_model_training_executor_initialized()