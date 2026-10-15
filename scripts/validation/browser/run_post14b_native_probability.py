"""Native-browser v2 bucket parity on an isolated, governed calibration fixture."""

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
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


BUCKETS = ("0.90", "0.80", "0.70", "0.60", "0.50")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Only a dedicated Post-14B QA root is allowed.")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    if manifest["fixture_kind"] != "PLANNER_CALIBRATABLE":
        raise ValueError("Probability browser case requires governed calibration fixture.")
    database = root / "state" / "qa.db"
    with sqlite3.connect(database) as connection:
        calibration = connection.execute(
            "SELECT calibration_artifact_id,scoring_run_id,status FROM score_calibration_artifacts "
            "WHERE status='PROMOTED' ORDER BY calibration_artifact_id DESC LIMIT 1"
        ).fetchone()
        if calibration is None:
            raise ValueError("A genuinely promoted bounded calibration artifact is required.")
        scored = connection.execute(
            "SELECT person_id,propensity_bucket FROM calibrated_propensity_scores "
            "WHERE calibration_artifact_id=?", (calibration[0],)
        ).fetchall()
    oracle = {bucket: {person_id for person_id, recorded in scored if recorded == bucket}
              for bucket in BUCKETS}
    if len(scored) != manifest["expected_demographics"]:
        raise ValueError("Calibrated score population does not match the frozen fixture.")
    report = {"scope": "BUSINESS_NATIVE_V2_GOVERNED_PROBABILITY", "status": "NOT_RUN",
              "qa_root": str(root), "calibration_artifact_id": calibration[0],
              "scoring_run_id": calibration[1], "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "probability_browser_profile",
                downloads_dir=root / "probability_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                responses = []
                page.on("response", lambda response: responses.append({
                    "method": response.request.method,
                    "path": response.url.split("/api/", 1)[-1].split("?", 1)[0],
                    "status": response.status,
                }) if "/api/" in response.url else None)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    for bucket in BUCKETS:
                        page.goto(base + "#find-potential-customers",
                                  wait_until="domcontentloaded", timeout=60_000)
                        page.locator("#business-search-form").wait_for(state="visible", timeout=40_000)
                        page.locator("#business-product_ids-trigger").click()
                        page.locator("#business-product_ids-panel input[value='P1']").check()
                        page.locator("#business-product_ids-trigger").press("Escape")
                        page.locator("#business-campaign_types-trigger").click()
                        page.locator(
                            "#business-campaign_types-panel input[value='Training Fixture']"
                        ).check()
                        page.locator("#business-campaign_types-trigger").press("Escape")
                        page.locator('input[name="business_score_mode"][value="probability"]').check()
                        page.locator("#business-campaign-name").fill(f"Bounded probability bucket {bucket}")
                        profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                          .find(o => !o.disabled && o.value && o.value.includes('EMAIL'))?.value || ''""")
                        assert profile
                        page.locator("#business-export-profile").select_option(profile)
                        page.locator(
                            f'input[name="business_propensity_bucket"][value="{bucket}"]'
                        ).check()
                        with page.expect_response(
                            lambda response: response.request.method == "POST" and
                            response.url.endswith("/api/potential-customer-search/preflight"),
                            timeout=40_000,
                        ) as preflight_info:
                            page.locator("#business-search-preflight").click()
                        preflight = preflight_info.value.json()
                        assert preflight_info.value.status == 200, preflight
                        assert preflight["selection_contract_version"] == "2", preflight
                        assert preflight_info.value.request.post_data_json["propensity_bucket"] == bucket
                        assert preflight["calibration_artifact_id"] == calibration[0], preflight
                        assert preflight["calibration_currentness"] == "CURRENT", preflight
                        assert preflight["selected_count"] == len(oracle[bucket]), preflight
                        item = {"id": f"V2_BUCKET_{bucket}", "status": "PASS",
                                "bucket": bucket, "preflight_selected": preflight["selected_count"],
                                "independent_oracle": len(oracle[bucket])}
                        if bucket in {"0.90", "0.80"}:
                            page.locator("#business-search-submit").click()
                            page.wait_for_url("**/#results/*", timeout=40_000)
                            run_id = int(page.url.rsplit("/", 1)[-1])
                            page.wait_for_function(
                                "id => document.querySelector('#result-detail-run-id')?.textContent"
                                ".includes(`Search #${id}`) && "
                                "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                                arg=run_id, timeout=180_000,
                            )
                            with sqlite3.connect(database) as connection:
                                run = connection.execute(
                                    "SELECT selection_contract_version,propensity_bucket,selected_count,"
                                    "calibration_artifact_id,result_snapshot_id FROM campaign_search_runs "
                                    "WHERE search_run_id=?", (run_id,)
                                ).fetchone()
                                snapshot = connection.execute(
                                    "SELECT resolved_count,storage_uri,snapshot_sha256,"
                                    "selection_contract_version,propensity_bucket,calibration_artifact_id "
                                    "FROM campaign_result_snapshots WHERE result_snapshot_id=?", (run[4],)
                                ).fetchone()
                            assert run[:4] == ("2", bucket, len(oracle[bucket]), calibration[0])
                            assert snapshot[0] == len(oracle[bucket])
                            assert snapshot[3:] == ("2", bucket, calibration[0])
                            artifact = (root / "source" / snapshot[1]).resolve()
                            assert artifact.is_relative_to((root / "source").resolve())
                            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == snapshot[2]
                            with gzip.open(artifact, "rt", newline="", encoding="utf-8") as source:
                                members = {row["person_id"] for row in csv.DictReader(source)}
                            assert members == oracle[bucket]
                            item.update({"run_id": run_id, "snapshot_sha256": snapshot[2],
                                         "materialized_members": len(members)})
                            page.reload(wait_until="domcontentloaded")
                            page.wait_for_function(
                                "id => document.querySelector('#result-detail-run-id')?.textContent"
                                ".includes(`Search #${id}`) && "
                                "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                                arg=run_id, timeout=60_000,
                            )
                            item["reopened_stored_contract"] = True
                        report["cases"].append(item)
                        print(f"V2 {bucket}: {len(oracle[bucket])} exact members", flush=True)
                    save_screenshot(page, root / "screenshots" / "probability_v2_reopened.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_V2_BUCKET_AND_MEMBERSHIP_MATRIX",
                                   "browser": session.metadata.to_dict(),
                                   "api_responses": responses, "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_V2_BUCKET_AND_MEMBERSHIP_MATRIX",
                       "error_type": type(exc).__name__, "error": str(exc)[:1500],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_probability_v2.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_V2_BUCKET_AND_MEMBERSHIP_MATRIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
