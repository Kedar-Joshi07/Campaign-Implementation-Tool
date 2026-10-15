"""Real Chrome 200% zoom, keyboard focus, and live-region bounded UI check."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_named_10k_qualification.json").is_file():
        raise ValueError("Zoom case requires the owned completed named-qualification QA root.")
    for relative in ("frontend/index.html", "frontend/js/sidebar.js", "frontend/js/business-search-form.js"):
        assert hashlib.sha256((root / "source" / relative).read_bytes()).digest() == hashlib.sha256(
            (REPOSITORY_ROOT / relative).read_bytes()).digest(), relative
    report = {"scope": "BUSINESS_NATIVE_ZOOM_ACCESSIBILITY", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        with sqlite3.connect(root / "state" / "qa.db") as connection:
            before = [connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("campaign_search_runs", "jobs", "buyer_similarity_score_generations")]
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "zoom_browser_profile", downloads_dir=root / "zoom_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#home", wait_until="domcontentloaded")
                    page.locator("#overview-view").wait_for(state="visible")
                    initial = page.evaluate("window.devicePixelRatio")
                    shortcuts = []
                    for candidate in ("Control+Equal", "Control+Shift+Equal"):
                        page.keyboard.press("Control+0")
                        for _ in range(5):
                            page.keyboard.press(candidate)
                        current = page.evaluate("window.devicePixelRatio")
                        shortcuts.append({"shortcut": candidate, "device_pixel_ratio": current})
                        if current >= initial * 1.95:
                            break
                    report["zoom_shortcuts_tested"] = shortcuts
                    zoom = page.evaluate("""() => ({dpr: window.devicePixelRatio,
                        css_width: window.innerWidth, document_width: document.documentElement.scrollWidth})""")
                    if zoom["dpr"] < initial * 1.95:
                        report["status"] = "BLOCKED_NATIVE_200_PERCENT_ZOOM_SHORTCUT"
                        report["zoom_observation"] = {"initial_dpr": initial, **zoom}
                        report["browser"] = session.metadata.to_dict()
                        return 2
                    assert zoom["css_width"] < 800
                    report["cases"].append({"id": "NATIVE_CHROME_200_PERCENT_ZOOM", "status": "PASS",
                                            "initial_dpr": initial, **zoom})
                    for route, visible in (("home", "#overview-view"),
                                           ("find-potential-customers", "#business-search-form"),
                                           ("results", "#results-view"),
                                           ("results/1", "#result-detail-view")):
                        page.goto(base + f"#{route}", wait_until="domcontentloaded")
                        page.locator(visible).wait_for(state="visible", timeout=60_000)
                        assert page.evaluate("window.devicePixelRatio") >= initial * 1.95
                        assert page.locator("#page-title").is_visible()
                        save_screenshot(page, root / "screenshots" /
                                        f"zoom_200_{route.replace('/', '_')}.png")
                        report["cases"].append({"id": f"ZOOM_VIEW_{route.upper().replace('/', '_')}",
                                                "status": "PASS"})
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=60_000)
                    trigger = page.locator("#business-product_ids-trigger")
                    trigger.focus()
                    assert page.evaluate("document.activeElement.id") == "business-product_ids-trigger"
                    trigger.press("Enter")
                    assert page.locator("#business-product_ids-panel").is_visible()
                    trigger.press("Escape")
                    assert page.locator("#business-product_ids-panel").is_hidden()
                    assert page.evaluate("document.activeElement.id") == "business-product_ids-trigger"
                    report["cases"].append({"id": "ZOOM_KEYBOARD_MENU_AND_FOCUS_RESTORE",
                                            "status": "PASS"})
                    status = page.locator("#business-search-preflight-result")
                    assert status.get_attribute("role") == "status"
                    assert status.get_attribute("aria-live") == "polite"
                    report["cases"].append({"id": "PREFLIGHT_LIVE_REGION", "status": "PASS"})
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_NATIVE_200_PERCENT_ZOOM_SLICE",
                                   "browser": session.metadata.to_dict(),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
        with sqlite3.connect(root / "state" / "qa.db") as connection:
            after = [connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("campaign_search_runs", "jobs", "buyer_similarity_score_generations")]
        assert after == before
        report["database_counts_before_after"] = before
    except Exception as exc:
        report.update({"status": "FAIL_NATIVE_200_PERCENT_ZOOM_SLICE",
                       "error_type": type(exc).__name__, "error": str(exc)[:1500],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_zoom_accessibility.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_NATIVE_200_PERCENT_ZOOM_SLICE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
