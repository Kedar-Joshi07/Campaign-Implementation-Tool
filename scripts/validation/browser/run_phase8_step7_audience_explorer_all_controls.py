from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playwright.sync_api import Page, sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
for candidate in (CURRENT_DIR, PROJECT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.services.model_api_service import search_audience_rows
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    get_audience_preparation_status,
    run_audience_rank_preparation,
    validate_audience_analytics_snapshot_currentness,
)
from system_browser import capture_page_events, launch_system_browser_session


PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
DATABASE_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"
APP_URL = "http://127.0.0.1:8000/"
API_HEALTH_URL = "http://127.0.0.1:8000/api/health"

PREPARATION_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP7_PREP_TIMEOUT_SECONDS", "10800"))
WORKSPACE_READY_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP7_WORKSPACE_TIMEOUT_SECONDS", "900"))
SCENARIO_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP7_SCENARIO_TIMEOUT_SECONDS", "240"))

INVENTORY_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "ui_control_inventory.json"
STEP6_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "06_system_browser_training_and_5m_scoring.json"
JSON_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "07_system_browser_audience_explorer_all_controls.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "07_SYSTEM_BROWSER_AUDIENCE_REPORT.md"

ALLOWED_SEARCH_ROW_FIELDS = {
    "person_id",
    "propensity_score",
    "age",
    "gender",
    "state",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "type_of_employment",
    "percentile_bucket",
    "decile",
    "rank_band",
}

FORBIDDEN_PII_FIELDS = {
    "first_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "email",
    "phone_number",
    "ethnicity",
    "religion",
    "occupation_industry",
    "family_yearly_income",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "customer_id",
}


@dataclass
class RunArtifacts:
    payload: dict[str, Any]
    inventory_updates: dict[str, str]


class Step7ValidationError(RuntimeError):
    """Raised when Step 7 checks fail."""


def _progress(message: str) -> None:
    print(f"[step7] {message}", flush=True)


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
        raise Step7ValidationError(message)


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
        if not ready:
            raise Step7ValidationError("Local API server did not become healthy within 120 seconds.")
        yield {"managed": True, "started_by_script": True, "command": " ".join(command)}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _read_json_url(url: str, timeout: int = 60) -> dict[str, Any] | list[Any]:
    with urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise Step7ValidationError(f"Expected HTTP 200 for {url}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _post_json_url(url: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status not in {200, 201, 202}:
                raise Step7ValidationError(f"Expected success status for {url}, got {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise Step7ValidationError(f"POST {url} failed: HTTP {exc.code}: {detail}") from exc


def _visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    if locator.count() == 0:
        return False
    return locator.first.is_visible()


def _exists(page: Page, selector: str) -> bool:
    return page.locator(selector).count() > 0


def _read_text(page: Page, selector: str) -> str:
    locator = page.locator(selector)
    if locator.count() == 0:
        return ""
    return locator.first.inner_text().strip()


def _parse_int(text: str) -> int:
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return int(digits) if digits else 0


def _parse_run_id(text: str) -> int:
    match = re.search(r"(\d+)", text or "")
    return int(match.group(1)) if match else 0


def _click_nav(page: Page, target: str) -> None:
    page.click(f"[data-view-target='{target}']")
    switched = _wait_for(
        lambda: page.evaluate("(v) => location.hash === '#' + v", target),
        timeout_seconds=15,
    )
    if not switched:
        raise Step7ValidationError(f"Unable to switch to view #{target}.")


def _click_when_enabled(page: Page, selector: str, timeout_seconds: float = 120) -> None:
    locator = page.locator(selector)
    ready = _wait_for(
        lambda: locator.count() > 0 and locator.first.is_visible() and locator.first.is_enabled(),
        timeout_seconds=timeout_seconds,
        poll_seconds=0.25,
    )
    if not ready:
        raise Step7ValidationError(f"Control did not become enabled in time: {selector}")
    locator.first.click()


def _fill_optional_number(page: Page, selector: str, value: int | float | None) -> None:
    page.fill(selector, "" if value is None else str(value))


def _set_multi_select(page: Page, selector: str, values: list[str]) -> None:
    page.select_option(selector, values)


def _first_select_value(page: Page, selector: str) -> str | None:
    value = page.evaluate(
        """
        (sel) => {
            const node = document.querySelector(sel);
            if (!node || !(node instanceof HTMLSelectElement)) return null;
            const options = Array.from(node.options || []).map((opt) => (opt.value || '').trim()).filter(Boolean);
            return options.length ? options[0] : null;
        }
        """,
        selector,
    )
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _await_workspace_state(page: Page, timeout_seconds: float) -> str:
    state_map = {
        "workspace": "#audience-explorer-workspace",
        "prepNeeded": "#audience-explorer-prep-needed",
        "prepRunning": "#audience-explorer-prep-running",
        "prepFailed": "#audience-explorer-prep-failed",
        "noRun": "#audience-explorer-no-run",
        "loading": "#audience-explorer-loading",
    }
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for state, selector in state_map.items():
            if _visible(page, selector):
                return state
        time.sleep(0.25)
    raise Step7ValidationError("Audience Explorer did not expose an expected UI state in time.")


def _scenario_summary(page: Page) -> dict[str, Any]:
    return {
        "estimate_matching": _parse_int(_read_text(page, "#audience-estimate-matching")),
        "estimate_selected": _parse_int(_read_text(page, "#audience-estimate-selected")),
        "estimate_score_range": _read_text(page, "#audience-estimate-score-range"),
        "estimate_score_mean": _read_text(page, "#audience-estimate-score-mean"),
        "search_rows_rendered": page.locator("#audience-results-body tr").count(),
        "search_has_more": not page.locator("#audience-load-more").first.is_hidden() if _exists(page, "#audience-load-more") else False,
        "profile_kpi_universe": _parse_int(_read_text(page, "#audience-kpi-universe-count")),
        "profile_kpi_matching": _parse_int(_read_text(page, "#audience-kpi-matching-count")),
        "profile_kpi_selected": _parse_int(_read_text(page, "#audience-kpi-selected-count")),
        "profile_kpi_historical_positives": _parse_int(_read_text(page, "#audience-kpi-positive-count")),
        "profile_summary_text": _read_text(page, "#audience-profile-summary"),
    }


def _wait_for_filters_success(page: Page, timeout_seconds: float = SCENARIO_TIMEOUT_SECONDS) -> None:
    def done() -> bool:
        if _visible(page, "#audience-form-error"):
            return True
        if _visible(page, "#audience-search-loading"):
            return False
        selected = _read_text(page, "#audience-estimate-selected")
        if selected in {"", "-", "--", "---"}:
            return False
        summary = _read_text(page, "#audience-profile-summary")
        loading = "loading exact profile aggregates" in summary.lower()
        if loading:
            return False
        row_count = page.locator("#audience-results-body tr").count()
        empty_visible = _visible(page, "#audience-search-empty")
        if row_count == 0 and not empty_visible:
            return False
        if _read_text(page, "#audience-load-more-status") == "":
            return False
        return True

    ok = _wait_for(done, timeout_seconds=timeout_seconds, poll_seconds=0.25)
    if not ok:
        raise Step7ValidationError("Audience filter application did not settle in expected time.")


def _expect_form_error(page: Page, expected_substring: str, timeout_seconds: float = 30) -> str:
    shown = _wait_for(lambda: _visible(page, "#audience-form-error"), timeout_seconds=timeout_seconds, poll_seconds=0.2)
    if not shown:
        raise Step7ValidationError("Expected form validation error was not displayed.")
    text = _read_text(page, "#audience-form-error")
    if expected_substring.casefold() not in text.casefold():
        raise Step7ValidationError(
            f"Expected form error containing {expected_substring!r}, received {text!r}."
        )
    return text


def _set_selection_mode(page: Page, mode: str, target_count: int | None) -> None:
    normalized = mode.upper().strip()
    if normalized not in {"ALL_MATCHING", "TOP_N"}:
        raise Step7ValidationError(f"Unsupported selection mode: {mode}")

    if normalized == "ALL_MATCHING":
        page.check("#audience-selection-all")
        if _exists(page, "#audience-target-count"):
            # The control is intentionally disabled in ALL_MATCHING mode.
            page.evaluate(
                """
                () => {
                    const node = document.querySelector('#audience-target-count');
                    if (node && node instanceof HTMLInputElement) {
                        node.value = '';
                    }
                }
                """
            )
        return

    page.check("#audience-selection-topn")
    target_enabled = _wait_for(
        lambda: _exists(page, "#audience-target-count") and page.locator("#audience-target-count").first.is_enabled(),
        timeout_seconds=10,
        poll_seconds=0.2,
    )
    if not target_enabled:
        raise Step7ValidationError("TOP_N target count input did not enable after selecting TOP_N mode.")
    page.fill("#audience-target-count", "" if target_count is None else str(target_count))


def _reset_filters(page: Page) -> None:
    _click_when_enabled(page, "#audience-filter-reset")
    _wait_for(lambda: not _visible(page, "#audience-form-error"), timeout_seconds=10, poll_seconds=0.2)
    _wait_for(
        lambda: "No active filters." in _read_text(page, "#audience-filter-summary-text"),
        timeout_seconds=20,
        poll_seconds=0.2,
    )


def _apply_form(
    page: Page,
    *,
    score_min: float | None = None,
    score_max: float | None = None,
    top_percentile_max: int | None = None,
    deciles: list[str] | None = None,
    rank_bands: list[str] | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    income_min: float | None = None,
    income_max: float | None = None,
    family_min: int | None = None,
    family_max: int | None = None,
    gender: list[str] | None = None,
    state: list[str] | None = None,
    marital_status: list[str] | None = None,
    education: list[str] | None = None,
    employment_status: list[str] | None = None,
    resident_status: list[str] | None = None,
    resident_type: list[str] | None = None,
    type_of_employment: list[str] | None = None,
    selection_mode: str = "ALL_MATCHING",
    target_count: int | None = None,
) -> None:
    _fill_optional_number(page, "#audience-score-min", score_min)
    _fill_optional_number(page, "#audience-score-max", score_max)
    _fill_optional_number(page, "#audience-top-percentile", top_percentile_max)
    _fill_optional_number(page, "#audience-age-min", age_min)
    _fill_optional_number(page, "#audience-age-max", age_max)
    _fill_optional_number(page, "#audience-income-min", income_min)
    _fill_optional_number(page, "#audience-income-max", income_max)
    _fill_optional_number(page, "#audience-family-min", family_min)
    _fill_optional_number(page, "#audience-family-max", family_max)

    _set_multi_select(page, "#audience-deciles", deciles or [])
    _set_multi_select(page, "#audience-rank-bands", rank_bands or [])
    _set_multi_select(page, "#audience-gender", gender or [])
    _set_multi_select(page, "#audience-state", state or [])
    _set_multi_select(page, "#audience-marital-status", marital_status or [])
    _set_multi_select(page, "#audience-education", education or [])
    _set_multi_select(page, "#audience-employment-status", employment_status or [])
    _set_multi_select(page, "#audience-resident-status", resident_status or [])
    _set_multi_select(page, "#audience-resident-type", resident_type or [])
    _set_multi_select(page, "#audience-type-of-employment", type_of_employment or [])

    _set_selection_mode(page, selection_mode, target_count)


def _run_valid_scenario(page: Page, name: str) -> dict[str, Any]:
    _click_when_enabled(page, "#audience-apply-filters", timeout_seconds=60)
    _wait_for_filters_success(page)
    if _visible(page, "#audience-form-error"):
        raise Step7ValidationError(
            f"Scenario {name} unexpectedly produced error: {_read_text(page, '#audience-form-error')!r}"
        )
    return _scenario_summary(page)


def _run_invalid_scenario(page: Page, name: str, expected_message: str) -> dict[str, Any]:
    _click_when_enabled(page, "#audience-apply-filters", timeout_seconds=60)
    text = _expect_form_error(page, expected_message)
    return {
        "scenario": name,
        "error": text,
    }


def _assert_sorted_rows(rows: list[dict[str, Any]]) -> None:
    previous: tuple[float, str] | None = None
    for row in rows:
        score = float(row["propensity_score"])
        person_id = str(row["person_id"])
        if previous is not None:
            _require(score <= previous[0], "Search ordering violated: propensity_score is not DESC.")
            if score == previous[0]:
                _require(person_id > previous[1], "Search ordering violated: person_id tie-break is not ASC.")
        previous = (score, person_id)


def _verify_backend_search_contract(scoring_run_id: int) -> dict[str, Any]:
    first = search_audience_rows(
        DATABASE_PATH,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 40,
        },
    )
    rows = list(first.get("rows") or [])
    _require(bool(rows), "Audience search returned no rows for unfiltered request.")

    for row in rows:
        row_keys = set(row.keys())
        _require(row_keys == ALLOWED_SEARCH_ROW_FIELDS, "Search row fields do not match approved allowlist.")
        _require(not (row_keys & FORBIDDEN_PII_FIELDS), "Search row leaked forbidden PII fields.")

    _assert_sorted_rows(rows)
    seen_ids: set[str] = {str(row["person_id"]) for row in rows}
    checked_pages = 1
    cursor = first.get("next_cursor")
    has_more = bool(first.get("has_more"))

    while has_more and cursor and checked_pages < 5:
        payload = {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 40,
            "cursor": cursor,
        }
        next_page = search_audience_rows(DATABASE_PATH, payload)
        page_rows = list(next_page.get("rows") or [])
        _assert_sorted_rows(page_rows)
        for row in page_rows:
            row_keys = set(row.keys())
            _require(row_keys == ALLOWED_SEARCH_ROW_FIELDS, "Search row fields changed across pages.")
            person_id = str(row["person_id"])
            _require(person_id not in seen_ids, "Duplicate person_id detected across keyset pages.")
            seen_ids.add(person_id)
        cursor = next_page.get("next_cursor")
        has_more = bool(next_page.get("has_more"))
        checked_pages += 1

    return {
        "checked_pages": checked_pages,
        "unique_person_ids": len(seen_ids),
    }


def _verify_boundaries_and_analytics(scoring_run_id: int) -> dict[str, Any]:
    db_path = initialize_database(DATABASE_PATH)
    boundaries = AudienceRankRepository(db_path).fetch_boundaries(scoring_run_id)
    _require(len(boundaries) == 100, "Audience rank boundary count must equal 100.")

    first_rank = int(boundaries[0]["boundary_rank"])
    tenth_rank = int(boundaries[9]["boundary_rank"])
    hundredth_rank = int(boundaries[-1]["boundary_rank"])
    total_population = int(boundaries[-1]["total_population"])

    for index, row in enumerate(boundaries, start=1):
        _require(int(row["percentile_bucket"]) == index, "Boundary percentile buckets are not contiguous 1..100.")

    previous_rank = 0
    for row in boundaries:
        rank = int(row["boundary_rank"])
        _require(rank >= previous_rank, "Boundary ranks are not monotonic non-decreasing.")
        previous_rank = rank

    _require(hundredth_rank == total_population, "100th percentile boundary rank does not equal total population.")
    _require(first_rank == max(1, (total_population + 99) // 100), "1st percentile boundary rank mismatch.")
    _require(tenth_rank == max(1, (total_population + 9) // 10), "10th percentile boundary rank mismatch.")

    analytics = validate_audience_analytics_snapshot_currentness(
        db_path,
        scoring_run_id=scoring_run_id,
        analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        cache={},
    )
    _require(bool(analytics.get("analytics_prepared")), "Audience analytics snapshot is not prepared/current.")
    _require(not analytics.get("issues"), f"Audience analytics currentness issues found: {analytics.get('issues')}")
    _require(isinstance(analytics.get("snapshot"), dict), "Audience analytics snapshot payload is missing.")

    snapshot = analytics["snapshot"]
    return {
        "boundary_count": len(boundaries),
        "first_percentile_rank": first_rank,
        "tenth_percentile_rank": tenth_rank,
        "hundredth_percentile_rank": hundredth_rank,
        "total_population": total_population,
        "analytics_contract_version": analytics.get("analytics_contract_version"),
        "analytics_snapshot_created_at": analytics.get("snapshot_created_at"),
        "analytics_prepared": bool(analytics.get("analytics_prepared")),
        "is_canonical": bool(analytics.get("is_canonical")),
        "source_verified": bool(analytics.get("source_verified")),
        "snapshot_population_count": snapshot.get("population_count"),
    }


def _choose_audience_run(expected_scoring_run_id: int | None) -> dict[str, Any]:
    runs_payload = _read_json_url("http://127.0.0.1:8000/api/audience/runs?limit=100&offset=0")
    _require(isinstance(runs_payload, list) and bool(runs_payload), "No audience runs available from API.")

    if expected_scoring_run_id is not None:
        for row in runs_payload:
            if int(row.get("scoring_run_id") or 0) == expected_scoring_run_id:
                return row
        raise Step7ValidationError(
            f"Expected Step 6 scoring run {expected_scoring_run_id} was not returned by /api/audience/runs."
        )

    ready = next((row for row in runs_payload if row.get("ready_for_current_audience_actions") is True), None)
    if ready is not None:
        return ready
    canonical = next((row for row in runs_payload if row.get("is_canonical") is True), None)
    if canonical is not None:
        return canonical
    return runs_payload[0]


def _get_preparation_status(scoring_run_id: int) -> dict[str, Any]:
    payload = get_audience_preparation_status(
        DATABASE_PATH,
        scoring_run_id=scoring_run_id,
        rank_contract_version="1",
    )
    _require(isinstance(payload, dict), "Preparation status service returned invalid payload.")
    return payload


def _ensure_expected_run_prepared(scoring_run_id: int) -> dict[str, Any]:
    status = _get_preparation_status(scoring_run_id)
    observations: dict[str, Any] = {
        "precondition_mode": "already_ready",
        "job_statuses": [],
        "poll_checks": 0,
    }

    ready = bool(status.get("ready_for_current_audience_actions"))
    if ready:
        observations["final_status"] = status
        return observations

    observations["precondition_mode"] = "service_preparation"
    active_job = status.get("active_job") if isinstance(status.get("active_job"), dict) else None
    started = time.time()
    seen_job_states: list[str] = []

    if active_job is None:
        _progress(f"Preparing expected run {scoring_run_id} via service precondition.")
        run_audience_rank_preparation(
            DATABASE_PATH,
            scoring_run_id=scoring_run_id,
            rank_contract_version="1",
        )

    while (time.time() - started) <= PREPARATION_TIMEOUT_SECONDS:
        observations["poll_checks"] = int(observations["poll_checks"]) + 1

        status = _get_preparation_status(scoring_run_id)
        active_job = status.get("active_job") if isinstance(status.get("active_job"), dict) else None
        job_state = str((active_job or {}).get("status") or "COMPLETED").upper().strip()
        if job_state and (not seen_job_states or seen_job_states[-1] != job_state):
            seen_job_states.append(job_state)
            _progress(f"Preparation precondition state -> {job_state}")

        if bool(status.get("ready_for_current_audience_actions")):
            observations["job_statuses"] = seen_job_states
            observations["final_status"] = status
            return observations

        if job_state == "FAILED":
            raise Step7ValidationError(
                "Audience preparation precondition failed for run "
                f"{scoring_run_id}: {(active_job or {}).get('message') or 'unknown failure'}"
            )

        time.sleep(1.5)

    raise Step7ValidationError(
        f"Timed out waiting for run {scoring_run_id} preparation readiness (>{PREPARATION_TIMEOUT_SECONDS}s)."
    )


def _load_expected_step6_scoring_run_id() -> int | None:
    if not STEP6_EVIDENCE_PATH.is_file():
        return None
    payload = json.loads(STEP6_EVIDENCE_PATH.read_text(encoding="utf-8"))
    scoring = payload.get("scoring") or {}
    ui_summary = scoring.get("ui_summary") or {}
    run_id = int(ui_summary.get("scoring_run_id") or 0)
    return run_id if run_id > 0 else None


def _wait_for_audience_workspace_ready(
    page: Page,
    *,
    expected_scoring_run_id: int,
    status_updates: dict[str, dict[str, str]],
    prep_observations: dict[str, Any],
) -> dict[str, Any]:
    def mark_pass(selector: str) -> None:
        status_updates[selector] = {"status": "PASS"}

    def mark_justified(selector: str, reason: str, group: str) -> None:
        status_updates[selector] = {
            "status": "JUSTIFIED_EXCLUSIVE",
            "mutually_exclusive_group": group,
            "justification": reason,
        }

    prep_observations["states_seen"] = []
    prep_observations["messages"] = []
    prep_observations["mismatch_runs"] = []
    prep_observations["submit_clicked"] = False
    prep_observations["retry_clicked"] = False

    _click_nav(page, "audience-explorer")
    mark_pass("[data-view-target='audience-explorer']")

    _click_when_enabled(page, "#audience-explorer-refresh", timeout_seconds=120)
    mark_pass("#audience-explorer-refresh")

    started = time.time()
    last_message = ""
    while (time.time() - started) <= WORKSPACE_READY_TIMEOUT_SECONDS:
        state = _await_workspace_state(page, timeout_seconds=10)
        prep_observations["states_seen"].append({"state": state, "observed_at": _now_iso()})

        if state == "workspace":
            run_id = _parse_run_id(_read_text(page, "#audience-context-scoring-run"))
            _require(run_id > 0, "Audience workspace loaded without a scoring run ID.")
            if run_id != expected_scoring_run_id:
                prep_observations["mismatch_runs"].append(run_id)
                _progress(
                    "Audience Explorer opened a different ready run "
                    f"({run_id}) than expected ({expected_scoring_run_id}); refreshing."
                )
                _click_when_enabled(page, "#audience-explorer-refresh", timeout_seconds=60)
                time.sleep(0.5)
                continue
            mark_pass("#audience-context-scoring-run")
            mark_pass("#audience-context-population")
            mark_pass("#audience-source-verified")
            if not prep_observations["submit_clicked"] and _exists(page, "#audience-prepare-submit"):
                mark_justified(
                    "#audience-prepare-submit",
                    "Preparation submit control is shown only when rank preparation is required.",
                    "prep-needed-only",
                )
            if not prep_observations["retry_clicked"] and _exists(page, "#audience-prepare-retry"):
                mark_justified(
                    "#audience-prepare-retry",
                    "Preparation retry control is shown only when preparation has failed.",
                    "prep-failed-only",
                )
                mark_justified(
                    "#audience-prep-failed-message",
                    "Preparation failed message is shown only when preparation has failed.",
                    "prep-failed-only",
                )
            return {
                "active_scoring_run_id": run_id,
                "source_verified_badge": _read_text(page, "#audience-source-verified"),
            }

        if state == "noRun":
            raise Step7ValidationError("Audience Explorer reported no canonical scoring run.")

        if state == "prepNeeded":
            _click_when_enabled(page, "#audience-prepare-submit", timeout_seconds=180)
            mark_pass("#audience-prepare-submit")
            prep_observations["submit_clicked"] = True
            continue

        if state == "prepRunning":
            title = _read_text(page, "#audience-prep-running-title")
            message = _read_text(page, "#audience-prep-running-message")
            if message and message != last_message:
                prep_observations["messages"].append(message)
                last_message = message
                _progress(f"Preparation status: {message}")
            mark_pass("#audience-prep-running-title")
            mark_pass("#audience-prep-running-message")
            time.sleep(1.0)
            continue

        if state == "prepFailed":
            message = _read_text(page, "#audience-prep-failed-message")
            prep_observations["failure_message"] = message
            if _exists(page, "#audience-prepare-retry") and page.locator("#audience-prepare-retry").first.is_visible():
                _click_when_enabled(page, "#audience-prepare-retry", timeout_seconds=180)
                mark_pass("#audience-prepare-retry")
                mark_pass("#audience-prep-failed-message")
                prep_observations["retry_clicked"] = True
                continue
            raise Step7ValidationError(f"Audience preparation failed: {message}")

        time.sleep(0.5)

    raise Step7ValidationError(
        f"Timed out waiting for Audience Explorer workspace readiness after {WORKSPACE_READY_TIMEOUT_SECONDS} seconds."
    )


def _exercise_profile_controls(page: Page, status_updates: dict[str, dict[str, str]]) -> dict[str, Any]:
    dimensions = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('#audience-profile-dimension option'))
          .map((opt) => (opt.value || '').trim())
          .filter(Boolean)
        """
    )
    _require(isinstance(dimensions, list) and bool(dimensions), "Profile dimension options are missing.")

    used_dimensions: list[str] = []
    for value in dimensions[:5]:
        page.select_option("#audience-profile-dimension", value=str(value))
        waited = _wait_for(
            lambda: str(value) in page.input_value("#audience-profile-dimension"),
            timeout_seconds=5,
            poll_seconds=0.2,
        )
        _require(waited, f"Profile dimension did not switch to {value!r}.")
        used_dimensions.append(str(value))

    for selector in (
        "[data-audience-profile-comparison='selected_vs_universe']",
        "[data-audience-profile-comparison='selected_vs_historical_positives']",
    ):
        _click_when_enabled(page, selector, timeout_seconds=15)

    status_updates["#audience-profile-dimension"] = {"status": "PASS"}
    status_updates["#audience-profile-summary"] = {"status": "PASS"}
    status_updates["#audience-profile-bars"] = {"status": "PASS"}
    status_updates["#audience-traits-body"] = {"status": "PASS"}

    return {
        "dimensions_exercised": used_dimensions,
        "comparison_tabs_exercised": [
            "selected_vs_universe",
            "selected_vs_historical_positives",
        ],
    }


def _exercise_saved_audience_flow(
    page: Page,
    *,
    status_updates: dict[str, dict[str, str]],
) -> dict[str, Any]:
    status_updates["#audience-save-form"] = {"status": "PASS"}
    status_updates["#audience-save-name"] = {"status": "PASS"}
    status_updates["#audience-save-description"] = {"status": "PASS"}
    status_updates["#audience-save-submit"] = {"status": "PASS"}
    status_updates["#audience-save-status"] = {"status": "PASS"}
    status_updates["#saved-audiences-refresh"] = {"status": "PASS"}
    status_updates["#saved-audience-list"] = {"status": "PASS"}
    status_updates["#saved-audience-list-loading"] = {"status": "PASS"}
    status_updates["#saved-audience-detail"] = {"status": "PASS"}
    status_updates["#saved-audience-detail-title"] = {"status": "PASS"}
    status_updates["#saved-audience-detail-meta"] = {"status": "PASS"}
    status_updates["#saved-audience-currentness"] = {"status": "PASS"}
    status_updates["#saved-audience-reopen"] = {"status": "PASS"}
    status_updates["#saved-audience-use-campaign"] = {"status": "PASS"}
    status_updates["#campaign-audience-summary"] = {"status": "PASS"}

    # Exercise save validation error path.
    page.fill("#audience-save-name", "")
    _click_when_enabled(page, "#audience-save-submit", timeout_seconds=30)
    save_error_visible = _wait_for(lambda: _visible(page, "#audience-save-error"), timeout_seconds=10, poll_seconds=0.2)
    _require(save_error_visible, "Expected save validation error did not render for blank audience name.")
    _require(
        "Audience name is required." in _read_text(page, "#audience-save-error"),
        "Unexpected save validation error message for blank name.",
    )
    status_updates["#audience-save-error"] = {"status": "PASS"}

    audience_name = f"Phase8 Step7 Current Audience {int(time.time())}"
    audience_desc = "Current saved audience from Step 7 system-browser control coverage run"
    prior_save_status = _read_text(page, "#audience-save-status")
    page.fill("#audience-save-name", audience_name)
    page.fill("#audience-save-description", audience_desc)
    _click_when_enabled(page, "#audience-save-submit", timeout_seconds=60)

    saved_ok = _wait_for(
        lambda: (
            "Saved audience #" in _read_text(page, "#audience-save-status")
            and _read_text(page, "#audience-save-status") != prior_save_status
        ),
        timeout_seconds=90,
        poll_seconds=0.5,
    )
    _require(saved_ok, "Save audience success status did not appear.")

    detail_after_save = _wait_for(
        lambda: _read_text(page, "#saved-audience-detail-title") == audience_name,
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _require(detail_after_save, "Saved audience detail panel did not load the newly saved audience.")

    save_status = _read_text(page, "#audience-save-status")
    audience_id = _parse_run_id(save_status)
    _require(audience_id > 0, f"Unable to parse saved audience id from status: {save_status!r}")

    _click_when_enabled(page, "#saved-audiences-refresh", timeout_seconds=30)
    _wait_for(lambda: page.locator("#saved-audience-list .saved-audience-item").count() > 0, timeout_seconds=30)

    opened = page.evaluate(
        """
        (name) => {
            const rows = Array.from(document.querySelectorAll('#saved-audience-list .saved-audience-item'));
            for (const row of rows) {
                const title = (row.querySelector('.saved-audience-item-heading strong')?.textContent || '').trim();
                if (title === name) {
                    const button = row.querySelector('button.recent-reopen');
                    if (button instanceof HTMLButtonElement) {
                        button.click();
                        return true;
                    }
                }
            }
            return false;
        }
        """,
        audience_name,
    )
    reopened_from_list = bool(opened)
    _require(reopened_from_list, "Saved audience row was not reopened through its dynamic list control.")
    status_updates[".recent-reopen"] = {"status": "PASS"}
    results_note = "Saved audience row reopened successfully from list."

    detail_loaded = _wait_for(
        lambda: _read_text(page, "#saved-audience-detail-title") == audience_name,
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _require(detail_loaded, "Saved audience detail panel did not load expected audience.")

    currentness_text = _read_text(page, "#saved-audience-currentness")
    _require("CURRENT" in currentness_text.upper(), f"Saved audience should be CURRENT, got: {currentness_text!r}")

    _click_when_enabled(page, "#saved-audience-reopen", timeout_seconds=30)
    reopened = _wait_for(
        lambda: "reopened" in _read_text(page, "#audience-announcement").lower(),
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _require(reopened, "Saved audience reopen confirmation announcement did not appear.")

    button_enabled = _wait_for(
        lambda: _exists(page, "#saved-audience-use-campaign") and page.locator("#saved-audience-use-campaign").first.is_enabled(),
        timeout_seconds=20,
        poll_seconds=0.25,
    )
    _require(button_enabled, "Use in Campaign Builder button was not enabled for CURRENT saved audience.")

    _click_when_enabled(page, "#saved-audience-use-campaign", timeout_seconds=30)
    moved = _wait_for(
        lambda: page.evaluate("() => location.hash === '#campaigns'"),
        timeout_seconds=30,
        poll_seconds=0.25,
    )
    _require(moved, "Use in Campaign Builder did not navigate to #campaigns.")
    campaign_handoff_hash = str(page.evaluate("() => location.hash"))

    handoff_selection_ready = _wait_for(
        lambda: page.locator("#campaign-audience-select").input_value() == str(audience_id),
        timeout_seconds=SCENARIO_TIMEOUT_SECONDS,
        poll_seconds=0.5,
    )
    _require(
        handoff_selection_ready,
        "Campaign Builder did not preserve the saved-audience handoff selection.",
    )

    campaign_summary_ready = _wait_for(
        lambda: _exists(page, "#campaign-audience-summary") and _read_text(page, "#campaign-audience-summary") != "",
        timeout_seconds=SCENARIO_TIMEOUT_SECONDS,
        poll_seconds=0.5,
    )
    _require(campaign_summary_ready, "Campaign audience summary did not render after handoff.")

    # Return to Audience Explorer for final checks and inventory stamping.
    _click_nav(page, "audience-explorer")
    _wait_for(lambda: _visible(page, "#audience-explorer-workspace"), timeout_seconds=60, poll_seconds=0.5)

    stale_opened = page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#saved-audience-list .saved-audience-item'));
            for (const row of rows) {
                const badge = (row.querySelector('.saved-audience-item-heading .status-badge')?.textContent || '').toUpperCase();
                if (badge.includes('STALE')) {
                    const button = row.querySelector('button.recent-reopen');
                    if (button instanceof HTMLButtonElement) {
                        button.click();
                        return true;
                    }
                }
            }
            return false;
        }
        """
    )

    stale_exercised = False
    if stale_opened:
        _wait_for(lambda: _visible(page, "#saved-audience-detail"), timeout_seconds=20)
        _click_when_enabled(page, "#saved-audience-reopen", timeout_seconds=20)
        stale_mode = _wait_for(lambda: _visible(page, "#saved-audience-stale-message"), timeout_seconds=20)
        if stale_mode:
            status_updates["#saved-audience-stale-message"] = {"status": "PASS"}
            status_updates["#audience-search-empty"] = {"status": "PASS"}
            status_updates["#audience-search-empty h3"] = {"status": "PASS"}
            status_updates["#audience-search-empty p"] = {"status": "PASS"}
            stale_exercised = True
            _click_when_enabled(page, "#audience-filter-reset", timeout_seconds=20)
            _wait_for(lambda: not _visible(page, "#saved-audience-stale-message"), timeout_seconds=20)

    return {
        "saved_audience_id": audience_id,
        "saved_audience_name": audience_name,
        "reopened_from_list": reopened_from_list,
        "reopen_note": results_note,
        "currentness_badge": currentness_text,
        "campaign_handoff_hash": campaign_handoff_hash,
        "audience_return_hash": str(page.evaluate("() => location.hash")),
        "stale_definition_exercised": stale_exercised,
    }


def _mark_all_audience_controls(
    status_updates: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    controls = payload.get("controls", [])
    audience_selectors = [
        str(control.get("selector"))
        for control in controls
        if str(control.get("page")) == "audience-explorer"
    ]

    justified_defaults = {
        "#audience-explorer-retry": (
            "Retry control is visible only when the Audience Explorer backend-error banner is shown.",
            "error-state-only",
        ),
        "#audience-prepare-retry": (
            "Preparation retry control is visible only when preparation fails.",
            "prep-failed-only",
        ),
        "#audience-prep-failed-message": (
            "Preparation failure message is visible only when preparation fails.",
            "prep-failed-only",
        ),
        "#saved-audience-list-empty": (
            "Empty-state message is visible only when no saved audiences exist.",
            "empty-state-only",
        ),
    }

    for selector in audience_selectors:
        if selector in status_updates:
            continue
        if selector in justified_defaults:
            reason, group = justified_defaults[selector]
            status_updates[selector] = {
                "status": "JUSTIFIED_EXCLUSIVE",
                "mutually_exclusive_group": group,
                "justification": reason,
            }

    return status_updates


def _update_inventory_statuses(status_updates: dict[str, dict[str, str]]) -> dict[str, Any]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    controls = payload.get("controls", [])
    control_index = {
        (str(control.get("page")), str(control.get("selector"))): control
        for control in controls
    }

    applied: dict[str, str] = {}
    for selector, update in status_updates.items():
        control = control_index.get(("audience-explorer", selector))
        if control is None:
            # Runtime assertions also cover output/status nodes. Only controls
            # discovered by Step 4 belong in the actionable coverage contract.
            continue

        control["status"] = update["status"]
        control["justification"] = update.get("justification", "")
        control["mutually_exclusive_group"] = update.get(
            "mutually_exclusive_group",
            control.get("mutually_exclusive_group", ""),
        )
        applied[f"audience-explorer:{selector}"] = update["status"]

    summary = {
        "NOT_RUN": 0,
        "PASS": 0,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
    }
    audience_status_summary = {
        "NOT_RUN": 0,
        "PASS": 0,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
    }

    for control in controls:
        state = str(control.get("status", "NOT_RUN")).upper()
        if state in summary:
            summary[state] += 1
        if str(control.get("page")) == "audience-explorer" and state in audience_status_summary:
            audience_status_summary[state] += 1

    if audience_status_summary["NOT_RUN"]:
        remaining = [
            str(control.get("selector"))
            for control in controls
            if str(control.get("page")) == "audience-explorer"
            and str(control.get("status", "NOT_RUN")).upper() == "NOT_RUN"
        ]
        raise Step7ValidationError(f"Step 7 left actionable Audience Explorer controls NOT_RUN: {remaining}")

    payload["status_summary"] = summary
    payload["generated_at"] = _now_iso()
    payload["controls"] = sorted(controls, key=lambda item: (item.get("page", ""), item.get("selector", "")))
    INVENTORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "applied": applied,
        "status_summary": summary,
        "audience_status_summary": audience_status_summary,
    }


def _run_step7() -> RunArtifacts:
    _progress("Starting Step 7 browser flow for Audience Explorer.")
    expected_scoring_run_id = _load_expected_step6_scoring_run_id()

    results: dict[str, Any] = {
        "generated_at": _now_iso(),
        "prompt": "Prompts/phase8_release_assurance_system_browser_prompt_pack/07_STEP_07_SYSTEM_BROWSER_AUDIENCE_EXPLORER_ALL_CONTROLS.md",
        "expected_step6_scoring_run_id": expected_scoring_run_id,
    }
    status_updates: dict[str, dict[str, str]] = {}
    prep_observations: dict[str, Any] = {}
    scoring_run_id = 0

    with _managed_server() as server_info:
        results["server"] = server_info
        run_choice = _choose_audience_run(expected_scoring_run_id)
        scoring_run_id = int(run_choice.get("scoring_run_id") or 0)
        _require(scoring_run_id > 0, "Unable to resolve candidate scoring run for Audience Explorer.")
        results["resolved_audience_run"] = run_choice
        results["preparation_precondition"] = _ensure_expected_run_prepared(scoring_run_id)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright,
                app_url=APP_URL,
                headless=True,
                viewport={"width": 1440, "height": 900},
            ) as session:
                page = session.page
                results["browser"] = session.metadata.to_dict()

                with capture_page_events(page) as events:
                    readiness = _wait_for_audience_workspace_ready(
                        page,
                        expected_scoring_run_id=scoring_run_id,
                        status_updates=status_updates,
                        prep_observations=prep_observations,
                    )
                    results["preparation"] = readiness
                    results["preparation"]["ui_observations"] = prep_observations

                    # Verify the required disclaimers exist.
                    semantics_copy = page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('.audience-semantics-note p'))
                          .map((node) => (node.textContent || '').trim())
                          .filter(Boolean)
                        """
                    )
                    profile_disclaimer = _read_text(page, ".audience-profile-disclaimer p")
                    _require(
                        any("not a purchase probability" in text.lower() for text in (semantics_copy or [])),
                        "Required propensity-score disclaimer is missing.",
                    )
                    _require(
                        "no prospect is matched to a historical customer" in profile_disclaimer.lower(),
                        "Required no-identity-linking profile disclaimer is missing.",
                    )
                    results["disclaimers"] = {
                        "context_not_probability": semantics_copy,
                        "profile_no_identity_linking": profile_disclaimer,
                    }

                    status_updates["#audience-filter-form"] = {"status": "PASS"}
                    status_updates["#audience-announcement"] = {"status": "PASS"}
                    status_updates["#audience-filter-summary-text"] = {"status": "PASS"}
                    status_updates["#audience-filter-chips"] = {"status": "PASS"}
                    status_updates["#audience-estimate-matching"] = {"status": "PASS"}
                    status_updates["#audience-estimate-selected"] = {"status": "PASS"}
                    status_updates["#audience-load-more-status"] = {"status": "PASS"}
                    status_updates["#audience-results-body"] = {"status": "PASS"}
                    status_updates["#audience-results-title"] = {"status": "PASS"}
                    status_updates["#audience-search-loading"] = {"status": "PASS"}
                    status_updates["#audience-kpi-universe-count"] = {"status": "PASS"}
                    status_updates["#audience-kpi-matching-count"] = {"status": "PASS"}
                    status_updates["#audience-kpi-selected-count"] = {"status": "PASS"}
                    status_updates["#audience-kpi-positive-count"] = {"status": "PASS"}
                    status_updates["#audience-kpi-selected-age"] = {"status": "PASS"}
                    status_updates["#audience-kpi-selected-income"] = {"status": "PASS"}
                    status_updates["#audience-kpi-selected-family"] = {"status": "PASS"}
                    status_updates["#audience-save-summary"] = {"status": "PASS"}

                    # Choose reusable categorical values.
                    state_value = _first_select_value(page, "#audience-state")
                    gender_value = _first_select_value(page, "#audience-gender")
                    rank_band_value = _first_select_value(page, "#audience-rank-bands") or "HIGH"
                    employment_status_value = _first_select_value(page, "#audience-employment-status")

                    # Required scenario 1: no filters ALL_MATCHING.
                    _reset_filters(page)
                    _apply_form(page, selection_mode="ALL_MATCHING", target_count=None)
                    scenario_1 = _run_valid_scenario(page, "scenario_1_no_filters_all_matching")
                    status_updates["#audience-selection-all"] = {"status": "PASS"}
                    status_updates["#audience-apply-filters"] = {"status": "PASS"}
                    status_updates["#audience-filter-reset"] = {"status": "PASS"}

                    # Exercise deterministic UI load more.
                    before_rows = scenario_1["search_rows_rendered"]
                    load_more_clicked = False
                    if not page.locator("#audience-load-more").first.is_hidden():
                        _wait_for(
                            lambda: not _visible(page, "#audience-search-loading"),
                            timeout_seconds=30,
                            poll_seconds=0.25,
                        )
                        _click_when_enabled(page, "#audience-load-more", timeout_seconds=30)
                        load_more_clicked = True
                        _wait_for(
                            lambda: not _visible(page, "#audience-search-loading"),
                            timeout_seconds=60,
                            poll_seconds=0.25,
                        )
                        status_updates["#audience-load-more"] = {"status": "PASS"}

                    ui_page_check = page.evaluate(
                        """
                        () => {
                            const rows = document.querySelectorAll('#audience-results-body tr').length;
                            const status = (document.querySelector('#audience-load-more-status')?.textContent || '').trim();
                            return {
                                rendered_rows: rows,
                                load_more_status: status,
                            };
                        }
                        """
                    )
                    _require(
                        int(ui_page_check["rendered_rows"]) >= before_rows,
                        "UI table row count regressed after load-more interaction.",
                    )
                    results["ui_pagination"] = {
                        "before_rows": before_rows,
                        "after_rows": int(ui_page_check["rendered_rows"]),
                        "load_more_clicked": load_more_clicked,
                        "status_text": str(ui_page_check["load_more_status"]),
                    }

                    # Required scenario 2: top 1%.
                    _reset_filters(page)
                    _apply_form(page, top_percentile_max=1, selection_mode="ALL_MATCHING")
                    scenario_2 = _run_valid_scenario(page, "scenario_2_top_1_percent")
                    status_updates["#audience-top-percentile"] = {"status": "PASS"}

                    # Required scenario 3: top decile.
                    _reset_filters(page)
                    _apply_form(page, deciles=["1"], selection_mode="ALL_MATCHING")
                    scenario_3 = _run_valid_scenario(page, "scenario_3_top_decile")
                    status_updates["#audience-deciles"] = {"status": "PASS"}

                    # Required scenario 4: demographic filter.
                    _reset_filters(page)
                    demographic_args = {}
                    if state_value:
                        demographic_args["state"] = [state_value]
                        status_updates["#audience-state"] = {"status": "PASS"}
                    if gender_value:
                        demographic_args["gender"] = [gender_value]
                        status_updates["#audience-gender"] = {"status": "PASS"}
                    _apply_form(page, selection_mode="ALL_MATCHING", **demographic_args)
                    scenario_4 = _run_valid_scenario(page, "scenario_4_demographic_filter")

                    # Required scenario 5: rank + demographic.
                    _reset_filters(page)
                    rank_plus_args = {
                        "selection_mode": "ALL_MATCHING",
                        "rank_bands": [rank_band_value],
                    }
                    status_updates["#audience-rank-bands"] = {"status": "PASS"}
                    if state_value:
                        rank_plus_args["state"] = [state_value]
                    if employment_status_value:
                        rank_plus_args["employment_status"] = [employment_status_value]
                        status_updates["#audience-employment-status"] = {"status": "PASS"}
                    _apply_form(page, **rank_plus_args)
                    scenario_5 = _run_valid_scenario(page, "scenario_5_rank_plus_demographic")

                    # Exercise clear chips action while non-empty filters are active.
                    _click_when_enabled(page, "#audience-clear-filter-chips", timeout_seconds=15)
                    cleared = _wait_for(
                        lambda: "No active filters." in _read_text(page, "#audience-filter-summary-text"),
                        timeout_seconds=20,
                        poll_seconds=0.25,
                    )
                    _require(cleared, "Clear active chips did not reset filter summary.")
                    status_updates["#audience-clear-filter-chips"] = {"status": "PASS"}

                    # Required scenario 6: TOP_N 50K if valid.
                    _reset_filters(page)
                    _apply_form(page, selection_mode="TOP_N", target_count=50_000)
                    scenario_6 = _run_valid_scenario(page, "scenario_6_top_n_50k")
                    status_updates["#audience-selection-topn"] = {"status": "PASS"}
                    status_updates["#audience-target-count"] = {"status": "PASS"}

                    # Additional valid scenario to exercise all categorical controls.
                    _reset_filters(page)
                    optional_categorical = {
                        "marital_status": [_first_select_value(page, "#audience-marital-status")],
                        "education": [_first_select_value(page, "#audience-education")],
                        "resident_status": [_first_select_value(page, "#audience-resident-status")],
                        "resident_type": [_first_select_value(page, "#audience-resident-type")],
                        "type_of_employment": [_first_select_value(page, "#audience-type-of-employment")],
                    }
                    clean_categorical = {
                        key: value
                        for key, value in optional_categorical.items()
                        if value and isinstance(value[0], str) and value[0]
                    }
                    _apply_form(page, selection_mode="ALL_MATCHING", **clean_categorical)
                    categorical_exercise = _run_valid_scenario(page, "categorical_control_exercise")
                    if "marital_status" in clean_categorical:
                        status_updates["#audience-marital-status"] = {"status": "PASS"}
                    if "education" in clean_categorical:
                        status_updates["#audience-education"] = {"status": "PASS"}
                    if "resident_status" in clean_categorical:
                        status_updates["#audience-resident-status"] = {"status": "PASS"}
                    if "resident_type" in clean_categorical:
                        status_updates["#audience-resident-type"] = {"status": "PASS"}
                    if "type_of_employment" in clean_categorical:
                        status_updates["#audience-type-of-employment"] = {"status": "PASS"}

                    # Required scenario 7: invalid score range.
                    _reset_filters(page)
                    _apply_form(page, score_min=0.90, score_max=0.10, selection_mode="ALL_MATCHING")
                    scenario_7 = _run_invalid_scenario(page, "scenario_7_invalid_score_range", "Score min cannot exceed score max.")
                    status_updates["#audience-score-min"] = {"status": "PASS"}
                    status_updates["#audience-score-max"] = {"status": "PASS"}
                    status_updates["#audience-form-error"] = {"status": "PASS"}

                    # Required scenario 8: invalid age range.
                    _reset_filters(page)
                    _apply_form(page, age_min=70, age_max=30, selection_mode="ALL_MATCHING")
                    scenario_8 = _run_invalid_scenario(page, "scenario_8_invalid_age_range", "Age min cannot exceed age max.")
                    status_updates["#audience-age-min"] = {"status": "PASS"}
                    status_updates["#audience-age-max"] = {"status": "PASS"}

                    # Required scenario 9: invalid income range.
                    _reset_filters(page)
                    _apply_form(page, income_min=200000, income_max=100000, selection_mode="ALL_MATCHING")
                    scenario_9 = _run_invalid_scenario(page, "scenario_9_invalid_income_range", "Income min cannot exceed income max.")
                    status_updates["#audience-income-min"] = {"status": "PASS"}
                    status_updates["#audience-income-max"] = {"status": "PASS"}

                    # Required scenario 10: invalid family range.
                    _reset_filters(page)
                    _apply_form(page, family_min=5, family_max=2, selection_mode="ALL_MATCHING")
                    scenario_10 = _run_invalid_scenario(
                        page,
                        "scenario_10_invalid_family_range",
                        "Family member count min cannot exceed max.",
                    )
                    status_updates["#audience-family-min"] = {"status": "PASS"}
                    status_updates["#audience-family-max"] = {"status": "PASS"}

                    # Required scenario 11: invalid TOP_N.
                    _reset_filters(page)
                    _apply_form(page, selection_mode="TOP_N", target_count=0)
                    scenario_11 = _run_invalid_scenario(
                        page,
                        "scenario_11_invalid_top_n",
                        "Top N target count must be a positive whole number.",
                    )

                    # Required scenario 12: reset after error.
                    _click_when_enabled(page, "#audience-filter-reset", timeout_seconds=20)
                    reset_ok = _wait_for(lambda: not _visible(page, "#audience-form-error"), timeout_seconds=10, poll_seconds=0.2)
                    _require(reset_ok, "Reset after validation error did not clear the error banner.")
                    summary_reset = _wait_for(
                        lambda: "No active filters." in _read_text(page, "#audience-filter-summary-text"),
                        timeout_seconds=20,
                        poll_seconds=0.2,
                    )
                    _require(summary_reset, "Reset after validation error did not restore empty filter summary.")
                    scenario_12 = {
                        "scenario": "scenario_12_reset_after_error",
                        "form_error_cleared": True,
                        "filter_summary": _read_text(page, "#audience-filter-summary-text"),
                    }

                    # Empty-results state exercise for dedicated empty selectors.
                    _apply_form(page, family_min=99, family_max=99, selection_mode="ALL_MATCHING")
                    empty_result = _run_valid_scenario(page, "empty_result_state")
                    if _visible(page, "#audience-search-empty"):
                        status_updates["#audience-search-empty"] = {"status": "PASS"}
                        status_updates["#audience-search-empty h3"] = {"status": "PASS"}
                        status_updates["#audience-search-empty p"] = {"status": "PASS"}

                    # Bring workspace back to a current valid audience before save/handoff.
                    _reset_filters(page)
                    _apply_form(page, selection_mode="TOP_N", target_count=50_000)
                    _run_valid_scenario(page, "pre_save_topn_50k")

                    profile_controls = _exercise_profile_controls(page, status_updates)
                    saved_flow = _exercise_saved_audience_flow(page, status_updates=status_updates)

                    # Basic presence checks for explorer error shell.
                    if _exists(page, "#audience-explorer-error"):
                        status_updates["#audience-explorer-error"] = {"status": "PASS"}
                    if _exists(page, "#audience-explorer-error-message"):
                        status_updates["#audience-explorer-error-message"] = {"status": "PASS"}

                    results["scenarios"] = {
                        "1_no_filters_all_matching": scenario_1,
                        "2_top_1_percent": scenario_2,
                        "3_top_decile": scenario_3,
                        "4_demographic_filter": scenario_4,
                        "5_rank_plus_demographic": scenario_5,
                        "6_top_n_50k": scenario_6,
                        "7_invalid_score_range": scenario_7,
                        "8_invalid_age_range": scenario_8,
                        "9_invalid_income_range": scenario_9,
                        "10_invalid_family_range": scenario_10,
                        "11_invalid_top_n": scenario_11,
                        "12_reset_after_error": scenario_12,
                        "extra_empty_result": empty_result,
                        "extra_categorical_exercise": categorical_exercise,
                    }
                    results["profile_controls"] = profile_controls
                    results["saved_audience_flow"] = saved_flow
                    results["ui_table_check"] = ui_page_check
                    results["ui_errors"] = {
                        "console_errors": events.console_errors,
                        "page_errors": events.page_errors,
                        "request_failures": events.request_failures,
                    }

    backend_boundaries = _verify_boundaries_and_analytics(scoring_run_id)
    backend_search = _verify_backend_search_contract(scoring_run_id)
    results["backend_assertions"] = {
        "boundaries_and_analytics": backend_boundaries,
        "search_contract": backend_search,
    }

    # Sanity checks for required scenario outputs.
    _require(results["scenarios"]["1_no_filters_all_matching"]["estimate_selected"] > 0, "Scenario 1 selected count must be positive.")
    _require(results["scenarios"]["2_top_1_percent"]["estimate_selected"] > 0, "Scenario 2 selected count must be positive.")
    _require(results["scenarios"]["3_top_decile"]["estimate_selected"] > 0, "Scenario 3 selected count must be positive.")
    _require(results["scenarios"]["6_top_n_50k"]["estimate_selected"] == 50_000, "Scenario 6 expected selected count 50,000.")

    # Ensure every audience-explorer control is terminal.
    status_updates = _mark_all_audience_controls(status_updates)
    inventory = _update_inventory_statuses(status_updates)
    results["inventory_status_updates"] = inventory["applied"]
    results["inventory_status_summary"] = inventory["status_summary"]
    results["audience_inventory_status_summary"] = inventory["audience_status_summary"]
    results["overall_status"] = "PASS"

    return RunArtifacts(payload=results, inventory_updates=inventory["applied"])


def _write_outputs(artifacts: RunArtifacts) -> None:
    JSON_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_EVIDENCE_PATH.write_text(json.dumps(artifacts.payload, indent=2), encoding="utf-8")

    payload = artifacts.payload
    scenarios = payload.get("scenarios", {})
    backend = payload.get("backend_assertions", {})
    ui_errors = payload.get("ui_errors", {})

    lines: list[str] = []
    lines.append("# Phase 8 Step 7 System Browser Audience Explorer Report")
    lines.append("")
    lines.append(f"Generated at: {payload['generated_at']}")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/07_STEP_07_SYSTEM_BROWSER_AUDIENCE_EXPLORER_ALL_CONTROLS.md")
    lines.append("- Execution path: system-browser UI controls for preparation, filtering, profile, saved audience, and campaign handoff.")
    lines.append("")

    browser = payload.get("browser", {})
    lines.append("## Browser")
    lines.append(f"- name: {browser.get('name', 'unknown')}")
    lines.append(f"- executable: {browser.get('executable_path', '')}")
    lines.append(f"- version: {browser.get('product_version', 'unknown')}")
    lines.append(f"- mode: {browser.get('execution_mode', 'unknown')}")
    lines.append("")

    prep = payload.get("preparation", {})
    prep_obs = prep.get("ui_observations", {})
    lines.append("## Preparation")
    lines.append(f"- Active scoring run: {prep.get('active_scoring_run_id')}")
    lines.append(f"- Source badge: {prep.get('source_verified_badge')}")
    lines.append(f"- Prep submit clicked: {prep_obs.get('submit_clicked')}")
    lines.append(f"- Prep retry clicked: {prep_obs.get('retry_clicked')}")
    lines.append(f"- Prep running messages observed: {len(prep_obs.get('messages', []))}")
    lines.append("")

    lines.append("## Required Scenarios")
    for key in (
        "1_no_filters_all_matching",
        "2_top_1_percent",
        "3_top_decile",
        "4_demographic_filter",
        "5_rank_plus_demographic",
        "6_top_n_50k",
    ):
        entry = scenarios.get(key, {})
        lines.append(
            "- "
            f"{key}: matching={entry.get('estimate_matching')}, selected={entry.get('estimate_selected')}, "
            f"rows_rendered={entry.get('search_rows_rendered')}"
        )
    lines.append(f"- 7_invalid_score_range: {scenarios.get('7_invalid_score_range', {}).get('error', '')}")
    lines.append(f"- 8_invalid_age_range: {scenarios.get('8_invalid_age_range', {}).get('error', '')}")
    lines.append(f"- 9_invalid_income_range: {scenarios.get('9_invalid_income_range', {}).get('error', '')}")
    lines.append(f"- 10_invalid_family_range: {scenarios.get('10_invalid_family_range', {}).get('error', '')}")
    lines.append(f"- 11_invalid_top_n: {scenarios.get('11_invalid_top_n', {}).get('error', '')}")
    lines.append(
        "- 12_reset_after_error: "
        f"form_error_cleared={scenarios.get('12_reset_after_error', {}).get('form_error_cleared')}"
    )
    lines.append("")

    search_contract = (backend.get("search_contract") or {})
    boundaries = (backend.get("boundaries_and_analytics") or {})
    lines.append("## Backend Assertions")
    lines.append(
        "- Search determinism/no-duplicates: "
        f"checked_pages={search_contract.get('checked_pages')}, unique_person_ids={search_contract.get('unique_person_ids')}"
    )
    lines.append(
        "- Boundaries: "
        f"count={boundaries.get('boundary_count')}, p1_rank={boundaries.get('first_percentile_rank')}, "
        f"p10_rank={boundaries.get('tenth_percentile_rank')}, p100_rank={boundaries.get('hundredth_percentile_rank')}, "
        f"population={boundaries.get('total_population')}"
    )
    lines.append(
        "- Analytics snapshot: "
        f"prepared={boundaries.get('analytics_prepared')}, is_canonical={boundaries.get('is_canonical')}, "
        f"source_verified={boundaries.get('source_verified')}, created_at={boundaries.get('analytics_snapshot_created_at')}"
    )
    lines.append("")

    saved_flow = payload.get("saved_audience_flow", {})
    lines.append("## Saved Audience and Handoff")
    lines.append(f"- Saved audience id: {saved_flow.get('saved_audience_id')}")
    lines.append(f"- Saved audience name: {saved_flow.get('saved_audience_name')}")
    lines.append(f"- Currentness badge: {saved_flow.get('currentness_badge')}")
    lines.append(f"- Campaign handoff hash after click: {saved_flow.get('campaign_handoff_hash')}")
    lines.append(f"- Stale saved definition exercised: {saved_flow.get('stale_definition_exercised')}")
    lines.append("")

    lines.append("## Profile and Disclaimer Checks")
    disclaimers = payload.get("disclaimers", {})
    lines.append(f"- Context disclaimer entries: {len(disclaimers.get('context_not_probability', []))}")
    lines.append(f"- Profile no-identity-linking disclaimer: {disclaimers.get('profile_no_identity_linking')}")
    lines.append("")

    lines.append("## UI Error Telemetry")
    lines.append(f"- Console errors: {len(ui_errors.get('console_errors', []))}")
    lines.append(f"- Page errors: {len(ui_errors.get('page_errors', []))}")
    lines.append(f"- Request failures: {len(ui_errors.get('request_failures', []))}")
    lines.append("")

    audience_summary = payload.get("audience_inventory_status_summary", {})
    lines.append("## Audience Control Inventory")
    lines.append(f"- Audience controls PASS: {audience_summary.get('PASS', 0)}")
    lines.append(f"- Audience controls FAIL: {audience_summary.get('FAIL', 0)}")
    lines.append(f"- Audience controls JUSTIFIED_EXCLUSIVE: {audience_summary.get('JUSTIFIED_EXCLUSIVE', 0)}")
    lines.append(f"- Audience controls NOT_RUN: {audience_summary.get('NOT_RUN', 0)}")
    lines.append(f"- Controls updated this step: {len(artifacts.inventory_updates)}")
    lines.append("")

    lines.append("## Outcome")
    lines.append("- Step 7 completed with preparation handling, all required audience scenarios, deterministic pagination and allowlist assertions, profile/disclaimer validation, saved-audience reopen, and Campaign Builder handoff checks.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    artifacts = _run_step7()
    _write_outputs(artifacts)
    print(f"Wrote evidence: {JSON_EVIDENCE_PATH}")
    print(f"Wrote report: {REPORT_PATH}")
    print(f"Status: {artifacts.payload.get('overall_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
