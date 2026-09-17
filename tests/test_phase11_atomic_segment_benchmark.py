from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.validation.phase11 import phase11_step10_benchmark as benchmark


def _options() -> dict[str, object]:
    categorical = {
        "state": [
            {"value": "Arizona"},
            {"value": "California"},
            {"value": "Colorado"},
            {"value": "Connecticut"},
            {"value": "Florida"},
        ]
    }
    for field in (
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "type_of_employment",
    ):
        categorical[field] = [{"value": f"{field}-value"}]
    return {
        "categorical_options": categorical,
        "score_summary": {"score_min": 0.01, "score_max": 0.99},
    }


def test_read_only_connection_rejects_writes(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE fixture (value INTEGER NOT NULL)")

    with benchmark._read_only_connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fixture").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO fixture (value) VALUES (1)")


def test_representative_cases_are_exact_and_include_real_top_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[dict[str, object]] = []

    def fake_estimate(_path: Path, request: dict[str, object]) -> dict[str, object]:
        observed.append(request)
        return {"matching_count": 10, "selected_count": 10}

    monkeypatch.setattr(benchmark, "estimate_audience", fake_estimate)
    cases = benchmark._cases(Path("fixture.db"), 7, _options())

    assert [case[0] for case in cases] == [
        "score_threshold_no_demographics",
        "one_state",
        "five_states",
        "age_income_bucket",
        "multi_age_multi_income_states",
        "advanced_demographics",
        "top_n_100",
    ]
    for _name, operation, _request in cases:
        operation()

    assert len(observed) == 7
    assert observed[-1]["selection"] == {"mode": "TOP_N", "target_count": 100}
    assert observed[-1]["filters"] == {
        "state": ["Arizona", "California", "Colorado", "Connecticut", "Florida"]
    }


def test_repeated_timing_requires_stable_results() -> None:
    stable = benchmark._timed(
        3,
        lambda: {"matching_count": 12, "selected_count": 12},
    )
    assert stable["repetitions"] == 3
    assert stable["stable_result"] == {
        "matching_count": 12,
        "selected_count": 12,
        "row_count": 0,
    }

    counter = iter((1, 2, 3))
    with pytest.raises(RuntimeError, match="Repeated benchmark output changed"):
        benchmark._timed(
            3,
            lambda: {"matching_count": next(counter), "selected_count": 1},
        )
