from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.validation.browser.system_browser import (
    BrowserTarget,
    DEFAULT_CHROME_PATH,
    DEFAULT_EDGE_PATH,
    SystemBrowserResolutionError,
    resolve_system_browser,
)
from scripts.validation.browser.run_phase8_step12_ci_green_branch_protection_and_freeze import (
    _build_checklist_items,
    _collect_control_summary,
    _collect_phase8_references,
    _evaluate_branch_protection,
)


def test_explicit_path_override_has_highest_priority() -> None:
    explicit = Path("C:/tools/custom-browser.exe")

    target = resolve_system_browser(
        system_browser="auto",
        system_browser_path=str(explicit),
        path_exists=lambda path: path == explicit,
    )

    assert isinstance(target, BrowserTarget)
    assert target.executable_path == explicit
    assert target.source == "explicit_path"


def test_auto_prefers_chrome_then_edge() -> None:
    target = resolve_system_browser(
        system_browser="auto",
        path_exists=lambda path: path == DEFAULT_CHROME_PATH,
    )

    assert target.name == "chrome"
    assert target.executable_path == DEFAULT_CHROME_PATH


def test_auto_falls_back_to_edge_when_chrome_missing() -> None:
    target = resolve_system_browser(
        system_browser="auto",
        path_exists=lambda path: path == DEFAULT_EDGE_PATH,
    )

    assert target.name == "edge"
    assert target.executable_path == DEFAULT_EDGE_PATH


def test_system_browser_env_and_path_are_honored() -> None:
    custom_path = Path("D:/portable/chrome.exe")
    env = {
        "SYSTEM_BROWSER": "chrome",
        "SYSTEM_BROWSER_PATH": str(custom_path),
    }

    target = resolve_system_browser(
        environ=env,
        path_exists=lambda path: path == custom_path,
    )

    assert target.executable_path == custom_path
    assert target.source == "explicit_path"


def test_invalid_browser_choice_fails_clearly() -> None:
    with pytest.raises(SystemBrowserResolutionError) as exc:
        resolve_system_browser(system_browser="firefox", path_exists=lambda _: False)

    assert "SYSTEM_BROWSER must be one of auto, chrome, edge" in str(exc.value)


def test_missing_selected_browser_fails_clearly() -> None:
    with pytest.raises(SystemBrowserResolutionError) as exc:
        resolve_system_browser(system_browser="chrome", path_exists=lambda _: False)

    assert "SYSTEM_BROWSER=chrome requested" in str(exc.value)


def test_step7_browser_runner_does_not_write_preparation_state_directly() -> None:
    runner_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validation"
        / "browser"
        / "run_phase8_step7_audience_explorer_all_controls.py"
    )
    runner = runner_path.read_text(encoding="utf-8")

    assert '"#audience-prepare-submit"' in runner
    assert "run_audience_rank_preparation(" not in runner
    assert '"direct_service_write": False' in runner
    assert 'PHASE8_STEP7_WORKSPACE_TIMEOUT_SECONDS", "10800"' in runner
    assert 'PHASE8_STEP7_SCENARIO_TIMEOUT_SECONDS", "900"' in runner
    assert 'if not prep_observations["submit_clicked"]:' in runner
    assert 'not prep_observations["retry_clicked"]' in runner


def test_step8_browser_runner_has_no_direct_workflow_state_write_fallbacks() -> None:
    runner_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validation"
        / "browser"
        / "run_phase8_step8_campaign_builder_and_exports.py"
    )
    runner = runner_path.read_text(encoding="utf-8")

    for forbidden_call in (
        "run_audience_rank_preparation(",
        "save_audience(",
        "create_campaign(",
        "update_campaign(",
        "finalize_campaign(",
    ):
        assert forbidden_call not in runner
    assert '"method": "browser_disabled_controls"' in runner
    assert '"direct_service_write": False' in runner


def test_step11_tears_down_the_complete_managed_server_tree_on_windows() -> None:
    runner_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validation"
        / "browser"
        / "run_phase8_step11_clean_head_certification.py"
    )
    runner = runner_path.read_text(encoding="utf-8")

    assert '["taskkill", "/PID", str(process.pid), "/T", "/F"]' in runner
    assert 'RESUME_EXISTING_ENV = "PHASE8_STEP11_RESUME_EXISTING"' in runner
    assert '"user_directed_no_scoring_rerun": True' in runner
    assert "SELECT model_run_id, status, selected_candidate, feature_contract_json," in runner
    assert "model_feature_contract_sha256 == latest_scoring[6]" in runner
    assert 'deterministic_max_abs_diff is not None' in runner
    assert 'deterministic_rescore.get("max_abs_diff") or 1.0' not in runner


def _step12_checklist_payload() -> dict:
    return {
        "local_regression": {
            "checks": [
                {"key": "full_pytest", "passed": True},
                {"key": "clean_room_phase1_to_phase7", "passed": True},
                {"key": "deterministic_generation_hash_checks", "passed": True},
            ]
        },
        "phase8_references": _collect_phase8_references(),
        "control_coverage": _collect_control_summary(),
        "github_ci": {"required_all_green": True, "candidate_matches": True},
        "branch_protection": {"evaluation": {"acceptable": True}},
    }


def test_step12_checklist_uses_precise_phase8_evidence_gates() -> None:
    items = {item["id"]: item for item in _build_checklist_items(_step12_checklist_payload())}

    for item_id in range(3, 26):
        assert items[item_id]["status"] == "PASS", items[item_id]
    assert items[26]["status"] == "PASS"
    assert items[27]["status"] == "PASS"
    assert items[28]["status"] == "PASS"


def test_step12_missing_browser_error_metrics_fail_closed() -> None:
    payload = _step12_checklist_payload()
    payload["phase8_references"] = deepcopy(payload["phase8_references"])
    browser_quality = payload["phase8_references"]["step9_browser_quality"]
    browser_quality["unexplained_console_total"] = None
    browser_quality["unexplained_critical_network_total"] = None

    items = {item["id"]: item for item in _build_checklist_items(payload)}

    assert items[15]["status"] == "FAIL"
    assert items[16]["status"] == "FAIL"


def test_step12_branch_protection_fallback_requires_complete_documentation() -> None:
    evaluation = _evaluate_branch_protection({"available": False})

    assert evaluation["api_settings_complete"] is False
    assert evaluation["documented_complete"] is True
    assert evaluation["acceptable"] is True


def test_step12_does_not_invoke_the_full_5m_scoring_runner() -> None:
    runner_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validation"
        / "browser"
        / "run_phase8_step12_ci_green_branch_protection_and_freeze.py"
    )
    runner = runner_path.read_text(encoding="utf-8")

    assert "run_phase8_step6_model_training_and_5m_scoring.py" not in runner
    assert '"full_5m_scoring_rerun": False' in runner
    assert "_query_ci_status(sha_now, required_ci_checks)" in runner
    assert 'str(LOCAL_RUNTIME_DIR / "cleanroom_phase1_to_phase7.json")' in runner
