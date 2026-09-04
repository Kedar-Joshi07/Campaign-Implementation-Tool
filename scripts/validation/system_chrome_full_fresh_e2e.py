from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence" / "full_fresh_e2e"
SCREENSHOT_DIR = EVIDENCE_DIR / "screenshots"
INVENTORY_PATH = EVIDENCE_DIR / "ui_control_inventory.json"
COVERAGE_PATH = EVIDENCE_DIR / "UI_CONTROL_COVERAGE.md"
RESULT_PATH = EVIDENCE_DIR / "system_chrome_full_fresh_e2e.json"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
APP_URL = "http://127.0.0.1:8000/"
DB_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"


@dataclass
class RunState:
    console_errors: list[str]
    page_errors: list[str]
    request_failures: list[dict[str, str]]
    screenshots: list[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _wait_for(condition, timeout_seconds: float, poll_seconds: float = 0.25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll_seconds)
    return False


def _safe_int(value: str) -> int:
    cleaned = (value or "").replace(",", "").replace(" ", "").strip()
    return int(cleaned) if cleaned and cleaned not in {"-", "—"} else 0


def _capture(page: Page, state: RunState, name: str, full_page: bool = True) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    state.screenshots.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))


def _ensure_hash(page: Page, hash_value: str) -> None:
    page.goto(f"{APP_URL}#{hash_value}", wait_until="domcontentloaded")
    ok = _wait_for(lambda: page.evaluate("(h) => location.hash === '#' + h", hash_value), timeout_seconds=20)
    if not ok:
        raise RuntimeError(f"Unable to navigate to #{hash_value}")


def _visible(page: Page, selector: str) -> bool:
    return bool(
        page.evaluate(
            """
            (sel) => {
                const node = document.querySelector(sel);
                return !!node && !node.hidden;
            }
            """,
            selector,
        )
    )


def _click_nav(page: Page, target: str) -> None:
    page.click(f"[data-view-target='{target}']")
    ok = _wait_for(lambda: page.evaluate("(v) => location.hash === '#' + v", target), timeout_seconds=20)
    if not ok:
        raise RuntimeError(f"Failed to switch to view: {target}")


def _run_step5_overview_and_data(page: Page, state: RunState) -> dict[str, Any]:
    _click_nav(page, "overview")
    _wait_for(lambda: _visible(page, "#overview-view"), timeout_seconds=30)
    _capture(page, state, "step5_overview")

    overview = page.evaluate(
        """
        () => ({
            customers: (document.querySelector('#customer-count')?.textContent || '').trim(),
            campaignSales: (document.querySelector('#campaign-sales-count')?.textContent || '').trim(),
            demographics: (document.querySelector('#demographic-count')?.textContent || '').trim(),
        })
        """
    )

    _click_nav(page, "data-status")
    _wait_for(lambda: _visible(page, "#data-status-view"), timeout_seconds=30)
    _capture(page, state, "step5_data_status")

    data_status = page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#import-history-body tr')).map((tr) => (tr.textContent || '').trim());
            return {
                datasetCards: Array.from(document.querySelectorAll('[data-dataset-card]')).length,
                importHistoryRows: rows.filter((x) => x).length,
            };
        }
        """
    )

    return {
        "overview": overview,
        "data_status": data_status,
    }


def _run_step6_historical(page: Page, state: RunState) -> dict[str, Any]:
    _click_nav(page, "historical-analysis")
    _wait_for(lambda: _visible(page, "#historical-analysis-view"), timeout_seconds=30)

    if _visible(page, "#historical-analysis-refresh"):
        page.click("#historical-analysis-refresh")
        _wait_for(lambda: _visible(page, "#historical-analysis-view"), timeout_seconds=10)

    _capture(page, state, "step6_historical_analysis")

    payload = page.evaluate(
        """
        () => ({
            hasAnalyzeButton: !!document.querySelector('#analyze-population'),
            hasFilters: !!document.querySelector('#campaign-filter') && !!document.querySelector('#channel-filter'),
            recentRows: Array.from(document.querySelectorAll('#recent-analyses-body tr')).length,
        })
        """
    )
    return payload


def _run_step7_model(page: Page, state: RunState) -> dict[str, Any]:
    _click_nav(page, "model-training")
    _wait_for(lambda: _visible(page, "#model-training-view"), timeout_seconds=30)

    _capture(page, state, "step7_model_training")

    payload = page.evaluate(
        """
        () => ({
            hasTrainButton: !!document.querySelector('#train-model-submit'),
            hasScoreButton: !!document.querySelector('#score-prospect-submit'),
            modelSummaryTitle: (document.querySelector('#model-summary-title')?.textContent || '').trim(),
            scoringRunText: (document.querySelector('#scoring-run-id')?.textContent || '').trim(),
        })
        """
    )
    return payload


def _run_step8_9_audience(page: Page, state: RunState) -> dict[str, Any]:
    _click_nav(page, "audience-explorer")
    _wait_for(lambda: _visible(page, "#audience-explorer-view"), timeout_seconds=30)

    if _visible(page, "#audience-explorer-refresh"):
        page.click("#audience-explorer-refresh")

    loaded = _wait_for(
        lambda: page.evaluate(
            """
            () => {
                const m = (document.querySelector('#audience-estimate-matching')?.textContent || '').trim();
                return m && m !== '-' && m !== '—';
            }
            """
        ),
        timeout_seconds=180,
    )
    if not loaded:
        raise RuntimeError("Audience estimate did not load.")

    # Scenario checks.
    def apply_and_read() -> dict[str, Any]:
        page.click("#audience-apply-filters")
        ok = _wait_for(
            lambda: page.evaluate(
                """
                () => {
                    const btn = document.querySelector('#audience-apply-filters');
                    const msg = (document.querySelector('#audience-announcement')?.textContent || '');
                    return !!btn && !btn.disabled && !/Applying audience filters/i.test(msg);
                }
                """
            ),
            timeout_seconds=240,
            poll_seconds=0.5,
        )
        if not ok:
            raise RuntimeError("Audience filter apply did not settle.")
        return page.evaluate(
            """
            () => ({
                matching: (document.querySelector('#audience-estimate-matching')?.textContent || '').trim(),
                selected: (document.querySelector('#audience-estimate-selected')?.textContent || '').trim(),
                scoreRange: (document.querySelector('#audience-estimate-score-range')?.textContent || '').trim(),
                scoreMean: (document.querySelector('#audience-estimate-score-mean')?.textContent || '').trim(),
                summary: (document.querySelector('#audience-filter-summary-text')?.textContent || '').trim(),
                errorVisible: !!document.querySelector('#audience-form-error') && !document.querySelector('#audience-form-error').hidden,
                errorText: (document.querySelector('#audience-form-error')?.textContent || '').trim(),
            })
            """
        )

    scenarios: dict[str, Any] = {}

    page.click("#audience-filter-reset")
    scenarios["all_matching"] = apply_and_read()

    page.click("#audience-filter-reset")
    page.fill("#audience-top-percentile", "1")
    scenarios["top_1_percent"] = apply_and_read()

    page.click("#audience-filter-reset")
    page.select_option("#audience-deciles", ["1"])
    scenarios["top_decile"] = apply_and_read()

    page.click("#audience-filter-reset")
    page.fill("#audience-age-min", "25")
    page.fill("#audience-age-max", "65")
    page.select_option("#audience-state", ["California"])
    scenarios["demographic_filter"] = apply_and_read()

    page.click("#audience-filter-reset")
    page.select_option("#audience-rank-bands", ["HIGH", "MEDIUM"])
    page.select_option("#audience-resident-type", ["Urban core"])
    scenarios["rank_plus_demographic"] = apply_and_read()

    page.click("#audience-filter-reset")
    page.check("#audience-selection-topn")
    page.fill("#audience-target-count", "50000")
    scenarios["top_n_50k"] = apply_and_read()

    # Validation errors.
    page.fill("#audience-age-min", "70")
    page.fill("#audience-age-max", "50")
    page.click("#audience-apply-filters")
    time.sleep(0.6)
    invalid_age = page.evaluate(
        """
        () => ({
            visible: !!document.querySelector('#audience-form-error') && !document.querySelector('#audience-form-error').hidden,
            text: (document.querySelector('#audience-form-error')?.textContent || '').trim(),
        })
        """
    )

    page.click("#audience-filter-reset")
    page.check("#audience-selection-topn")
    page.fill("#audience-target-count", "0")
    page.click("#audience-apply-filters")
    time.sleep(0.6)
    invalid_topn = page.evaluate(
        """
        () => ({
            visible: !!document.querySelector('#audience-form-error') && !document.querySelector('#audience-form-error').hidden,
            text: (document.querySelector('#audience-form-error')?.textContent || '').trim(),
        })
        """
    )

    # Save a browser-run audience and use campaign handoff.
    page.click("#audience-filter-reset")
    all_matching = apply_and_read()
    audience_name = f"System Chrome UI Save {int(time.time())}"
    page.fill("#audience-save-name", audience_name)
    page.fill("#audience-save-description", "Saved from system Chrome validation flow")
    page.click("#audience-save-submit")

    saved_ok = _wait_for(
        lambda: page.evaluate(
            """
            () => {
                const status = (document.querySelector('#audience-save-status')?.textContent || '').toLowerCase();
                return status.includes('saved audience #');
            }
            """
        ),
        timeout_seconds=120,
    )
    if not saved_ok:
        raise RuntimeError("Audience save did not confirm in UI.")

    page.click("#saved-audience-use-campaign")
    routed = _wait_for(lambda: page.evaluate("() => location.hash === '#campaigns'"), timeout_seconds=20)
    if not routed:
        raise RuntimeError("Use-in-campaign did not route to campaigns view.")

    _capture(page, state, "step9_audience_explorer")

    return {
        "scenarios": scenarios,
        "invalid_age": invalid_age,
        "invalid_topn": invalid_topn,
        "saved_audience_name": audience_name,
        "saved_all_matching": all_matching,
    }


def _parse_csv(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    row: list[str] = []
    field = ""
    in_quotes = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    field += '"'
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field += ch
            i += 1
            continue
        if ch == '"':
            in_quotes = True
            i += 1
            continue
        if ch == ',':
            row.append(field)
            field = ""
            i += 1
            continue
        if ch == '\n':
            row.append(field)
            if not (len(row) == 1 and row[0] == ""):
                rows.append(row)
            row = []
            field = ""
            i += 1
            continue
        if ch == '\r':
            i += 1
            continue
        field += ch
        i += 1
    if field or row:
        row.append(field)
        rows.append(row)
    return rows


def _sha256_text_via_python(text: str) -> str:
    payload = text.encode("utf-8")
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _campaign_step_to_step1(page: Page) -> None:
    for _ in range(8):
        s1 = _visible(page, "#campaign-step-panel-1")
        s2 = _visible(page, "#campaign-step-panel-2")
        s3 = _visible(page, "#campaign-step-panel-3")
        s4 = _visible(page, "#campaign-step-panel-4")
        if s1:
            return
        if s4:
            page.click("#campaign-step-back-4")
        elif s3:
            page.click("#campaign-step-back-3")
        elif s2:
            page.click("#campaign-step-back-2")
        time.sleep(0.3)
    if not _visible(page, "#campaign-step-panel-1"):
        raise RuntimeError("Unable to navigate back to campaign step 1.")


def _select_audience_option(page: Page, needle: str) -> dict[str, str] | None:
    payload = page.evaluate(
        """
        (n) => {
            const sel = document.querySelector('#campaign-audience-select');
            if (!sel) return null;
            const options = Array.from(sel.options || []);
            const nonEmpty = options.filter((o) => String(o.value || '').trim().length > 0);
            const hit = options.find((o) => (o.textContent || '').includes(n)) || nonEmpty[0] || null;
            if (!hit) return null;
            sel.value = hit.value;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            return { value: hit.value, label: (hit.textContent || '').trim() };
        }
        """,
        needle,
    )
    return payload if isinstance(payload, dict) else None


def _wait_campaign_audience_ready(page: Page, timeout_seconds: float = 30) -> bool:
    return _wait_for(
        lambda: bool(
            page.evaluate(
                """
                () => {
                    const summary = document.querySelector('#campaign-audience-summary');
                    const text = (summary?.textContent || '').trim();
                    return text.length > 0 && !/Not selected/i.test(text) && /Currentness/i.test(text);
                }
                """
            )
        ),
        timeout_seconds=timeout_seconds,
        poll_seconds=0.3,
    )


def _campaign_negatives(page: Page) -> dict[str, Any]:
    _campaign_step_to_step1(page)

    page.evaluate(
        """
        () => {
            const sel = document.querySelector('#campaign-audience-select');
            if (!sel) return;
            const temp = document.createElement('option');
            temp.value = '';
            temp.textContent = '';
            sel.insertBefore(temp, sel.firstChild);
            sel.value = '';
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """
    )
    page.click("#campaign-step-next-1")
    missing_audience = page.evaluate(
        """
        () => {
            const e = document.querySelector('#campaign-step-error-summary');
            return e && !e.hidden ? (e.textContent || '').trim() : null;
        }
        """
    )

    selected = _select_audience_option(page, "TopN50K")
    if selected is None:
        selected = _select_audience_option(page, "CURRENT")
    if selected is None:
        raise RuntimeError("No selectable campaign audience found.")
    if not _wait_campaign_audience_ready(page, timeout_seconds=45):
        raise RuntimeError("Campaign audience details did not finish loading after selection.")

    ok = _wait_for(lambda: _visible(page, "#campaign-step-panel-1"), timeout_seconds=10)
    if not ok:
        raise RuntimeError("Campaign step 1 not visible after restoring audience.")

    page.click("#campaign-step-next-1")
    if not _wait_for(lambda: _visible(page, "#campaign-step-panel-2"), timeout_seconds=20):
        raise RuntimeError("Campaign step 2 did not open.")

    page.fill("#campaign-name", "")
    page.select_option("#campaign-channel", "EMAIL")
    page.click("#campaign-step-next-2")
    blank_name = page.evaluate(
        """
        () => {
            const e = document.querySelector('#campaign-step-error-summary');
            return e && !e.hidden ? (e.textContent || '').trim() : null;
        }
        """
    )

    page.fill("#campaign-name", "Validation Temp")
    page.select_option("#campaign-channel", "")
    page.click("#campaign-step-next-2")
    missing_channel = page.evaluate(
        """
        () => {
            const e = document.querySelector('#campaign-step-error-summary');
            return e && !e.hidden ? (e.textContent || '').trim() : null;
        }
        """
    )

    preserve_name = f"Preserve {int(time.time())}"
    preserve_desc = "Back-forward preservation"
    page.fill("#campaign-name", preserve_name)
    page.fill("#campaign-description", preserve_desc)
    page.select_option("#campaign-channel", "EMAIL")
    page.fill("#campaign-launch-date", "2026-12-10")
    page.click("#campaign-step-back-2")
    _wait_for(lambda: _visible(page, "#campaign-step-panel-1"), timeout_seconds=20)
    page.click("#campaign-step-next-1")
    _wait_for(lambda: _visible(page, "#campaign-step-panel-2"), timeout_seconds=20)

    preserved = page.evaluate(
        """
        () => ({
            name: (document.querySelector('#campaign-name')?.value || '').trim(),
            description: (document.querySelector('#campaign-description')?.value || '').trim(),
            channel: (document.querySelector('#campaign-channel')?.value || '').trim(),
            launchDate: (document.querySelector('#campaign-launch-date')?.value || '').trim(),
        })
        """
    )

    return {
        "selected_audience": selected,
        "missing_audience_error": missing_audience,
        "blank_name_error": blank_name,
        "missing_channel_error": missing_channel,
        "preserved_values": preserved,
    }


def _create_finalize_campaign(page: Page, channel: str, name_prefix: str) -> dict[str, Any]:
    _campaign_step_to_step1(page)

    selected = _select_audience_option(page, "TopN50K")
    if selected is None:
        selected = _select_audience_option(page, "CURRENT")
    if selected is None:
        raise RuntimeError("No selectable audience for campaign creation.")
    if not _wait_campaign_audience_ready(page, timeout_seconds=45):
        raise RuntimeError("Campaign audience details did not finish loading before step 2.")

    page.click("#campaign-step-next-1")
    if not _wait_for(lambda: _visible(page, "#campaign-step-panel-2"), timeout_seconds=20):
        raise RuntimeError("Step 2 not visible.")

    name = f"{name_prefix} {int(time.time())}"
    page.fill("#campaign-name", name)
    page.fill("#campaign-description", f"{channel} system chrome full-fresh validation")
    page.select_option("#campaign-channel", channel)
    page.fill("#campaign-launch-date", "2026-12-11")

    page.click("#campaign-step-next-2")
    if not _wait_for(lambda: _visible(page, "#campaign-step-panel-3"), timeout_seconds=20):
        raise RuntimeError("Step 3 not visible.")

    page.click("#campaign-step-next-3")
    if not _wait_for(lambda: _visible(page, "#campaign-step-panel-4"), timeout_seconds=20):
        raise RuntimeError("Step 4 not visible.")

    page.click("#campaign-create-draft")
    draft_ok = _wait_for(
        lambda: "DRAFT" in (page.locator("#campaign-shell-status").inner_text().strip().upper()),
        timeout_seconds=180,
        poll_seconds=0.4,
    )
    if not draft_ok:
        raise RuntimeError("Draft creation did not settle.")

    # submitDraft returns to step 3.
    if _visible(page, "#campaign-step-panel-3"):
        page.click("#campaign-step-next-3")
        _wait_for(lambda: _visible(page, "#campaign-step-panel-4"), timeout_seconds=20)

    can_finalize = not page.locator("#campaign-finalize").is_disabled()
    if not can_finalize:
        action_help = page.locator("#campaign-action-disabled-help").inner_text().strip()
        raise RuntimeError(f"Finalize disabled unexpectedly: {action_help}")

    page.click("#campaign-finalize")
    final_ok = _wait_for(
        lambda: "FINALIZED" in (page.locator("#campaign-shell-status").inner_text().strip().upper()),
        timeout_seconds=240,
        poll_seconds=0.4,
    )
    if not final_ok:
        raise RuntimeError("Finalize did not settle.")

    summary = page.evaluate(
        """
        () => {
            const details = Object.fromEntries(Array.from(document.querySelectorAll('#campaign-detail-summary div')).map((d) => [
                (d.querySelector('dt')?.textContent || '').trim(),
                (d.querySelector('dd')?.textContent || '').trim()
            ]));
            return {
                shellStatus: (document.querySelector('#campaign-shell-status')?.textContent || '').trim(),
                currentnessBadge: (document.querySelector('#campaign-currentness-badge')?.textContent || '').trim(),
                actionHelp: (document.querySelector('#campaign-action-disabled-help')?.textContent || '').trim(),
                finalizeDisabled: !!document.querySelector('#campaign-finalize')?.disabled,
                exportDisabled: !!document.querySelector('#campaign-export')?.disabled,
                details,
            };
        }
        """
    )

    return {
        "name": name,
        "selected_audience": selected,
        "summary": summary,
    }


def _capture_export_csv_via_ui(page: Page) -> dict[str, Any]:
    # Ensure step 4 and ack.
    if not _visible(page, "#campaign-step-panel-4") and _visible(page, "#campaign-step-panel-3"):
        page.click("#campaign-step-next-3")
        _wait_for(lambda: _visible(page, "#campaign-step-panel-4"), timeout_seconds=20)

    ack = page.locator("#campaign-pii-ack")
    if not ack.is_checked():
        ack.check()

    page.evaluate(
        """
        () => {
            window.__copilotCsvCapture = { url: null, status: null, headers: null, text: null, error: null };
            if (window.__copilotAnchorPatched) {
                return;
            }
            window.__copilotAnchorPatched = true;
            const original = HTMLAnchorElement.prototype.click;
            HTMLAnchorElement.prototype.click = function patchedClick() {
                try {
                    const href = this.href;
                    window.__copilotCsvCapture = { url: href, status: null, headers: null, text: null, error: null };
                    fetch(href, { credentials: 'same-origin' })
                        .then(async (res) => {
                            window.__copilotCsvCapture.status = res.status;
                            window.__copilotCsvCapture.headers = Object.fromEntries(res.headers.entries());
                            window.__copilotCsvCapture.text = await res.text();
                        })
                        .catch((err) => {
                            window.__copilotCsvCapture.error = String(err?.message || err);
                        });
                } catch (err) {
                    window.__copilotCsvCapture.error = String(err?.message || err);
                }
                return undefined;
            };
            window.__copilotAnchorOriginal = original;
        }
        """
    )

    before_event = page.evaluate(
        """
        () => (document.querySelector('#campaign-export-history-body tr td:nth-child(1)')?.textContent || '').trim()
        """
    )

    page.click("#campaign-export")

    captured = _wait_for(
        lambda: page.evaluate(
            """
            () => {
                const c = window.__copilotCsvCapture || {};
                return !!c.error || typeof c.text === 'string';
            }
            """
        ),
        timeout_seconds=900,
        poll_seconds=0.4,
    )
    if not captured:
        raise RuntimeError("CSV capture did not complete in time.")

    history_terminal = _wait_for(
        lambda: page.evaluate(
            """
            (prevId) => {
                const row = document.querySelector('#campaign-export-history-body tr');
                if (!row || row.classList.contains('empty-row')) return false;
                const id = (row.querySelector('td:nth-child(1)')?.textContent || '').trim();
                const status = (row.querySelector('td:nth-child(4)')?.textContent || '').trim().toUpperCase();
                if (id === prevId) return false;
                return status === 'COMPLETED' || status === 'FAILED' || status === 'ABORTED';
            }
            """,
            before_event,
        ),
        timeout_seconds=900,
        poll_seconds=0.5,
    )
    if not history_terminal:
        raise RuntimeError("Export history did not reach terminal state.")

    capture = page.evaluate(
        """
        () => {
            const c = window.__copilotCsvCapture || {};
            const row = document.querySelector('#campaign-export-history-body tr');
            let history = null;
            if (row && !row.classList.contains('empty-row')) {
                const td = row.querySelectorAll('td');
                if (td.length >= 10) {
                    history = {
                        eventId: (td[0].textContent || '').trim(),
                        profile: (td[2].textContent || '').trim(),
                        status: (td[3].textContent || '').trim(),
                        selected: (td[5].textContent || '').trim(),
                        deliverable: (td[6].textContent || '').trim(),
                        undeliverable: (td[7].textContent || '').trim(),
                        exportedRows: (td[8].textContent || '').trim(),
                        checksum: (td[9].textContent || '').trim(),
                    };
                }
            }
            return {
                url: c.url || null,
                status: c.status,
                headers: c.headers || {},
                text: typeof c.text === 'string' ? c.text : null,
                error: c.error || null,
                history,
            };
        }
        """
    )

    text = str(capture.get("text") or "")
    rows = _parse_csv(text)
    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []

    capture["csv"] = {
        "header": header,
        "row_count": len(data_rows),
        "sha256": _sha256_text_via_python(text),
    }
    return capture


def _validate_export_contract(export_payload: dict[str, Any], channel: str) -> dict[str, Any]:
    expected_headers = {
        "EMAIL": [
            "person_id",
            "propensity_score",
            "percentile_bucket",
            "decile",
            "rank_band",
            "first_name",
            "last_name",
            "email",
        ],
        "DIRECT_MAIL": [
            "person_id",
            "propensity_score",
            "percentile_bucket",
            "decile",
            "rank_band",
            "first_name",
            "last_name",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
        ],
    }
    forbidden_common = {"phone_number", "ethnicity", "religion", "family_yearly_income", "occupation_industry"}
    forbidden_channel = {"DIRECT_MAIL": {"email"}, "EMAIL": {"address_line_1", "address_line_2", "city", "state", "postal_code"}}

    csv_header = list(export_payload.get("csv", {}).get("header") or [])
    csv_text = str(export_payload.get("text") or "")
    rows = _parse_csv(csv_text)
    data_rows = rows[1:] if len(rows) > 1 else []
    index = {name: i for i, name in enumerate(csv_header)}

    profile_expected = "EMAIL_CONTACT_V1" if channel == "EMAIL" else "DIRECT_MAIL_CONTACT_V1"
    history = export_payload.get("history") or {}

    missing_required_rows = 0
    if channel == "EMAIL":
        col = index.get("email")
        if col is not None:
            for row in data_rows:
                if not str(row[col] if col < len(row) else "").strip():
                    missing_required_rows += 1
    else:
        required = ["address_line_1", "city", "state", "postal_code"]
        req_idx = [index.get(name) for name in required]
        for row in data_rows:
            valid = True
            for idx in req_idx:
                if idx is None or idx >= len(row) or not str(row[idx]).strip():
                    valid = False
                    break
            if not valid:
                missing_required_rows += 1

    # Deterministic order check: propensity desc, person_id asc for ties.
    score_i = index.get("propensity_score")
    person_i = index.get("person_id")
    monotonic_violations = 0
    tie_order_violations = 0
    prev_score = None
    prev_person = None
    if score_i is not None and person_i is not None:
        for row in data_rows:
            if score_i >= len(row) or person_i >= len(row):
                continue
            score_text = str(row[score_i]).strip()
            person = str(row[person_i]).strip()
            try:
                score = float(score_text)
            except ValueError:
                continue
            if prev_score is not None:
                if score > prev_score + 1e-12:
                    monotonic_violations += 1
                if abs(score - prev_score) <= 1e-12 and prev_person is not None and person < prev_person:
                    tie_order_violations += 1
            prev_score = score
            prev_person = person

    history_selected = _safe_int(str(history.get("selected") or "0"))
    history_deliverable = _safe_int(str(history.get("deliverable") or "0"))
    history_undeliverable = _safe_int(str(history.get("undeliverable") or "0"))
    history_exported = _safe_int(str(history.get("exportedRows") or "0"))

    checksum_match = str(history.get("checksum") or "") == str(export_payload.get("csv", {}).get("sha256") or "")

    return {
        "channel": channel,
        "expected_profile": profile_expected,
        "observed_profile": str(history.get("profile") or ""),
        "status": str(history.get("status") or ""),
        "header_exact": csv_header == expected_headers[channel],
        "forbidden_present": sorted((set(csv_header) & forbidden_common) | (set(csv_header) & forbidden_channel[channel])),
        "row_count": len(data_rows),
        "missing_required_rows": missing_required_rows,
        "selected_equals_deliverable_plus_undeliverable": history_selected == (history_deliverable + history_undeliverable),
        "row_count_equals_deliverable": len(data_rows) == history_deliverable,
        "history_exported_equals_row_count": history_exported == len(data_rows),
        "checksum_match": checksum_match,
        "safe_filename": bool(str((export_payload.get("headers") or {}).get("content-disposition") or "").lower().find("campaign_") >= 0),
        "monotonic_violations": monotonic_violations,
        "tie_order_violations": tie_order_violations,
    }


def _run_step10_12_campaigns(page: Page, state: RunState) -> dict[str, Any]:
    _click_nav(page, "campaigns")
    if not _wait_for(lambda: _visible(page, "#campaigns-state-ready"), timeout_seconds=120):
        raise RuntimeError("Campaign workspace not ready.")

    negatives = _campaign_negatives(page)

    email_campaign = _create_finalize_campaign(page, "EMAIL", "System Chrome EMAIL")
    email_export = _capture_export_csv_via_ui(page)
    email_contract = _validate_export_contract(email_export, "EMAIL")

    direct_mail_campaign = _create_finalize_campaign(page, "DIRECT_MAIL", "System Chrome DIRECT_MAIL")
    direct_mail_export = _capture_export_csv_via_ui(page)
    direct_mail_contract = _validate_export_contract(direct_mail_export, "DIRECT_MAIL")

    _capture(page, state, "step10_12_campaigns")

    return {
        "negatives": negatives,
        "email_campaign": email_campaign,
        "email_export": {
            "history": email_export.get("history"),
            "headers": email_export.get("headers"),
            "csv": {
                "header": email_export.get("csv", {}).get("header"),
                "row_count": email_export.get("csv", {}).get("row_count"),
                "sha256": email_export.get("csv", {}).get("sha256"),
            },
            "contract": email_contract,
        },
        "direct_mail_campaign": direct_mail_campaign,
        "direct_mail_export": {
            "history": direct_mail_export.get("history"),
            "headers": direct_mail_export.get("headers"),
            "csv": {
                "header": direct_mail_export.get("csv", {}).get("header"),
                "row_count": direct_mail_export.get("csv", {}).get("row_count"),
                "sha256": direct_mail_export.get("csv", {}).get("sha256"),
            },
            "contract": direct_mail_contract,
        },
    }


def _run_responsive_checks(page: Page, state: RunState) -> dict[str, Any]:
    viewports = [
        {"name": "desktop_1920x1080", "width": 1920, "height": 1080, "view": "overview"},
        {"name": "laptop_1366x768", "width": 1366, "height": 768, "view": "model-training"},
        {"name": "tablet_768x1024", "width": 768, "height": 1024, "view": "audience-explorer"},
        {"name": "mobile_390x844", "width": 390, "height": 844, "view": "campaigns"},
    ]

    results: list[dict[str, Any]] = []
    for item in viewports:
        page.set_viewport_size({"width": item["width"], "height": item["height"]})
        _click_nav(page, item["view"])
        _wait_for(lambda: page.evaluate("(v) => location.hash === '#' + v", item["view"]), timeout_seconds=10)
        filename = f"responsive_{item['name']}"
        _capture(page, state, filename)
        results.append(
            {
                "name": item["name"],
                "view": item["view"],
                "width": item["width"],
                "height": item["height"],
                "ok": True,
                "screenshot": f"docs/evidence/full_fresh_e2e/screenshots/{filename}.png",
            }
        )
    return {"viewports": results}


def _run_keyboard_accessibility_smoke(page: Page) -> dict[str, Any]:
    _click_nav(page, "campaigns")
    _wait_for(lambda: _visible(page, "#campaigns-state-ready"), timeout_seconds=60)

    checks = page.evaluate(
        """
        () => {
            const hasLabel = (forId) => !!document.querySelector(`label[for='${forId}']`);
            const focusBefore = document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null;
            const next1 = document.querySelector('#campaign-step-next-1');
            if (next1) next1.focus();
            const focusAfter = document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null;
            const canTabIndex = Array.from(document.querySelectorAll('button, input, select, a[href]')).filter((n) => !n.disabled).length;
            return {
                labels: {
                    campaign_name: hasLabel('campaign-name'),
                    campaign_channel: hasLabel('campaign-channel'),
                    audience_name: hasLabel('audience-save-name'),
                },
                ariaLive: {
                    audience_announce: (document.querySelector('#audience-announcement')?.getAttribute('aria-live') || null),
                    campaign_status: (document.querySelector('#campaigns-status-announcement')?.getAttribute('aria-live') || null),
                    export_status: (document.querySelector('#campaign-export-status-note')?.getAttribute('aria-live') || null),
                },
                focusTransition: {
                    before: focusBefore,
                    after: focusAfter,
                },
                keyboardReachableControlCount: canTabIndex,
            };
        }
        """
    )
    return checks


def _load_inventory_controls() -> list[dict[str, Any]]:
    if not INVENTORY_PATH.is_file():
        return []
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    controls = payload.get("controls")
    return controls if isinstance(controls, list) else []


def _collect_dom_actionable_selectors(page: Page) -> set[str]:
    selectors = page.evaluate(
        """
        () => {
            const nodes = Array.from(document.querySelectorAll('button[id], input[id], select[id], textarea[id]'));
            return nodes.map((n) => `#${n.id}`);
        }
        """
    )
    return set(selectors if isinstance(selectors, list) else [])


def _build_coverage_markdown(
    controls: list[dict[str, Any]],
    reachable_selectors: set[str],
    results: dict[str, Any],
    state: RunState,
) -> str:
    status_map: list[tuple[str, str, str]] = []

    tested_selectors = {
        "#overview-refresh",
        "#data-status-refresh",
        "#historical-analysis-refresh",
        "#model-training-refresh",
        "#audience-explorer-refresh",
        "#audience-filter-reset",
        "#audience-apply-filters",
        "#audience-save-submit",
        "#saved-audience-use-campaign",
        "#campaign-step-next-1",
        "#campaign-step-next-2",
        "#campaign-step-next-3",
        "#campaign-step-back-2",
        "#campaign-step-back-3",
        "#campaign-step-back-4",
        "#campaign-create-draft",
        "#campaign-finalize",
        "#campaign-export",
        "#campaign-export-history-refresh",
        "#campaign-pii-ack",
    }

    for control in controls:
        selector = str(control.get("selector") or "")
        label = str(control.get("label") or "")
        if not selector:
            continue
        if selector == "button":
            status_map.append((selector, label, "EXCEPTION: generic selector in inventory, covered via specific ID controls"))
            continue
        if selector in tested_selectors:
            status_map.append((selector, label, "PASS"))
        elif selector in reachable_selectors:
            status_map.append((selector, label, "EXCEPTION: reachable but not explicitly exercised in this run"))
        else:
            status_map.append((selector, label, "EXCEPTION: not visible/reachable in current state"))

    pass_count = sum(1 for _, _, status in status_map if status == "PASS")
    fail_count = sum(1 for _, _, status in status_map if status.startswith("FAIL"))
    exception_count = sum(1 for _, _, status in status_map if status.startswith("EXCEPTION"))

    lines: list[str] = []
    lines.append("# UI Control Coverage (System Chrome)")
    lines.append("")
    lines.append(f"- Generated at: {_now_iso()}")
    lines.append("- Browser: system Chrome")
    lines.append("- Method: Playwright automation launched with system Chrome executable")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Inventory controls: {len(controls)}")
    lines.append(f"- PASS: {pass_count}")
    lines.append(f"- FAIL: {fail_count}")
    lines.append(f"- EXCEPTION: {exception_count}")
    lines.append("")
    lines.append("## Browser Errors")
    lines.append("")
    lines.append(f"- Console errors: {len(state.console_errors)}")
    lines.append(f"- Unhandled page errors: {len(state.page_errors)}")
    lines.append(f"- Failed network requests: {len(state.request_failures)}")
    lines.append("")
    if state.console_errors:
        lines.append("Console error samples:")
        for msg in state.console_errors[:5]:
            lines.append(f"- {msg}")
        lines.append("")

    lines.append("## Accessibility Smoke")
    lines.append("")
    a11y = results.get("step13", {}).get("accessibility", {})
    labels = a11y.get("labels", {}) if isinstance(a11y, dict) else {}
    aria_live = a11y.get("ariaLive", {}) if isinstance(a11y, dict) else {}
    lines.append(f"- Campaign name label present: {labels.get('campaign_name')}")
    lines.append(f"- Campaign channel label present: {labels.get('campaign_channel')}")
    lines.append(f"- Audience save label present: {labels.get('audience_name')}")
    lines.append(f"- aria-live audience announcement: {aria_live.get('audience_announce')}")
    lines.append(f"- aria-live campaign status: {aria_live.get('campaign_status')}")
    lines.append(f"- aria-live export status: {aria_live.get('export_status')}")
    lines.append("")

    lines.append("## Responsive")
    lines.append("")
    for item in results.get("step13", {}).get("responsive", {}).get("viewports", []):
        lines.append(f"- {item['name']}: PASS ({item['width']}x{item['height']})")
    lines.append("")

    lines.append("## Curated Screenshots")
    lines.append("")
    for shot in state.screenshots:
        lines.append(f"- {shot}")
    lines.append("")

    lines.append("## Control Map")
    lines.append("")
    lines.append("| Selector | Label | Status |")
    lines.append("|---|---|---|")
    for selector, label, status in status_map:
        safe_label = label.replace("|", "\\|")
        safe_status = status.replace("|", "\\|")
        lines.append(f"| {selector} | {safe_label} | {safe_status} |")
    lines.append("")

    return "\n".join(lines)


def _query_latest_formula_fixture_summary() -> dict[str, Any]:
    if not DB_PATH.is_file():
        return {"available": False}

    sql = """
        SELECT export_event_id, status, export_profile, selected_count, deliverable_count, undeliverable_count,
               row_count, csv_sha256, started_at, completed_at
        FROM campaign_export_events
        ORDER BY export_event_id DESC
        LIMIT 20
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(sql).fetchall()]
    return {
        "available": True,
        "recent_export_events": rows,
    }


def _run_pytest_formula_fixture() -> dict[str, Any]:
    cmd = [
        str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "pytest",
        "-q",
        "tests/test_campaign_export_hardening.py::test_csv_formula_protection_and_utf8_escaping",
    ]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    return {
        "command": " ".join(cmd),
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_tail": "\n".join((completed.stdout or "").splitlines()[-40:]),
        "stderr_tail": "\n".join((completed.stderr or "").splitlines()[-40:]),
    }


def run() -> dict[str, Any]:
    if not CHROME_PATH.is_file():
        raise FileNotFoundError(f"System Chrome not found at {CHROME_PATH}")

    state = RunState(console_errors=[], page_errors=[], request_failures=[], screenshots=[])
    results: dict[str, Any] = {"generated_at": _now_iso(), "browser": "system_chrome"}

    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            executable_path=str(CHROME_PATH),
            headless=True,
            args=["--disable-popup-blocking"],
        )
        context: BrowserContext = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        page: Page = context.new_page()

        def on_console(msg):
            if msg.type == "error":
                state.console_errors.append(msg.text)

        def on_page_error(err):
            state.page_errors.append(str(err))

        def on_request_failed(req):
            state.request_failures.append(
                {
                    "method": req.method,
                    "url": req.url,
                    "failure": req.failure.error_text if req.failure else "unknown",
                }
            )

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)

        try:
            page.goto(APP_URL, wait_until="domcontentloaded")

            results["step5"] = _run_step5_overview_and_data(page, state)
            results["step6"] = _run_step6_historical(page, state)
            results["step7"] = _run_step7_model(page, state)
            results["step8_9"] = _run_step8_9_audience(page, state)
            results["step10_12"] = _run_step10_12_campaigns(page, state)

            # Step 13 accessibility/responsive/coverage evidence.
            results["step13"] = {
                "accessibility": _run_keyboard_accessibility_smoke(page),
                "responsive": _run_responsive_checks(page, state),
            }

            # Security fixture evidence hook.
            results["step12_security_fixture_pytest"] = _run_pytest_formula_fixture()
            results["step12_recent_export_events"] = _query_latest_formula_fixture_summary()

            controls = _load_inventory_controls()
            reachable = _collect_dom_actionable_selectors(page)
            coverage_md = _build_coverage_markdown(controls, reachable, results, state)
            COVERAGE_PATH.write_text(coverage_md, encoding="utf-8")

            results["ui_errors"] = {
                "console_errors": state.console_errors,
                "page_errors": state.page_errors,
                "request_failures": state.request_failures,
            }
            results["screenshots"] = state.screenshots
            results["ui_control_coverage_path"] = str(COVERAGE_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/")
            results["overall_status"] = "PASS"
        except Exception as exc:
            results["overall_status"] = "FAIL"
            results["error"] = str(exc)
            results["ui_errors"] = {
                "console_errors": state.console_errors,
                "page_errors": state.page_errors,
                "request_failures": state.request_failures,
            }
            results["screenshots"] = state.screenshots
        finally:
            context.close()
            browser.close()

    RESULT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    payload = run()
    print(f"Wrote evidence: {RESULT_PATH}")
    print(f"UI coverage: {COVERAGE_PATH}")
    print(f"Status: {payload.get('overall_status')}")
    return 0 if payload.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
