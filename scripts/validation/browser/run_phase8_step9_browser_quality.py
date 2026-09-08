from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Page, Playwright, Route, sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
for candidate in (CURRENT_DIR, PROJECT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.database.schema import initialize_database
from system_browser import launch_system_browser_session

PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
DATABASE_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"
APP_URL = "http://127.0.0.1:8000/"
API_HEALTH_URL = "http://127.0.0.1:8000/api/health"

STEP6_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "06_system_browser_training_and_5m_scoring.json"
JSON_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "09_browser_quality_evidence.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "09_BROWSER_QUALITY_REPORT.md"
INVENTORY_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "ui_control_inventory.json"

SCENARIO_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP9_SCENARIO_TIMEOUT_SECONDS", "240"))

VIEWPORTS: list[dict[str, Any]] = [
    {"name": "1920x1080", "width": 1920, "height": 1080},
    {"name": "1366x768", "width": 1366, "height": 768},
    {"name": "1024x768", "width": 1024, "height": 768},
    {"name": "768x1024", "width": 768, "height": 1024},
    {"name": "390x844", "width": 390, "height": 844},
]

VIEW_TARGETS = [
    "overview",
    "data-status",
    "historical-analysis",
    "model-training",
    "audience-explorer",
    "campaigns",
]

CRITICAL_CONTROL_BY_VIEW = {
    "overview": "#overview-refresh",
    "data-status": "#data-status-refresh",
    "historical-analysis": "#historical-analysis-refresh",
    "model-training": "#model-training-refresh",
    "audience-explorer": "#audience-explorer-refresh",
    "campaigns": "#campaigns-refresh",
}


class Step9ValidationError(RuntimeError):
    """Raised when Step 9 validation cannot produce a reliable outcome."""


@dataclass
class RunArtifacts:
    payload: dict[str, Any]


class EventCollector:
    def __init__(self, page: Page, scenario_ref: dict[str, str]):
        self._page = page
        self._scenario_ref = scenario_ref
        self.console_errors: list[dict[str, Any]] = []
        self.page_errors: list[dict[str, Any]] = []
        self.request_failures: list[dict[str, Any]] = []
        self.http_errors: list[dict[str, Any]] = []
        self._listeners: dict[str, Any] = {}

    def _scenario(self) -> str:
        return str(self._scenario_ref.get("name") or "unknown")

    def attach(self) -> None:
        def on_console(message: Any) -> None:
            try:
                if message.type == "error":
                    self.console_errors.append({"scenario": self._scenario(), "text": str(message.text)})
            except Exception:
                self.console_errors.append({"scenario": self._scenario(), "text": str(message)})

        def on_page_error(error: Any) -> None:
            self.page_errors.append({"scenario": self._scenario(), "text": str(error)})

        def on_request_failed(request: Any) -> None:
            failure = getattr(request, "failure", None)
            error_text = "unknown"
            if failure is not None:
                error_text = getattr(failure, "error_text", None) or str(failure)
            self.request_failures.append(
                {
                    "scenario": self._scenario(),
                    "method": str(getattr(request, "method", "")),
                    "url": str(getattr(request, "url", "")),
                    "failure": str(error_text),
                }
            )

        def on_response(response: Any) -> None:
            try:
                status = int(getattr(response, "status", 0) or 0)
            except Exception:
                status = 0
            if status < 400:
                return
            request = getattr(response, "request", None)
            method = str(getattr(request, "method", "")) if request is not None else ""
            url = str(getattr(response, "url", ""))
            self.http_errors.append(
                {
                    "scenario": self._scenario(),
                    "method": method,
                    "url": url,
                    "status": status,
                }
            )

        self._listeners = {
            "console": on_console,
            "pageerror": on_page_error,
            "requestfailed": on_request_failed,
            "response": on_response,
        }
        for event_name, callback in self._listeners.items():
            self._page.on(event_name, callback)

    def detach(self) -> None:
        for event_name, callback in self._listeners.items():
            self._page.remove_listener(event_name, callback)
        self._listeners = {}


def _progress(message: str) -> None:
    print(f"[step9] {message}", flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _wait_for(condition, timeout_seconds: float, poll_seconds: float = 0.25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll_seconds)
    return False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Step9ValidationError(message)


def _exists(page: Page, selector: str) -> bool:
    return page.locator(selector).count() > 0


def _visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    return locator.count() > 0 and locator.first.is_visible()


def _enabled(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    return locator.count() > 0 and locator.first.is_enabled()


def _read_text(page: Page, selector: str) -> str:
    locator = page.locator(selector)
    if locator.count() == 0:
        return ""
    return locator.first.inner_text().strip()


def _goto_with_retry(page: Page, url: str, *, attempts: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(0.5 * attempt)
    raise Step9ValidationError(f"Navigation failed for {url}: {last_error}")


def _active_hash(page: Page) -> str:
    return str(page.evaluate("() => location.hash") or "")


def _click_nav(page: Page, target: str) -> None:
    page.click(f"[data-view-target='{target}']")
    ok = _wait_for(lambda: _active_hash(page) == f"#{target}", timeout_seconds=20)
    _require(ok, f"Unable to switch to view #{target}.")


def _wait_view_loaded(page: Page, target: str) -> None:
    selector = f"#{target}-view"
    ok = _wait_for(
        lambda: _exists(page, selector) and page.evaluate("(sel) => !document.querySelector(sel)?.hidden", selector),
        timeout_seconds=SCENARIO_TIMEOUT_SECONDS,
        poll_seconds=0.25,
    )
    _require(ok, f"View did not become visible in time: {target}")


def _server_healthy() -> bool:
    try:
        with urlopen(API_HEALTH_URL, timeout=3) as response:
            return 200 <= response.status < 300
    except (URLError, TimeoutError, ConnectionError):
        return False


@contextmanager
def _managed_server() -> Iterator[dict[str, Any]]:
    if _server_healthy():
        yield {"managed": False, "started_by_script": False}
        return

    command = [
        str(PYTHON_EXE),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready = _wait_for(_server_healthy, timeout_seconds=120, poll_seconds=0.5)
        _require(ready, "Local API server did not become healthy within 120 seconds.")
        yield {"managed": True, "started_by_script": True, "command": " ".join(command)}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _read_json_url(url: str, timeout_seconds: int = 60) -> dict[str, Any] | list[Any]:
    with urlopen(url, timeout=timeout_seconds) as response:
        _require(200 <= response.status < 300, f"Expected HTTP 2xx for {url}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _wait_for_campaign_ready(page: Page) -> str:
    _wait_view_loaded(page, "campaigns")

    def terminal_state_visible() -> bool:
        return (
            _visible(page, "#campaigns-state-ready")
            or _visible(page, "#campaigns-state-no-eligible")
            or _visible(page, "#campaigns-state-backend-unavailable")
        )

    ready = _wait_for(terminal_state_visible, timeout_seconds=SCENARIO_TIMEOUT_SECONDS, poll_seconds=0.25)
    if not ready and _wait_for(lambda: _enabled(page, "#campaigns-refresh"), timeout_seconds=10, poll_seconds=0.25):
        page.click("#campaigns-refresh")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(45, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)
    if not ready:
        page.reload(wait_until="domcontentloaded")
        _click_nav(page, "campaigns")
        _wait_view_loaded(page, "campaigns")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(60, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)

    _require(ready, "Campaign view did not settle into a terminal state.")
    if _visible(page, "#campaigns-state-ready"):
        return "ready"
    if _visible(page, "#campaigns-state-no-eligible"):
        return "no_eligible"
    return "backend_unavailable"


def _wait_for_audience_ready(page: Page) -> str:
    _wait_view_loaded(page, "audience-explorer")

    def terminal_state_visible() -> bool:
        return (
            _visible(page, "#audience-explorer-workspace")
            or _visible(page, "#audience-explorer-no-run")
            or _visible(page, "#audience-explorer-prep-needed")
            or _visible(page, "#audience-explorer-prep-running")
            or _visible(page, "#audience-explorer-prep-failed")
        )

    ready = _wait_for(terminal_state_visible, timeout_seconds=SCENARIO_TIMEOUT_SECONDS, poll_seconds=0.25)
    if not ready and _wait_for(lambda: _enabled(page, "#audience-explorer-refresh"), timeout_seconds=10, poll_seconds=0.25):
        page.click("#audience-explorer-refresh")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(45, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)
    if not ready:
        page.reload(wait_until="domcontentloaded")
        _click_nav(page, "audience-explorer")
        _wait_view_loaded(page, "audience-explorer")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(60, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)

    _require(ready, "Audience Explorer did not settle into a terminal state.")
    if _visible(page, "#audience-explorer-workspace"):
        return "workspace"
    if _visible(page, "#audience-explorer-prep-needed"):
        return "prep_needed"
    if _visible(page, "#audience-explorer-prep-running"):
        return "prep_running"
    if _visible(page, "#audience-explorer-prep-failed"):
        return "prep_failed"
    return "no_run"


def _wait_for_model_training_ready(page: Page) -> str:
    _wait_view_loaded(page, "model-training")

    def terminal_state_visible() -> bool:
        return (
            _visible(page, "#model-training-workspace")
            or _visible(page, "#model-training-empty")
            or _visible(page, "#model-training-error")
        )

    ready = _wait_for(terminal_state_visible, timeout_seconds=SCENARIO_TIMEOUT_SECONDS, poll_seconds=0.25)
    if not ready and _wait_for(lambda: _enabled(page, "#model-training-refresh"), timeout_seconds=10, poll_seconds=0.25):
        page.click("#model-training-refresh")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(45, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)
    if not ready:
        page.reload(wait_until="domcontentloaded")
        _click_nav(page, "model-training")
        _wait_view_loaded(page, "model-training")
        ready = _wait_for(terminal_state_visible, timeout_seconds=min(60, SCENARIO_TIMEOUT_SECONDS), poll_seconds=0.25)

    _require(ready, "Model training view did not settle into a terminal state.")
    if _visible(page, "#model-training-workspace"):
        return "workspace"
    if _visible(page, "#model-training-empty"):
        return "empty"
    return "error"


def _with_injected_route_once(page: Page, pattern: str, resolver) -> tuple[str, Any]:
    state = {"used": False}

    def handler(route: Route, request: Any) -> None:
        if state["used"]:
            route.continue_()
            return
        state["used"] = True
        resolver(route, request)

    page.route(pattern, handler)
    return pattern, handler


def _with_injected_route(page: Page, pattern: str, resolver) -> tuple[str, Any]:
    def handler(route: Route, request: Any) -> None:
        resolver(route, request)

    page.route(pattern, handler)
    return pattern, handler


def _remove_route(page: Page, route_info: tuple[str, Any] | None) -> None:
    if route_info is None:
        return
    pattern, handler = route_info
    try:
        page.unroute(pattern, handler)
    except Exception:
        pass


def _exercise_state_coverage(page: Page, scenario_ref: dict[str, str]) -> dict[str, Any]:
    results: dict[str, Any] = {}

    synthetic_empty_options_payload = {
        "supported_channels": ["EMAIL", "DIRECT_MAIL"],
        "profiles_by_channel": {
            "EMAIL": "EMAIL_CONTACT_V1",
            "DIRECT_MAIL": "DIRECT_MAIL_CONTACT_V1",
        },
        "eligible_saved_audiences": [],
    }

    _click_nav(page, "campaigns")
    state = _wait_for_campaign_ready(page)
    results["campaign_initial_state"] = state

    # Stale/historical read-only state from real Audience Explorer data, with a
    # deterministic response-only injection when the current database has no stale row.
    scenario_ref["name"] = "state_stale_read_only_audience"
    _click_nav(page, "audience-explorer")
    audience_state = _wait_for_audience_ready(page)
    results["audience_terminal_state"] = audience_state

    stale_opened = page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#saved-audience-list .saved-audience-item'));
            for (const row of rows) {
                const badge = (row.querySelector('.status-badge')?.textContent || '').toUpperCase();
                if (!badge.includes('STALE')) continue;
                const title = (row.querySelector('.saved-audience-item-heading strong')?.textContent || '').trim();
                const button = row.querySelector('button.recent-reopen');
                if (button instanceof HTMLButtonElement) {
                    button.click();
                    return { ok: true, title };
                }
            }
            return { ok: false, title: '' };
        }
        """
    )
    stale_ok = bool((stale_opened or {}).get("ok"))
    stale_source = "database"
    stale_routes: list[tuple[str, Any]] = []
    if not stale_ok:
        stale_source = "injected_response"
        scenario_ref["name"] = "injected_stale_read_only_audience"
        synthetic_stale_id = 999901
        synthetic_stale_summary = {
            "audience_id": synthetic_stale_id,
            "audience_name": "Synthetic stale audience",
            "is_current": False,
            "selection_mode": "TOP_N",
            "target_count": 50,
            "resolved_count": 50,
            "created_at": _now_iso(),
        }
        synthetic_stale_detail = {
            "audience_id": synthetic_stale_id,
            "audience_name": "Synthetic stale audience",
            "created_at": _now_iso(),
            "definition": {
                "selection_mode": "TOP_N",
                "target_count": 50,
                "resolved_count": 50,
            },
            "currentness": {
                "is_current": False,
                "issues": ["Synthetic source/model lineage is stale for Step 9 state coverage."],
            },
        }
        stale_routes.append(
            _with_injected_route_once(
                page,
                "**/api/audiences?limit=20&offset=0",
                lambda route, _request: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps([synthetic_stale_summary]),
                ),
            )
        )
        stale_routes.append(
            _with_injected_route_once(
                page,
                f"**/api/audiences/{synthetic_stale_id}",
                lambda route, _request: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(synthetic_stale_detail),
                ),
            )
        )
        page.click("#saved-audiences-refresh")
        injected_row_ready = _wait_for(
            lambda: "Synthetic stale audience" in _read_text(page, "#saved-audience-list"),
            timeout_seconds=20,
            poll_seconds=0.25,
        )
        _require(injected_row_ready, "Injected stale audience row did not render.")
        stale_opened = page.evaluate(
            """
            () => {
                const row = document.querySelector('#saved-audience-list .saved-audience-item');
                const button = row?.querySelector('button.recent-reopen');
                if (!(button instanceof HTMLButtonElement)) return { ok: false, title: '' };
                const title = (row.querySelector('.saved-audience-item-heading strong')?.textContent || '').trim();
                button.click();
                return { ok: true, title };
            }
            """
        )
        stale_ok = bool((stale_opened or {}).get("ok"))

    stale_result: dict[str, Any] = {"stale_candidate_found": stale_ok, "source": stale_source}
    if stale_ok:
        stale_title = str((stale_opened or {}).get("title") or "")
        detail_loaded = _wait_for(
            lambda: _read_text(page, "#saved-audience-detail-title") == stale_title,
            timeout_seconds=30,
            poll_seconds=0.25,
        )
        _require(detail_loaded, "Stale saved audience detail did not load.")
        stale_message_seen = _wait_for(lambda: _visible(page, "#saved-audience-stale-message"), timeout_seconds=20)
        use_in_campaign_disabled = page.locator("#saved-audience-use-campaign").first.is_disabled()
        stale_result.update(
            {
                "stale_message_seen": bool(stale_message_seen),
                "use_in_campaign_disabled": bool(use_in_campaign_disabled),
                "stale_message": _read_text(page, "#saved-audience-stale-message"),
            }
        )
    for stale_route in stale_routes:
        _remove_route(page, stale_route)
    results["stale_read_only_state"] = stale_result

    # Long-running, completed, failed, aborted export states on Campaigns.
    scenario_ref["name"] = "state_export_variants_campaigns"
    _click_nav(page, "campaigns")
    _wait_for_campaign_ready(page)

    opened_campaign = page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#campaign-recent-body tr'));
            for (const row of rows) {
                if (row.classList.contains('empty-row')) continue;
                const statusText = (row.querySelector('td:nth-child(3)')?.textContent || '').toUpperCase();
                const idText = (row.querySelector('td:nth-child(1)')?.textContent || '');
                const match = idText.match(/\\d+/);
                const campaignId = match ? Number.parseInt(match[0], 10) : 0;
                const openButton = row.querySelector('button');
                if (!(openButton instanceof HTMLButtonElement)) continue;
                if (statusText.includes('FINALIZED')) {
                    openButton.click();
                    return { ok: true, campaignId, statusText };
                }
            }
            return { ok: false, campaignId: 0, statusText: '' };
        }
        """
    )
    _require(bool((opened_campaign or {}).get("ok")), "No finalized campaign row was available for export state checks.")

    campaign_id = int((opened_campaign or {}).get("campaignId") or 0)
    _require(campaign_id > 0, "Unable to parse campaign id for export state checks.")

    _wait_for(
        lambda: f"(#{campaign_id})" in _read_text(page, "#campaign-detail-summary")
        or _read_text(page, "#campaign-shell-status").upper().startswith("FINALIZED"),
        timeout_seconds=30,
        poll_seconds=0.25,
    )

    if not _visible(page, "#campaign-step-panel-4"):
        page.click("#campaign-step-4")
    _wait_for(lambda: _visible(page, "#campaign-step-panel-4"), timeout_seconds=20)

    started_event = {
        "export_event_id": 999001,
        "campaign_id": campaign_id,
        "export_contract_version": "1",
        "export_snapshot_contract_version": "1",
        "export_profile": "EMAIL_CONTACT_V1",
        "status": "STARTED",
        "selected_count": 50000,
        "deliverable_count": 0,
        "undeliverable_count": 0,
        "row_count": 0,
        "csv_sha256": None,
        "start_provenance_sha256": "synthetic",
        "source_changed_during_export": False,
        "completion_currentness_state": "CURRENT",
        "started_at": _now_iso(),
        "completed_at": None,
        "safe_error_message": None,
    }

    started_route = _with_injected_route(
        page,
        "**/api/campaigns/*/exports?limit=50",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([started_event]),
        ),
    )
    page.click("#campaign-export-history-refresh")
    started_seen = _wait_for(
        lambda: "Still running" in _read_text(page, "#campaign-export-status-note"),
        timeout_seconds=20,
        poll_seconds=0.25,
    )
    _remove_route(page, started_route)

    failed_aborted_route = _with_injected_route(
        page,
        "**/api/campaigns/*/exports?limit=50",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        **started_event,
                        "export_event_id": 999002,
                        "status": "FAILED",
                        "completed_at": _now_iso(),
                        "safe_error_message": "Synthetic failed state",
                    },
                    {
                        **started_event,
                        "export_event_id": 999003,
                        "status": "ABORTED",
                        "completed_at": _now_iso(),
                        "safe_error_message": "Synthetic aborted state",
                    },
                ]
            ),
        ),
    )
    page.click("#campaign-export-history-refresh")
    failed_or_aborted_seen = _wait_for(
        lambda: "FAILED" in _read_text(page, "#campaign-export-history-body")
        and "ABORTED" in _read_text(page, "#campaign-export-history-body"),
        timeout_seconds=20,
        poll_seconds=0.25,
    )
    _remove_route(page, failed_aborted_route)

    # Restore real completed state.
    page.click("#campaign-export-history-refresh")
    completed_seen = _wait_for(
        lambda: "COMPLETED" in _read_text(page, "#campaign-export-history-body"),
        timeout_seconds=30,
        poll_seconds=0.25,
    )

    results["export_state_coverage"] = {
        "started_seen": bool(started_seen),
        "failed_and_aborted_seen": bool(failed_or_aborted_seen),
        "completed_seen": bool(completed_seen),
    }

    # Loading state via deterministic injected responses.
    scenario_ref["name"] = "injected_loading_campaigns"
    _click_nav(page, "campaigns")
    _wait_for_campaign_ready(page)

    loading_options_route = _with_injected_route_once(
        page,
        "**/api/campaigns/options",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(synthetic_empty_options_payload),
        ),
    )
    loading_campaigns_route = _with_injected_route_once(
        page,
        "**/api/campaigns?limit=20&offset=0",
        lambda route, _request: route.fulfill(status=200, content_type="application/json", body="[]"),
    )
    loading_seen = bool(
        page.evaluate(
            """
            () => {
                document.querySelector('#campaigns-refresh')?.click();
                const loading = document.querySelector('#campaigns-state-loading');
                return Boolean(loading && !loading.hidden);
            }
            """
        )
    )
    loading_terminal_state = _wait_for_campaign_ready(page)
    _remove_route(page, loading_options_route)
    _remove_route(page, loading_campaigns_route)
    results["loading_state"] = {
        "campaigns_loading_seen": bool(loading_seen),
        "state_after_loading": loading_terminal_state,
    }

    # Retryable backend error with deterministic retry recovery.
    scenario_ref["name"] = "injected_retryable_error_campaigns"
    retry_route = _with_injected_route_once(
        page,
        "**/api/campaigns/options",
        lambda route, _request: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "Injected Step 9 retryable error"}),
        ),
    )
    page.click("#campaigns-refresh")
    retry_error_seen = _wait_for(
        lambda: _visible(page, "#campaigns-state-backend-unavailable") and _visible(page, "#campaigns-retry"),
        timeout_seconds=20,
        poll_seconds=0.25,
    )
    _remove_route(page, retry_route)
    _require(retry_error_seen, "Injected retryable Campaigns error state did not appear.")

    retry_recover_options_route = _with_injected_route_once(
        page,
        "**/api/campaigns/options",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(synthetic_empty_options_payload),
        ),
    )
    retry_recover_campaigns_route = _with_injected_route_once(
        page,
        "**/api/campaigns?limit=20&offset=0",
        lambda route, _request: route.fulfill(status=200, content_type="application/json", body="[]"),
    )
    page.click("#campaigns-retry")
    state_after_retry = _wait_for_campaign_ready(page)
    _remove_route(page, retry_recover_options_route)
    _remove_route(page, retry_recover_campaigns_route)
    results["retryable_error_state"] = {
        "campaigns_backend_unavailable_seen": bool(retry_error_seen),
        "state_after_retry": state_after_retry,
    }

    # Empty/no-eligible state.
    scenario_ref["name"] = "injected_empty_campaigns"
    options_route = _with_injected_route_once(
        page,
        "**/api/campaigns/options",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(synthetic_empty_options_payload),
        ),
    )
    campaigns_route = _with_injected_route_once(
        page,
        "**/api/campaigns?limit=20&offset=0",
        lambda route, _request: route.fulfill(status=200, content_type="application/json", body="[]"),
    )
    page.click("#campaigns-refresh")
    no_eligible_seen = _wait_for(lambda: _visible(page, "#campaigns-state-no-eligible"), timeout_seconds=20, poll_seconds=0.25)
    _remove_route(page, options_route)
    _remove_route(page, campaigns_route)
    _require(no_eligible_seen, "Injected Campaigns empty/no-eligible state did not appear.")
    results["empty_state"] = {
        "campaigns_no_eligible_seen": bool(no_eligible_seen),
        "state_after_empty": "no_eligible",
    }

    # Long-running + failed job states via injected model-training options.
    scenario_ref["name"] = "injected_model_training_job_states"
    _click_nav(page, "model-training")
    _wait_for_model_training_ready(page)

    model_options = _read_json_url(f"{APP_URL}api/models/training-options")
    _require(isinstance(model_options, dict), "Model training options payload was not a JSON object.")

    injected_running = dict(model_options)
    injected_running["active_job"] = {
        "job_id": 888001,
        "job_type": "MODEL_TRAINING",
        "status": "RUNNING",
        "stage": "TRAINING",
        "message": "Synthetic RUNNING job for Step 9 state coverage.",
        "analysis_run_id": 1,
        "model_run_id": None,
        "created_at": _now_iso(),
        "started_at": _now_iso(),
        "finished_at": None,
        "progress_percent": 37,
        "failure_message": None,
        "result": None,
    }

    running_route = _with_injected_route_once(
        page,
        "**/api/models/training-options",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(injected_running),
        ),
    )
    page.click("#model-training-refresh")
    running_seen = _wait_for(
        lambda: _visible(page, "#model-job-content") and "RUNNING" in _read_text(page, "#model-job-status").upper(),
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _remove_route(page, running_route)

    injected_failed = dict(model_options)
    injected_failed["active_job"] = {
        "job_id": 888002,
        "job_type": "MODEL_TRAINING",
        "status": "FAILED",
        "stage": "FAILED",
        "message": "Synthetic FAILED job for Step 9 state coverage.",
        "analysis_run_id": 1,
        "model_run_id": None,
        "created_at": _now_iso(),
        "started_at": _now_iso(),
        "finished_at": _now_iso(),
        "progress_percent": 100,
        "failure_message": "Synthetic failure for retry UX validation.",
        "result": None,
    }

    failed_route = _with_injected_route_once(
        page,
        "**/api/models/training-options",
        lambda route, _request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(injected_failed),
        ),
    )
    page.click("#model-training-refresh")
    failed_seen = _wait_for(
        lambda: _visible(page, "#model-job-content") and _visible(page, "#model-job-failure"),
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _remove_route(page, failed_route)

    # Return to real workspace.
    page.click("#model-training-refresh")
    restored_state = _wait_for_model_training_ready(page)

    results["job_state_coverage"] = {
        "running_seen": bool(running_seen),
        "failed_seen": bool(failed_seen),
        "restored_state": restored_state,
    }

    scenario_ref["name"] = "baseline"
    return results


def _focus_indicator_visible(page: Page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const element = document.activeElement;
                if (!(element instanceof HTMLElement)) return false;
                const style = getComputedStyle(element);
                const outlineWidth = Number.parseFloat(style.outlineWidth || '0');
                const hasOutline = Number.isFinite(outlineWidth) && outlineWidth > 0 && style.outlineStyle !== 'none';
                const hasShadow = style.boxShadow && style.boxShadow !== 'none';
                const focusVisible = element.matches(':focus-visible');
                return Boolean(hasOutline || hasShadow || focusVisible);
            }
            """
        )
    )


def _run_accessibility_smoke(page: Page) -> dict[str, Any]:
    results: dict[str, Any] = {}

    _click_nav(page, "overview")
    _wait_view_loaded(page, "overview")

    page.focus("[data-view-target='overview']")
    page.keyboard.press("Tab")
    focused_after_tab = str(
        page.evaluate(
            """
            () => {
                const el = document.activeElement;
                if (!el) return '';
                return el.id || el.getAttribute('data-view-target') || el.tagName;
            }
            """
        )
        or ""
    )
    focus_visible = _focus_indicator_visible(page)

    page.keyboard.press("Shift+Tab")
    focused_after_shift_tab = str(
        page.evaluate(
            """
            () => {
                const el = document.activeElement;
                if (!el) return '';
                return el.id || el.getAttribute('data-view-target') || el.tagName;
            }
            """
        )
        or ""
    )

    results["visible_focus"] = {
        "focus_visible": bool(focus_visible),
        "focused_after_tab": focused_after_tab,
    }
    results["tab_shift_tab_traversal"] = {
        "tab_target": focused_after_tab,
        "shift_tab_target": focused_after_shift_tab,
        "changed": focused_after_tab != focused_after_shift_tab,
    }

    # Enter/Space activation via keyboard.
    page.focus("[data-view-target='data-status']")
    page.keyboard.press("Enter")
    enter_activated = _wait_for(lambda: _active_hash(page) == "#data-status", timeout_seconds=10)

    page.focus("[data-view-target='overview']")
    page.keyboard.press(" ")
    space_activated = _wait_for(lambda: _active_hash(page) == "#overview", timeout_seconds=10)

    results["enter_space_activation"] = {
        "enter_activated": bool(enter_activated),
        "space_activated": bool(space_activated),
    }

    # Labels for visible form controls.
    missing_labels = page.evaluate(
        """
        () => {
            const activeView = document.querySelector('[data-view]:not([hidden])') || document;
            const controls = Array.from(activeView.querySelectorAll('input, select, textarea'));
            const missing = [];
            for (const control of controls) {
                if (!(control instanceof HTMLElement)) continue;
                const rect = control.getBoundingClientRect();
                const style = getComputedStyle(control);
                const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                if (!visible) continue;
                const id = control.id || '';
                const hasAriaLabel = Boolean(control.getAttribute('aria-label'));
                const hasAriaLabelledBy = Boolean(control.getAttribute('aria-labelledby'));
                let hasForLabel = false;
                if (id) {
                    hasForLabel = Boolean(document.querySelector(`label[for="${id}"]`));
                }
                const wrappedByLabel = Boolean(control.closest('label'));
                if (!(hasAriaLabel || hasAriaLabelledBy || hasForLabel || wrappedByLabel)) {
                    missing.push(id || control.tagName.toLowerCase());
                }
            }
            return missing;
        }
        """
    )
    results["labels_for_controls"] = {
        "missing": list(missing_labels or []),
        "missing_count": len(list(missing_labels or [])),
    }

    # Validation focus/error summary + disabled-action explanation + stepper semantics.
    _click_nav(page, "campaigns")
    campaign_state = _wait_for_campaign_ready(page)
    results["campaign_state_for_accessibility"] = campaign_state

    validation_result: dict[str, Any] = {
        "error_visible": False,
        "error_focused": False,
        "error_text": "",
        "skipped": False,
    }

    try:
        page.click("#campaign-new-draft")
        new_form_ready = _wait_for(
            lambda: (
                "new campaign draft form ready" in _read_text(page, "#campaigns-status-announcement").lower()
                and _visible(page, "#campaign-step-panel-1")
            ),
            timeout_seconds=20,
            poll_seconds=0.25,
        )
        _require(new_form_ready, "New campaign form did not become ready for validation-focus testing.")
        page.evaluate(
            """
            () => {
                const select = document.querySelector('#campaign-audience-select');
                if (select && select instanceof HTMLSelectElement && select.options.length > 0) {
                    select.selectedIndex = 0;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            """
        )
        audience_current = _wait_for(
            lambda: "CURRENT" in _read_text(page, "#campaign-audience-summary").upper(),
            timeout_seconds=SCENARIO_TIMEOUT_SECONDS,
            poll_seconds=0.25,
        )
        _require(audience_current, "Current audience detail did not settle for validation-focus testing.")
        page.click("#campaign-step-next-1")
        step2_visible = _wait_for(lambda: _visible(page, "#campaign-step-panel-2"), timeout_seconds=20)
        _require(step2_visible, "Campaign details step did not open for validation-focus testing.")
        page.fill("#campaign-name", "")
        page.select_option("#campaign-channel", "")
        page.click("#campaign-step-next-2")

        error_visible = _wait_for(lambda: _visible(page, "#campaign-step-error-summary"), timeout_seconds=10)
        active_id = str(page.evaluate("() => document.activeElement?.id || ''") or "")
        validation_result = {
            "error_visible": bool(error_visible),
            "error_focused": active_id == "campaign-step-error-summary",
            "error_text": _read_text(page, "#campaign-step-error-summary"),
            "active_element_id": active_id,
            "skipped": False,
        }
    except Exception as exc:
        validation_result = {
            "error_visible": False,
            "error_focused": False,
            "error_text": "",
            "skipped": True,
            "reason": str(exc),
        }
    results["validation_focus_error_summary"] = validation_result

    if _exists(page, "#campaign-step-4"):
        page.click("#campaign-step-4")
        _wait_for(lambda: _visible(page, "#campaign-step-panel-4"), timeout_seconds=10)

    finalize_disabled = page.locator("#campaign-finalize").first.is_disabled() if _exists(page, "#campaign-finalize") else True
    export_disabled = page.locator("#campaign-export").first.is_disabled() if _exists(page, "#campaign-export") else True
    action_help = _read_text(page, "#campaign-action-disabled-help")

    results["disabled_action_explanation"] = {
        "finalize_disabled": bool(finalize_disabled),
        "export_disabled": bool(export_disabled),
        "help_text": action_help,
        "help_present": bool(action_help),
    }

    stepper_semantics = page.evaluate(
        """
        () => {
            return Array.from(document.querySelectorAll('.campaign-step')).map((button) => ({
                id: button.id,
                ariaCurrent: button.getAttribute('aria-current') || '',
                ariaSelected: button.getAttribute('aria-selected') || '',
                tabIndex: Number(button.tabIndex),
            }));
        }
        """
    )
    results["stepper_semantics"] = stepper_semantics

    # Table/control reachability + no color-only status.
    table_reachability = {
        "open_button_focusable": False,
        "open_button_activates": False,
    }
    if _exists(page, "#campaign-recent-body button"):
        page.focus("#campaign-recent-body button")
        focused_open = bool(page.evaluate("() => document.activeElement?.closest('#campaign-recent-body button') !== null"))
        table_reachability["open_button_focusable"] = focused_open
        if focused_open:
            before = _read_text(page, "#campaigns-status-announcement")
            page.keyboard.press("Enter")
            changed = _wait_for(
                lambda: _read_text(page, "#campaigns-status-announcement") != before,
                timeout_seconds=8,
                poll_seconds=0.25,
            )
            table_reachability["open_button_activates"] = bool(changed)
    results["table_control_reachability"] = table_reachability

    status_badge_check = page.evaluate(
        """
        () => {
            const badges = Array.from(document.querySelectorAll('.status-badge'));
            let visible = 0;
            let emptyText = 0;
            for (const badge of badges) {
                if (!(badge instanceof HTMLElement)) continue;
                const rect = badge.getBoundingClientRect();
                const style = getComputedStyle(badge);
                if (rect.width <= 0 || rect.height <= 0 || style.display === 'none' || style.visibility === 'hidden') {
                    continue;
                }
                visible += 1;
                if (!(badge.textContent || '').trim()) {
                    emptyText += 1;
                }
            }
            return { visible, emptyText };
        }
        """
    )
    results["no_color_only_status"] = {
        "visible_badges": int((status_badge_check or {}).get("visible") or 0),
        "badges_missing_text": int((status_badge_check or {}).get("emptyText") or 0),
    }

    # aria-live checks.
    live_checks = page.evaluate(
        """
        () => {
            const selectors = [
                '#backend-status',
                '#analysis-run-announcement',
                '#campaigns-status-announcement',
                '#campaign-export-status-note',
                '#audience-announcement',
                '#audience-load-more-status',
                '#audience-save-status',
            ];
            return selectors.map((selector) => {
                const node = document.querySelector(selector);
                return {
                    selector,
                    exists: Boolean(node),
                    ariaLive: node ? (node.getAttribute('aria-live') || '') : '',
                    role: node ? (node.getAttribute('role') || '') : '',
                };
            });
        }
        """
    )
    results["aria_live_states"] = live_checks

    # Reduced-motion behavior.
    page.emulate_media(reduced_motion="reduce")
    reduce_matches = bool(page.evaluate("() => matchMedia('(prefers-reduced-motion: reduce)').matches"))
    _click_nav(page, "data-status")
    _wait_view_loaded(page, "data-status")
    _click_nav(page, "overview")
    _wait_view_loaded(page, "overview")
    page.emulate_media(reduced_motion="no-preference")
    results["reduced_motion"] = {
        "reduce_media_query_matches": reduce_matches,
        "navigation_still_operational": True,
    }

    return results


def _run_responsive_validation(playwright: Playwright, scenario_ref: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    viewport_results: list[dict[str, Any]] = []

    aggregated = {
        "console_errors": [],
        "page_errors": [],
        "request_failures": [],
        "http_errors": [],
    }

    with launch_system_browser_session(
        playwright,
        app_url=APP_URL,
        headless=True,
        viewport={"width": int(VIEWPORTS[0]["width"]), "height": int(VIEWPORTS[0]["height"])} ,
    ) as session:
        page = session.page
        collector = EventCollector(page, scenario_ref)
        collector.attach()
        try:
            for viewport in VIEWPORTS:
                scenario_ref["name"] = f"responsive_{viewport['name']}"
                page.set_viewport_size({"width": int(viewport["width"]), "height": int(viewport["height"])})
                _goto_with_retry(page, APP_URL)

                checks: list[dict[str, Any]] = []
                for target in VIEW_TARGETS:
                    _click_nav(page, target)
                    _wait_view_loaded(page, target)

                    control_selector = CRITICAL_CONTROL_BY_VIEW[target]
                    visibility = page.evaluate(
                        """
                        (selector) => {
                            const control = document.querySelector(selector);
                            if (!(control instanceof HTMLElement)) {
                                return { exists: false, withinViewport: false };
                            }
                            control.scrollIntoView({ block: 'center', inline: 'center' });
                            const rect = control.getBoundingClientRect();
                            const within = rect.width > 0
                                && rect.height > 0
                                && rect.left >= 0
                                && rect.right <= (window.innerWidth + 1)
                                && rect.top >= 0
                                && rect.bottom <= (window.innerHeight + 1);
                            return { exists: true, withinViewport: within };
                        }
                        """,
                        control_selector,
                    )

                    overflow = page.evaluate(
                        """
                        () => {
                            const doc = document.documentElement;
                            return {
                                horizontalOverflowPx: Math.max(0, doc.scrollWidth - window.innerWidth),
                                verticalOverflowPx: Math.max(0, doc.scrollHeight - window.innerHeight),
                            };
                        }
                        """
                    )

                    checks.append(
                        {
                            "view": target,
                            "critical_control": control_selector,
                            "control_exists": bool((visibility or {}).get("exists")),
                            "control_within_viewport": bool((visibility or {}).get("withinViewport")),
                            "horizontal_overflow_px": int((overflow or {}).get("horizontalOverflowPx") or 0),
                            "vertical_overflow_px": int((overflow or {}).get("verticalOverflowPx") or 0),
                        }
                    )

                viewport_results.append(
                    {
                        "viewport": viewport,
                        "browser": session.metadata.to_dict(),
                        "checks": checks,
                    }
                )
        finally:
            collector.detach()
            aggregated["console_errors"].extend(collector.console_errors)
            aggregated["page_errors"].extend(collector.page_errors)
            aggregated["request_failures"].extend(collector.request_failures)
            aggregated["http_errors"].extend(collector.http_errors)

    scenario_ref["name"] = "baseline"
    return viewport_results, aggregated


def _validate_accessibility_results(accessibility: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not bool((accessibility.get("visible_focus") or {}).get("focus_visible")):
        failures.append("visible keyboard focus was not detected")
    traversal = accessibility.get("tab_shift_tab_traversal") or {}
    if not bool(traversal.get("changed")) or not traversal.get("tab_target") or not traversal.get("shift_tab_target"):
        failures.append("Tab/Shift+Tab traversal did not reach distinct controls")
    activation = accessibility.get("enter_space_activation") or {}
    if not bool(activation.get("enter_activated")) or not bool(activation.get("space_activated")):
        failures.append("Enter/Space keyboard activation failed")
    if int((accessibility.get("labels_for_controls") or {}).get("missing_count") or 0) != 0:
        failures.append("one or more visible form controls are missing labels")

    validation = accessibility.get("validation_focus_error_summary") or {}
    if bool(validation.get("skipped")):
        failures.append(f"validation focus scenario was skipped: {validation.get('reason')}")
    elif not (
        bool(validation.get("error_visible"))
        and bool(validation.get("error_focused"))
        and bool(str(validation.get("error_text") or "").strip())
    ):
        failures.append("validation error summary was not visible, populated, and focused")

    live_states = accessibility.get("aria_live_states") or []
    if not live_states or any(
        not bool(item.get("exists"))
        or not (str(item.get("ariaLive") or "").strip() or str(item.get("role") or "").strip() == "status")
        for item in live_states
    ):
        failures.append("one or more required live-status regions lack aria-live/role=status semantics")

    disabled = accessibility.get("disabled_action_explanation") or {}
    if not (
        bool(disabled.get("finalize_disabled"))
        and bool(disabled.get("export_disabled"))
        and bool(str(disabled.get("help_text") or "").strip())
    ):
        failures.append("disabled finalize/export actions lack a visible explanation")

    stepper = accessibility.get("stepper_semantics") or []
    if (
        len(stepper) != 4
        or sum(str(item.get("ariaCurrent") or "") == "step" for item in stepper) != 1
        or sum(str(item.get("ariaSelected") or "") == "true" for item in stepper) != 1
        or sum(int(item.get("tabIndex") or 0) == 0 for item in stepper) != 1
    ):
        failures.append("campaign stepper does not expose one current/selected roving-tab stop")

    reachability = accessibility.get("table_control_reachability") or {}
    if not bool(reachability.get("open_button_focusable")) or not bool(reachability.get("open_button_activates")):
        failures.append("campaign table Open control was not keyboard reachable and activatable")
    status = accessibility.get("no_color_only_status") or {}
    if int(status.get("visible_badges") or 0) <= 0 or int(status.get("badges_missing_text") or 0) != 0:
        failures.append("status badges were absent or relied on color without text")
    reduced = accessibility.get("reduced_motion") or {}
    if not bool(reduced.get("reduce_media_query_matches")) or not bool(reduced.get("navigation_still_operational")):
        failures.append("reduced-motion mode was not honored while navigation remained operational")
    return failures


def _validate_responsive_results(viewport_results: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    expected_viewports = {item["name"] for item in VIEWPORTS}
    observed_viewports = {str((item.get("viewport") or {}).get("name") or "") for item in viewport_results}
    if observed_viewports != expected_viewports:
        failures.append(f"viewport matrix mismatch: expected={sorted(expected_viewports)}, observed={sorted(observed_viewports)}")
    for viewport_result in viewport_results:
        viewport_name = str((viewport_result.get("viewport") or {}).get("name") or "unknown")
        checks = viewport_result.get("checks") or []
        if {str(item.get("view") or "") for item in checks} != set(VIEW_TARGETS):
            failures.append(f"{viewport_name}: major-page coverage is incomplete")
        for check in checks:
            view = str(check.get("view") or "unknown")
            if not bool(check.get("control_exists")):
                failures.append(f"{viewport_name}/{view}: critical control is missing")
            if not bool(check.get("control_within_viewport")):
                failures.append(f"{viewport_name}/{view}: critical control cannot be brought within viewport")
            if int(check.get("horizontal_overflow_px") or 0) != 0:
                failures.append(f"{viewport_name}/{view}: document has horizontal overflow")
    return failures


def _validate_state_coverage(state_coverage: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    stale = state_coverage.get("stale_read_only_state") or {}
    if not (
        bool(stale.get("stale_candidate_found"))
        and bool(stale.get("stale_message_seen"))
        and bool(stale.get("use_in_campaign_disabled"))
    ):
        failures.append("stale/historical audience read-only state was not fully exercised")
    export = state_coverage.get("export_state_coverage") or {}
    if not all(bool(export.get(key)) for key in ("started_seen", "failed_and_aborted_seen", "completed_seen")):
        failures.append("STARTED/COMPLETED/FAILED/ABORTED export state coverage is incomplete")
    loading = state_coverage.get("loading_state") or {}
    if not bool(loading.get("campaigns_loading_seen")):
        failures.append("Campaign Builder loading state was not observed")
    retry = state_coverage.get("retryable_error_state") or {}
    if not bool(retry.get("campaigns_backend_unavailable_seen")):
        failures.append("retryable backend-error state was not observed")
    empty = state_coverage.get("empty_state") or {}
    if not bool(empty.get("campaigns_no_eligible_seen")):
        failures.append("empty/no-eligible state was not observed")
    jobs = state_coverage.get("job_state_coverage") or {}
    if not bool(jobs.get("running_seen")) or not bool(jobs.get("failed_seen")):
        failures.append("long-running and failed job states were not both observed")
    return failures


def _update_global_inventory() -> dict[str, Any]:
    _require(INVENTORY_PATH.is_file(), f"UI control inventory is missing: {INVENTORY_PATH}")
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    controls = inventory.get("controls") or []
    expected_selectors = {
        "#backend-status",
        *{f"[data-view-target='{target}']" for target in VIEW_TARGETS},
    }
    applied: list[str] = []
    for item in controls:
        if str(item.get("page") or "").casefold() != "global":
            continue
        selector = str(item.get("selector") or "")
        if selector in expected_selectors:
            item["status"] = "PASS"
            item["justification"] = "Step 9 system-browser navigation/accessibility/responsive coverage passed."
            applied.append(selector)
    missing = expected_selectors.difference(applied)
    _require(not missing, f"Global inventory controls were not found: {sorted(missing)}")
    summary: dict[str, int] = {}
    for item in controls:
        status = str(item.get("status") or "NOT_RUN")
        summary[status] = summary.get(status, 0) + 1
    inventory["status_summary"] = summary
    INVENTORY_PATH.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return {"applied": sorted(applied), "status_summary": summary}


def _classify_events(
    *,
    console_errors: list[dict[str, Any]],
    page_errors: list[dict[str, Any]],
    request_failures: list[dict[str, Any]],
    http_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    explained: list[dict[str, Any]] = []
    unexplained_console: list[dict[str, Any]] = []
    unexplained_js: list[dict[str, Any]] = []
    unexplained_critical_network: list[dict[str, Any]] = []

    for item in http_errors:
        url = str(item.get("url") or "")
        status = int(item.get("status") or 0)
        scenario = str(item.get("scenario") or "")
        if status == 404 and url.endswith("/favicon.ico"):
            explained.append({**item, "reason": "optional_asset_favicon"})
            continue
        if scenario.startswith("injected_"):
            explained.append({**item, "reason": "intentional_state_injection"})
            continue
        if "/api/" in url:
            unexplained_critical_network.append({**item, "reason": "critical_api_http_error"})
            continue
        unexplained_critical_network.append({**item, "reason": "unexpected_asset_http_error"})

    for item in request_failures:
        url = str(item.get("url") or "")
        scenario = str(item.get("scenario") or "")
        if scenario.startswith("injected_"):
            explained.append({**item, "reason": "intentional_state_injection"})
            continue
        if "/api/" in url:
            unexplained_critical_network.append({**item, "reason": "critical_api_request_failed"})
            continue
        explained.append({**item, "reason": "non_critical_request_failed"})

    for item in console_errors:
        text = str(item.get("text") or "")
        scenario = str(item.get("scenario") or "")
        lower = text.casefold()
        if "favicon" in lower:
            explained.append({**item, "reason": "optional_asset_favicon"})
            continue
        if scenario.startswith("injected_") and (
            "request failed" in lower
            or "failed to load resource" in lower
            or "service unavailable" in lower
            or "503" in lower
        ):
            explained.append({**item, "reason": "intentional_state_injection"})
            continue
        if (
            "failed to load resource" in lower
            and "404" in lower
            and any(str(err.get("url") or "").endswith("/favicon.ico") for err in http_errors)
        ):
            explained.append({**item, "reason": "optional_asset_favicon"})
            continue
        unexplained_console.append(item)

    for item in page_errors:
        unexplained_js.append(item)

    return {
        "explained_events": explained,
        "unexplained_console_errors": unexplained_console,
        "unexplained_js_errors": unexplained_js,
        "unexplained_critical_network_failures": unexplained_critical_network,
        "summary": {
            "console_errors_total": len(console_errors),
            "page_errors_total": len(page_errors),
            "request_failures_total": len(request_failures),
            "http_errors_total": len(http_errors),
            "explained_total": len(explained),
            "unexplained_console_total": len(unexplained_console),
            "unexplained_js_total": len(unexplained_js),
            "unexplained_critical_network_total": len(unexplained_critical_network),
        },
    }


def _write_outputs(artifacts: RunArtifacts) -> None:
    payload = artifacts.payload
    JSON_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_EVIDENCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    classification = payload.get("error_classification", {})
    summary = classification.get("summary", {})
    accessibility = payload.get("accessibility", {})
    state_coverage = payload.get("state_coverage", {})
    responsive = payload.get("responsive", {}).get("viewports", [])

    lines: list[str] = []
    lines.append("# Phase 8 Step 9 Browser Quality Report")
    lines.append("")
    lines.append(f"Generated at: {payload.get('generated_at')}")
    lines.append(f"Prompt: {payload.get('prompt')}")
    lines.append("")

    lines.append("## Browser")
    lines.append(f"- Name: {payload.get('browser', {}).get('name', 'unknown')}")
    lines.append(f"- Executable: {payload.get('browser', {}).get('executable_path', '')}")
    lines.append(f"- Version: {payload.get('browser', {}).get('product_version', 'unknown')}")
    lines.append(f"- Mode: {payload.get('browser', {}).get('execution_mode', 'unknown')}")
    lines.append("")

    lines.append("## Console and Network")
    lines.append(f"- Total console errors: {summary.get('console_errors_total', 0)}")
    lines.append(f"- Total uncaught/page errors: {summary.get('page_errors_total', 0)}")
    lines.append(f"- Total failed requests: {summary.get('request_failures_total', 0)}")
    lines.append(f"- Total HTTP >=400 responses: {summary.get('http_errors_total', 0)}")
    lines.append(f"- Explained events: {summary.get('explained_total', 0)}")
    lines.append(f"- Unexplained console errors: {summary.get('unexplained_console_total', 0)}")
    lines.append(f"- Unexplained JS errors: {summary.get('unexplained_js_total', 0)}")
    lines.append(f"- Unexplained critical network failures: {summary.get('unexplained_critical_network_total', 0)}")
    lines.append("")

    lines.append("## Accessibility Smoke")
    lines.append(f"- Visible keyboard focus: {accessibility.get('visible_focus', {})}")
    lines.append(f"- Tab and Shift+Tab traversal: {accessibility.get('tab_shift_tab_traversal', {})}")
    lines.append(f"- Enter and Space activation: {accessibility.get('enter_space_activation', {})}")
    lines.append(f"- Labels for controls: {accessibility.get('labels_for_controls', {})}")
    lines.append(f"- Validation focus and error summary: {accessibility.get('validation_focus_error_summary', {})}")
    lines.append(f"- aria-live checks: {accessibility.get('aria_live_states', {})}")
    lines.append(f"- Disabled-action explanation: {accessibility.get('disabled_action_explanation', {})}")
    lines.append(f"- Stepper semantics: {accessibility.get('stepper_semantics', {})}")
    lines.append(f"- Table/control reachability: {accessibility.get('table_control_reachability', {})}")
    lines.append(f"- No color-only status check: {accessibility.get('no_color_only_status', {})}")
    lines.append(f"- Reduced motion behavior: {accessibility.get('reduced_motion', {})}")
    lines.append("")

    lines.append("## Responsive Validation")
    for viewport_result in responsive:
        viewport = viewport_result.get("viewport", {})
        lines.append(f"### {viewport.get('name')}")
        for check in viewport_result.get("checks", []):
            lines.append(
                "- "
                f"{check.get('view')}: control={check.get('critical_control')} "
                f"exists={check.get('control_exists')} "
                f"within_viewport={check.get('control_within_viewport')} "
                f"horizontal_overflow_px={check.get('horizontal_overflow_px')}"
            )
    lines.append("")

    lines.append("## State Coverage")
    lines.append(f"- Loading state: {state_coverage.get('loading_state', {})}")
    lines.append(f"- Empty state: {state_coverage.get('empty_state', {})}")
    lines.append(f"- Retryable error state: {state_coverage.get('retryable_error_state', {})}")
    lines.append(f"- Stale/historical read-only: {state_coverage.get('stale_read_only_state', {})}")
    lines.append(f"- Long-running/completed/failed/aborted export: {state_coverage.get('export_state_coverage', {})}")
    lines.append(f"- Long-running/failed job states: {state_coverage.get('job_state_coverage', {})}")
    lines.append("")

    lines.append("## Outcome")
    lines.append(f"- Overall status: {payload.get('overall_status')}")
    lines.append(f"- Browser quality gate: {payload.get('quality_gate', {}).get('status')}")
    lines.append(f"- Browser quality failures: {payload.get('quality_gate', {}).get('failures', {})}")
    lines.append(f"- Global inventory controls updated: {len(payload.get('inventory', {}).get('applied', []))}")
    lines.append(
        "- Final targets: "
        f"unexplained_console_errors={summary.get('unexplained_console_total', 0)}, "
        f"unexplained_critical_network_failures={summary.get('unexplained_critical_network_total', 0)}"
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _run_step9() -> RunArtifacts:
    _progress("Starting Step 9 browser quality validation.")

    initialize_database(DATABASE_PATH)

    if not STEP6_EVIDENCE_PATH.exists():
        raise Step9ValidationError(
            "Step 6 evidence is required for Step 9 reuse semantics. "
            f"Missing: {STEP6_EVIDENCE_PATH}"
        )

    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "prompt": "Prompts/phase8_release_assurance_system_browser_prompt_pack/09_STEP_09_BROWSER_ERROR_ACCESSIBILITY_RESPONSIVE_AND_STATE_TESTS.md",
    }

    with _managed_server() as server_info:
        payload["server"] = server_info

        with sync_playwright() as playwright:
            # Baseline session: accessibility + state coverage + core error collection.
            scenario_ref = {"name": "baseline"}
            with launch_system_browser_session(
                playwright,
                app_url=APP_URL,
                headless=True,
                viewport={"width": 1366, "height": 768},
            ) as session:
                page = session.page
                payload["browser"] = session.metadata.to_dict()

                page.add_init_script(
                    """
                    window.addEventListener('unhandledrejection', (event) => {
                        const reason = event && event.reason ? String(event.reason) : 'unknown';
                        console.error('[unhandledrejection]', reason);
                    });
                    window.addEventListener('error', (event) => {
                        if (!event || !event.error) {
                            return;
                        }
                        console.error('[uncaught-error]', String(event.error));
                    });
                    """
                )

                collector = EventCollector(page, scenario_ref)
                collector.attach()
                try:
                    _goto_with_retry(page, APP_URL)
                    _wait_view_loaded(page, "overview")

                    accessibility = _run_accessibility_smoke(page)
                    _progress("Accessibility smoke checks complete.")

                    state_coverage = _exercise_state_coverage(page, scenario_ref)
                    _progress("State coverage checks complete.")
                finally:
                    collector.detach()

                payload["accessibility"] = accessibility
                payload["state_coverage"] = state_coverage

                core_events = {
                    "console_errors": collector.console_errors,
                    "page_errors": collector.page_errors,
                    "request_failures": collector.request_failures,
                    "http_errors": collector.http_errors,
                }

            # Responsive sessions: required viewport matrix.
            responsive_results, responsive_events = _run_responsive_validation(playwright, scenario_ref)
            _progress("Responsive viewport validation complete.")

    merged_events = {
        "console_errors": [*core_events["console_errors"], *responsive_events["console_errors"]],
        "page_errors": [*core_events["page_errors"], *responsive_events["page_errors"]],
        "request_failures": [*core_events["request_failures"], *responsive_events["request_failures"]],
        "http_errors": [*core_events["http_errors"], *responsive_events["http_errors"]],
    }

    payload["events"] = merged_events
    payload["responsive"] = {
        "viewports": responsive_results,
    }

    classification = _classify_events(**merged_events)
    payload["error_classification"] = classification

    quality_failures = {
        "accessibility": _validate_accessibility_results(payload.get("accessibility") or {}),
        "responsive": _validate_responsive_results(responsive_results),
        "state_coverage": _validate_state_coverage(payload.get("state_coverage") or {}),
    }
    payload["quality_gate"] = {
        "status": "PASS" if not any(quality_failures.values()) else "FAIL",
        "failures": quality_failures,
    }

    summary = classification.get("summary", {})
    _require(
        int(summary.get("unexplained_console_total", 0)) == 0,
        f"Unexplained console errors detected: {classification.get('unexplained_console_errors')}",
    )
    _require(
        int(summary.get("unexplained_critical_network_total", 0)) == 0,
        "Unexplained critical network failures detected: "
        f"{classification.get('unexplained_critical_network_failures')}",
    )
    _require(
        int(summary.get("unexplained_js_total", 0)) == 0,
        f"Unexplained JS/page errors detected: {classification.get('unexplained_js_errors')}",
    )
    _require(
        not any(quality_failures.values()),
        f"Browser quality assertions failed: {quality_failures}",
    )

    payload["inventory"] = _update_global_inventory()
    payload["overall_status"] = "PASS"
    return RunArtifacts(payload=payload)


def main() -> int:
    artifacts = _run_step9()
    _write_outputs(artifacts)
    print(f"Wrote evidence: {JSON_EVIDENCE_PATH}")
    print(f"Wrote report: {REPORT_PATH}")
    print(f"Status: {artifacts.payload.get('overall_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
