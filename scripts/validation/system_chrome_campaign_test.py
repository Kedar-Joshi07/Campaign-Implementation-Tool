from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence" / "full_fresh_e2e"
SCREENSHOT_DIR = EVIDENCE_DIR / "screenshots"
EVIDENCE_PATH = EVIDENCE_DIR / "system_chrome_campaign_test.json"
SCREENSHOT_PATH = SCREENSHOT_DIR / "system_chrome_campaigns.png"

APP_URL = "http://127.0.0.1:8000/#campaigns"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


@dataclass
class ExportRow:
    event_id: str
    profile: str
    status: str
    selected: str
    deliverable: str
    undeliverable: str
    exported_rows: str
    checksum: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _wait_for(condition, timeout_seconds: float, poll_seconds: float = 0.25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll_seconds)
    return False


def _panel_visible(page: Page, panel_selector: str) -> bool:
    return page.evaluate(
        """
        (selector) => {
            const node = document.querySelector(selector);
            return !!node && !node.hidden;
        }
        """,
        panel_selector,
    )


def _get_top_export_row(page: Page) -> ExportRow | None:
    payload = page.evaluate(
        """
        () => {
            const row = document.querySelector('#campaign-export-history-body tr');
            if (!row || row.classList.contains('empty-row')) {
                return null;
            }
            const cells = row.querySelectorAll('td');
            if (cells.length < 10) {
                return null;
            }
            return {
                event_id: (cells[0].textContent || '').trim(),
                profile: (cells[2].textContent || '').trim(),
                status: (cells[3].textContent || '').trim(),
                selected: (cells[5].textContent || '').trim(),
                deliverable: (cells[6].textContent || '').trim(),
                undeliverable: (cells[7].textContent || '').trim(),
                exported_rows: (cells[8].textContent || '').trim(),
                checksum: (cells[9].textContent || '').trim(),
            };
        }
        """
    )
    if not payload:
        return None
    return ExportRow(**payload)


def _open_latest_finalized_campaign(page: Page) -> bool:
    return page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#campaign-recent-body tr'));
            for (const row of rows) {
                if (row.classList.contains('empty-row')) {
                    continue;
                }
                const statusText = (row.querySelector('td:nth-child(3)')?.textContent || '').trim().toUpperCase();
                if (statusText !== 'FINALIZED') {
                    continue;
                }
                const openButton = row.querySelector('button');
                if (!openButton) {
                    continue;
                }
                openButton.click();
                return true;
            }
            return false;
        }
        """
    )


def _ui_debug_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
            const panelVisible = (selector) => {
                const node = document.querySelector(selector);
                return !!node && !node.hidden;
            };
            const text = (selector) => (document.querySelector(selector)?.textContent || '').trim();
            return {
                hash: location.hash,
                shell_status: text('#campaign-shell-status'),
                status_announcement: text('#campaigns-status-announcement'),
                action_help: text('#campaign-action-disabled-help'),
                step_error_visible: !!document.querySelector('#campaign-step-error-summary') && !document.querySelector('#campaign-step-error-summary').hidden,
                step_error_text: text('#campaign-step-error-summary'),
                backend_error_visible: !!document.querySelector('#campaigns-error') && !document.querySelector('#campaigns-error').hidden,
                backend_error_text: text('#campaigns-error-message'),
                state_ready_visible: panelVisible('#campaigns-state-ready'),
                state_loading_visible: panelVisible('#campaigns-state-loading'),
                state_no_eligible_visible: panelVisible('#campaigns-state-no-eligible'),
                state_backend_unavailable_visible: panelVisible('#campaigns-state-backend-unavailable'),
                step1_visible: panelVisible('#campaign-step-panel-1'),
                step2_visible: panelVisible('#campaign-step-panel-2'),
                step3_visible: panelVisible('#campaign-step-panel-3'),
                step4_visible: panelVisible('#campaign-step-panel-4'),
                campaign_recent_rows: Array.from(document.querySelectorAll('#campaign-recent-body tr')).map((row) => {
                    if (row.classList.contains('empty-row')) {
                        return { empty: true, text: (row.textContent || '').trim() };
                    }
                    const cells = row.querySelectorAll('td');
                    return {
                        id: (cells[0]?.textContent || '').trim(),
                        name: (cells[1]?.textContent || '').trim(),
                        status: (cells[2]?.textContent || '').trim(),
                        channel: (cells[3]?.textContent || '').trim(),
                    };
                }),
            };
        }
        """
    )


def _ensure_step4(page: Page) -> None:
    if _panel_visible(page, "#campaign-step-panel-4"):
        return

    if _panel_visible(page, "#campaign-step-panel-3"):
        page.click("#campaign-step-next-3")
        if _wait_for(lambda: _panel_visible(page, "#campaign-step-panel-4"), timeout_seconds=30):
            return

    if _panel_visible(page, "#campaign-step-panel-2"):
        page.click("#campaign-step-next-2")
        _wait_for(lambda: _panel_visible(page, "#campaign-step-panel-3"), timeout_seconds=30)
        page.click("#campaign-step-next-3")
        if _wait_for(lambda: _panel_visible(page, "#campaign-step-panel-4"), timeout_seconds=30):
            return

    if _open_latest_finalized_campaign(page):
        if _wait_for(lambda: _panel_visible(page, "#campaign-step-panel-4"), timeout_seconds=45):
            return

    raise RuntimeError("Unable to navigate to campaign step 4 via workflow controls.")


def _ensure_campaigns_ready(page: Page) -> None:
    page.goto(APP_URL, wait_until="domcontentloaded")
    if not _wait_for(lambda: page.evaluate("() => location.hash === '#campaigns'"), timeout_seconds=20):
        raise RuntimeError("Campaign view did not load.")

    ready = _wait_for(
        lambda: page.evaluate(
            """
            () => {
                const ready = document.querySelector('#campaigns-state-ready');
                return !!ready && !ready.hidden;
            }
            """
        ),
        timeout_seconds=120,
    )
    if not ready:
        raise RuntimeError("Campaign workspace did not reach ready state.")


def _run_campaign_export_probe(context: BrowserContext, page: Page) -> dict[str, Any]:
    console_errors: list[str] = []
    request_failures: list[dict[str, str]] = []

    def on_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)

    def on_request_failed(req):
        request_failures.append(
            {
                "method": req.method,
                "url": req.url,
                "failure": (req.failure.error_text if req.failure else "unknown"),
            }
        )

    page.on("console", on_console)
    page.on("requestfailed", on_request_failed)

    try:
        _ensure_campaigns_ready(page)
        # Ensure we are operating on a finalized campaign context.
        shell_status_now = page.locator("#campaign-shell-status").inner_text().strip()
        if "FINALIZED" not in shell_status_now.upper():
            opened = _open_latest_finalized_campaign(page)
            if not opened:
                raise RuntimeError("No finalized campaign row available in Recent campaigns.")
            loaded = _wait_for(
                lambda: "FINALIZED" in page.locator("#campaign-shell-status").inner_text().strip().upper(),
                timeout_seconds=120,
            )
            if not loaded:
                raise RuntimeError("Opened campaign did not load finalized state in time.")

        _ensure_step4(page)

        shell_status = page.locator("#campaign-shell-status").inner_text().strip()
        if "FINALIZED" not in shell_status.upper():
            raise RuntimeError(f"Expected FINALIZED campaign in step 4, got: {shell_status}")

        ack = page.locator("#campaign-pii-ack")
        if not ack.is_checked():
            ack.check()

        export_button = page.locator("#campaign-export")
        if export_button.is_disabled():
            help_text = page.locator("#campaign-action-disabled-help").inner_text().strip()
            raise RuntimeError(f"Export button disabled: {help_text}")

        before_row = _get_top_export_row(page)
        before_event = before_row.event_id if before_row else None

        export_button.click()

        completed = _wait_for(
            lambda: (
                (row := _get_top_export_row(page)) is not None
                and (before_event is None or row.event_id != before_event)
                and row.status.upper() in {"COMPLETED", "FAILED", "ABORTED", "STARTED"}
            ),
            timeout_seconds=60,
        )
        if not completed:
            raise RuntimeError("No new export row observed after clicking export.")

        # Wait for terminal status for the newly created event.
        terminal = _wait_for(
            lambda: (
                (row := _get_top_export_row(page)) is not None
                and (before_event is None or row.event_id != before_event)
                and row.status.upper() in {"COMPLETED", "FAILED", "ABORTED"}
            ),
            timeout_seconds=600,
            poll_seconds=0.5,
        )
        if not terminal:
            raise RuntimeError("New export event did not reach terminal state in time.")

        after_row = _get_top_export_row(page)
        if after_row is None:
            raise RuntimeError("Unable to read latest export row.")

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)

        return {
            "status": "PASS",
            "shell_status": shell_status,
            "before_row": (before_row.__dict__ if before_row else None),
            "after_row": after_row.__dict__,
            "status_note": page.locator("#campaign-export-status-note").inner_text().strip(),
            "announcement": page.locator("#campaigns-status-announcement").inner_text().strip(),
            "action_help": page.locator("#campaign-action-disabled-help").inner_text().strip(),
            "console_errors": console_errors,
            "request_failures": request_failures,
            "debug": _ui_debug_snapshot(page),
            "screenshot": str(SCREENSHOT_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        }
    finally:
        page.remove_listener("console", on_console)
        page.remove_listener("requestfailed", on_request_failed)


def _launch_system_chrome(playwright) -> tuple[Browser, BrowserContext, Page]:
    if not CHROME_PATH.is_file():
        raise FileNotFoundError(f"Chrome executable not found: {CHROME_PATH}")

    browser = playwright.chromium.launch(
        executable_path=str(CHROME_PATH),
        headless=True,
        args=["--disable-popup-blocking"],
    )
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    return browser, context, page


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "app_url": APP_URL,
        "browser": {
            "name": "system_chrome",
            "executable_path": str(CHROME_PATH),
        },
    }

    with sync_playwright() as playwright:
        browser, context, page = _launch_system_chrome(playwright)
        try:
            result = _run_campaign_export_probe(context, page)
            payload["result"] = result
            payload["overall_status"] = "PASS"
        except Exception as exc:
            debug_snapshot: dict[str, Any] | None = None
            try:
                debug_snapshot = _ui_debug_snapshot(page)
            except Exception:
                debug_snapshot = None
            payload["result"] = {
                "status": "FAIL",
                "error": str(exc),
                "debug": debug_snapshot,
            }
            payload["overall_status"] = "FAIL"
        finally:
            context.close()
            browser.close()

    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote evidence: {EVIDENCE_PATH}")
    print(f"Status: {payload['overall_status']}")

    return 0 if payload["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
