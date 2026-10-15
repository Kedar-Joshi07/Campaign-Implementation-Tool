"""Truthful 10K qualification branch on the named, capped 12K browser fixture."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import traceback

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    root = prepare_qa_root(fixture_kind="NAMED_10K_QUALIFICATION")
    print(f"Named 10K QA root: {root}", flush=True)
    report = {"scope": "BUSINESS_NATIVE_NAMED_10K_QUALIFICATION", "status": "NOT_RUN",
              "qa_root": str(root)}
    process = None
    try:
        process, port = start_qa_server(root, timeout_seconds=180.0)
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            demographics = connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0]
        assert demographics == 12_000
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "qualification_browser_profile",
                downloads_dir=root / "qualification_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded",
                              timeout=90_000)
                    page.locator("#business-search-form").wait_for(state="visible", timeout=60_000)
                    page.locator("#business-product_ids-trigger").click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    page.locator("#business-product_ids-trigger").press("Escape")
                    page.locator('input[name="business_score_mode"][value="similarity"]').check()
                    minimum = float(page.locator(
                        'input[name="business_similarity_minimum"]:checked').input_value())
                    assert minimum == 0.70
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
                    assert profile
                    page.locator("#business-export-profile").select_option(profile)
                    page.locator("#business-campaign-name").fill("Bounded 12K qualification check")
                    started = time.monotonic()
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=60_000)
                    run_id = int(page.url.rsplit("/", 1)[-1])
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=run_id, timeout=900_000,
                    )
                    elapsed = round(time.monotonic() - started, 3)
                    with sqlite3.connect(database) as connection:
                        run = connection.execute(
                            "SELECT selected_count,similarity_generation_id,similarity_result_snapshot_id "
                            "FROM campaign_search_runs WHERE search_run_id=?", (run_id,)
                        ).fetchone()
                        score_rows = connection.execute(
                            "SELECT person_id,buyer_similarity_score FROM buyer_similarity_scores "
                            "WHERE product_id='P1' AND is_valid=1"
                        ).fetchall()
                        snapshot = connection.execute(
                            "SELECT resolved_count,storage_uri,snapshot_sha256 FROM "
                            "buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
                            (run[2],)
                        ).fetchone()
                    oracle = sum(float(score) >= minimum for _, score in score_rows)
                    assert len(score_rows) == demographics
                    assert run[0] == snapshot[0] == oracle
                    artifact = (root / "source" / snapshot[1]).resolve()
                    assert artifact.is_relative_to((root / "source").resolve())
                    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == snapshot[2]
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded",
                              timeout=90_000)
                    page.locator("#business-search-form").wait_for(state="visible", timeout=60_000)
                    page.locator("#business-product_ids-trigger").click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    page.locator("#business-product_ids-trigger").press("Escape")
                    page.locator("#business-export-profile").select_option(profile)
                    with page.expect_response(
                        lambda response: response.request.method == "POST" and
                        response.url.endswith("/api/potential-customer-search/preflight"),
                        timeout=60_000,
                    ) as preflight_info:
                        page.locator("#business-search-preflight").click()
                    assert preflight_info.value.status == 200
                    preflight = preflight_info.value.json()
                    assert preflight["selected_count"] == oracle
                    assert oracle >= 10_000
                    assert "demo_ready" not in preflight  # v3 reports the exact count, not a v2 flag.
                    assert preflight["similarity_currentness"] == "CURRENT"
                    visible_preflight = page.locator("#business-search-preflight-result")
                    assert "12,000" in visible_preflight.inner_text()
                    save_screenshot(page, root / "screenshots" / "named_10k_preflight.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_NAMED_10K_TRUTHFUL_QUALIFICATION",
                                   "browser": session.metadata.to_dict(),
                                   "run_id": run_id, "demographics": demographics,
                                   "valid_score_rows": len(score_rows), "minimum": minimum,
                                   "independent_qualifying_count": oracle,
                                   "selected_count": run[0],
                                   "qualification_threshold_met": oracle >= 10_000,
                                   "v3_demo_ready_field_present": False,
                                   "generation_id": run[1], "snapshot_sha256": snapshot[2],
                                   "submit_to_completed_seconds": elapsed,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_NAMED_10K_TRUTHFUL_QUALIFICATION",
                       "error_type": type(exc).__name__, "error": str(exc)[:1800],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_named_10k_qualification.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_NAMED_10K_TRUTHFUL_QUALIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
