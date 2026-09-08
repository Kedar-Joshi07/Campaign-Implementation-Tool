from __future__ import annotations

from pathlib import Path

from scripts.validation.browser.build_ui_control_inventory import build_inventory_payload
from scripts.validation.browser.check_ui_control_coverage import evaluate_inventory


def test_inventory_builder_outputs_required_contract_fields() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = build_inventory_payload(project_root)

    assert "controls" in payload
    assert payload["controls"]
    assert payload["status_summary"]["NOT_RUN"] == len(payload["controls"])

    required_fields = {
        "page",
        "selector",
        "label",
        "type",
        "enable_conditions",
        "mutually_exclusive_group",
        "expected_behavior",
        "required_scenario",
        "status",
    }
    for control in payload["controls"]:
        assert required_fields.issubset(control.keys())
        assert control["status"] == "NOT_RUN"

    identities = [(control["page"], control["selector"]) for control in payload["controls"]]
    assert len(identities) == len(set(identities))


def test_inventory_excludes_non_actionable_javascript_output_selectors() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = build_inventory_payload(project_root)
    identities = {(control["page"], control["selector"]) for control in payload["controls"]}

    assert ("overview", "#customer-count") not in identities
    assert ("historical-analysis", "#analysis-results-status") not in identities
    assert ("model-training", "#model-job-status") not in identities
    assert ("audience-explorer", "#audience-estimate-selected") not in identities
    assert ("campaigns", "#campaign-export-status-note") not in identities


def test_inventory_includes_page_scoped_runtime_created_controls() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = build_inventory_payload(project_root)
    identities = {(control["page"], control["selector"]) for control in payload["controls"]}

    assert ("historical-analysis", ".recent-reopen") in identities
    assert ("model-training", ".recent-reopen") in identities
    assert ("audience-explorer", ".recent-reopen") in identities
    assert ("campaigns", ".campaign-open") in identities
    assert ("historical-analysis", "input[name='conversion_definition']") in identities


def test_coverage_checker_fails_with_not_run_controls() -> None:
    payload = {
        "controls": [
            {
                "selector": "#sample",
                "status": "NOT_RUN",
                "mutually_exclusive_group": "",
                "justification": "",
            }
        ]
    }

    result = evaluate_inventory(payload)
    assert result["ok"] is False
    assert result["counts"]["NOT_RUN"] == 1
    assert any("NOT_RUN controls remaining" in err for err in result["errors"])


def test_coverage_checker_accepts_terminal_pass_set() -> None:
    payload = {
        "controls": [
            {
                "selector": "#a",
                "status": "PASS",
                "mutually_exclusive_group": "",
                "justification": "",
            },
            {
                "selector": "#b",
                "status": "JUSTIFIED_EXCLUSIVE",
                "mutually_exclusive_group": "campaign-channel",
                "justification": "Control is hidden when alternate channel is selected.",
            },
        ]
    }

    result = evaluate_inventory(payload)
    assert result["ok"] is True
    assert result["counts"]["FAIL"] == 0
    assert result["counts"]["NOT_RUN"] == 0
