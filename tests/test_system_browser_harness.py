from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.browser.system_browser import (
    BrowserTarget,
    DEFAULT_CHROME_PATH,
    DEFAULT_EDGE_PATH,
    SystemBrowserResolutionError,
    resolve_system_browser,
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
