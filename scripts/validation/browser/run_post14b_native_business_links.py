"""Native business shortcuts, recent-result link and v3 technical disclosure."""

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


def _counts(database: Path) -> tuple[int, int, int]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("campaign_search_runs", "jobs", "buyer_similarity_result_snapshots"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_named_10k_qualification.json").is_file():
        raise ValueError("Business-link case requires the owned completed bounded QA root.")
    report = {"scope": "BUSINESS_NATIVE_LINKS_AND_TECHNICAL", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        before = _counts(database)
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "business_links_profile", downloads_dir=root / "business_links_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#home", wait_until="domcontentloaded")
                    page.locator("#home-recent-results a, #home-recent-results button").first.wait_for(
                        state="visible", timeout=60_000)
                    page.locator('[data-view-target="results"]:visible').first.click()
                    page.wait_for_url("**/#results")
                    page.locator("#results-view").wait_for(state="visible")
                    report["cases"].append({"id": "HOME_VIEW_ALL_RESULTS", "status": "PASS"})
                    page.locator('#results-view [data-view-target="find-potential-customers"]').click()
                    page.wait_for_url("**/#find-potential-customers")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=60_000)
                    report["cases"].append({"id": "RESULTS_FIND_CUSTOMERS_SHORTCUT", "status": "PASS"})
                    page.locator('a[data-view-target="home"]').click()
                    page.wait_for_url("**/#home")
                    page.locator("#home-recent-results a, #home-recent-results button").first.click()
                    page.wait_for_url("**/#results/1")
                    page.wait_for_function(
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        timeout=60_000)
                    report["cases"].append({"id": "BRAND_HOME_AND_RECENT_RESULT", "status": "PASS"})
                    disclosure = page.locator("#result-technical-disclosure")
                    disclosure.locator("summary").click()
                    assert disclosure.get_attribute("open") is not None
                    technical = page.locator("#result-technical-details").text_content()
                    assert technical and "3" in technical
                    assert "PRODUCT_BUYER_SIMILARITY" in technical
                    assert "12,000" in page.locator("#result-detail-content").inner_text()
                    save_screenshot(page, root / "screenshots" / "business_links_v3_technical.png")
                    report["cases"].append({"id": "V3_TECHNICAL_DISCLOSURE", "status": "PASS"})
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_BUSINESS_LINKS_AND_V3_TECHNICAL",
                                   "browser": session.metadata.to_dict(),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
        after = _counts(database)
        assert after == before, (before, after)
        report["database_counts_before_after"] = before
    except Exception as exc:
        report.update({"status": "FAIL_BUSINESS_LINKS_AND_V3_TECHNICAL",
                       "error_type": type(exc).__name__, "error": str(exc)[:1600],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_business_links.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_BUSINESS_LINKS_AND_V3_TECHNICAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
