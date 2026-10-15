"""Retained Historical Analysis alternate filter and outcome-control browser matrix."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


FILTERS = {
    "campaign_ids": "#campaign-filter", "product_ids": "#product-filter",
    "product_categories": "#product-category-filter", "campaign_channels": "#channel-filter",
    "campaign_types": "#campaign-type-filter",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root(
        fixture_kind="UI_CATALOG_DIVERSE")
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Historical alternates need an owned bounded QA root.")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    if manifest["fixture_kind"] != "UI_CATALOG_DIVERSE":
        raise ValueError("Historical alternates require the populated synthetic catalog fixture.")
    report = {"scope": "RETAINED_NATIVE_HISTORICAL_ALTERNATES", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        process, port = start_qa_server(root)
        with sqlite3.connect(database) as connection:
            before = connection.execute("SELECT COUNT(*) FROM historical_analysis_runs").fetchone()[0]
            assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 230
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "historical_alternates_profile",
                downloads_dir=root / "historical_alternates_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#historical-analysis",
                              wait_until="domcontentloaded")
                    page.locator("#historical-analysis-workspace").wait_for(
                        state="visible", timeout=90_000)
                    with page.expect_response(
                        lambda response: "/api/historical/" in response.url
                        and response.request.method == "GET", timeout=30_000,
                    ) as refresh_response:
                        page.locator("#historical-analysis-refresh").click()
                    assert refresh_response.value.status == 200
                    page.locator("#historical-analysis-workspace").wait_for(state="visible")
                    report["cases"].append({"id": "HISTORICAL_OPTIONS_REFRESH", "status": "PASS"})

                    original_from = page.locator("#contact-date-from").input_value()
                    original_to = page.locator("#contact-date-to").input_value()
                    assert original_from and original_to
                    page.locator("#contact-date-from").fill("2025-12-31")
                    page.locator("#contact-date-to").fill("2025-01-01")
                    page.locator("#analyze-population").click()
                    error = page.locator("#historical-form-error")
                    error.wait_for(state="visible")
                    assert "on or before" in error.inner_text()
                    with sqlite3.connect(database) as connection:
                        assert connection.execute("SELECT COUNT(*) FROM historical_analysis_runs").fetchone()[0] == before
                    page.locator("#historical-analysis-reset").click()
                    assert page.locator("#contact-date-from").input_value() == original_from
                    assert page.locator("#contact-date-to").input_value() == original_to
                    report["cases"].append({"id": "HISTORICAL_DATE_GUARD_RESET", "status": "PASS"})

                    selected = {}
                    for field, selector in FILTERS.items():
                        values = page.locator(selector).evaluate(
                            "e => [...e.options].filter(o => o.value).map(o => o.value)")
                        assert values, (field, selector)
                        chosen = "Retention" if field == "campaign_types" and "Retention" in values else values[0]
                        page.locator(selector).select_option(chosen)
                        assert page.locator(selector).evaluate(
                            "e => [...e.selectedOptions].map(o => o.value)") == [chosen]
                        selected[field] = chosen
                        report["cases"].append({"id": f"HISTORICAL_FILTER_{field.upper()}",
                                                "status": "PASS", "chosen": chosen})

                    for conversion, contacted_only in (
                        ("ATTRIBUTED_PURCHASE", True), ("ANY_PURCHASE", False), ("RESPONSE", True),
                    ):
                        page.locator(
                            f'input[name="conversion_definition"][value="{conversion}"]').check()
                        page.locator("#contacted-only").set_checked(contacted_only)
                        page.locator("#analysis-name").fill(f"Bounded alternate {conversion}")
                        with page.expect_response(
                            lambda response: response.request.method == "POST"
                            and response.url.endswith("/api/historical/analyses"), timeout=60_000,
                        ) as analysis_response:
                            page.locator("#analyze-population").click()
                        assert analysis_response.value.status == 201, (
                            analysis_response.value.status, analysis_response.value.text[:600])
                        payload = analysis_response.value.json()
                        run_id = int(payload.get("analysis_run_id") or payload.get("run_id"))
                        with sqlite3.connect(database) as connection:
                            row = connection.execute(
                                "SELECT status,conversion_definition,filters_json,observation_count,"
                                "selected_customer_count,positive_customer_count FROM historical_analysis_runs "
                                "WHERE analysis_run_id=?", (run_id,),
                            ).fetchone()
                        assert row and row[0] == "COMPLETED" and row[1] == conversion
                        page.wait_for_function(
                            "id => document.querySelector('#result-run-id')?.textContent.includes(String(id))"
                            " && document.querySelector('#analysis-results-status')?.textContent.trim()"
                            ".toUpperCase() === 'COMPLETED'", arg=run_id, timeout=30_000)
                        assert page.locator("#result-observations").inner_text().strip() == str(row[3])
                        assert page.locator("#result-selected").inner_text().strip() == str(row[4])
                        assert page.locator("#result-positive").inner_text().strip() == str(row[5])
                        filters = json.loads(row[2])
                        assert filters["contacted_only"] is contacted_only
                        for field, value in selected.items():
                            assert filters[field] == [value], (field, filters[field], value)
                        report["cases"].append({"id": f"HISTORICAL_CONVERSION_{conversion}",
                                                "status": "PASS", "run_id": run_id,
                                                "observation_count": row[3],
                                                "selected_count": row[4],
                                                "positive_count": row[5]})
                    with page.expect_response(
                        lambda response: "/api/historical/" in response.url
                        and response.request.method == "GET", timeout=30_000,
                    ) as recent_response:
                        page.locator("#recent-analyses-refresh").click()
                    assert recent_response.value.status == 200
                    page.locator("#recent-analyses-body .recent-reopen").first.click()
                    page.locator("#analysis-results-status").wait_for(state="visible")
                    report["cases"].append({"id": "HISTORICAL_RECENT_REFRESH_REOPEN", "status": "PASS"})
                    save_screenshot(page, root / "screenshots" / "historical_alternates.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_RETAINED_HISTORICAL_ALTERNATES",
                                   "browser": session.metadata.to_dict(), "selected_filters": selected,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
        with sqlite3.connect(database) as connection:
            after = connection.execute("SELECT COUNT(*) FROM historical_analysis_runs").fetchone()[0]
        assert after == before + 3, (before, after)
        report["analysis_runs_before_after"] = [before, after]
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_HISTORICAL_ALTERNATES",
                       "error_type": type(exc).__name__, "error": str(exc)[:1600],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_historical_alternates.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_RETAINED_HISTORICAL_ALTERNATES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
