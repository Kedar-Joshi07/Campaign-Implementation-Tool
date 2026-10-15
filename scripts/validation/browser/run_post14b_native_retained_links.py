"""Bounded headed-browser proof for Insights links and hidden production routing."""

from __future__ import annotations

import json
import sqlite3
import traceback
from importlib.metadata import version
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    root = prepare_qa_root()
    print(f"Retained links QA root: {root}", flush=True)
    process = None
    report = {"scope": "RETAINED_COMPONENT_HARNESS_INSIGHTS_LINKS",
              "status": "NOT_RUN", "qa_root": str(root), "headless": False}
    try:
        process, port = start_qa_server(root)
        report["loopback_port"] = port
        database = root / "state" / "qa.db"
        responses = []
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)

                def on_response(response):
                    path = urlsplit(response.url).path
                    if path.startswith("/api/"):
                        responses.append({"method": response.request.method,
                                          "path": path, "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#insights", wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => !document.querySelector('#overview-view')?.hidden && "
                        "document.querySelector('#insights-view')?.hidden",
                        timeout=20_000,
                    )
                    assert page.locator("#insights-view").is_hidden()
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#insights",
                              wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => !document.querySelector('#insights-view')?.hidden && "
                        "document.querySelector('#page-title')?.textContent === 'Insights'",
                        timeout=20_000,
                    )
                    save_screenshot(page, root / "screenshots" / "insights_destinations.png")
                    page.locator('#insights-view [data-view-target="historical-analysis"]').click()
                    page.wait_for_function(
                        "() => location.hash === '#historical-analysis' && "
                        "!document.querySelector('#historical-analysis-view')?.hidden",
                        timeout=20_000,
                    )
                    page.locator("#historical-options-loading").wait_for(
                        state="hidden", timeout=30_000)
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#insights",
                              wait_until="domcontentloaded")
                    page.locator('#insights-view [data-view-target="audience-explorer"]').click()
                    page.wait_for_function(
                        "() => location.hash === '#audience-explorer' && "
                        "!document.querySelector('#audience-explorer-view')?.hidden",
                        timeout=20_000,
                    )
                    page.wait_for_function(
                        "() => !document.querySelector('#audience-explorer-no-run')?.hidden || "
                        "!document.querySelector('#audience-explorer-workspace')?.hidden",
                        timeout=30_000,
                    )
                    assert page.locator("#audience-explorer-workspace").is_hidden()
                    with sqlite3.connect(database) as connection:
                        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                        scores = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
                    assert (jobs, scores) == (0, 0)
                    assert any(r["path"] == "/api/historical/options" and r["status"] == 200
                               for r in responses)
                    assert any(r["path"] == "/api/audience/runs" and r["status"] == 200
                               for r in responses)
                    assert not capture.console_errors and not capture.page_errors
                    assert not capture.request_failures
                    report.update({
                        "status": "PASS_RETAINED_INSIGHTS_LINKS_AND_ROUTING_BOUNDARY",
                        "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "business_insights_hash_hidden": True,
                        "retained_destinations_clicked": ["historical-analysis", "audience-explorer"],
                        "audience_no_run_guard_visible": True,
                        "jobs_after_navigation": jobs, "scoring_runs_after_navigation": scores,
                        "api_responses": responses,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                    })
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_INSIGHTS_LINKS",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_retained_links.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_RETAINED_INSIGHTS_LINKS_AND_ROUTING_BOUNDARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
