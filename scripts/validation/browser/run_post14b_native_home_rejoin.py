"""Headed-browser Home failure/retry and search page-close/rejoin on bounded QA."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def _state(database: Path) -> dict:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT search_run_id,status,current_attempt_number,selected_count "
            "FROM campaign_search_runs ORDER BY search_run_id DESC LIMIT 1"
        ).fetchone()
        return {
            "run": dict(run) if run else None,
            "attempts": connection.execute(
                "SELECT COUNT(*) FROM campaign_search_attempts"
            ).fetchone()[0],
            "snapshots": connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_result_snapshots"
            ).fetchone()[0],
            "generations": connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_score_generations"
            ).fetchone()[0],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart-server", action="store_true")
    args = parser.parse_args()
    root = prepare_qa_root()
    report = {"scope": "BUSINESS_NATIVE_HOME_FAILURE_AND_PAGE_REJOIN",
              "status": "NOT_RUN", "qa_root": str(root), "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        assert _state(database)["run"] is None
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                base = f"http://127.0.0.1:{port}/"
                try:
                    page.goto(base + "#results", wait_until="domcontentloaded")
                    page.locator("#results-view").wait_for(state="visible")
                    # A genuine failed fetch, never a fabricated successful API response.
                    page.route("**/api/business/overview", lambda route: route.abort("failed"))
                    page.locator("#nav-home").click()
                    page.locator("#overview-error").wait_for(state="visible")
                    assert "Unavailable" in page.locator("#home-search-runs").inner_text()
                    assert page.locator("#backend-status").get_attribute("class").find("is-offline") >= 0
                    save_screenshot(page, root / "screenshots" / "home_transport_failed.png")
                    page.unroute("**/api/business/overview")
                    with page.expect_response(lambda response: response.url.endswith(
                        "/api/business/overview") and response.status == 200):
                        page.locator("#overview-retry").click()
                    page.locator("#overview-error").wait_for(state="hidden")
                    page.wait_for_function("document.querySelector('#home-search-runs')?.textContent === '0'")
                    page.locator("#home-results-empty").wait_for(state="visible", timeout=30_000)
                    assert _state(database)["run"] is None
                    report["cases"].append({"id": "HOME_FAILED_FETCH_RETRY_REAL_EMPTY", "status": "PASS"})

                    page.locator("#home-find-potential-customers").click()
                    page.locator("#business-search-form").wait_for(state="visible")
                    page.locator("#business-campaign-name").fill("Bounded page-close rejoin")
                    trigger = page.locator("#business-product_ids-trigger")
                    trigger.click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    trigger.press("Escape")
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.textContent.includes('Email'))?.value || ''""")
                    assert profile
                    page.locator("#business-export-profile").select_option(profile)
                    with page.expect_response(lambda response: response.request.method == "POST"
                                              and response.url.endswith("/api/potential-customer-search/runs"),
                                              timeout=30_000) as submitted:
                        page.locator("#business-search-submit").click()
                    assert submitted.value.status in (200, 201, 202)
                    run_id = int(submitted.value.json()["search_run_id"])
                    before_close = _state(database)
                    report["state_at_page_close"] = before_close
                    # Keep the QA-only persistent Chrome profile alive while its
                    # application tab is closed and the owned server is restarted.
                    keeper = session.context.new_page()
                    keeper.goto("about:blank")
                    page.close()
                    detach_page_event_capture(page, listeners)

                    if args.restart_server:
                        assert before_close["run"]["status"] in {"QUEUED", "PROCESSING"}
                        stop_qa_server(process)
                        assert process.poll() is not None
                        process, port = start_qa_server(root)
                        base = f"http://127.0.0.1:{port}/"
                        report["server_restart_after_page_close"] = True

                    reopened = session.context.new_page()
                    keeper.close()
                    reopened.goto(base + f"#results/{run_id}", wait_until="domcontentloaded")
                    reopened.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=run_id, timeout=240_000,
                    )
                    final = _state(database)
                    assert final["run"]["status"] == "COMPLETED"
                    assert final["run"]["current_attempt_number"] == 1
                    assert final["run"]["selected_count"] > 0
                    assert final["attempts"] == final["snapshots"] == final["generations"] == 1
                    with sqlite3.connect(database) as connection:
                        stages = [row[0] for row in connection.execute(
                            "SELECT stage_code FROM campaign_search_progress_events "
                            "WHERE search_run_id=? ORDER BY progress_event_id", (run_id,)
                        )]
                        active = connection.execute(
                            "SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')"
                        ).fetchone()[0]
                    assert "SCORING_PROSPECTS" in stages and "COMPLETED" in stages
                    assert active == 0
                    with sqlite3.connect(database) as connection:
                        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
                        population = connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0]
                    assert integrity == "ok" and not foreign_keys and population == 200
                    admissions = [json.loads(line) for line in
                                  (root / "guard_admissions.jsonl").read_text(encoding="utf-8").splitlines()]
                    assert admissions
                    assert all(entry["counts"]["demographics"] <= entry["cap"] <= 2_000
                               for entry in admissions)
                    assert any(entry["operation"] == "v3_score_generation" for entry in admissions)
                    assert reopened.locator("#result-detail-download").is_visible()
                    save_screenshot(reopened, root / "screenshots" / "result_rejoined_new_page.png")
                    report["cases"].append({"id": "PAGE_CLOSE_REOPEN_DURABLE_SEARCH", "status": "PASS",
                                            "state_at_close": before_close["run"]["status"],
                                            "final_selected_count": final["run"]["selected_count"],
                                            "stages": stages})
                    if args.restart_server:
                        report["cases"].append({"id": "SERVER_RESTART_RECOVERS_ACTIVE_SEARCH",
                                                "status": "PASS"})
                    report.update({"status": "PASS_HOME_FAILURE_AND_PAGE_REJOIN",
                                   "browser": session.metadata.to_dict(), "final_state": final,
                                   "sqlite_integrity": integrity,
                                   "foreign_key_violations": len(foreign_keys),
                                   "admitted_operations": [entry["operation"] for entry in admissions],
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    if not page.is_closed():
                        detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_HOME_FAILURE_AND_PAGE_REJOIN",
                       "error_type": type(exc).__name__, "error": str(exc)[:1500],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_home_restart_rejoin.json" if args.restart_server
                       else "native_home_rejoin.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_HOME_FAILURE_AND_PAGE_REJOIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
