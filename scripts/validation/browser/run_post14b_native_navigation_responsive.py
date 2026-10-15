"""Headed-Chrome business navigation/sidebar and responsive functional slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, REPOSITORY_ROOT, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _compute_counts(database: Path) -> tuple[int, int, int]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("campaign_search_runs", "jobs", "buyer_similarity_score_generations"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_feedback_matrix.json").is_file():
        raise ValueError("Navigation requires the completed, owned feedback QA root.")
    for relative in ("frontend/index.html", "frontend/js/app.js", "frontend/js/sidebar.js",
                     "frontend/js/view-contract.js", "frontend/js/overview.js",
                     "frontend/js/business-search-status.js"):
        if relative in {"frontend/js/app.js", "frontend/js/view-contract.js"}:
            continue  # QA-only retained route seam is recorded in the manifest.
        assert hashlib.sha256((root / "source" / relative).read_bytes()).digest() == hashlib.sha256(
            (REPOSITORY_ROOT / relative).read_bytes()).digest(), relative
    report = {"scope": "BUSINESS_NATIVE_NAVIGATION_RESPONSIVE", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        before = _compute_counts(database)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "navigation_browser_profile",
                downloads_dir=root / "navigation_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#home", wait_until="domcontentloaded")
                    page.locator("#home-results-status").wait_for(state="visible", timeout=30_000)
                    page.wait_for_function(
                        "document.querySelector('#home-search-runs')?.textContent?.includes('1')",
                        timeout=30_000,
                    )
                    assert page.locator("#page-title").inner_text() == "Home"
                    assert page.locator("#nav-home").get_attribute("aria-current") == "page"
                    page.locator("#home-recent-results a, #home-recent-results button").first.wait_for(
                        state="visible", timeout=30_000)
                    report["cases"].append({"id": "HOME_COUNTS_RECENT_AND_NAV", "status": "PASS"})

                    page.locator("#home-find-potential-customers").click()
                    assert page.url.endswith("#find-potential-customers")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                    assert page.locator("#page-title").inner_text() == "Find Potential Customers"
                    assert page.locator("#nav-find-potential-customers").get_attribute("aria-current") == "page"
                    page.locator("#nav-results").click()
                    assert page.url.endswith("#results")
                    page.wait_for_function(
                        "document.querySelector('#nav-results')?.getAttribute('aria-current') === 'page'")
                    assert page.locator("#nav-results").get_attribute("aria-current") == "page"
                    page.locator("#business-history-refresh").click()
                    page.wait_for_function(
                        "document.querySelector('#business-search-history')?.textContent?.includes('Bounded feedback matrix')",
                        timeout=30_000,
                    )
                    page.go_back(wait_until="domcontentloaded")
                    assert page.url.endswith("#find-potential-customers")
                    page.go_forward(wait_until="domcontentloaded")
                    assert page.url.endswith("#results")
                    page.locator("#nav-results").click()  # Same route remains usable.
                    assert page.url.endswith("#results")
                    report["cases"].append({"id": "THREE_ROUTES_BACK_FORWARD_REPEAT", "status": "PASS"})

                    page.goto(base + "#overview", wait_until="domcontentloaded")
                    page.wait_for_url("**/#home", timeout=10_000)
                    assert page.url.endswith("#home")
                    page.goto(base + "#campaign-planner", wait_until="domcontentloaded")
                    page.wait_for_url("**/#find-potential-customers", timeout=10_000)
                    assert page.url.endswith("#find-potential-customers")
                    page.goto(base + "#model-training", wait_until="domcontentloaded")
                    page.wait_for_url("**/#home", timeout=10_000)
                    assert page.url.endswith("#home")
                    assert page.locator("#model-training-view").is_hidden()
                    page.goto(base + "#not-a-route", wait_until="domcontentloaded")
                    page.wait_for_url("**/#home", timeout=10_000)
                    assert page.url.endswith("#home")
                    report["cases"].append({"id": "ALIASES_AND_RETAINED_ROUTE_BOUNDARY", "status": "PASS"})

                    for width, height in ((1920, 1080), (1366, 768), (1024, 768),
                                          (768, 1024), (390, 844)):
                        page.set_viewport_size({"width": width, "height": height})
                        page.locator("#nav-results").click()
                        page.locator("#results-view").wait_for(state="visible")
                        page.locator("#nav-home").click()
                        page.locator("#overview-view").wait_for(state="visible")
                        page.locator("#sidebar-collapse").click()
                        assert page.locator("#primary-sidebar").get_attribute("aria-hidden") == "true"
                        assert page.locator("#sidebar-expand").is_visible()
                        assert page.locator("#sidebar-expand").get_attribute("aria-expanded") == "false"
                        page.locator("#sidebar-expand").click()
                        assert page.locator("#primary-sidebar").get_attribute("aria-hidden") == "false"
                        assert page.locator("#sidebar-expand").is_hidden()
                        handle = page.locator("#sidebar-resize-handle")
                        if width > 780:
                            assert handle.is_visible()
                            initial = int(handle.get_attribute("aria-valuenow"))
                            handle.focus()
                            handle.press("ArrowRight")
                            after_key = int(handle.get_attribute("aria-valuenow"))
                            assert after_key > initial
                            page.wait_for_function("""() => {
                              const handle = document.querySelector('#sidebar-resize-handle');
                              const shell = document.querySelector('.app-shell');
                              return Math.abs(handle.getBoundingClientRect().right
                                - shell.getBoundingClientRect().left
                                - Number(handle.getAttribute('aria-valuenow'))) < 3;
                            }""")
                            box = handle.bounding_box()
                            assert box is not None
                            page.mouse.move(box["x"] + box["width"] / 2,
                                            box["y"] + box["height"] / 2)
                            page.mouse.down()
                            during_down = page.evaluate("""() => ({
                              resizing: document.querySelector('.app-shell').classList.contains('sidebar-is-resizing'),
                              width: document.querySelector('#sidebar-resize-handle').getAttribute('aria-valuenow'),
                              element: document.elementFromPoint(
                                document.querySelector('#sidebar-resize-handle').getBoundingClientRect().x + 5,
                                document.querySelector('#sidebar-resize-handle').getBoundingClientRect().y + 20
                              )?.id,
                            })""")
                            page.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2,
                                            steps=5)
                            during_move = page.evaluate("""() => ({
                              resizing: document.querySelector('.app-shell').classList.contains('sidebar-is-resizing'),
                              width: document.querySelector('#sidebar-resize-handle').getAttribute('aria-valuenow')
                            })""")
                            page.mouse.up()
                            assert int(handle.get_attribute("aria-valuenow")) != after_key, (
                                width, box, during_down, during_move, after_key)
                            stored = page.evaluate("JSON.parse(localStorage.getItem('campaign-sidebar-layout-v1'))")
                            assert stored["width"] == int(handle.get_attribute("aria-valuenow"))
                        else:
                            assert handle.is_hidden()
                        page.reload(wait_until="domcontentloaded")
                        assert page.locator("#primary-sidebar").get_attribute("aria-hidden") == "false"
                        save_screenshot(page, root / "screenshots" / f"navigation_{width}x{height}.png")
                        report["cases"].append({"id": f"RESPONSIVE_{width}X{height}",
                                                "status": "PASS", "resize_handle_visible": width > 780})
                        print(f"Responsive navigation {width}x{height} passed", flush=True)
                    page.goto(base + "#results/999999", wait_until="domcontentloaded")
                    page.locator("#result-detail-error").wait_for(state="visible", timeout=30_000)
                    page.locator("#result-detail-retry").click()
                    page.locator("#result-detail-error").wait_for(state="visible", timeout=30_000)
                    page.locator("#result-detail-back").click()
                    assert page.url.endswith("#results")
                    report["cases"].append({"id": "INVALID_RESULT_ID_RETRY_BACK", "status": "PASS"})
                    assert _compute_counts(database) == before
                    assert not capture.page_errors
                    report.update({"status": "PASS_NAVIGATION_RESPONSIVE_SLICE",
                                   "browser": session.metadata.to_dict(),
                                   "database_counts_before_after": before,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_NAVIGATION_RESPONSIVE_SLICE",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_navigation_responsive.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_NAVIGATION_RESPONSIVE_SLICE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
