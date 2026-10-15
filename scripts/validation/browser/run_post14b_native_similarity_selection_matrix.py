"""Exact v3 threshold/preflight/materialization parity through headed Chrome."""

from __future__ import annotations

import gzip
import csv
import hashlib
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


MINIMA = (0.5, 0.6, 0.7, 0.8, 0.9)


def _score_oracle(database):
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT person_id,buyer_similarity_score FROM buyer_similarity_scores "
            "WHERE product_id='P1' AND is_valid=1 ORDER BY person_id"
        ).fetchall()
    return {str(person_id): float(score) for person_id, score in rows}


def _select_p1(page):
    trigger = page.locator("#business-product_ids-trigger")
    trigger.click()
    page.locator("#business-product_ids-panel input[value='P1']").check()
    trigger.press("Escape")
    assert page.locator("#business-product_ids").evaluate(
        "e => [...e.selectedOptions].map(o => o.value)") == ["P1"]
    page.locator('input[name="business_score_mode"][value="similarity"]').check()
    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
      .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
    assert profile
    page.locator("#business-export-profile").select_option(profile)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root(fixture_kind="SIMILARITY_THRESHOLDS")
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Only the dedicated Post-14B QA root is allowed.")
    print(f"Similarity matrix QA root: {root}", flush=True)
    report = {"scope": "BUSINESS_NATIVE_V3_EXACT_SELECTION_MATRIX", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            existing = connection.execute(
                "SELECT search_run_id,status FROM campaign_search_runs ORDER BY search_run_id LIMIT 1"
            ).fetchone()
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "similarity_browser_profile",
                downloads_dir=root / "similarity_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    if existing:
                        assert existing[1] == "COMPLETED"
                        first_id = existing[0]
                        page.goto(base + f"#results/{first_id}", wait_until="domcontentloaded")
                    else:
                        page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                        page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                        _select_p1(page)
                        page.locator("#business-campaign-name").fill("Bounded similarity fresh P1")
                        page.locator("#business-search-submit").click()
                        page.wait_for_url("**/#results/*", timeout=30_000)
                        first_id = int(page.url.rsplit("/", 1)[-1])
                    page.wait_for_function(
                        "id => document.querySelector('#result-detail-run-id')?.textContent"
                        ".includes(`Search #${id}`) && "
                        "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                        arg=first_id, timeout=60_000 if existing else 240_000,
                    )
                    report["completed_result_reopened"] = bool(existing)
                    scores = _score_oracle(database)
                    assert 0 < len(scores) <= 200
                    with sqlite3.connect(database) as connection:
                        invalid_count = connection.execute(
                            "SELECT COUNT(*) FROM buyer_similarity_scores "
                            "WHERE product_id='P1' AND is_valid=0"
                        ).fetchone()[0]
                    assert len(scores) + invalid_count == 200
                    report["score_range"] = {"min": min(scores.values()),
                                             "max": max(scores.values()),
                                             "valid_count": len(scores),
                                             "invalid_count": invalid_count}
                    generation_ids = set()
                    for minimum in MINIMA:
                        page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                        page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                        _select_p1(page)
                        page.locator("#business-campaign-name").fill(
                            f"Bounded similarity minimum {int(minimum * 100)}")
                        page.locator(
                            f'input[name="business_similarity_minimum"][value="{minimum}"]').check()
                        expected = {person_id for person_id, score in scores.items()
                                    if score >= minimum}
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith("/api/potential-customer-search/preflight"),
                            timeout=30_000,
                        ) as preflight_info:
                            page.locator("#business-search-preflight").click()
                        preflight = preflight_info.value.json()
                        assert preflight_info.value.status == 200
                        assert preflight["selection_contract_version"] == "3"
                        assert preflight["score_semantics"] == "PRODUCT_BUYER_SIMILARITY"
                        assert preflight["threshold_predicate"] == "GREATER_THAN_OR_EQUAL"
                        assert preflight["similarity_minimum"] == minimum
                        assert preflight["valid_similarity_count"] == len(scores)
                        assert preflight["invalid_similarity_count"] == invalid_count
                        assert preflight["similarity_qualifying_count"] == len(expected)
                        assert preflight["selected_count"] == len(expected)
                        assert preflight["similarity_currentness"] == "CURRENT"
                        page.locator("#business-search-submit").click()
                        page.wait_for_url("**/#results/*", timeout=30_000)
                        run_id = int(page.url.rsplit("/", 1)[-1])
                        page.wait_for_function(
                            "id => document.querySelector('#result-detail-run-id')?.textContent"
                            ".includes(`Search #${id}`) && "
                            "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                            arg=run_id, timeout=180_000,
                        )
                        with sqlite3.connect(database) as connection:
                            run = connection.execute(
                                "SELECT selected_count,similarity_minimum,similarity_generation_id,"
                                "similarity_result_snapshot_id,result_source "
                                "FROM campaign_search_runs WHERE search_run_id=?", (run_id,),
                            ).fetchone()
                            snapshot = connection.execute(
                                "SELECT resolved_count,storage_uri,snapshot_sha256 "
                                "FROM buyer_similarity_result_snapshots "
                                "WHERE similarity_result_snapshot_id=?", (run[3],),
                            ).fetchone()
                        assert run[0] == snapshot[0] == len(expected)
                        assert run[1] == minimum and run[2] > 0
                        artifact = (root / "source" / snapshot[1]).resolve()
                        assert artifact.is_relative_to((root / "source").resolve())
                        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == snapshot[2]
                        with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
                            actual = {row["person_id"] for row in csv.DictReader(source)}
                        assert actual == expected
                        generation_ids.add(run[2])
                        report["cases"].append({"id": f"V3_MINIMUM_{int(minimum * 100)}",
                                                "status": "PASS", "run_id": run_id,
                                                "preflight_qualifying": preflight["similarity_qualifying_count"],
                                                "selected": run[0], "result_source": run[4],
                                                "snapshot_sha256": snapshot[2]})
                        print(f"V3 minimum {minimum:.1f}: exact {len(expected)} selected", flush=True)
                    assert len(generation_ids) == 1
                    save_screenshot(page, root / "screenshots" / "similarity_minimum_90.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_V3_SELECTION_MINIMUM_MATRIX",
                                   "browser": session.metadata.to_dict(),
                                   "generation_count": len(generation_ids),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_V3_SELECTION_MINIMUM_MATRIX",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
        try:
            report["browser_failure_state"] = page.evaluate("""() => ({
              hash: location.hash,
              runId: document.querySelector('#result-detail-run-id')?.textContent,
              badgeText: document.querySelector('#result-detail-badge')?.textContent,
              badgeStatus: document.querySelector('#result-detail-badge')?.dataset.status,
              detailHidden: document.querySelector('#result-detail-content')?.hidden,
              errorHidden: document.querySelector('#result-detail-error')?.hidden,
              status: document.querySelector('#result-detail-status')?.textContent,
            })""")
            report["browser_failure_console_errors"] = capture.console_errors
            report["browser_failure_page_errors"] = capture.page_errors
        except Exception:
            pass
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_similarity_selection_matrix_resume.json" if args.qa_root
                       else "native_similarity_selection_matrix.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_V3_SELECTION_MINIMUM_MATRIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
