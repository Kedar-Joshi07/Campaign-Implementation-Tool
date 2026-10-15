"""Native UI TOP_N and honest zero-result checks on a verified v3 QA generation."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import QA_PARENT, start_qa_server, stop_qa_server
from scripts.validation.browser.run_post14b_native_similarity_selection_matrix import _select_p1
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


def _members(root: Path, connection: sqlite3.Connection, run_id: int) -> tuple[dict, list[str]]:
    connection.row_factory = sqlite3.Row
    run = dict(connection.execute(
        "SELECT selected_count,similarity_minimum,selection_mode,target_count,"
        "similarity_result_snapshot_id,similarity_generation_id "
        "FROM campaign_search_runs WHERE search_run_id=?", (run_id,),
    ).fetchone())
    snapshot = dict(connection.execute(
        "SELECT resolved_count,storage_uri,snapshot_sha256 FROM buyer_similarity_result_snapshots "
        "WHERE similarity_result_snapshot_id=?", (run["similarity_result_snapshot_id"],),
    ).fetchone())
    artifact = (root / "source" / snapshot["storage_uri"]).resolve()
    assert artifact.is_relative_to((root / "source").resolve())
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == snapshot["snapshot_sha256"]
    with gzip.open(artifact, "rt", encoding="utf-8", newline="") as source:
        members = [row["person_id"] for row in csv.DictReader(source)]
    assert len(members) == len(set(members)) == snapshot["resolved_count"] == run["selected_count"]
    return run, members


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Only a dedicated capped Post-14B QA root is allowed.")
    prior = json.loads((root / "native_similarity_selection_matrix.json").read_text(encoding="utf-8"))
    assert prior["status"] == "PASS_V3_SELECTION_MINIMUM_MATRIX"
    report = {"scope": "BUSINESS_NATIVE_V3_TOPN_AND_ZERO", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    prior_case_path = root / "native_similarity_topn_zero.json"
    is_resume = prior_case_path.is_file()
    if is_resume:
        prior_cases = json.loads(prior_case_path.read_text(encoding="utf-8"))
        if prior_cases.get("status") == "FAIL_TOPN_AND_HONEST_ZERO":
            report["cases"] = [case for case in prior_cases.get("cases", [])
                               if case.get("status") == "PASS"]
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            score_rows = connection.execute(
                "SELECT person_id,buyer_similarity_score FROM buyer_similarity_scores "
                "WHERE product_id='P1' AND is_valid=1"
            ).fetchall()
            ny_90 = connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_scores s "
                "JOIN demographics d ON d.person_id=s.person_id "
                "WHERE s.product_id='P1' AND s.is_valid=1 AND s.buyer_similarity_score>=0.9 "
                "AND d.state='New York'"
            ).fetchone()[0]
        assert len(score_rows) == 200 and ny_90 == 0
        top_ten = [person_id for person_id, score in sorted(
            score_rows, key=lambda item: (-item[1], item[0]))[:10]]
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "topn_zero_browser_profile",
                downloads_dir=root / "topn_zero_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    for case_id, minimum, top_n, state in (
                        ("TOP_N_10", 0.5, 10, None),
                        ("ZERO_NEW_YORK_AT_90", 0.9, None, "New York"),
                    ):
                        if any(case["id"] == case_id for case in report["cases"]):
                            continue
                        page.goto(base + "#find-potential-customers", wait_until="domcontentloaded")
                        page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                        _select_p1(page)
                        page.locator("#business-campaign-name").fill(f"Bounded {case_id}")
                        page.locator(f'input[name="business_similarity_minimum"][value="{minimum}"]').check()
                        if top_n is not None:
                            page.locator("#business-selection-mode").select_option("TOP_N")
                            page.locator("#business-target-count").fill(str(top_n))
                        else:
                            page.locator("#business-selection-mode").select_option("ALL_MATCHING")
                        if state:
                            page.locator("#business-states-trigger").click()
                            page.locator(
                                "#business-states-panel .multi-select-option input[value='New York']"
                            ).check()
                            page.locator("#business-states-trigger").press("Escape")
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith("/api/potential-customer-search/preflight"),
                            timeout=30_000,
                        ) as preflight_info:
                            page.locator("#business-search-preflight").click()
                        preflight = preflight_info.value.json()
                        assert preflight_info.value.status == 200
                        expected_qualifying = 200 if top_n is not None else 0
                        expected_selected = top_n if top_n is not None else 0
                        assert preflight["similarity_qualifying_count"] == expected_qualifying
                        assert preflight["selected_count"] == expected_selected
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
                            run, members = _members(root, connection, run_id)
                        assert run["selected_count"] == expected_selected
                        assert run["similarity_minimum"] == minimum
                        assert run["selection_mode"] == ("TOP_N" if top_n else "ALL_MATCHING")
                        if top_n:
                            assert run["target_count"] == top_n and members == top_ten
                        else:
                            assert run["target_count"] is None and not members
                        report["cases"].append({"id": case_id, "status": "PASS",
                                                "run_id": run_id,
                                                "qualified": expected_qualifying,
                                                "selected": expected_selected,
                                                "generation_id": run["similarity_generation_id"]})
                        print(f"{case_id}: qualified {expected_qualifying}, selected {expected_selected}",
                              flush=True)
                    save_screenshot(page, root / "screenshots" / "similarity_zero_result.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_TOPN_AND_HONEST_ZERO",
                                   "browser": session.metadata.to_dict(),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_TOPN_AND_HONEST_ZERO",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_similarity_topn_zero_resume.json" if is_resume
                       else "native_similarity_topn_zero.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_TOPN_AND_HONEST_ZERO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
