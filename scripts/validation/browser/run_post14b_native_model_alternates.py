"""Retained model setup validation, bounded alternate training, and saved reopen."""

from __future__ import annotations

import argparse
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
    if root.parent != QA_PARENT.resolve() or not (root / "native_retained_planner_positive_resume.json").is_file():
        raise ValueError("Model alternates require the owned grouped-training QA root.")
    report = {"scope": "RETAINED_NATIVE_MODEL_ALTERNATES", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            before_models = connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0]
            before_scoring = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
            analysis = connection.execute(
                "SELECT analysis_run_id FROM historical_analysis_runs WHERE status='COMPLETED' "
                "AND positive_customer_count >= 100 AND unlabeled_customer_count >= 100 "
                "ORDER BY analysis_run_id LIMIT 1"
            ).fetchone()
        assert analysis and before_models >= 1
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "model_alternates_profile",
                downloads_dir=root / "model_alternates_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#model-training",
                              wait_until="domcontentloaded")
                    page.locator("#model-training-workspace").wait_for(state="visible", timeout=90_000)
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/models/training-options")
                        and response.request.method == "GET", timeout=30_000,
                    ) as refresh_response:
                        page.locator("#model-training-refresh").click()
                    assert refresh_response.value.status == 200
                    page.locator("#model-training-workspace").wait_for(state="visible", timeout=60_000)
                    page.locator("#source-analysis-select").select_option(str(analysis[0]))
                    report["cases"].append({"id": "MODEL_WORKSPACE_REFRESH_AND_SOURCE", "status": "PASS"})

                    page.locator("#random-seed-input").fill("2.5")
                    page.locator("#train-model-submit").click()
                    error = page.locator("#model-training-form-error")
                    error.wait_for(state="visible")
                    assert "whole number" in error.inner_text()
                    with sqlite3.connect(database) as connection:
                        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == before_models
                    report["cases"].append({"id": "MODEL_RANDOM_SEED_GUARD", "status": "PASS"})

                    page.locator("#random-seed-input").fill("73")
                    page.locator("#validation-fraction-input").fill("1.5")
                    page.locator("#train-model-submit").click()
                    error.wait_for(state="visible")
                    assert "greater than 0 and less than 1" in error.inner_text()
                    with sqlite3.connect(database) as connection:
                        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == before_models
                    report["cases"].append({"id": "MODEL_VALIDATION_FRACTION_GUARD", "status": "PASS"})

                    page.locator("#validation-fraction-input").fill("0.25")
                    page.locator("#run-elkan-challenger-input").uncheck()
                    page.locator("#model-name-input").fill("Bounded no-challenger alternate")
                    with page.expect_request(
                        lambda request: request.url.endswith("/api/models/train")
                        and request.method == "POST", timeout=30_000,
                    ) as request_info, page.expect_response(
                        lambda response: response.url.endswith("/api/models/train")
                        and response.request.method == "POST", timeout=30_000,
                    ) as response_info:
                        page.locator("#train-model-submit").click()
                    request_payload = request_info.value.post_data_json
                    assert request_payload["analysis_run_id"] == analysis[0]
                    assert request_payload["random_seed"] == 73
                    assert request_payload["validation_fraction"] == 0.25
                    assert request_payload["run_elkan_challenger"] is False
                    assert response_info.value.status == 202
                    page.wait_for_function(
                        "document.querySelector('#model-job-status')?.textContent.trim().toUpperCase()"
                        " === 'COMPLETED'", timeout=240_000)
                    with sqlite3.connect(database) as connection:
                        rows = connection.execute(
                            "SELECT model_run_id,status,analysis_run_id,random_seed,validation_fraction "
                            "FROM model_runs ORDER BY model_run_id"
                        ).fetchall()
                        scoring_after = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
                    assert len(rows) == before_models + 1
                    newest = rows[-1]
                    assert newest[1:] == ("COMPLETED", analysis[0], 73, 0.25)
                    assert scoring_after == before_scoring
                    report["cases"].append({"id": "MODEL_ALTERNATE_REAL_TRAIN_NO_CHALLENGER",
                                            "status": "PASS", "model_run_id": newest[0]})

                    with page.expect_response(
                        lambda response: "/api/models/" in response.url
                        and response.request.method == "GET", timeout=30_000,
                    ) as recent_response:
                        page.locator("#recent-model-runs-refresh").click()
                    assert recent_response.value.status == 200
                    page.locator("#recent-model-runs-body button").first.wait_for(
                        state="visible", timeout=30_000)
                    page.locator("#recent-model-runs-body button").first.click()
                    page.wait_for_function(
                        "id => document.querySelector('#summary-model-run-id')?.textContent"
                        ".includes(String(id))", arg=newest[0], timeout=60_000)
                    report["cases"].append({"id": "MODEL_RECENT_REFRESH_REOPEN", "status": "PASS"})
                    save_screenshot(page, root / "screenshots" / "model_alternates_completed.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_RETAINED_MODEL_ALTERNATES",
                                   "browser": session.metadata.to_dict(),
                                   "analysis_run_id": analysis[0],
                                   "model_runs_before_after": [before_models, len(rows)],
                                   "scoring_runs_before_after": [before_scoring, scoring_after],
                                   "request_payload": request_payload,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_MODEL_ALTERNATES",
                       "error_type": type(exc).__name__, "error": str(exc)[:1700],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_model_alternates.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_RETAINED_MODEL_ALTERNATES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
