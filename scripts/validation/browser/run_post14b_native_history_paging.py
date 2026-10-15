"""Read-only headed-browser history pagination on an existing 20-run QA root."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import QA_PARENT, start_qa_server, stop_qa_server
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _counts(database):
    with sqlite3.connect(database) as connection:
        return {
            "runs": connection.execute("SELECT COUNT(*) FROM campaign_search_runs").fetchone()[0],
            "profiles": connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles").fetchone()[0],
            "generations": connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_score_generations").fetchone()[0],
            "jobs": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "qa_fixture_manifest.json").is_file():
        raise ValueError("History test requires an existing dedicated QA root.")
    print(f"History paging QA root: {root}", flush=True)
    report = {"scope": "BUSINESS_NATIVE_HISTORY_PAGING", "status": "NOT_RUN", "qa_root": str(root)}
    process = None
    try:
        database = root / "state" / "qa.db"
        before = _counts(database)
        assert before["runs"] == 20
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "history_browser_profile",
                downloads_dir=root / "history_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                history_responses = []

                def on_response(response):
                    if "/api/potential-customer-search/results?" in response.url:
                        history_responses.append({"status": response.status,
                                                  "url": response.url.split("/api/", 1)[-1]})

                page.on("response", on_response)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#results", wait_until="domcontentloaded")
                    page.wait_for_function("() => document.querySelectorAll('.result-card').length === 20",
                                           timeout=30_000)
                    cards = page.locator(".result-card")
                    ids = [int(item.get_attribute("data-search-run-id")) for item in cards.all()]
                    assert ids == list(range(20, 0, -1))
                    older = page.locator("#business-history-more")
                    assert older.is_visible()
                    with page.expect_response(
                        lambda response: "/api/potential-customer-search/results?" in response.url
                        and "before_search_run_id=1" in response.url,
                        timeout=30_000,
                    ) as older_response:
                        older.click()
                    assert older_response.value.status == 200
                    assert older_response.value.json() == []
                    page.wait_for_function("() => document.querySelector('#business-history-more').hidden")
                    assert page.locator(".result-card").count() == 20
                    card = page.locator(".result-card[data-search-run-id='20']")
                    assert card.locator(".result-status-badge").get_attribute("data-status") == "COMPLETED"
                    card.locator("a:has-text('View Result')").click()
                    page.wait_for_url("**/#results/20", timeout=20_000)
                    page.wait_for_function(
                        "() => document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        timeout=30_000,
                    )
                    assert "Buyer Similarity" in page.locator("#result-profile-title").inner_text()
                    page.go_back(wait_until="domcontentloaded")
                    page.wait_for_function("() => document.querySelectorAll('.result-card').length === 20",
                                           timeout=30_000)
                    with page.expect_response(
                        lambda response: "/api/potential-customer-search/results?" in response.url
                        and "before_search_run_id" not in response.url,
                        timeout=30_000,
                    ):
                        page.locator("#business-history-refresh").click()
                    assert page.locator(".result-card").count() == 20
                    save_screenshot(page, root / "screenshots" / "twenty_run_history.png")
                    assert _counts(database) == before
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_HISTORY_PAGING_BOUNDARY",
                                   "browser": session.metadata.to_dict(),
                                   "ordered_run_ids": ids,
                                   "history_responses": history_responses,
                                   "database_counts_unchanged": before,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_HISTORY_PAGING_BOUNDARY",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_history_paging.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_HISTORY_PAGING_BOUNDARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
