from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import run_phase11_bounded_cleanroom as cleanroom


@pytest.mark.cleanroom
def test_runtime_root_must_be_new_dedicated_repository_child(tmp_path: Path) -> None:
    with pytest.raises(cleanroom.Phase11CleanRoomError):
        cleanroom._safe_runtime_root(cleanroom.PROJECT_ROOT)
    outside = tmp_path / "outside"
    with pytest.raises(cleanroom.Phase11CleanRoomError):
        cleanroom._safe_runtime_root(outside)
    existing = cleanroom.PROJECT_ROOT / ".tmp" / "existing-phase11-cleanroom"
    existing.mkdir(parents=True, exist_ok=True)
    try:
        with pytest.raises(cleanroom.Phase11CleanRoomError):
            cleanroom._safe_runtime_root(existing)
    finally:
        existing.rmdir()


@pytest.mark.cleanroom
def test_cleanroom_contract_has_all_ten_scenarios_and_deterministic_digest() -> None:
    assert len(cleanroom.SCENARIO_KEYS) == 10
    assert len(set(cleanroom.SCENARIO_KEYS)) == 10
    sample = {"scenarios": list(cleanroom.SCENARIO_KEYS), "count": 10}
    assert cleanroom._digest(sample) == cleanroom._digest(
        {"count": 10, "scenarios": list(cleanroom.SCENARIO_KEYS)}
    )


@pytest.mark.cleanroom
def test_report_declares_isolation_determinism_and_stop_boundary() -> None:
    scenarios = {key: {"status": "PASS"} for key in cleanroom.SCENARIO_KEYS}
    run = {"scenarios": scenarios, "canonical_result_sha256": "a" * 64}
    report = cleanroom._report(
        {
            "runs": [run, run],
            "deterministic_match": True,
            "duration_seconds": 1.0,
            "runtime_cleanup": {"runtime_removed": True},
        }
    )
    assert "PASS_STEP_18_BOUNDED_CLEANROOM_PHASE11_CERTIFICATION" in report
    assert "Canonical database opened: `false`" in report
    assert "Exact relevant-result equality: `true`" in report
    assert "STOP_AFTER_STEP_18" in report
