"""Verify visible v1/v2 result controls through installed headed Chrome."""

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
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_legacy_v1_reopen.json").is_file():
        raise ValueError("Legacy detail actions require the owned v1/v2 QA root.")
    report = {"scope": "BUSINESS_NATIVE_LEGACY_DETAIL_ACTIONS", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            runs = connection.execute(
                "SELECT search_run_id,selection_contract_version,selected_count "
                "FROM campaign_search_runs WHERE status='COMPLETED' "
                "AND selection_contract_version IN ('1','2') ORDER BY search_run_id"
            ).fetchall()
            before_feedback = connection.execute("SELECT COUNT(*) FROM campaign_feedback_batches").fetchone()[0]
            before_runs = connection.execute("SELECT COUNT(*) FROM campaign_search_runs").fetchone()[0]
        assert len(runs) == 3 and sorted(row[1] for row in runs) == ["1", "2", "2"]
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "legacy_detail_actions_profile",
                downloads_dir=root / "legacy_detail_actions_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(25_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    for run_id, version, selected in runs:
                        page.goto(base + f"#results/{run_id}", wait_until="domcontentloaded")
                        page.wait_for_function(
                            "id => document.querySelector('#result-detail-run-id')?.textContent"
                            ".includes(`Search #${id}`) && "
                            "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                            arg=run_id, timeout=60_000)
                        with page.expect_response(
                            lambda response: response.url.endswith(f"/runs/{run_id}/result")
                            and response.request.method == "GET", timeout=30_000,
                        ) as refresh_response:
                            page.locator("#result-detail-refresh").click()
                        detail = refresh_response.value.json()
                        assert refresh_response.value.status == 200
                        assert detail["selection_contract_version"] == version
                        assert detail["selected_count"] == selected
                        if not page.locator("#result-technical-disclosure").evaluate("el => el.open"):
                            page.locator("#result-technical-disclosure summary").click()
                        assert page.locator("#result-technical-disclosure").evaluate("el => el.open")
                        technical = page.locator("#result-technical-details").inner_text()
                        assert "selection contract version" in technical.lower(), (run_id, technical[:300])
                        report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_REFRESH_TECHNICAL",
                                                "status": "PASS", "selected": selected})

                        for kind in ("csv", "json"):
                            with page.expect_download(timeout=30_000) as download_info:
                                page.locator(f"#result-feedback-{kind}-template").click()
                            download = download_info.value
                            destination = root / "legacy_detail_actions_downloads" / (
                                f"run{run_id}_{download.suggested_filename}")
                            download.save_as(destination)
                            body = destination.read_text(encoding="utf-8-sig")
                            assert "person_id" in body and "outcome" in body and "outcome_at" in body
                            report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_{kind.upper()}_TEMPLATE",
                                                    "status": "PASS", "sha256": hashlib.sha256(
                                                        destination.read_bytes()).hexdigest()})
                        if not page.locator("#result-feedback-format-guide").evaluate("el => el.open"):
                            page.locator("#result-feedback-format-guide summary").click()
                        assert page.locator("#result-feedback-format-guide").evaluate("el => el.open")
                        report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_FORMAT_GUIDE",
                                                "status": "PASS"})
                        page.locator("#result-feedback-upload").click()
                        assert "Choose a CSV or JSON file first" in page.locator(
                            "#result-feedback-status").inner_text()
                        page.locator("#result-feedback-file").set_input_files({
                            "name": "wrong-member.json", "mimeType": "application/json",
                            "buffer": json.dumps({"rows": [{"person_id": "NOT_IN_RESULT",
                                "outcome": 1, "outcome_at": "2026-01-01T00:00:00Z"}]}).encode(),
                        })
                        assert page.locator("#result-feedback-file-name").inner_text() == "wrong-member.json"
                        with page.expect_response(
                            lambda response: response.url.endswith(f"/runs/{run_id}/feedback")
                            and response.request.method == "POST", timeout=30_000,
                        ) as bad_upload:
                            page.locator("#result-feedback-upload").click()
                        assert bad_upload.value.status == 422
                        page.wait_for_function(
                            "() => !document.querySelector('#result-feedback-status')?.textContent"
                            ".includes('Validating governed outcome feedback')", timeout=30_000)
                        assert "accepted" not in page.locator("#result-feedback-status").inner_text().lower()
                        report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_UPLOAD_GUARDS",
                                                "status": "PASS", "http_status": 422})

                        if page.locator("#result-detail-download").is_visible():
                            with page.expect_download(timeout=45_000) as download_info:
                                page.locator("#result-detail-download").click()
                            download = download_info.value
                            destination = root / "legacy_detail_actions_downloads" / (
                                f"run{run_id}_{download.suggested_filename}")
                            download.save_as(destination)
                            assert destination.stat().st_size > 0
                            with destination.open("r", encoding="utf-8-sig", newline="") as stream:
                                reader = csv.DictReader(stream)
                                exported = list(reader)
                            with sqlite3.connect(database) as connection:
                                audit = connection.execute(
                                    "SELECT selected_count,deliverable_count,undeliverable_count,"
                                    "row_count,csv_sha256 FROM campaign_result_export_events "
                                    "WHERE search_run_id=? ORDER BY export_event_id DESC LIMIT 1",
                                    (run_id,),
                                ).fetchone()
                            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                            assert audit and audit[0] == selected
                            assert audit[0] == audit[1] + audit[2]
                            assert audit[1] == audit[3] == len(exported)
                            assert audit[4] == digest
                            report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_EXPORT",
                                                    "status": "PASS", "sha256": digest,
                                                    "exported": len(exported)})
                        elif selected == 0:
                            report["cases"].append({"id": f"LEGACY_V{version}_{run_id}_ZERO_EXPORT_STATE",
                                                    "status": "PASS", "visible": page.locator(
                                                        "#result-detail-download").is_visible()})
                        if version == "2":
                            page.locator("#result-detail-run-again").click()
                            page.wait_for_url("**/#find-potential-customers", timeout=30_000)
                            page.locator('input[name="business_score_mode"][value="probability"]').wait_for(
                                state="visible", timeout=30_000)
                            assert page.locator('input[name="business_score_mode"][value="probability"]').is_checked()
                            page.goto(base + f"#results/{run_id}", wait_until="domcontentloaded")
                            page.locator("#result-detail-content").wait_for(state="visible", timeout=60_000)
                            report["cases"].append({"id": f"LEGACY_V2_{run_id}_RUN_AGAIN_RESTORE",
                                                    "status": "PASS"})
                        else:
                            assert page.locator("#result-detail-run-again").count() == 0
                        save_screenshot(page, root / "screenshots" / f"legacy_detail_{run_id}.png")

                    with sqlite3.connect(database) as connection:
                        after_feedback = connection.execute("SELECT COUNT(*) FROM campaign_feedback_batches").fetchone()[0]
                        after_runs = connection.execute("SELECT COUNT(*) FROM campaign_search_runs").fetchone()[0]
                    assert [after_feedback, after_runs] == [before_feedback, before_runs]
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_LEGACY_DETAIL_ACTIONS", "browser": session.metadata.to_dict(),
                                   "runs": runs, "feedback_batches_before_after": [before_feedback, after_feedback],
                                   "search_runs_before_after": [before_runs, after_runs],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_LEGACY_DETAIL_ACTIONS", "error_type": type(exc).__name__,
                       "error": str(exc)[:1700], "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_legacy_detail_actions.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_LEGACY_DETAIL_ACTIONS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
