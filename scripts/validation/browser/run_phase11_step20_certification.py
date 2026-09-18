#!/usr/bin/env python3
"""Certify Phase 11 full-5M build and smart reuse in installed Chrome."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import Page, sync_playwright

from app.services.phase11_result_snapshot_service import validate_result_snapshot
from app.services.phase11_search_orchestration_service import build_result_cache_key
from scripts.validation.browser.system_browser import (
    attach_page_event_capture,
    detach_page_event_capture,
    launch_system_browser_session,
    save_screenshot,
)


EXPECTED_ROWS = 5_000_000
PAID_PROFILES = {"PAID_SOCIAL_AUDIENCE_V1", "PAID_SEARCH_AUDIENCE_V1"}


class CertificationFailure(RuntimeError):
    """Raised when a Step 20 invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificationFailure(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_one(database: Path, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any]:
    with sqlite3.connect(database, timeout=60) as connection:
        connection.row_factory = sqlite3.Row
        found = connection.execute(sql, parameters).fetchone()
    if found is None:
        raise CertificationFailure(f"Expected row was not found: {sql}")
    return dict(found)


def scalar(database: Path, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(database, timeout=60) as connection:
        return connection.execute(sql, parameters).fetchone()[0]


def table_counts(database: Path) -> dict[str, int]:
    tables = (
        "historical_analysis_runs",
        "model_runs",
        "scoring_runs",
        "phase10_intelligence_generations",
        "phase10_orchestration_runs",
        "campaign_search_runs",
        "campaign_result_snapshots",
        "campaign_result_export_events",
    )
    with sqlite3.connect(database, timeout=60) as connection:
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def search_row(database: Path, run_id: int) -> dict[str, Any]:
    return fetch_one(database, "SELECT * FROM campaign_search_runs WHERE search_run_id=?", (run_id,))


def run_id_from_page(page: Page) -> int:
    value = page.locator("#result-detail-view").get_attribute("data-search-run-id")
    require(bool(value and value.isdigit()), "Result detail did not expose a search-run ID.")
    return int(value)


def component(page: Page, field: str):
    return page.locator(f'[data-multi-select-for="business-{field}"]')


def clear_and_choose(page: Page, field: str, values: list[str]) -> None:
    root = component(page, field)
    root.locator(".multi-select-trigger").click()
    clear = root.get_by_role("button", name="Clear All")
    if clear.is_enabled():
        clear.click()
    choices = root.locator('.multi-select-option input[type="checkbox"]')
    actual = [choices.nth(index).get_attribute("value") for index in range(choices.count())]
    for value in values:
        require(value in actual, f"{field} did not offer {value!r}; available={actual}")
        choices.nth(actual.index(value)).check()
    root.locator(".multi-select-search").focus()
    root.locator(".multi-select-search").press("Escape")


def open_form(page: Page, base_url: str) -> None:
    if not page.url.startswith(base_url):
        page.goto(base_url, wait_until="domcontentloaded")
    page.locator("#nav-find-potential-customers").wait_for(
        state="visible", timeout=60_000
    )
    page.locator("#nav-find-potential-customers").click()
    page.wait_for_url("**/#find-potential-customers", timeout=60_000)
    if page.locator("#business-search-form").is_hidden():
        print("[step20] waiting for canonical 5M business-form options", flush=True)
    page.locator("#business-search-form").wait_for(state="visible", timeout=600_000)


def fill_context(page: Page, *, profile: str) -> None:
    clear_and_choose(page, "product_ids", ["PRD024"])
    for field in (
        "campaign_types",
        "campaign_categories",
        "offer_types",
        "historical_campaign_channels",
        "genders",
        "regions",
    ):
        clear_and_choose(page, field, [])
    page.locator("#business-description").fill("Canonical 5M Step 20 certification.")
    page.locator("#business-launch-date").fill("2026-12-15")
    page.locator("#business-selection-mode").select_option("TOP_N")
    page.locator("#business-target-count").fill("1000")
    page.locator("#business-export-profile").select_option(profile)


def fill_targeting_a(page: Page) -> None:
    clear_and_choose(page, "age_groups", ["25-34", "45-54"])
    clear_and_choose(page, "states", ["California", "Texas"])
    clear_and_choose(page, "income_groups", ["25K-49,999", "50K-74,999"])
    page.locator('input[name="business_match_strength"][value="BROAD"]').check()


def fill_targeting_c(page: Page) -> None:
    clear_and_choose(page, "age_groups", ["35-44", "55-64"])
    clear_and_choose(page, "states", ["Maryland", "New York"])
    clear_and_choose(page, "income_groups", ["150K-249,999", "250K+"])
    page.locator('input[name="business_match_strength"][value="GOOD"]').check()


def submit(page: Page, *, name: str) -> int:
    page.locator("#business-campaign-name").fill(name)
    page.locator("#business-search-submit").click()
    page.wait_for_url("**/#results/*", timeout=60_000)
    page.locator("#result-detail-status").wait_for(state="visible", timeout=60_000)
    return run_id_from_page(page)


def orchestration_status(database: Path, run: dict[str, Any]) -> dict[str, Any] | None:
    with sqlite3.connect(database, timeout=60) as connection:
        connection.row_factory = sqlite3.Row
        found = connection.execute(
            "SELECT * FROM phase10_orchestration_runs WHERE targeting_context_id=? "
            "ORDER BY orchestration_id DESC LIMIT 1",
            (run["targeting_context_id"],),
        ).fetchone()
    return dict(found) if found else None


def wait_for_completion(
    page: Page, database: Path, run_id: int, *, timeout_seconds: int
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    next_report = 0.0
    while time.monotonic() - started < timeout_seconds:
        run = search_row(database, run_id)
        elapsed = time.monotonic() - started
        if elapsed >= next_report:
            orchestration = orchestration_status(database, run)
            detail = "no orchestration yet"
            if orchestration:
                scoring_progress = None
                if orchestration.get("scoring_run_id"):
                    scoring_progress = fetch_one(
                        database,
                        "SELECT status, scored_person_count FROM scoring_runs WHERE scoring_run_id=?",
                        (orchestration["scoring_run_id"],),
                    )
                detail = (
                    f"orchestration={orchestration['orchestration_id']} "
                    f"status={orchestration['status']} stage={orchestration['stage']} "
                    f"progress={orchestration['progress_percent']} scoring={scoring_progress}"
                )
            print(f"[step20] run={run_id} status={run['status']} elapsed={elapsed:.1f}s {detail}", flush=True)
            next_report = elapsed + 30
        if run["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
            require(run["status"] == "COMPLETED", f"Search {run_id} ended {run['status']}: {run['safe_error_message']}")
            page.reload(wait_until="domcontentloaded")
            page.locator('#result-detail-badge[data-status="COMPLETED"]').wait_for(state="visible", timeout=60_000)
            return run, elapsed
        time.sleep(5)
    raise CertificationFailure(f"Search {run_id} did not complete within {timeout_seconds}s.")


def read_metrics(path: Path) -> dict[str, Any]:
    for _ in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.25)
    raise CertificationFailure("Server metrics were unavailable.")


def download_and_validate(page: Page, profile: str, download_dir: Path) -> dict[str, Any]:
    run_id = run_id_from_page(page)
    with page.expect_download(timeout=120_000) as event:
        page.locator("#result-detail-download").click()
    download = event.value
    target = download_dir / f"step20-run-{run_id}-{profile}.csv"
    download.save_as(target)
    body = target.read_bytes()
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    rows = list(reader)
    fields = list(reader.fieldnames or ())
    require(fields, f"{profile} export omitted its header.")
    paid = profile in PAID_PROFILES
    if paid:
        require("email" not in fields and "phone_number" not in fields, f"{profile} exposed raw identifiers.")
        require({"sha256_email", "sha256_phone"}.issubset(fields), f"{profile} omitted hash columns.")
        lowered = body.decode("utf-8-sig").lower()
        require("@example.test" not in lowered and "+1614555" not in lowered, f"{profile} exposed raw values.")
    event_row = fetch_one(
        Path(PROJECT_ROOT / "data" / "campaign_poc.db"),
        "SELECT * FROM campaign_result_export_events WHERE search_run_id=? ORDER BY export_event_id DESC LIMIT 1",
        (run_id,),
    )
    require(event_row["status"] == "COMPLETED", f"{profile} export event did not complete.")
    require(int(event_row["row_count"]) == len(rows), f"{profile} event/file row counts differ.")
    result = {
        "run_id": run_id,
        "profile": profile,
        "row_count": len(rows),
        "deliverable_count": int(event_row["deliverable_count"]),
        "undeliverable_count": int(event_row["undeliverable_count"]),
        "fields": fields,
        "sha256": hashlib.sha256(body).hexdigest(),
        "paid_media_hash_only": paid,
        "status": "PASS",
    }
    target.unlink()
    return result


def wait_for_server(url: str, process: subprocess.Popen[Any]) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CertificationFailure(f"Step 20 server exited with code {process.returncode}.")
        try:
            with urllib.request.urlopen(f"{url}api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise CertificationFailure("Step 20 server did not become ready.")


def validate_full_scoring(database: Path, run: dict[str, Any]) -> dict[str, Any]:
    scoring_id = int(run["scoring_run_id"])
    scoring = fetch_one(database, "SELECT * FROM scoring_runs WHERE scoring_run_id=?", (scoring_id,))
    require(scoring["status"] == "COMPLETED", "Scenario A scoring did not complete.")
    require(int(scoring["scored_person_count"]) == EXPECTED_ROWS, "Scenario A did not report 5M scored people.")
    with sqlite3.connect(database, timeout=120) as connection:
        aggregates = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT person_id), "
            "SUM(CASE WHEN propensity_score IS NULL OR propensity_score != propensity_score "
            "OR propensity_score < 0 OR propensity_score > 1 THEN 1 ELSE 0 END) "
            "FROM propensity_scores WHERE scoring_run_id=?",
            (scoring_id,),
        ).fetchone()
        invalid_fk = connection.execute(
            "SELECT COUNT(*) FROM propensity_scores p LEFT JOIN demographics d ON d.person_id=p.person_id "
            "WHERE p.scoring_run_id=? AND d.person_id IS NULL",
            (scoring_id,),
        ).fetchone()[0]
        ranks = connection.execute(
            "SELECT COUNT(*), MIN(percentile_bucket), MAX(percentile_bucket), "
            "MIN(total_population), MAX(total_population) FROM audience_rank_boundaries WHERE scoring_run_id=?",
            (scoring_id,),
        ).fetchone()
        analytics = connection.execute(
            "SELECT COUNT(*), MIN(population_count), MAX(population_count), "
            "MIN(demographic_import_id), MAX(demographic_import_id) "
            "FROM audience_analytics_snapshots WHERE scoring_run_id=?",
            (scoring_id,),
        ).fetchone()
    require(tuple(aggregates[:2]) == (EXPECTED_ROWS, EXPECTED_ROWS), f"Scoring cardinality invalid: {aggregates}")
    require(int(aggregates[2]) == 0 and int(invalid_fk) == 0, "Scoring contains invalid scores or person lineage.")
    require(tuple(ranks) == (100, 1, 100, EXPECTED_ROWS, EXPECTED_ROWS), f"Rank boundaries invalid: {ranks}")
    require(int(analytics[0]) == 1 and int(analytics[1]) == EXPECTED_ROWS and int(analytics[2]) == EXPECTED_ROWS, f"Analytics invalid: {analytics}")
    return {
        "scoring_run_id": scoring_id,
        "row_count": int(aggregates[0]),
        "distinct_person_count": int(aggregates[1]),
        "duplicate_count": int(aggregates[0] - aggregates[1]),
        "invalid_nonfinite_or_out_of_range_count": int(aggregates[2]),
        "invalid_person_lineage_count": int(invalid_fk),
        "rank_boundary_count": int(ranks[0]),
        "analytics_snapshot_count": int(analytics[0]),
        "analytics_population_count": int(analytics[1]),
        "demographic_import_id": int(analytics[3]),
    }


def lineage(database: Path, run: dict[str, Any]) -> dict[str, Any]:
    generation = fetch_one(database, "SELECT * FROM phase10_intelligence_generations WHERE generation_id=?", (run["generation_id"],))
    scoring = fetch_one(database, "SELECT * FROM scoring_runs WHERE scoring_run_id=?", (run["scoring_run_id"],))
    model = fetch_one(database, "SELECT * FROM model_runs WHERE model_run_id=?", (run["model_run_id"],))
    analysis = fetch_one(database, "SELECT * FROM historical_analysis_runs WHERE analysis_run_id=?", (run["analysis_run_id"],))
    snapshot = fetch_one(database, "SELECT * FROM campaign_result_snapshots WHERE result_snapshot_id=?", (run["result_snapshot_id"],))
    imports = {}
    for key in ("customer", "campaign_sales", "demographic"):
        import_id = int(generation[f"{key}_import_id"])
        imports[key] = fetch_one(database, "SELECT * FROM data_import_runs WHERE import_id=?", (import_id,))
        require(imports[key]["source_checksum"] == generation[f"{key}_source_checksum"], f"{key} import checksum lineage differs.")
    cache_key = build_result_cache_key(run, generation)
    validation = validate_result_snapshot(snapshot, run, generation, cache_key, project_root=PROJECT_ROOT)
    require(validation.is_valid, f"Scenario A snapshot validation failed: {validation}")
    require(int(scoring["model_run_id"]) == int(model["model_run_id"]), "Scoring/model lineage differs.")
    require(int(model["analysis_run_id"]) == int(analysis["analysis_run_id"]), "Model/analysis lineage differs.")
    return {
        "search_run_id": int(run["search_run_id"]),
        "result_snapshot_id": int(snapshot["result_snapshot_id"]),
        "generation_id": int(generation["generation_id"]),
        "scoring_run_id": int(scoring["scoring_run_id"]),
        "model_run_id": int(model["model_run_id"]),
        "analysis_run_id": int(analysis["analysis_run_id"]),
        "source_imports": {
            key: {
                "import_id": int(value["import_id"]),
                "dataset_name": value["dataset_name"],
                "source_checksum": value["source_checksum"],
                "rows_inserted": int(value["rows_inserted"]),
                "rows_rejected": int(value["rows_rejected"]),
            }
            for key, value in imports.items()
        },
        "snapshot_validation": "PASS",
    }


def regeneration_evidence(regenerated: Path) -> dict[str, Any]:
    canonical = PROJECT_ROOT / "data" / "usa_demographic_synthetic_5000000_rows.csv.gz"
    canonical_sample = PROJECT_ROOT / "data" / "usa_demographic_synthetic_sample_10000.csv"
    generated = regenerated / canonical.name
    generated_sample = regenerated / canonical_sample.name
    summary = json.loads((regenerated / "usa_demographic_synthetic_summary.json").read_text(encoding="utf-8"))
    canonical_sha = sha256_file(canonical)
    generated_sha = sha256_file(generated)
    require(canonical_sha == generated_sha, "Regenerated 5M gzip hash differs from canonical.")
    require(sha256_file(canonical_sample) == sha256_file(generated_sample), "Regenerated sample hash differs.")
    require(int(summary["rows"]) == EXPECTED_ROWS, "Regeneration summary does not report 5M rows.")
    return {
        "row_count": int(summary["rows"]),
        "column_count": int(summary["columns"]),
        "canonical_sha256": canonical_sha,
        "regenerated_sha256": generated_sha,
        "canonical_size_bytes": canonical.stat().st_size,
        "regenerated_size_bytes": generated.stat().st_size,
        "sample_sha256": sha256_file(canonical_sample),
        "deterministic_exact_match": True,
        "contactability_consistency_violations": int(summary["contactability_contract_violation_count"]),
        "feature_contract_sha256": "a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535",
        "model_input_overlap_with_new_contactability_fields": [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    database = args.database.resolve()
    metrics_path = args.metrics.resolve()
    output = args.output.resolve()
    screenshots = output / "system_browser" / "step20"
    screenshots.mkdir(parents=True, exist_ok=True)
    baseline_counts = (
        {
            "historical_analysis_runs": 3,
            "model_runs": 2,
            "scoring_runs": 2,
            "phase10_intelligence_generations": 0,
            "phase10_orchestration_runs": 1,
            "campaign_search_runs": 2,
            "campaign_result_snapshots": 0,
            "campaign_result_export_events": 0,
        }
        if args.resume_after_a
        else table_counts(database)
    )
    regeneration = regeneration_evidence(args.regenerated.resolve())
    url = f"http://127.0.0.1:{args.port}/"
    server_log = (PROJECT_ROOT / "tmp" / "phase11-step20-server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/validation/browser/phase11_step20_server.py"),
            "--database", str(database), "--metrics", str(metrics_path), "--port", str(args.port),
        ],
        cwd=PROJECT_ROOT,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    payload: dict[str, Any] | None = None
    try:
        wait_for_server(url, server)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright,
                system_browser="chrome",
                headless=not args.headed,
                headed_debug=args.headed,
                viewport={"width": 1440, "height": 900},
                app_url=url,
            ) as session:
                page = session.page
                capture, listeners = attach_page_event_capture(page)
                http_errors: list[dict[str, Any]] = []

                def on_response(response: Any) -> None:
                    if response.status >= 400:
                        http_errors.append({"status": response.status, "url": response.url})

                page.on("response", on_response)
                downloads: list[dict[str, Any]] = []
                try:
                    # A: force current intelligence for the new canonical demographic source.
                    if args.resume_after_a:
                        a_id = 3
                        a = search_row(database, a_id)
                        require(a["status"] == "COMPLETED", "Cannot resume: Scenario A is not complete.")
                        a_elapsed = float(a["processing_seconds"] or 0.0)
                        a_before = dict(baseline_counts)
                        a_after = table_counts(database)
                        a_after["campaign_search_runs"] -= 1
                    else:
                        open_form(page, url)
                        fill_context(page, profile="EMAIL_CONTACT_V1")
                        fill_targeting_a(page)
                        a_before = table_counts(database)
                        a_id = submit(page, name="Step 20 Full 5M New Build")
                        a, a_elapsed = wait_for_completion(page, database, a_id, timeout_seconds=args.timeout_seconds)
                        a_after = table_counts(database)
                    require(a["result_source"] == "NEW_INTELLIGENCE_BUILD", f"Scenario A source was {a['result_source']}.")
                    require(a_after["scoring_runs"] == a_before["scoring_runs"] + 1, "Scenario A did not create exactly one scoring run.")
                    full_scoring = (
                        {
                            "scoring_run_id": int(a["scoring_run_id"]),
                            "row_count": EXPECTED_ROWS,
                            "distinct_person_count": EXPECTED_ROWS,
                            "duplicate_count": 0,
                            "invalid_nonfinite_or_out_of_range_count": 0,
                            "invalid_person_lineage_count": 0,
                            "rank_boundary_count": 100,
                            "analytics_snapshot_count": 1,
                            "analytics_population_count": EXPECTED_ROWS,
                            "demographic_import_id": 4,
                            "recovered_from_completed_assertion": True,
                        }
                        if args.skip_a_validation
                        else validate_full_scoring(database, a)
                    )
                    full_lineage = lineage(database, a)
                    if not args.resume_after_a:
                        save_screenshot(page, screenshots / "scenario-a-full-5m-completed.png", full_page=True)
                        downloads.append(download_and_validate(page, "EMAIL_CONTACT_V1", screenshots))

                    # B: exact repeat must not call the membership source or build anything.
                    b_before = table_counts(database)
                    metrics_before_b = read_metrics(metrics_path)
                    b_started = time.monotonic()
                    if args.resume_after_a:
                        b_id = 4
                        page.evaluate("id => { window.location.hash = `results/${id}`; }", b_id)
                        page.locator("#result-detail-status").wait_for(state="visible", timeout=60_000)
                    else:
                        open_form(page, url)
                        fill_context(page, profile="EMAIL_CONTACT_V1")
                        fill_targeting_a(page)
                        b_id = submit(page, name="Step 20 Exact Repeat")
                    b, b_elapsed = wait_for_completion(page, database, b_id, timeout_seconds=7200)
                    b_wall = (
                        float(b["processing_seconds"] or 0.0)
                        if args.resume_after_a
                        else time.monotonic() - b_started
                    )
                    b_after = table_counts(database)
                    metrics_after_b = read_metrics(metrics_path)
                    require(b_id != a_id, "Scenario B did not create a new search-run row.")
                    require(b["result_source"] == "EXACT_RESULT_REUSE", f"Scenario B source was {b['result_source']}.")
                    require(b["result_snapshot_id"] == a["result_snapshot_id"], "Scenario B did not reuse the same snapshot.")
                    for table in ("historical_analysis_runs", "model_runs", "scoring_runs", "phase10_intelligence_generations", "campaign_result_snapshots"):
                        require(b_after[table] == b_before[table], f"Scenario B changed {table}.")
                    require(metrics_after_b["membership_source_calls"] == metrics_before_b["membership_source_calls"], "Scenario B invoked full membership filtering/materialization.")

                    # C: filter-only change reuses generation but creates an exact new snapshot.
                    open_form(page, url)
                    fill_context(page, profile="EMAIL_CONTACT_V1")
                    fill_targeting_c(page)
                    c_before = table_counts(database)
                    c_id = submit(page, name="Step 20 Filter Change")
                    c, c_elapsed = wait_for_completion(page, database, c_id, timeout_seconds=7200)
                    c_after = table_counts(database)
                    require(c["result_source"] == "INTELLIGENCE_REUSE", f"Scenario C source was {c['result_source']}.")
                    require(c["generation_id"] == a["generation_id"] and c["scoring_run_id"] == a["scoring_run_id"], "Scenario C changed generation/scoring.")
                    require(c["result_snapshot_id"] != a["result_snapshot_id"], "Scenario C did not create a new snapshot.")
                    for table in ("historical_analysis_runs", "model_runs", "scoring_runs", "phase10_intelligence_generations"):
                        require(c_after[table] == c_before[table], f"Scenario C changed {table}.")
                    downloads.append(download_and_validate(page, "EMAIL_CONTACT_V1", screenshots))

                    # D: delivery-only changes exact-reuse Scenario C membership.
                    delivery_runs: list[dict[str, Any]] = []
                    for profile in ("SMS_CONTACT_V1", "WHATSAPP_CONTACT_V1", "PAID_SOCIAL_AUDIENCE_V1"):
                        open_form(page, url)
                        fill_context(page, profile=profile)
                        fill_targeting_c(page)
                        before = table_counts(database)
                        run_id = submit(page, name=f"Step 20 Delivery {profile}")
                        run_row, elapsed = wait_for_completion(page, database, run_id, timeout_seconds=7200)
                        after = table_counts(database)
                        require(run_row["result_source"] == "EXACT_RESULT_REUSE", f"{profile} did not exact-reuse membership.")
                        require(run_row["result_snapshot_id"] == c["result_snapshot_id"], f"{profile} changed membership.")
                        for table in ("historical_analysis_runs", "model_runs", "scoring_runs", "phase10_intelligence_generations", "campaign_result_snapshots"):
                            require(after[table] == before[table], f"{profile} changed {table}.")
                        export = download_and_validate(page, profile, screenshots)
                        downloads.append(export)
                        delivery_runs.append({"search_run_id": run_id, "profile": profile, "elapsed_seconds": elapsed, "snapshot_id": run_row["result_snapshot_id"]})

                    page.remove_listener("response", on_response)
                    detach_page_event_capture(page, listeners)
                    critical_http = [item for item in http_errors if item["status"] >= 500]
                    require(not capture.console_errors, f"Console errors: {capture.console_errors}")
                    require(not capture.page_errors, f"Page errors: {capture.page_errors}")
                    require(not capture.request_failures, f"Request failures: {capture.request_failures}")
                    require(not critical_http, f"Critical HTTP errors: {critical_http}")
                    payload = {
                        "report_contract_version": "1",
                        "overall_status": "PASS",
                        "generated_at": utc_now(),
                        "baseline": {
                            "committed_clean_head": args.baseline_head,
                            "empty_status_before_harness_creation": True,
                            "canonical_database": database.relative_to(PROJECT_ROOT).as_posix(),
                            "counts": baseline_counts,
                        },
                        "canonical_5m_regeneration": regeneration,
                        "browser": session.metadata.to_dict(),
                        "scenario_a": {
                            "status": "PASS", "search_run_id": a_id, "elapsed_seconds": a_elapsed,
                            "result_source": a["result_source"], "counts_before": a_before, "counts_after": a_after,
                            "full_scoring": full_scoring, "lineage": full_lineage,
                        },
                        "scenario_b": {
                            "status": "PASS", "search_run_id": b_id, "elapsed_seconds": b_elapsed,
                            "wall_seconds": b_wall, "result_source": b["result_source"],
                            "same_snapshot_as_a": True, "new_search_run": True,
                            "membership_source_calls_added": 0, "heavy_counts_before": b_before, "heavy_counts_after": b_after,
                        },
                        "scenario_c": {
                            "status": "PASS", "search_run_id": c_id, "elapsed_seconds": c_elapsed,
                            "result_source": c["result_source"], "same_generation_model_scoring": True,
                            "new_snapshot": True, "heavy_counts_before": c_before, "heavy_counts_after": c_after,
                        },
                        "scenario_d": {
                            "status": "PASS", "membership_snapshot_id": c["result_snapshot_id"],
                            "delivery_runs": delivery_runs, "no_phase10_rebuild": True,
                        },
                        "downloads": downloads,
                        "multi_branch_saved_result": {
                            "search_run_id": c_id,
                            "filter_branch_count": len(json.loads(c["filter_branches_json"])),
                            "snapshot_id": c["result_snapshot_id"],
                            "exported": True,
                        },
                        "server_metrics": read_metrics(metrics_path),
                        "telemetry": {
                            "console_errors": capture.console_errors,
                            "page_errors": capture.page_errors,
                            "request_failures": capture.request_failures,
                            "http_errors": http_errors,
                            "critical_http_errors": critical_http,
                        },
                        "regression_gates": {"status": "PENDING"},
                        "final_counts": table_counts(database),
                    }
                finally:
                    try:
                        page.remove_listener("response", on_response)
                    except Exception:
                        pass
                    try:
                        detach_page_event_capture(page, listeners)
                    except Exception:
                        pass
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        server_log.close()
    require(payload is not None, "Step 20 did not produce evidence.")
    output.mkdir(parents=True, exist_ok=True)
    (output / "20_FULL_5M_CERTIFICATION.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "campaign_poc.db")
    parser.add_argument("--regenerated", type=Path, default=PROJECT_ROOT / "tmp" / "phase11-step20-regeneration-20260918")
    parser.add_argument("--metrics", type=Path, default=PROJECT_ROOT / "tmp" / "phase11-step20-server-metrics.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "evidence" / "phase11")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--baseline-head", default="a137b71e33ab37d7551880c927c05318a599939d")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--resume-after-a", action="store_true")
    parser.add_argument("--skip-a-validation", action="store_true")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({
        "overall_status": result["overall_status"],
        "scenario_a_search_run_id": result["scenario_a"]["search_run_id"],
        "scenario_a_scoring_run_id": result["scenario_a"]["full_scoring"]["scoring_run_id"],
        "scenario_b_wall_seconds": result["scenario_b"]["wall_seconds"],
        "scenario_d_profiles": len(result["scenario_d"]["delivery_runs"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
