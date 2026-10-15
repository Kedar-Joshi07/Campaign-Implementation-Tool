"""Reopen a genuine v1 QA result in native Chrome without claiming v1 form creation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import QA_PARENT, start_qa_server, stop_qa_server
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Legacy reopen requires a dedicated QA root.")
    database = root / "state" / "qa.db"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT r.targeting_criteria_json,r.export_profile,r.catalog_version,"
            "c.campaign_context_json FROM campaign_search_runs r "
            "JOIN campaign_targeting_contexts c ON c.targeting_context_id=r.targeting_context_id "
            "WHERE r.selection_contract_version='2' AND r.status='COMPLETED' "
            "ORDER BY r.search_run_id LIMIT 1"
        ).fetchone()
        existing_v1 = connection.execute(
            "SELECT search_run_id FROM campaign_search_runs WHERE selection_contract_version='1' "
            "AND status='COMPLETED' ORDER BY search_run_id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("A completed same-source v2 context is required as v1 setup.")
    criteria = json.loads(row[0])
    context = json.loads(row[3])
    context.pop("campaign_targeting_context_contract_version", None)
    criteria.pop("propensity_bucket", None)
    for key in list(criteria):
        if key.endswith("_contract_version"):
            criteria.pop(key)
    criteria["match_strength"] = "BROAD"
    report = {"scope": "BUSINESS_NATIVE_LEGACY_V1_REOPEN", "status": "NOT_RUN",
              "qa_root": str(root), "setup": "Real v1 API submission; browser action under test is reopen."}
    process = None
    try:
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "legacy_reopen_browser_profile",
                downloads_dir=root / "legacy_reopen_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    payload = {"campaign_name": "Synthetic legacy v1 reopen fixture",
                               "description": "Read-only browser compatibility case",
                               "context": context, "criteria": criteria,
                               "export_profile": row[1], "catalog_version": row[2]}
                    if existing_v1:
                        run_id = int(existing_v1[0])
                        report["setup"] = "Reused the same QA root's real completed v1 API fixture."
                    else:
                        setup = page.request.post(
                            base + "api/potential-customer-search/runs", data=payload,
                            timeout=40_000,
                        )
                        assert setup.status == 201, setup.text()
                        created = setup.json()
                        run_id = int(created["search_run_id"])
                    page.goto(base + f"#results/{run_id}", wait_until="domcontentloaded",
                              timeout=60_000)
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=run_id, timeout=180_000,
                    )
                    with sqlite3.connect(database) as connection:
                        actual = connection.execute(
                            "SELECT selection_contract_version,propensity_bucket,selected_count,"
                            "result_snapshot_id,scoring_run_id FROM campaign_search_runs "
                            "WHERE search_run_id=?", (run_id,)
                        ).fetchone()
                        snapshot = connection.execute(
                            "SELECT selection_contract_version,resolved_count "
                            "FROM campaign_result_snapshots WHERE result_snapshot_id=?", (actual[3],)
                        ).fetchone()
                    assert actual[0] == "1" and actual[1] is None
                    assert actual[2] == snapshot[1] and snapshot[0] == "1"
                    assert actual[4] == 1
                    detail_text = page.locator("#result-detail-content").inner_text()
                    assert "Legacy" in detail_text or "legacy" in detail_text
                    if not page.locator("#result-technical-disclosure").evaluate("e => e.open"):
                        page.locator("#result-technical-disclosure summary").click()
                    assert page.locator("#result-technical-disclosure").evaluate("e => e.open")
                    assert page.locator("#result-technical-details").is_visible()
                    assert "Selection Contract Version" in page.locator(
                        "#result-technical-details").text_content()
                    page.goto(base + "#results", wait_until="domcontentloaded")
                    card = page.locator(f'a[href="#results/{run_id}"]')
                    card.wait_for(state="visible")
                    card.click()
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=run_id, timeout=60_000,
                    )
                    with page.expect_download(timeout=45_000) as download_info:
                        page.locator("#result-detail-download").click()
                    download = download_info.value
                    destination = root / "legacy_reopen_downloads" / download.suggested_filename
                    download.save_as(destination)
                    with destination.open("r", newline="", encoding="utf-8-sig") as stream:
                        reader = csv.DictReader(stream)
                        header = reader.fieldnames
                        exported = list(reader)
                    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                    with sqlite3.connect(database) as connection:
                        audit = connection.execute(
                            "SELECT status,selected_count,deliverable_count,undeliverable_count,"
                            "row_count,csv_sha256,export_profile FROM campaign_result_export_events "
                            "WHERE search_run_id=? ORDER BY export_event_id DESC LIMIT 1", (run_id,)
                        ).fetchone()
                    assert audit is not None and audit[0] == "COMPLETED"
                    assert audit[1] == actual[2] and audit[2] + audit[3] == audit[1]
                    assert audit[4] == len(exported) == audit[2] and audit[5] == digest
                    assert audit[6] == row[1] and header and len(header) == len(set(header))
                    save_screenshot(page, root / "screenshots" / "legacy_v1_reopened.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_LEGACY_V1_REOPEN", "browser": session.metadata.to_dict(),
                                   "run_id": run_id, "selected_count": actual[2],
                                   "exported_count": len(exported), "csv_sha256": digest,
                                   "export_profile": audit[6], "export_header": header,
                                   "selection_contract_version": actual[0],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_LEGACY_V1_REOPEN", "error_type": type(exc).__name__,
                       "error": str(exc)[:1600], "traceback": traceback.format_exc()[-3000:]})
        try:
            report["browser_failure_state"] = page.evaluate("""() => ({
              hash: location.hash,
              badge: document.querySelector('#result-detail-badge')?.dataset.status,
              technicalOpen: document.querySelector('#result-technical-disclosure')?.open,
              technicalText: document.querySelector('#result-technical-details')?.textContent?.slice(0, 700),
              detailText: document.querySelector('#result-detail-content')?.textContent?.slice(0, 700),
            })""")
        except Exception:
            pass
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_legacy_v1_reopen.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_LEGACY_V1_REOPEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
