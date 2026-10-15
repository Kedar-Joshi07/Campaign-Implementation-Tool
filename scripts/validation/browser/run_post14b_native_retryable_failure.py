"""One-shot QA fault, real UI retry, and genuine bounded v3 worker recovery."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _attempts(database):
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT attempt_number,status,failure_code,retryable,completed_at "
            "FROM campaign_search_attempts WHERE search_run_id=1 ORDER BY attempt_number"
        ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--two-tabs", action="store_true")
    args = parser.parse_args()
    root = prepare_qa_root(fixture_kind="FAULT_ONCE")
    print(f"Retryable-failure QA root: {root}", flush=True)
    report = {"scope": "FAULT_NATIVE_ONE_SHOT_RETRY", "status": "NOT_RUN",
              "qa_root": str(root)}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                responses = []

                def on_response(response):
                    if "/api/potential-customer-search/runs" in response.url:
                        responses.append({"method": response.request.method,
                                          "path": response.url.split("/api/", 1)[-1],
                                          "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                              wait_until="domcontentloaded")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                    trigger = page.locator("#business-product_ids-trigger")
                    trigger.click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    trigger.press("Escape")
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
                    assert profile
                    page.locator("#business-export-profile").select_option(profile)
                    page.locator("#business-campaign-name").fill("Bounded one-shot retry")
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=30_000)
                    run_id = int(page.url.rsplit("/", 1)[-1])
                    assert run_id == 1
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'FAILED'",
                        arg=run_id, timeout=90_000,
                    )
                    assert (root / "fault_once_fired.json").is_file()
                    failure_issue = page.locator("#result-detail-issue").inner_text()
                    assert "retry" in failure_issue.lower() or "try again" in failure_issue.lower()
                    retry = page.locator("#result-detail-issue button:has-text('Retry Search')")
                    assert retry.is_visible() and retry.is_enabled()
                    first_attempts = _attempts(database)
                    assert len(first_attempts) == 1
                    assert first_attempts[0][0:2] == (1, "FAILED")
                    assert first_attempts[0][3] == 1
                    if args.two_tabs:
                        other = session.context.new_page()
                        other.goto(f"http://127.0.0.1:{port}/#results/{run_id}",
                                   wait_until="domcontentloaded", timeout=60_000)
                        other_retry = other.locator("#result-detail-issue button:has-text('Retry Search')")
                        other_retry.wait_for(state="visible", timeout=30_000)
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith(f"/api/potential-customer-search/runs/{run_id}/retry"),
                            timeout=30_000,
                        ) as retry_response, other.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith(f"/api/potential-customer-search/runs/{run_id}/retry"),
                            timeout=30_000,
                        ) as competing_response:
                            retry.click()
                            other_retry.click()
                        competing_status = competing_response.value.status
                        assert competing_status in (202, 409), competing_status
                        report["competing_retry_status"] = competing_status
                        report["second_tab_retry_visible_before_click"] = True
                    else:
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith(f"/api/potential-customer-search/runs/{run_id}/retry"),
                            timeout=30_000,
                        ) as retry_response:
                            retry.click()
                    assert retry_response.value.status in (200, 201, 202)
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=run_id, timeout=240_000,
                    )
                    second_attempts = _attempts(database)
                    assert len(second_attempts) == 2
                    assert second_attempts[0] == first_attempts[0]
                    assert second_attempts[1][0:2] == (2, "COMPLETED")
                    with sqlite3.connect(database) as connection:
                        run = connection.execute(
                            "SELECT status,current_attempt_number,selected_count,"
                            "similarity_generation_id,similarity_result_snapshot_id "
                            "FROM campaign_search_runs WHERE search_run_id=?", (run_id,),
                        ).fetchone()
                        profile_count = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_profiles"
                        ).fetchone()[0]
                        generation_count = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_score_generations"
                        ).fetchone()[0]
                    assert run[0:3] == ("COMPLETED", 2, 200)
                    assert run[3] > 0 and run[4] > 0
                    assert profile_count == generation_count == 1
                    assert page.locator("#result-detail-issue").is_hidden()
                    save_screenshot(page, root / "screenshots" / "retry_completed.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": ("PASS_FAULT_TWO_TAB_RETRY_FENCED" if args.two_tabs
                                              else "PASS_FAULT_RETRY_COMPLETED"),
                                   "browser": session.metadata.to_dict(),
                                   "run_id": run_id, "failure_issue": failure_issue,
                                   "first_attempts": first_attempts,
                                   "final_attempts": second_attempts,
                                   "run": run, "profile_count": profile_count,
                                   "generation_count": generation_count,
                                   "api_responses": responses,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                except Exception:
                    try:
                        report["failure_state"] = page.evaluate("""() => ({
                          hash: location.hash,
                          badge: document.querySelector('#result-detail-badge')?.dataset.status,
                          status: document.querySelector('#result-detail-status')?.textContent,
                          issue: document.querySelector('#result-detail-issue')?.textContent,
                        })""")
                        report["failure_console_errors"] = capture.console_errors
                        report["failure_page_errors"] = capture.page_errors
                    except Exception:
                        pass
                    raise
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_FAULT_RETRY_COMPLETED",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_retry_two_tabs.json" if args.two_tabs
                       else "native_retryable_failure.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] in {
        "PASS_FAULT_RETRY_COMPLETED", "PASS_FAULT_TWO_TAB_RETRY_FENCED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
