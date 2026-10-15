"""Exercise retained Audience Explorer's alternate controls against bounded real APIs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import QA_PARENT, start_qa_server, stop_qa_server
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


FIELDS = {
    "#audience-top-percentile": ("top_percentile_max", "100"),
    "#audience-age-min": ("age_min", "18"),
    "#audience-age-max": ("age_max", "100"),
    "#audience-income-min": ("individual_yearly_income_min", "0"),
    "#audience-income-max": ("individual_yearly_income_max", "999999999"),
    "#audience-family-min": ("family_member_count_min", "1"),
    "#audience-family-max": ("family_member_count_max", "100"),
}
SELECTS = {
    "#audience-deciles": "deciles", "#audience-rank-bands": "rank_bands",
    "#audience-gender": "gender", "#audience-state": "state",
    "#audience-marital-status": "marital_status", "#audience-education": "education",
    "#audience-employment-status": "employment_status",
    "#audience-resident-status": "resident_status",
    "#audience-resident-type": "resident_type",
    "#audience-type-of-employment": "type_of_employment",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_retained_historical.json").is_file():
        raise ValueError("Audience alternatives require a retained owned QA root.")
    report = {"scope": "RETAINED_NATIVE_AUDIENCE_ALTERNATES", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            before_audiences = connection.execute("SELECT COUNT(*) FROM saved_audiences").fetchone()[0]
            before_scoring = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
        assert before_scoring > 0
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "audience_alternates_profile",
                downloads_dir=root / "audience_alternates_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#audience-explorer",
                              wait_until="domcontentloaded")
                    page.locator("#audience-filter-form").wait_for(state="visible", timeout=90_000)
                    page.locator("#audience-apply-filters").wait_for(state="visible", timeout=90_000)
                    assert page.locator("#audience-apply-filters").is_enabled()
                    with page.expect_response(
                        lambda response: "/api/audience/runs?" in response.url
                        and response.request.method == "GET", timeout=30_000,
                    ) as refresh:
                        page.locator("#audience-explorer-refresh").click()
                    assert refresh.value.status == 200
                    page.wait_for_function(
                        "() => !document.querySelector('#audience-explorer-refresh')?.disabled && "
                        "document.querySelector('#audience-context-scoring-run')?.textContent.trim()"
                        " !== '-'", timeout=60_000)
                    report["cases"].append({"id": "AUDIENCE_WORKSPACE_REFRESH", "status": "PASS"})

                    for selector, (field, value) in FIELDS.items():
                        page.locator("#audience-filter-reset").click()
                        page.locator(selector).fill(value)
                        assert page.locator(selector).input_value() == value
                        with page.expect_response(
                            lambda response: response.url.endswith("/api/audience/estimate")
                            and response.request.method == "POST", timeout=30_000,
                        ) as response_info:
                            page.locator("#audience-apply-filters").click()
                        response = response_info.value
                        assert response.status == 200, (field, response.status, response.text()[:350])
                        payload = response.request.post_data_json
                        expected = int(value)
                        assert payload["filters"][field] == expected, (field, expected, payload["filters"][field])
                        body = response.json()
                        page.wait_for_function(
                            "count => document.querySelector('#audience-estimate-matching')?.textContent.trim()"
                            " === String(count)", arg=body["matching_count"], timeout=30_000)
                        assert body["selected_count"] == body["matching_count"]
                        report["cases"].append({"id": f"AUDIENCE_FILTER_{field.upper()}",
                                                "status": "PASS", "value": expected,
                                                "matching": body["matching_count"]})

                    for selector, field in SELECTS.items():
                        page.locator("#audience-filter-reset").click()
                        values = page.locator(f"{selector} option").evaluate_all(
                            "options => options.map(option => option.value)")
                        if not values:
                            report["cases"].append({"id": f"AUDIENCE_FILTER_{field.upper()}",
                                                    "status": "NOT_RUN", "reason": "No fixture options"})
                            continue
                        chosen = values[0]
                        page.locator(selector).select_option([chosen])
                        with page.expect_response(
                            lambda response: response.url.endswith("/api/audience/estimate")
                            and response.request.method == "POST", timeout=30_000,
                        ) as response_info:
                            page.locator("#audience-apply-filters").click()
                        response = response_info.value
                        assert response.status == 200, (field, response.status, response.text()[:350])
                        payload = response.request.post_data_json
                        expected = [int(chosen)] if field == "deciles" else [chosen]
                        assert payload["filters"][field] == expected
                        body = response.json()
                        page.wait_for_function(
                            "count => document.querySelector('#audience-estimate-matching')?.textContent.trim()"
                            " === String(count)", arg=body["matching_count"], timeout=30_000)
                        assert body["selected_count"] == body["matching_count"]
                        report["cases"].append({"id": f"AUDIENCE_FILTER_{field.upper()}",
                                                "status": "PASS", "value": chosen,
                                                "matching": body["matching_count"]})

                    page.locator("#audience-clear-filter-chips").click()
                    assert page.locator("#audience-selection-all").is_checked()
                    assert page.locator("#audience-top-percentile").input_value() == ""
                    assert page.locator("#audience-gender").evaluate(
                        "element => [...element.selectedOptions].length") == 0
                    report["cases"].append({"id": "AUDIENCE_CLEAR_CHIPS_ALL_MODE", "status": "PASS"})

                    with page.expect_response(
                        lambda response: "/api/audiences?" in response.url
                        and response.request.method == "GET", timeout=30_000,
                    ) as saved_refresh:
                        page.locator("#saved-audiences-refresh").click()
                    assert saved_refresh.value.status == 200
                    page.locator("#audience-apply-filters").click()
                    page.wait_for_function(
                        "() => document.querySelector('#audience-estimate-selected')?.textContent.trim()"
                        " !== '-'", timeout=30_000)
                    page.locator("#audience-save-name").fill("Bounded audience alternate description")
                    page.locator("#audience-save-description").fill("Synthetic QA description via native browser")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/audiences")
                        and response.request.method == "POST", timeout=30_000,
                    ) as save_response:
                        page.locator("#audience-save-submit").click()
                    assert save_response.value.status in (200, 201)
                    with sqlite3.connect(database) as connection:
                        audiences = connection.execute("SELECT COUNT(*) FROM saved_audiences").fetchone()[0]
                        saved = connection.execute(
                            "SELECT description,resolved_count FROM saved_audiences ORDER BY audience_id DESC LIMIT 1"
                        ).fetchone()
                        scoring = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
                    assert audiences == before_audiences + 1
                    assert saved[0] == "Synthetic QA description via native browser"
                    assert scoring == before_scoring
                    page.locator("#saved-audience-list .saved-audience-item").filter(
                        has_text="Bounded audience alternate description").get_by_role(
                        "button", name="View").click()
                    page.locator("#saved-audience-detail-title").get_by_text(
                        "Bounded audience alternate description").wait_for(state="visible")
                    report["cases"].append({"id": "AUDIENCE_SAVED_REFRESH_DESCRIPTION_VIEW",
                                            "status": "PASS", "resolved_count": saved[1]})
                    save_screenshot(page, root / "screenshots" / "audience_alternates.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_RETAINED_AUDIENCE_ALTERNATES",
                                   "browser": session.metadata.to_dict(),
                                   "audiences_before_after": [before_audiences, audiences],
                                   "scoring_runs_before_after": [before_scoring, scoring],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_AUDIENCE_ALTERNATES",
                       "error_type": type(exc).__name__, "error": str(exc)[:1700],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_audience_alternates.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_RETAINED_AUDIENCE_ALTERNATES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
