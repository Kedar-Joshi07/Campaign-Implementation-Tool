"""Headed-browser two-product ANY/max selection and unique snapshot oracle."""

from __future__ import annotations

import csv
import gzip
import hashlib
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


def _select_form(page, minimum: float, name: str):
    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
    trigger = page.locator("#business-product_ids-trigger")
    trigger.click()
    for product in ("P1", "P2"):
        page.locator(f"#business-product_ids-panel input[value='{product}']").check()
    trigger.press("Escape")
    assert page.locator("#business-product_ids").evaluate(
        "e => [...e.selectedOptions].map(o => o.value)") == ["P1", "P2"]
    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
      .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
    assert profile
    page.locator("#business-export-profile").select_option(profile)
    page.locator("#business-campaign-name").fill(name)
    page.locator(f'input[name="business_similarity_minimum"][value="{minimum}"]').check()


def main() -> int:
    root = prepare_qa_root(fixture_kind="SIMILARITY_THRESHOLDS")
    print(f"Multi-product QA root: {root}", flush=True)
    report = {"scope": "BUSINESS_NATIVE_MULTI_PRODUCT_ANY_MAX", "status": "NOT_RUN",
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
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                    _select_form(page, 0.5, "Bounded two-product fresh")
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=30_000)
                    fresh_id = int(page.url.rsplit("/", 1)[-1])
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=fresh_id, timeout=240_000,
                    )
                    with sqlite3.connect(database) as connection:
                        score_rows = connection.execute(
                            "SELECT person_id,product_id,buyer_similarity_score,is_valid "
                            "FROM buyer_similarity_scores WHERE product_id IN ('P1','P2')"
                        ).fetchall()
                        profiles = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_profiles"
                        ).fetchone()[0]
                        generations = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_score_generations"
                        ).fetchone()[0]
                    assert profiles == generations == 2
                    assert len(score_rows) == 400
                    maxima = {}
                    for person_id, _product_id, score, valid in score_rows:
                        if valid:
                            maxima[person_id] = max(maxima.get(person_id, 0.0), float(score))
                    assert len(maxima) == 200
                    page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                    _select_form(page, 0.9, "Bounded two-product strict")
                    with page.expect_response(
                        lambda response: response.request.method == "POST" and
                        response.url.endswith("/api/potential-customer-search/preflight"),
                        timeout=30_000,
                    ) as preflight_response:
                        page.locator("#business-search-preflight").click()
                    preflight = preflight_response.value.json()
                    assert preflight_response.value.status == 200
                    expected = {person_id for person_id, score in maxima.items() if score >= 0.9}
                    assert preflight["product_match_policy"] == "ANY_SELECTED_PRODUCT_MAX_V1"
                    assert preflight["similarity_qualifying_count"] == len(expected)
                    assert preflight["selected_count"] == len(expected)
                    page.locator("#business-search-submit").click()
                    page.wait_for_url("**/#results/*", timeout=30_000)
                    strict_id = int(page.url.rsplit("/", 1)[-1])
                    assert strict_id != fresh_id
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=strict_id, timeout=120_000,
                    )
                    with sqlite3.connect(database) as connection:
                        run = connection.execute(
                            "SELECT selected_count,similarity_result_snapshot_id,result_source "
                            "FROM campaign_search_runs WHERE search_run_id=?", (strict_id,),
                        ).fetchone()
                        snapshot = connection.execute(
                            "SELECT resolved_count,storage_uri,snapshot_sha256 "
                            "FROM buyer_similarity_result_snapshots "
                            "WHERE similarity_result_snapshot_id=?", (run[1],),
                        ).fetchone()
                        assert connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_profiles"
                        ).fetchone()[0] == 2
                        assert connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_score_generations"
                        ).fetchone()[0] == 2
                    assert run[0] == snapshot[0] == len(expected)
                    artifact = (root / "source" / snapshot[1]).resolve()
                    assert artifact.is_relative_to((root / "source").resolve())
                    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == snapshot[2]
                    with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
                        members = [row["person_id"] for row in csv.DictReader(source)]
                    assert len(members) == len(set(members)) == len(expected)
                    assert set(members) == expected
                    save_screenshot(page, root / "screenshots" / "multi_product_strict.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_MULTI_PRODUCT_ANY_MAX",
                                   "browser": session.metadata.to_dict(),
                                   "fresh_run_id": fresh_id, "strict_run_id": strict_id,
                                   "profile_count": profiles, "generation_count": generations,
                                   "score_rows": len(score_rows),
                                   "unique_score_people": len(maxima),
                                   "strict_expected": len(expected),
                                   "strict_selected": run[0],
                                   "strict_snapshot_sha256": snapshot[2],
                                   "strict_result_source": run[2],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                except Exception:
                    try:
                        report["failure_state"] = page.evaluate("""() => ({
                          hash: location.hash,
                          badge: document.querySelector('#result-detail-badge')?.dataset.status,
                          status: document.querySelector('#result-detail-status')?.textContent,
                        })""")
                        report["failure_page_errors"] = capture.page_errors
                    except Exception:
                        pass
                    raise
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_MULTI_PRODUCT_ANY_MAX",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_multi_product.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_MULTI_PRODUCT_ANY_MAX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
