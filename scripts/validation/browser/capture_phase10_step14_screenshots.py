#!/usr/bin/env python3
"""Capture responsive Phase 10 evidence in the installed system Chrome."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright

from app.services.campaign_targeting_context_service import (
    get_business_targeting_criteria,
    get_campaign_targeting_context,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture,
    detach_page_event_capture,
    launch_system_browser_session,
    save_screenshot,
)


VIEWPORTS = (
    (1920, 1080),
    (1366, 768),
    (1024, 768),
    (768, 1024),
    (390, 844),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--context-id", type=int, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8014/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    context = get_campaign_targeting_context(
        args.database, targeting_context_id=args.context_id
    )["context"]
    criteria = get_business_targeting_criteria(
        args.database, targeting_context_id=args.context_id
    )["criteria"]
    state = {
        "contractVersion": "1",
        "currentStep": 4,
        "furthestStep": 4,
        "completedSteps": [1, 2, 3],
        "campaignDetails": {
            "campaignName": "Step 14 Responsive Certification",
            "description": "Installed Chrome responsive evidence.",
            "plannedLaunchDate": "",
        },
        "targetingContextId": args.context_id,
        "campaignContext": context,
        "targetingCriteria": criteria,
        "savedAt": None,
    }
    init_script = (
        "window.sessionStorage.setItem('phase9-campaign-planner-draft-v1', "
        f"{json.dumps(json.dumps(state))});"
    )
    args.output.mkdir(parents=True, exist_ok=True)
    screenshots: list[dict[str, object]] = []
    http_errors: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        with launch_system_browser_session(
            playwright,
            system_browser="chrome",
            headless=True,
            viewport={"width": 1920, "height": 1080},
        ) as session:
            session.context.add_init_script(script=init_script)
            capture, listeners = attach_page_event_capture(session.page)

            def on_response(response) -> None:
                if response.status >= 400:
                    http_errors.append(
                        {"status": response.status, "method": response.request.method, "url": response.url}
                    )

            session.page.on("response", on_response)
            try:
                for width, height in VIEWPORTS:
                    session.page.set_viewport_size({"width": width, "height": height})
                    session.page.goto(f"{args.url}#campaign-planner", wait_until="domcontentloaded")
                    session.page.locator("#planner-target-preview:not([hidden])").wait_for(
                        state="visible", timeout=30_000
                    )
                    session.page.wait_for_timeout(500)
                    overflow = session.page.evaluate(
                        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                    )
                    path = args.output / f"phase10-ready-{width}x{height}.png"
                    save_screenshot(session.page, path, full_page=False)
                    screenshots.append(
                        {
                            "viewport": {"width": width, "height": height},
                            "path": path.as_posix(),
                            "horizontal_overflow": bool(overflow),
                        }
                    )
            finally:
                session.page.remove_listener("response", on_response)
                detach_page_event_capture(session.page, listeners)
            result = {
                "browser": session.metadata.to_dict(),
                "screenshots": screenshots,
                "telemetry": {
                    "console_errors": capture.console_errors,
                    "page_errors": capture.page_errors,
                    "request_failures": capture.request_failures,
                    "http_errors": http_errors,
                },
            }

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
