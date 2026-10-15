"""One causal headed-Chrome v3 search case on the isolated bounded QA app.

This is a 19.3 business slice, not the comprehensive all-controls certificate.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


def _counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in (
                "customers", "campaign_sales", "demographics", "campaign_search_runs",
                "campaign_search_attempts", "buyer_similarity_profiles",
                "buyer_similarity_score_generations", "buyer_similarity_result_snapshots",
            )
        }


def main() -> int:
    root = prepare_qa_root()
    print(f"Business QA root: {root}", flush=True)
    process = None
    report = {"scope": "BUSINESS_NATIVE_ONE_FRESH_V3_CASE", "status": "NOT_RUN",
              "qa_root": str(root), "headless": False, "cases": []}
    try:
        process, port = start_qa_server(root, timeout_seconds=90.0)
        report["loopback_port"] = port
        database = root / "state" / "qa.db"
        before = _counts(database)
        report["database_before"] = before
        assert before["customers"] == 230 and before["campaign_sales"] == 640
        assert before["demographics"] == 200 and before["campaign_search_runs"] == 0
        responses = []
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)

                def on_response(response):
                    path = urlsplit(response.url).path
                    if path.startswith("/api/"):
                        responses.append({"method": response.request.method,
                                          "path": path, "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                              wait_until="domcontentloaded")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                    page.locator("#business-campaign-name").fill("Bounded native v3 P1 case")
                    trigger = page.locator("#business-product_ids-trigger")
                    trigger.click()
                    product = page.locator("#business-product_ids-panel input[value='P1']")
                    assert product.count() == 1
                    product.check()
                    trigger.press("Escape")
                    assert page.locator("#business-product_ids").evaluate(
                        "e => [...e.selectedOptions].map(o => o.value)") == ["P1"]
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.value.includes('EMAIL') &&
                        o.value.includes('V3'))?.value || ''""")
                    if not profile:
                        profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                          .find(o => !o.disabled && o.value && o.textContent.includes('Email'))?.value || ''""")
                    assert profile, "No available email export profile in bounded fixture."
                    page.locator("#business-export-profile").select_option(profile)
                    assert page.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
                    page.locator("#business-search-preflight").click()
                    page.wait_for_function("!document.querySelector('#business-search-preflight').disabled",
                                           timeout=30_000)
                    preflight_text = page.locator("#business-search-preflight-result").inner_text()
                    assert "Not prepared" in preflight_text or "not available" in preflight_text.lower(), preflight_text
                    report["cases"].append({"id": "V3_PREFLIGHT_UNPREPARED", "status": "PASS",
                                            "visible_state": preflight_text[:400]})
                    save_screenshot(page, root / "screenshots" / "v3_form_before_submit.png")
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=30_000)
                    run_id = int(page.url.rsplit("/", 1)[-1])
                    report["search_run_id"] = run_id
                    page.locator("#result-detail-content").wait_for(state="visible", timeout=30_000)
                    page.wait_for_function(
                        "() => ['COMPLETED','FAILED','BLOCKED'].includes("
                        "document.querySelector('#result-detail-badge')?.dataset.status)",
                        timeout=240_000,
                    )
                    status = page.locator("#result-detail-badge").get_attribute("data-status")
                    report["terminal_status"] = status
                    report["visible_terminal_message"] = page.locator("#result-detail-status").inner_text()[:400]
                    assert status == "COMPLETED", report["visible_terminal_message"]
                    save_screenshot(page, root / "screenshots" / "v3_completed_detail.png")
                    with sqlite3.connect(database) as connection:
                        connection.row_factory = sqlite3.Row
                        run = dict(connection.execute(
                            "SELECT search_run_id,status,selected_count,result_source,"
                            "selection_contract_version FROM campaign_search_runs WHERE search_run_id=?",
                            (run_id,),
                        ).fetchone())
                        events = [dict(row) for row in connection.execute(
                            "SELECT stage_code,processed_count,total_count "
                            "FROM campaign_search_progress_events WHERE search_run_id=? "
                            "ORDER BY progress_event_id", (run_id,),
                        )]
                    assert run["status"] == "COMPLETED"
                    assert run["selection_contract_version"] == "3"
                    assert 0 < run["selected_count"] <= 200
                    assert any(event["stage_code"] == "SCORING_PROSPECTS" for event in events)
                    assert any(event["stage_code"] == "COMPLETED" for event in events)
                    assert page.locator("#result-detail-download").is_visible()
                    with page.expect_download(timeout=30_000) as download_info:
                        page.locator("#result-detail-download").click()
                    download = download_info.value
                    export_path = root / "downloads" / download.suggested_filename
                    download.save_as(export_path)
                    with export_path.open("r", encoding="utf-8-sig", newline="") as file:
                        rows = list(csv.DictReader(file))
                    assert rows and all(row["email"].endswith("@example.test") for row in rows)
                    assert len({row["person_id"] for row in rows}) == len(rows)
                    assert len(rows) <= run["selected_count"]
                    export_sha = hashlib.sha256(export_path.read_bytes()).hexdigest()
                    with sqlite3.connect(database) as connection:
                        export_event = connection.execute(
                            "SELECT status,selected_count,deliverable_count,undeliverable_count,"
                            "row_count,csv_sha256 FROM buyer_similarity_export_events "
                            "WHERE search_run_id=? ORDER BY export_event_id DESC LIMIT 1",
                            (run_id,),
                        ).fetchone()
                    assert export_event is not None
                    assert export_event[0] == "COMPLETED"
                    assert (export_event[1], export_event[2] + export_event[3]) == (
                        run["selected_count"], run["selected_count"])
                    assert export_event[4] == len(rows)
                    assert export_event[5] == export_sha
                    page.locator("#result-detail-refresh").click()
                    page.wait_for_function(
                        "() => { const text = document.querySelector('#result-download-details')?.textContent || '';"
                        " return text.includes('160') && text.includes('40'); }",
                        timeout=30_000,
                    )
                    report["cases"].append({"id": "V3_EXPORT_AUDIT_VISIBLE_AFTER_REFRESH",
                                            "status": "PASS", "selected_count": 200,
                                            "exportable_count": 160, "excluded_count": 40})
                    report["cases"].append({"id": "V3_FRESH_UI_TO_WORKER_TO_DB_TO_EXPORT",
                                            "status": "PASS", "search_run_id": run_id,
                                            "selection_contract_version": run["selection_contract_version"],
                                            "selected_count": run["selected_count"],
                                            "exported_count": len(rows),
                                            "export_sha256": export_sha,
                                            "event_count": len(events),
                                            "stages": list(dict.fromkeys(e["stage_code"] for e in events))})
                    templates = {}
                    for kind in ("csv", "json"):
                        with page.expect_download(timeout=30_000) as template_info:
                            page.locator(f"#result-feedback-{kind}-template").click()
                        template_download = template_info.value
                        template_path = root / "downloads" / template_download.suggested_filename
                        template_download.save_as(template_path)
                        content = template_path.read_text(encoding="utf-8-sig")
                        if kind == "csv":
                            assert list(csv.DictReader(content.splitlines()))
                            assert content.startswith("person_id,outcome,outcome_at")
                        else:
                            assert isinstance(json.loads(content)["rows"], list)
                        templates[kind] = hashlib.sha256(template_path.read_bytes()).hexdigest()
                    page.locator("#result-feedback-format-guide summary").click()
                    assert page.locator("#result-feedback-format-guide").get_attribute("open") is not None
                    feedback_path = root / "downloads" / "synthetic_verified_outcome.csv"
                    with feedback_path.open("w", encoding="utf-8", newline="") as file:
                        writer = csv.DictWriter(file, fieldnames=("person_id", "outcome", "outcome_at"))
                        writer.writeheader()
                        writer.writerow({"person_id": rows[0]["person_id"], "outcome": "1",
                                         "outcome_at": "2026-01-01T00:00:00Z"})
                    page.locator("#result-feedback-file").set_input_files(feedback_path)
                    page.locator("#result-feedback-upload").click()
                    page.locator("#result-feedback-status").get_by_text(
                        "1 outcomes accepted", exact=False).wait_for(timeout=30_000)
                    with sqlite3.connect(database) as connection:
                        batch_count = connection.execute(
                            "SELECT COUNT(*) FROM campaign_feedback_batches WHERE search_run_id=?",
                            (run_id,),
                        ).fetchone()[0]
                        outcome_count = connection.execute(
                            "SELECT COUNT(*) FROM campaign_feedback_outcomes o "
                            "JOIN campaign_feedback_batches b ON b.feedback_batch_id=o.feedback_batch_id "
                            "WHERE b.search_run_id=?",
                            (run_id,),
                        ).fetchone()[0]
                    assert batch_count == 1 and outcome_count == 1
                    report["cases"].append({"id": "V3_NATIVE_FEEDBACK_TEMPLATES_AND_UPLOAD",
                                            "status": "PASS", "template_sha256": templates,
                                            "accepted_outcomes": outcome_count})
                    invalid_path = root / "downloads" / "synthetic_wrong_member.json"
                    invalid_path.write_text(json.dumps({"rows": [{
                        "person_id": "NOT_IN_THIS_RESULT", "outcome": 1,
                        "outcome_at": "2026-01-01T00:00:00Z",
                    }]}) + "\n", encoding="utf-8")
                    page.locator("#result-feedback-file").set_input_files(invalid_path)
                    page.locator("#result-feedback-upload").click()
                    page.wait_for_function(
                        "() => { const text = document.querySelector('#result-feedback-status')?.textContent || '';"
                        " return text && !text.includes('Validating governed outcome feedback'); }",
                        timeout=30_000,
                    )
                    invalid_message = page.locator("#result-feedback-status").inner_text()
                    assert "accepted" not in invalid_message.lower(), invalid_message
                    with sqlite3.connect(database) as connection:
                        assert connection.execute(
                            "SELECT COUNT(*) FROM campaign_feedback_batches WHERE search_run_id=?",
                            (run_id,),
                        ).fetchone()[0] == 1
                    assert any(r["method"] == "POST" and r["path"].endswith("/feedback")
                               and r["status"] == 422 for r in responses)
                    report["cases"].append({"id": "V3_NATIVE_FEEDBACK_WRONG_MEMBER_REJECTED",
                                            "status": "PASS", "http_status": 422,
                                            "safe_ui_message": invalid_message[:200]})
                    page.locator("#result-detail-run-again").click()
                    page.wait_for_url("**/#find-potential-customers", timeout=30_000)
                    page.locator("#business-search-form").wait_for(state="visible")
                    assert page.locator("#business-product_ids").evaluate(
                        "e => [...e.selectedOptions].map(o => o.value)") == ["P1"]
                    assert page.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
                    page.locator("#business-campaign-name").fill("Bounded native v3 P1 exact repeat")
                    page.locator("#business-search-preflight").click()
                    page.wait_for_function("!document.querySelector('#business-search-preflight').disabled",
                                           timeout=30_000)
                    ready_text = page.locator("#business-search-preflight-result").inner_text()
                    assert "Current buyer similarity" in ready_text, ready_text
                    assert "200" in ready_text, ready_text
                    report["cases"].append({"id": "V3_READY_EXACT_PREFLIGHT", "status": "PASS",
                                            "visible_state": ready_text[:400]})
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=30_000)
                    repeat_id = int(page.url.rsplit("/", 1)[-1])
                    assert repeat_id != run_id
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent.trim()"
                        " === `Search #${id}` && ['COMPLETED','FAILED','BLOCKED'].includes("
                        "document.querySelector('#result-detail-badge')?.dataset.status)",
                        arg=repeat_id,
                        timeout=120_000,
                    )
                    assert page.locator("#result-detail-badge").get_attribute("data-status") == "COMPLETED"
                    with sqlite3.connect(database) as connection:
                        repeat = connection.execute(
                            "SELECT result_source,selected_count FROM campaign_search_runs "
                            "WHERE search_run_id=?", (repeat_id,),
                        ).fetchone()
                    assert repeat == ("EXACT_RESULT_REUSE", 200), repeat
                    after_reuse = _counts(database)
                    assert after_reuse["buyer_similarity_profiles"] == 1
                    assert after_reuse["buyer_similarity_score_generations"] == 1
                    assert after_reuse["buyer_similarity_result_snapshots"] == 1
                    report["cases"].append({"id": "V3_UI_EXACT_RESULT_REUSE", "status": "PASS",
                                            "search_run_id": repeat_id, "selected_count": 200,
                                            "result_source": repeat[0]})
                    save_screenshot(page, root / "screenshots" / "v3_exact_reuse_detail.png")
                    report["browser"] = session.metadata.to_dict()
                    report["playwright_version"] = version("playwright")
                    report["api_responses"] = responses
                    report["console_errors"] = capture.console_errors
                    report["page_errors"] = capture.page_errors
                    report["request_failures"] = capture.request_failures
                    expected_console = [message for message in capture.console_errors
                                        if "422 (Unprocessable Entity)" in message]
                    unexpected_console = [message for message in capture.console_errors
                                          if message not in expected_console]
                    report["expected_console_errors"] = expected_console
                    report["unexpected_console_errors"] = unexpected_console
                    assert len(expected_console) == 1
                    assert not unexpected_console and not capture.page_errors and not capture.request_failures
                    assert any(r["method"] == "POST" and r["path"] == "/api/potential-customer-search/runs"
                               and r["status"] == 201 for r in responses)
                    assert any(r["method"] == "POST" and r["path"] == "/api/potential-customer-search/preflight"
                               and r["status"] == 200 for r in responses)
                    # Chrome's native download is not consistently surfaced as a
                    # page response; its file and durable export audit are the oracle.
                    report["database_after"] = _counts(database)
                    assert report["database_after"]["campaign_search_runs"] == 2
                    assert report["database_after"]["demographics"] == 200
                    report["status"] = "PASS_ONE_BUSINESS_CASE"
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_ONE_BUSINESS_CASE", "error_type": type(exc).__name__,
                       "error": str(exc)[:1200]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_business_case.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_ONE_BUSINESS_CASE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
