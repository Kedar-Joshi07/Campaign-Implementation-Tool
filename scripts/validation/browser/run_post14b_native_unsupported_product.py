"""Exercise a genuine v3 support block through the headed business UI."""

from __future__ import annotations

import json
import sqlite3
import traceback
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root(fixture_kind="SPARSE_BUYERS")
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Only the dedicated Post-14B QA root is allowed.")
    print(f"Unsupported-product QA root: {root}", flush=True)
    report = {"scope": "BUSINESS_NATIVE_PERMANENT_SUPPORT_BLOCK", "status": "NOT_RUN",
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
                try:
                    with sqlite3.connect(database) as connection:
                        existing = connection.execute(
                            "SELECT search_run_id,status FROM campaign_search_runs ORDER BY search_run_id LIMIT 1"
                        ).fetchone()
                    if existing:
                        assert existing[1] == "BLOCKED"
                        run_id = int(existing[0])
                        preflight = None
                        page.goto(f"http://127.0.0.1:{port}/#results/{run_id}",
                                  wait_until="domcontentloaded")
                    else:
                        page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                                  wait_until="domcontentloaded")
                        page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                        race_states = page.evaluate("""async () => {
                          const { isRunActive } = await import('/static/js/run-progress.js');
                          return [
                            isRunActive({status:'PROCESSING', progress:{lifecycle_status:'BLOCKED'}}),
                            isRunActive({status:'BLOCKED', progress:{lifecycle_status:'PROCESSING'}}),
                            isRunActive({status:'BLOCKED', progress:{lifecycle_status:'BLOCKED'}}),
                          ];
                        }""")
                        assert race_states == [True, True, False]
                        report["mixed_status_polling_contract"] = race_states
                        product = page.locator("#business-product_ids-trigger")
                        product.click()
                        page.locator("#business-product_ids-panel input[value='P4']").check()
                        product.press("Escape")
                        profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                          .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
                        assert profile
                        page.locator("#business-export-profile").select_option(profile)
                        page.locator("#business-campaign-name").fill("Bounded unsupported P4")
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith("/api/potential-customer-search/preflight"),
                            timeout=30_000,
                        ) as preflight_info:
                            page.locator("#business-search-preflight").click()
                        preflight = preflight_info.value.json()
                        assert preflight_info.value.status == 200
                        page.locator("#business-search-submit").click()
                        page.wait_for_url("**/#results/*", timeout=30_000)
                        run_id = int(page.url.rsplit("/", 1)[-1])
                    try:
                        page.wait_for_function(
                            "id => document.querySelector('#result-detail-run-id')?.textContent"
                            ".includes(`Search #${id}`) && "
                            "document.querySelector('#result-detail-badge')?.dataset.status === 'BLOCKED'",
                            arg=run_id, timeout=45_000,
                        )
                    except Exception:
                        report["browser_failure_state"] = page.evaluate("""() => ({
                          hash: location.hash,
                          runId: document.querySelector('#result-detail-run-id')?.textContent,
                          badge: document.querySelector('#result-detail-badge')?.dataset.status,
                          detailHidden: document.querySelector('#result-detail-content')?.hidden,
                          errorHidden: document.querySelector('#result-detail-error')?.hidden,
                          status: document.querySelector('#result-detail-status')?.textContent,
                          issue: document.querySelector('#result-detail-issue')?.textContent,
                        })""")
                        report["browser_failure_console_errors"] = list(capture.console_errors)
                        report["browser_failure_page_errors"] = list(capture.page_errors)
                        report["browser_failure_request_failures"] = list(capture.request_failures)
                        save_screenshot(page, root / "screenshots" / "unsupported_product_initial_failure.png")
                        raise
                    issue_text = page.locator("#result-detail-issue").inner_text()
                    assert page.locator("#result-detail-issue").is_visible()
                    assert "buyer" in issue_text.lower() or "history" in issue_text.lower()
                    assert page.locator("#result-detail-issue button:has-text('Retry Search')").count() == 0
                    with sqlite3.connect(database) as connection:
                        run = connection.execute(
                            "SELECT status,current_attempt_number,selected_count "
                            "FROM campaign_search_runs WHERE search_run_id=?", (run_id,),
                        ).fetchone()
                        runtime = connection.execute(
                            "SELECT failure_code,failure_category,failure_summary,retryable "
                            "FROM campaign_search_run_runtime WHERE search_run_id=?", (run_id,),
                        ).fetchone()
                        attempts = connection.execute(
                            "SELECT attempt_number,status,retryable FROM campaign_search_attempts "
                            "WHERE search_run_id=?", (run_id,),
                        ).fetchall()
                        profile_count = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_profiles"
                        ).fetchone()[0]
                    assert run == ("BLOCKED", 1, None)
                    assert runtime[0] == "PROFILE_NOT_ELIGIBLE" and runtime[3] == 0
                    assert attempts == [(1, "BLOCKED", 0)]
                    assert profile_count == 0
                    page.goto(f"http://127.0.0.1:{port}/#results", wait_until="domcontentloaded")
                    card = page.locator(f".result-card[data-search-run-id='{run_id}']")
                    card.wait_for(state="visible", timeout=30_000)
                    assert card.locator(".result-status-badge").get_attribute("data-status") == "BLOCKED"
                    assert "buyer" in card.inner_text().lower() or "history" in card.inner_text().lower()
                    assert card.locator("button:has-text('Retry Search')").count() == 0
                    save_screenshot(page, root / "screenshots" / "unsupported_product_history.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_PERMANENT_SUPPORT_BLOCK",
                                   "browser": session.metadata.to_dict(),
                                   "run_id": run_id, "reopened": bool(existing),
                                   "preflight_status": (preflight or {}).get("status"),
                                   "preflight_qualifying": (preflight or {}).get("similarity_qualifying_count"),
                                   "run": run, "runtime": runtime,
                                   "attempts": attempts, "profile_count": profile_count,
                                   "issue_text": issue_text,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_PERMANENT_SUPPORT_BLOCK",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3500:]})
        try:
            report["browser_failure_state"] = page.evaluate("""() => ({
              hash: location.hash,
              runId: document.querySelector('#result-detail-run-id')?.textContent,
              badge: document.querySelector('#result-detail-badge')?.dataset.status,
              detailHidden: document.querySelector('#result-detail-content')?.hidden,
              errorHidden: document.querySelector('#result-detail-error')?.hidden,
              status: document.querySelector('#result-detail-status')?.textContent,
              issue: document.querySelector('#result-detail-issue')?.textContent,
            })""")
            report["browser_failure_console_errors"] = capture.console_errors
            report["browser_failure_page_errors"] = capture.page_errors
            report["browser_failure_request_failures"] = capture.request_failures
        except Exception:
            pass
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_unsupported_product_reopen.json" if args.qa_root
                       else "native_unsupported_product.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_PERMANENT_SUPPORT_BLOCK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
