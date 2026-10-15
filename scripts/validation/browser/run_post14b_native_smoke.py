"""Initial headed installed-Chrome business smoke on the real bounded QA app.

This is intentionally a partial diagnostic, not the 19.3 all-control certificate.
"""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path
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
    print(f"Native QA root: {root}", flush=True)
    process = None
    report: dict = {"scope": "BUSINESS_NATIVE_PARTIAL_SMOKE", "qa_root": str(root),
                    "headless": False, "status": "NOT_RUN"}
    try:
        process, port = start_qa_server(root)
        report["loopback_port"] = port
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(15_000)
                capture, listeners = attach_page_event_capture(page)
                requests = []

                def on_response(response):
                    parsed = urlsplit(response.url)
                    if parsed.path.startswith("/api/"):
                        requests.append({"method": response.request.method,
                                         "path": parsed.path, "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                    page.locator("#nav-home").wait_for(state="visible")
                    assert page.locator("#nav-home").get_attribute("aria-current") == "page"
                    save_screenshot(page, root / "screenshots" / "home.png")
                    page.locator("#sidebar-collapse").click()
                    assert page.locator("#sidebar-expand").is_visible()
                    page.locator("#sidebar-expand").click()
                    assert page.locator("#sidebar-collapse").is_visible()
                    page.locator("#sidebar-resize-handle").focus()
                    before_width = page.locator("#sidebar-resize-handle").get_attribute("aria-valuenow")
                    page.locator("#sidebar-resize-handle").press("ArrowRight")
                    after_width = page.locator("#sidebar-resize-handle").get_attribute("aria-valuenow")
                    assert int(after_width) >= int(before_width)
                    page.locator("#nav-find-potential-customers").click()
                    page.wait_for_url("**/#find-potential-customers")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=20_000)
                    assert page.locator("#business-product_ids-trigger").is_enabled()
                    save_screenshot(page, root / "screenshots" / "find.png")
                    page.locator("#nav-results").click()
                    page.wait_for_url("**/#results")
                    page.locator("#results-view").wait_for(state="visible")
                    save_screenshot(page, root / "screenshots" / "results.png")
                    report.update({
                        "status": "PASS_PARTIAL_SMOKE",
                        "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "viewport": {"width": 1366, "height": 768},
                        "sidebar_width_before": before_width,
                        "sidebar_width_after": after_width,
                        "api_responses": requests,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                    })
                    if capture.console_errors or capture.page_errors or capture.request_failures:
                        report["status"] = "FINDINGS_PARTIAL_SMOKE"
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_PARTIAL_SMOKE", "error_type": type(exc).__name__,
                       "error": str(exc)[:1000]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_smoke.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}, sort_keys=True),
              flush=True)
    return 0 if report["status"] == "PASS_PARTIAL_SMOKE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
