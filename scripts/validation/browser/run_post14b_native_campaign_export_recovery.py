"""Restart and native-Edge retry of an interrupted bounded campaign export."""

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
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True, type=int)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_campaign_builder.json").is_file():
        raise ValueError("Recovery requires the existing owned campaign QA root.")
    report = {"scope": "RETAINED_NATIVE_CAMPAIGN_EXPORT_RESTART_RECOVERY",
              "status": "NOT_RUN", "qa_root": str(root), "campaign_id": args.campaign_id}
    process = None
    try:
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            prior = connection.execute(
                "SELECT status FROM campaign_export_events WHERE campaign_id=? ORDER BY export_event_id DESC LIMIT 1",
                (args.campaign_id,),
            ).fetchone()
        assert prior in {("STARTED",), ("ABORTED",)}, prior
        process, port = start_qa_server(root)
        with sqlite3.connect(database) as connection:
            reconciled = connection.execute(
                "SELECT status FROM campaign_export_events WHERE campaign_id=? ORDER BY export_event_id DESC LIMIT 1",
                (args.campaign_id,),
            ).fetchone()
        assert reconciled == ("ABORTED",), reconciled
        report["reconciled_interrupted_event"] = "ABORTED"
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="edge", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "campaign_recovery_edge_profile",
                downloads_dir=root / "campaign_recovery_edge_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#campaigns",
                              wait_until="domcontentloaded")
                    page.wait_for_function("""() => ['campaigns-state-ready',
                      'campaigns-state-no-eligible', 'campaigns-state-backend-unavailable']
                      .some(id => !document.getElementById(id)?.hidden)""", timeout=120_000)
                    state = page.evaluate("""() => ({
                      title: document.querySelector('#page-title')?.textContent,
                      ready: !document.querySelector('#campaigns-state-ready')?.hidden,
                      noEligible: !document.querySelector('#campaigns-state-no-eligible')?.hidden,
                      backendUnavailable: !document.querySelector('#campaigns-state-backend-unavailable')?.hidden,
                      error: document.querySelector('#campaigns-error-message')?.textContent,
                      announcement: document.querySelector('#campaigns-status-announcement')?.textContent,
                    })""")
                    report["workspace_state"] = state
                    assert state["ready"], state
                    row = page.locator("#campaign-recent-body tr").filter(
                        has_text=f"Bounded retained DIRECT_MAIL campaign")
                    row.get_by_role("button", name="Open").click()
                    page.locator("#campaign-step-panel-4").wait_for(state="visible", timeout=30_000)
                    assert page.locator("#campaign-export").is_disabled()
                    page.locator("#campaign-pii-ack").check()
                    assert page.locator("#campaign-export").is_enabled()
                    with page.expect_download(timeout=120_000) as download_info:
                        page.locator("#campaign-export").click()
                    download = download_info.value
                    path = root / "campaign_recovery_edge_downloads" / download.suggested_filename
                    download.save_as(path)
                    with path.open("r", encoding="utf-8-sig", newline="") as source:
                        reader = csv.DictReader(source)
                        header = tuple(reader.fieldnames or ())
                        rows = list(reader)
                    sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    page.locator("#campaign-export-history-refresh").click()
                    page.wait_for_function(
                        "() => document.querySelector('#campaign-export-history-body')?.textContent"
                        ".includes('COMPLETED')", timeout=30_000)
                    with sqlite3.connect(database) as connection:
                        events = connection.execute(
                            "SELECT status,export_profile,selected_count,deliverable_count,"
                            "undeliverable_count,row_count,csv_sha256 FROM campaign_export_events "
                            "WHERE campaign_id=? ORDER BY export_event_id",
                            (args.campaign_id,),
                        ).fetchall()
                    assert len(events) == 2 and events[0][0] == "ABORTED"
                    latest = events[1]
                    assert latest[0:3] == ("COMPLETED", "DIRECT_MAIL_CONTACT_V1", 200)
                    assert latest[3] + latest[4] == latest[2]
                    assert latest[3] == latest[5] == len(rows)
                    assert latest[6] == sha and len({row["person_id"] for row in rows}) == len(rows)
                    assert "postal_code" in header
                    assert not capture.page_errors and not capture.request_failures
                    save_screenshot(page, root / "screenshots" / "campaign_direct_mail_recovered_edge.png")
                    report.update({"status": "PASS_RESTART_AND_EDGE_EXPORT",
                                   "browser": session.metadata.to_dict(),
                                   "selected": 200, "deliverable": len(rows), "excluded": latest[4],
                                   "csv_sha256": sha, "header": header,
                                   "event_statuses": [item[0] for item in events],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RESTART_AND_EDGE_EXPORT",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_campaign_export_recovery.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_RESTART_AND_EDGE_EXPORT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
