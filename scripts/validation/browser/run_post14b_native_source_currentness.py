"""Real bounded source replacement and browser-visible historical-result currentness."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import traceback

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, qa_environment, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _state(database):
    with sqlite3.connect(database) as connection:
        return {
            "profiles": connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles").fetchone()[0],
            "generations": connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_score_generations").fetchone()[0],
            "snapshots": connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_result_snapshots").fetchone()[0],
            "run": connection.execute(
                "SELECT status,selected_count,similarity_result_snapshot_id "
                "FROM campaign_search_runs WHERE search_run_id=1").fetchone(),
        }


def main() -> int:
    root = prepare_qa_root()
    print(f"Source-currentness QA root: {root}", flush=True)
    report = {"scope": "FAULT_NATIVE_BOUNDED_SOURCE_REPLACEMENT", "status": "NOT_RUN",
              "qa_root": str(root)}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "currentness_browser_profile",
                downloads_dir=root / "currentness_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded",
                              timeout=60_000)
                    page.locator("#business-search-form").wait_for(state="visible", timeout=40_000)
                    page.locator("#business-product_ids-trigger").click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    page.locator("#business-product_ids-trigger").press("Escape")
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
                    assert profile
                    page.locator("#business-export-profile").select_option(profile)
                    page.locator("#business-campaign-name").fill("Bounded source currentness")
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=40_000)
                    assert page.url.endswith("/1")
                    page.wait_for_function(
                        "() => document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        timeout=240_000,
                    )
                    before = _state(database)
                    assert before["run"][0:2] == ("COMPLETED", 200)
                    assert before["profiles"] == before["generations"] == before["snapshots"] == 1
                    with sqlite3.connect(database) as connection:
                        saved = connection.execute(
                            "SELECT storage_uri,snapshot_sha256 FROM buyer_similarity_result_snapshots "
                            "WHERE similarity_result_snapshot_id=?", (before["run"][2],)
                        ).fetchone()
                    old_artifact = (root / "source" / saved[0]).resolve()
                    assert old_artifact.is_relative_to((root / "source").resolve())
                    assert hashlib.sha256(old_artifact.read_bytes()).hexdigest() == saved[1]

                    # Fixture setup only: a new synthetic source revision is imported
                    # through the real governed import service in the isolated copy.
                    original = root / "source" / "sources" / "qa_v1" / "demographics.csv"
                    revised = root / "source" / "sources" / "qa_v1" / "demographics_revised.csv"
                    with original.open("r", newline="", encoding="utf-8") as stream:
                        reader = csv.DictReader(stream)
                        header = reader.fieldnames
                        rows = list(reader)
                    assert header and len(rows) == 200
                    previous_age = int(rows[0]["age"])
                    rows[0]["age"] = str(previous_age + 1 if previous_age < 100 else previous_age - 1)
                    with revised.open("w", newline="", encoding="utf-8") as stream:
                        writer = csv.DictWriter(stream, fieldnames=header)
                        writer.writeheader()
                        writer.writerows(rows)
                    env = qa_environment(root)
                    child = subprocess.run(
                        [sys.executable, "-c",
                         "import os; from app.services.data_import_service import import_demographics; "
                         "print(import_demographics((os.environ['QA_REVISED_SOURCE'],), "
                         "database_path=os.environ['DATABASE_PATH'], replace=True).rows_inserted)"],
                        cwd=root / "source", env={**env, "QA_REVISED_SOURCE": str(revised)},
                        text=True, capture_output=True, timeout=120,
                    )
                    assert child.returncode == 0, child.stderr[-1500:]
                    assert child.stdout.strip().splitlines()[-1] == "200", child.stdout[-1200:]
                    with sqlite3.connect(database) as connection:
                        stale = connection.execute(
                            "SELECT currentness_state FROM buyer_similarity_result_snapshots "
                            "WHERE similarity_result_snapshot_id=?", (before["run"][2],)
                        ).fetchone()[0]
                    report["post_import_snapshot_state"] = stale
                    effective = page.request.get(
                        base + "api/potential-customer-search/runs/1/result", timeout=30_000
                    )
                    assert effective.status == 200
                    effective_result = effective.json()
                    assert effective_result["currentness"] == "STALE"
                    assert effective_result["download_eligible"] is False
                    page.reload(wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_function(
                        "() => document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        timeout=60_000,
                    )
                    assert page.locator("#result-detail-download").is_hidden()
                    detail = page.locator("#result-detail-content").inner_text().lower()
                    assert "stale" in detail or "historical" in detail or "not current" in detail
                    save_screenshot(page, root / "screenshots" / "stale_result_historical.png")
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded",
                              timeout=60_000)
                    page.locator("#business-search-form").wait_for(state="visible", timeout=40_000)
                    page.locator("#business-product_ids-trigger").click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    page.locator("#business-product_ids-trigger").press("Escape")
                    page.locator("#business-export-profile").select_option(profile)
                    with page.expect_response(
                        lambda response: response.request.method == "POST" and
                        response.url.endswith("/api/potential-customer-search/preflight"),
                        timeout=40_000,
                    ) as preflight_info:
                        page.locator("#business-search-preflight").click()
                    assert preflight_info.value.status == 200
                    preflight = preflight_info.value.json()
                    assert preflight["selected_count"] is None, preflight
                    assert preflight["similarity_currentness"] != "CURRENT", preflight
                    after = _state(database)
                    assert after == before
                    assert hashlib.sha256(old_artifact.read_bytes()).hexdigest() == saved[1]
                    save_screenshot(page, root / "screenshots" / "stale_preflight_unknown.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_BOUNDED_SOURCE_REPLACEMENT_CURRENTNESS",
                                   "browser": session.metadata.to_dict(),
                                   "before": before, "after": after,
                                   "effective_result_currentness": effective_result["currentness"],
                                   "post_import_preflight": {
                                       "currentness": preflight["similarity_currentness"],
                                       "selected_count": preflight["selected_count"],
                                       "reason_code": preflight["reason_code"],
                                   },
                                   "old_snapshot_sha256": saved[1],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_BOUNDED_SOURCE_REPLACEMENT_CURRENTNESS",
                       "error_type": type(exc).__name__, "error": str(exc)[:1700],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_source_currentness.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_BOUNDED_SOURCE_REPLACEMENT_CURRENTNESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
