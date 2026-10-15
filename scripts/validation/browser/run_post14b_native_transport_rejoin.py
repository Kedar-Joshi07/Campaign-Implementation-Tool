"""Bounded native result-detail offline failure and genuine online retry."""

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


def _counts(database: Path) -> tuple[int, int, int, int]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("campaign_search_runs", "campaign_search_attempts", "jobs",
                                   "buyer_similarity_result_snapshots"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_named_10k_qualification.json").is_file():
        raise ValueError("Transport case requires the owned bounded completed v3 root.")
    report = {"scope": "FAULT_NATIVE_TRANSPORT_REJOIN", "status": "NOT_RUN",
              "qa_root": str(root)}
    process = None
    try:
        database = root / "state" / "qa.db"
        before = _counts(database)
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "rejoin_browser_profile",
                downloads_dir=root / "rejoin_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#results/1", wait_until="domcontentloaded")
                    page.wait_for_function(
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        timeout=60_000)
                    assert "12,000" in page.locator("#result-detail-content").inner_text()
                    status_button = page.locator("#backend-status")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/health")
                        and response.request.method == "GET", timeout=30_000,
                    ) as online_health:
                        status_button.click()
                    assert online_health.value.status == 200
                    page.wait_for_function(
                        "document.querySelector('#backend-status')?.classList.contains('is-online')")
                    session.context.set_offline(True)
                    status_button.click()
                    page.wait_for_function(
                        "document.querySelector('#backend-status')?.classList.contains('is-offline')")
                    assert "Backend unavailable" in status_button.inner_text()
                    page.locator("#result-detail-refresh").click()
                    page.locator("#result-detail-error").wait_for(state="visible", timeout=30_000)
                    assert page.locator("#result-detail-retry").is_visible()
                    assert page.locator("#result-detail-status").get_attribute("aria-live") == "polite"
                    save_screenshot(page, root / "screenshots" / "native_transport_offline.png")
                    expected_failures = list(capture.request_failures)
                    assert any("result" in item.get("url", "") for item in expected_failures), expected_failures
                    assert any("health" in item.get("url", "") for item in expected_failures), expected_failures
                    session.context.set_offline(False)
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/health")
                        and response.request.method == "GET", timeout=30_000,
                    ) as recovered_health:
                        status_button.click()
                    assert recovered_health.value.status == 200
                    page.wait_for_function(
                        "document.querySelector('#backend-status')?.classList.contains('is-online')")
                    page.locator("#result-detail-retry").click()
                    page.locator("#result-detail-error").wait_for(state="hidden", timeout=30_000)
                    page.wait_for_function(
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'"
                        " && !document.querySelector('#result-detail-content')?.hidden",
                        timeout=60_000)
                    assert "12,000" in page.locator("#result-detail-content").inner_text()
                    save_screenshot(page, root / "screenshots" / "native_transport_rejoined.png")
                    assert not capture.page_errors
                    report.update({"status": "PASS_NATIVE_TRANSPORT_REJOIN", "browser": session.metadata.to_dict(),
                                   "offline_request_failures": expected_failures,
                                   "backend_status_sequence": ["ONLINE", "OFFLINE", "ONLINE"],
                                   "final_request_failures": capture.request_failures,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors})
                finally:
                    session.context.set_offline(False)
                    detach_page_event_capture(page, listeners)
        after = _counts(database)
        assert after == before, (before, after)
        report["database_counts_before_after"] = before
    except Exception as exc:
        report.update({"status": "FAIL_NATIVE_TRANSPORT_REJOIN", "error_type": type(exc).__name__,
                       "error": str(exc)[:1600], "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_transport_rejoin.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_NATIVE_TRANSPORT_REJOIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
