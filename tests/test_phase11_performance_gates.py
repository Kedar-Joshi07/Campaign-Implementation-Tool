"""Step 17 bounded performance measurements for the Phase 11 product paths.

These are relative/observational gates, not production SLA claims.  They use a
deterministic local fixture and never open the canonical 5M database.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import time
from typing import Any, Callable

import pytest

from app.services import phase11_export_service as export_service
from app.services.audience_preparation_service import classify_rank_band
from app.services.omnichannel_profile_contracts import OMNICHANNEL_PROFILE_REGISTRY
from app.services.phase11_result_snapshot_service import (
    ResultSnapshotMaterializer,
    validate_result_snapshot,
)
from app.services.phase11_search_orchestration_service import (
    build_result_cache_key,
    execute_phase11_search,
)
from tests.test_phase11_business_search_form import (
    client,
    database_path,
    request_payload,
)
from tests.test_phase11_omnichannel_export_engine import (
    NeverDisconnected,
    _consume,
    export_case,
)
from tests.test_phase11_search_result_registry import _search, case
from tests.test_phase11_smart_reuse_engine import fixed_reader, generation, ready_response


REPETITIONS = 5
MEMBERSHIP_ROWS = 20_000


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _measure(operation: Callable[[], Any], *, repetitions: int = REPETITIONS) -> tuple[dict[str, Any], Any]:
    samples: list[float] = []
    result: Any = None
    for _ in range(repetitions):
        started = time.perf_counter()
        result = operation()
        samples.append(time.perf_counter() - started)
    return {
        "repetitions": repetitions,
        "seconds": [round(value, 6) for value in samples],
        "median_seconds": round(statistics.median(samples), 6),
        "minimum_seconds": round(min(samples), 6),
        "maximum_seconds": round(max(samples), 6),
    }, result


def _members(count: int = MEMBERSHIP_ROWS):
    for index in range(count):
        percentile = index % 100 + 1
        yield {
            "person_id": f"P{index + 1:09d}",
            "propensity_score": 1.0 - (index / max(count, 1)),
            "percentile_bucket": percentile,
            "decile": min(10, (percentile - 1) // 10 + 1),
            "rank_band": classify_rank_band(percentile),
        }


def _assert_response(response: Any) -> int:
    assert response.status_code == 200, response.text
    return response.status_code


def _write_metrics(metrics: dict[str, Any]) -> None:
    target = os.environ.get("PHASE11_STEP17_METRICS")
    if not target:
        return
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


@pytest.mark.performance
def test_bounded_phase11_performance_gates(
    client,
    case,
    export_case,
) -> None:
    metrics: dict[str, Any] = {
        "contract": "phase11-step17-bounded-performance-v1",
        "generated_at": _timestamp(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "fixture_membership_rows": MEMBERSHIP_ROWS,
            "canonical_database_opened": False,
        },
        "absolute_sla_asserted": False,
        "timings": {},
    }

    timings = metrics["timings"]
    timings["home_load"], _ = _measure(
        lambda: _assert_response(client.get("/api/business/overview"))
    )
    timings["options_load"], _ = _measure(
        lambda: _assert_response(client.get("/api/potential-customer-search/options"))
    )

    path, _, _, repository = case
    current = generation(case)
    phase10_reader = fixed_reader(ready_response(current))
    materializer = ResultSnapshotMaterializer(path.parent)

    initial_run = _search(case)
    initial_started = time.perf_counter()
    initial = execute_phase11_search(
        path,
        initial_run,
        materializer=materializer,
        project_root=path.parent,
        phase10_reader=phase10_reader,
        membership_source=lambda *_: _members(),
    )
    initial_seconds = time.perf_counter() - initial_started
    assert initial.status == "COMPLETED"
    assert initial.result_source == "INTELLIGENCE_REUSE"
    snapshot = repository.fetch_snapshot(initial.result_snapshot_id)
    run = repository.fetch_search_run(initial_run)
    assert snapshot is not None and run is not None
    cache_key = build_result_cache_key(run, current)
    timings["snapshot_write"] = {
        "repetitions": 1,
        "seconds": [round(initial_seconds, 6)],
        "median_seconds": round(initial_seconds, 6),
        "rows": MEMBERSHIP_ROWS,
    }

    timings["snapshot_read"], validation = _measure(
        lambda: validate_result_snapshot(
            snapshot, run, current, cache_key, project_root=path.parent
        )
    )
    assert validation.is_valid and validation.row_count == MEMBERSHIP_ROWS

    exact_samples: list[float] = []
    forbidden_membership_calls = 0

    def forbidden_membership_source(*_args):
        nonlocal forbidden_membership_calls
        forbidden_membership_calls += 1
        raise AssertionError("An exact cache hit must not scan or filter score membership.")

    for index in range(REPETITIONS):
        exact_run = _search(case, campaign_name=f"Exact cache timing {index}")
        started = time.perf_counter()
        outcome = execute_phase11_search(
            path,
            exact_run,
            materializer=materializer,
            project_root=path.parent,
            phase10_reader=phase10_reader,
            membership_source=forbidden_membership_source,
        )
        exact_samples.append(time.perf_counter() - started)
        assert outcome.result_source == "EXACT_RESULT_REUSE"
        assert outcome.result_snapshot_id == initial.result_snapshot_id
    assert forbidden_membership_calls == 0
    exact_median = statistics.median(exact_samples)
    timings["exact_cache_hit"] = {
        "repetitions": REPETITIONS,
        "seconds": [round(value, 6) for value in exact_samples],
        "median_seconds": round(exact_median, 6),
        "membership_source_calls": forbidden_membership_calls,
        "propensity_score_population_scan": False,
    }

    filter_samples: list[float] = []
    for index in range(REPETITIONS):
        state = f"Bounded fixture state {index}"
        filtered_run = _search(
            case,
            campaign_name=f"Intelligence reuse timing {index}",
            targeting_criteria={"states": [state]},
            filter_branches=[{"state": [state]}],
        )
        started = time.perf_counter()
        outcome = execute_phase11_search(
            path,
            filtered_run,
            materializer=materializer,
            project_root=path.parent,
            phase10_reader=phase10_reader,
            membership_source=lambda *_: _members(),
        )
        filter_samples.append(time.perf_counter() - started)
        assert outcome.result_source == "INTELLIGENCE_REUSE"
    filter_median = statistics.median(filter_samples)
    speedup = filter_median / exact_median
    timings["intelligence_reuse_filter_and_materialize"] = {
        "repetitions": REPETITIONS,
        "seconds": [round(value, 6) for value in filter_samples],
        "median_seconds": round(filter_median, 6),
        "rows_per_snapshot": MEMBERSHIP_ROWS,
    }
    metrics["exact_cache_relative_gate"] = {
        "comparison": "intelligence_reuse_filter_and_materialize / exact_cache_hit",
        "speedup_ratio": round(speedup, 3),
        "required_minimum_ratio": 1.25,
        "passed": speedup >= 1.25,
    }
    assert speedup >= 1.25

    submitted = client.post(
        "/api/potential-customer-search/runs", json=request_payload()
    )
    assert submitted.status_code == 201, submitted.text
    timings["result_history"], _ = _measure(
        lambda: _assert_response(
            client.get("/api/potential-customer-search/results?limit=20")
        )
    )

    export_path, _, _, runs = export_case
    export_timings: dict[str, Any] = {}
    for profile_name in OMNICHANNEL_PROFILE_REGISTRY:
        def export(profile_name: str = profile_name) -> int:
            response = export_service.stream_phase11_result_export_csv(
                export_path,
                search_run_id=runs[profile_name],
                request=NeverDisconnected(),
                project_root=export_path.parent,
            )
            return len(asyncio.run(_consume(response)))

        export_timings[profile_name], body_bytes = _measure(export, repetitions=3)
        export_timings[profile_name]["body_bytes"] = body_bytes
        assert body_bytes > 0
    timings["export_profiles"] = export_timings
    assert set(export_timings) == set(OMNICHANNEL_PROFILE_REGISTRY)

    metrics["optional_atomic_optimization_comparison"] = {
        "status": "NOT_APPLICABLE",
        "reason": (
            "The current Phase 11 5M generation benchmark completed with stable "
            "exact results. Step 10 retained the existing indexed Audience Engine "
            "because no additional atomic candidate demonstrated a net runtime and "
            "storage benefit; therefore no before/after candidate comparison exists."
        ),
    }
    _write_metrics(metrics)
