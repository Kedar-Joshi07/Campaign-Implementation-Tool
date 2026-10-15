"""Exercise governed feedback uploads through headed Chrome on a completed QA run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, REPOSITORY_ROOT, prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _count(database: Path) -> tuple[int, int]:
    with sqlite3.connect(database) as connection:
        return (
            connection.execute("SELECT COUNT(*) FROM campaign_feedback_batches").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM campaign_feedback_outcomes").fetchone()[0],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root()
    if root.parent != QA_PARENT.resolve() or not (root / "qa_fixture_manifest.json").is_file():
        raise ValueError("Feedback matrix requires a dedicated Post-14B QA root.")
    prior = None
    run_id = None
    member = None
    if args.qa_root:
        if not (root / "native_export_matrix.json").is_file():
            raise ValueError("Reused feedback root requires completed export evidence.")
        prior = json.loads((root / "native_export_matrix.json").read_text(encoding="utf-8"))
        assert prior["status"] == "PASS_V3_ALL_AVAILABLE_EXPORT_PROFILES"
        for relative in (
            "frontend/js/business-search-status.js",
            "app/services/phase11_feedback_service.py",
            "app/routers/potential_customer_search.py",
        ):
            assert hashlib.sha256((root / "source" / relative).read_bytes()).digest() == hashlib.sha256(
                (REPOSITORY_ROOT / relative).read_bytes()).digest(), relative
        run_id = prior["profiles"][0]["run_id"]
        with (root / "downloads" / next(
            path.name for path in (root / "downloads").iterdir()
            if path.name.startswith("01_potential_customers_")))\
                .open("r", encoding="utf-8-sig", newline="") as source:
            member = next(csv.DictReader(source))["person_id"]
    report = {"scope": "BUSINESS_NATIVE_FEEDBACK_NEGATIVE_MATRIX", "status": "NOT_RUN",
              "qa_root": str(root), "run_id": run_id, "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        assert _count(database) == (0, 0)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "feedback_browser_profile",
                downloads_dir=root / "feedback_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    if run_id is None:
                        page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                                  wait_until="domcontentloaded")
                        page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                        page.locator("#business-campaign-name").fill("Bounded feedback matrix")
                        trigger = page.locator("#business-product_ids-trigger")
                        trigger.click()
                        page.locator("#business-product_ids-panel input[value='P1']").check()
                        trigger.press("Escape")
                        page.locator('input[name="business_score_mode"][value="similarity"]').check()
                        profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                          .find(o => !o.disabled && o.value && o.value.includes('EMAIL') &&
                            o.value.includes('V3'))?.value || ''""")
                        if not profile:
                            profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                              .find(o => !o.disabled && o.value && o.textContent.includes('Email'))?.value || ''""")
                        assert profile
                        page.locator("#business-export-profile").select_option(profile)
                        page.locator("#business-search-submit").click()
                        page.wait_for_url("**/#results/*", timeout=30_000)
                        run_id = int(page.url.rsplit("/", 1)[-1])
                        page.wait_for_function(
                            "id => document.querySelector('#result-detail-run-id')?.textContent"
                            ".includes(`Search #${id}`) && "
                            "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                            arg=run_id, timeout=240_000,
                        )
                        with page.expect_download(timeout=30_000) as download_info:
                            page.locator("#result-detail-download").click()
                        download = download_info.value
                        downloaded = root / "feedback_downloads" / download.suggested_filename
                        download.save_as(downloaded)
                        with downloaded.open("r", encoding="utf-8-sig", newline="") as source:
                            member = next(csv.DictReader(source))["person_id"]
                        report["run_id"] = run_id
                        report["cases"].append({"id": "FRESH_V3_PREREQUISITE", "status": "PASS",
                                                "run_id": run_id})
                    assert run_id is not None and member
                    page.goto(f"http://127.0.0.1:{port}/#results/{run_id}",
                              wait_until="domcontentloaded")
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-feedback-panel')?.hidden === false",
                        arg=run_id, timeout=30_000,
                    )
                    status = page.locator("#result-feedback-status")
                    upload = page.locator("#result-feedback-upload")
                    file_input = page.locator("#result-feedback-file")
                    upload.click()
                    assert "Choose a CSV or JSON" in status.inner_text()
                    report["cases"].append({"id": "NO_FILE_CLIENT_GUARD", "status": "PASS"})

                    fixture_dir = root / "feedback_matrix_fixtures"
                    fixture_dir.mkdir(exist_ok=True)
                    wrong_format = fixture_dir / "wrong_format.txt"
                    wrong_format.write_text("synthetic feedback only\n", encoding="utf-8")
                    file_input.set_input_files(wrong_format)
                    upload.click()
                    assert "Use the downloadable CSV or JSON template" in status.inner_text()
                    report["cases"].append({"id": "WRONG_EXTENSION_CLIENT_GUARD", "status": "PASS"})

                    cases = (
                        ("MISSING_COLUMNS", "csv", "person_id,outcome\n" + member + ",1\n", 422),
                        ("MALFORMED_JSON", "json", '{"rows": [', 422),
                        ("INVALID_UTF8_JSON", "json", b'\xff\xfe', 422),
                        ("JSON_ROWS_NOT_ARRAY", "json", '{"rows": {}}', 422),
                        ("EMPTY_JSON_ROWS", "json", '{"rows": []}', 422),
                        ("DUPLICATE_ROWS", "csv", "person_id,outcome,outcome_at\n" +
                         f"{member},1,2026-01-01T00:00:00Z\n{member},0,2026-01-01T00:00:00Z\n", 422),
                        ("UNKNOWN_MEMBER", "json", json.dumps({"rows": [{
                            "person_id": "NOT_A_RESULT_MEMBER", "outcome": 1,
                            "outcome_at": "2026-01-01T00:00:00Z"}]}), 422),
                        ("FUTURE_TIMESTAMP", "csv", "person_id,outcome,outcome_at\n" +
                         f"{member},1,2099-01-01T00:00:00Z\n", 422),
                        ("MISSING_TIMEZONE", "csv", "person_id,outcome,outcome_at\n" +
                         f"{member},1,2026-01-01T00:00:00\n", 422),
                        ("INVALID_OUTCOME", "csv", "person_id,outcome,outcome_at\n" +
                         f"{member},maybe,2026-01-01T00:00:00Z\n", 422),
                        ("NONFINITE_OUTCOME_VALUE", "csv", "person_id,outcome,outcome_at,outcome_value\n" +
                         f"{member},1,2026-01-01T00:00:00Z,nan\n", 422),
                        ("OVERSIZE_CSV", "csv", "person_id,outcome,outcome_at\n" +
                         "X" * (10 * 1024 * 1024 + 1), 422),
                        ("VALID_JSON", "json", json.dumps({"source_name": "bounded-synthetic-qa",
                            "rows": [{"person_id": member, "outcome": 1,
                                      "outcome_at": "2026-01-01T00:00:00Z"}]}), 201),
                        ("DUPLICATE_PRIOR_OUTCOME", "csv", "person_id,outcome,outcome_at\n" +
                         f"{member},0,2026-01-01T00:00:00Z\n", 409),
                    )
                    for case_id, suffix, content, expected_status in cases:
                        fixture = fixture_dir / f"{case_id.lower()}.{suffix}"
                        if isinstance(content, bytes):
                            fixture.write_bytes(content)
                        else:
                            fixture.write_text(content, encoding="utf-8")
                        file_input.set_input_files(fixture)
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith(f"/api/potential-customer-search/runs/{run_id}/feedback"),
                            timeout=30_000,
                        ) as response_info:
                            upload.click()
                        actual_status = response_info.value.status
                        page.wait_for_function("!document.querySelector('#result-feedback-upload').disabled")
                        message = status.inner_text()
                        assert actual_status == expected_status, (case_id, actual_status, message)
                        assert ("accepted" in message.lower()) == (expected_status == 201), (
                            case_id, message)
                        assert _count(database) == ((1, 1) if expected_status == 201 or
                            case_id == "DUPLICATE_PRIOR_OUTCOME" else (0, 0)), (case_id, _count(database))
                        if case_id == "VALID_JSON":
                            with sqlite3.connect(database) as connection:
                                lineage = connection.execute(
                                    "SELECT search_run_id,attempt_number,selection_contract_version,"
                                    "similarity_result_snapshot_id,similarity_generation_id,"
                                    "similarity_profile_set_sha256,similarity_score_method_version "
                                    "FROM campaign_feedback_batches").fetchone()
                            assert lineage[0:3] == (run_id, 1, "3")
                            assert lineage[3] > 0 and lineage[4] > 0
                            assert len(lineage[5]) == 64 and lineage[6] == "BUYER_PROFILE_DISTANCE_V1"
                            report["lineage"] = {"search_run_id": lineage[0],
                                                 "attempt_number": lineage[1],
                                                 "selection_contract_version": lineage[2],
                                                 "similarity_snapshot_id": lineage[3],
                                                 "similarity_generation_id": lineage[4],
                                                 "profile_sha256": lineage[5],
                                                 "score_method_version": lineage[6]}
                        report["cases"].append({"id": case_id, "status": "PASS",
                                                "http_status": actual_status,
                                                "safe_ui_message": message[:160]})
                        print(f"Feedback case {case_id}: HTTP {actual_status}", flush=True)
                    save_screenshot(page, root / "screenshots" / "feedback_matrix_terminal.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_FEEDBACK_NEGATIVE_MATRIX",
                                   "browser": session.metadata.to_dict(),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures,
                                   "database_counts": _count(database)})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_FEEDBACK_NEGATIVE_MATRIX",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_feedback_matrix.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_FEEDBACK_NEGATIVE_MATRIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
