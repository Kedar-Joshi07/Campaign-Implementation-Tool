"""Exercise the retained campaign stepper and existing campaign reopen in bounded Chrome."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import QA_PARENT, REPOSITORY_ROOT, start_qa_server, stop_qa_server
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
    save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_campaign_builder.json").is_file():
        raise ValueError("Campaign stepper requires an owned retained campaign QA root.")
    source = "frontend/js/campaigns.js"
    assert hashlib.sha256((root / "source" / source).read_bytes()).digest() == hashlib.sha256(
        (REPOSITORY_ROOT / source).read_bytes()).digest()
    report = {"scope": "RETAINED_NATIVE_CAMPAIGN_STEPPER", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            before = connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
            finalized = connection.execute(
                "SELECT campaign_id,campaign_name FROM campaigns WHERE status='FINALIZED' "
                "ORDER BY campaign_id LIMIT 1").fetchone()
            audience = connection.execute("SELECT audience_id FROM saved_audiences ORDER BY audience_id LIMIT 1").fetchone()
        assert before >= 1 and finalized and audience
        process, port = start_qa_server(root)
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "campaign_stepper_profile",
                downloads_dir=root / "campaign_stepper_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(30_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    base = f"http://127.0.0.1:{port}/qa-retained"
                    page.goto(base + "#saved-target-groups", wait_until="domcontentloaded")
                    page.locator("#business-target-groups-list .saved-audience-item").first.wait_for(
                        state="visible", timeout=60_000)
                    page.get_by_role("button", name="Create Campaign").click()
                    page.wait_for_function(
                        "() => location.hash === '#campaign-planner' || "
                        "location.hash === '#find-potential-customers'", timeout=30_000)
                    assert page.locator("#campaign-planner-view").is_visible()
                    report["cases"].append({"id": "SAVED_GROUP_CREATE_CAMPAIGN_ROUTE",
                                            "status": "PASS", "hash": page.evaluate("location.hash")})

                    page.goto(base + "#campaigns", wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => ['ready','no-eligible','backend-unavailable'].some(name => "
                        "!document.querySelector(`#campaigns-state-${name}`)?.hidden)", timeout=120_000)
                    assert page.locator("#campaigns-state-ready").is_visible(), page.evaluate(
                        """() => ({noEligible: !document.querySelector('#campaigns-state-no-eligible').hidden,
                        backendError: document.querySelector('#campaigns-error-message').textContent,
                        announcement: document.querySelector('#campaigns-status-announcement').textContent})""")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/campaigns/options")
                        and response.request.method == "GET", timeout=30_000,
                    ) as refresh:
                        page.locator("#campaigns-refresh").click()
                    assert refresh.value.status == 200
                    page.wait_for_function(
                        "() => !document.querySelector('#campaigns-refresh')?.disabled", timeout=90_000)
                    assert page.locator("#campaigns-state-ready").is_visible()
                    report["cases"].append({"id": "CAMPAIGN_WORKSPACE_REFRESH", "status": "PASS"})

                    page.locator("#campaign-new-draft").click()
                    page.locator("#campaign-step-4").click()
                    assert "Complete the current campaign steps" in page.locator(
                        "#campaign-step-error-summary").inner_text()
                    assert page.locator("#campaign-step-panel-1").is_visible()
                    page.locator("#campaign-audience-select").select_option(str(audience[0]))
                    page.locator("#campaign-step-next-1").click()
                    page.locator("#campaign-step-panel-2").wait_for(state="visible")
                    page.locator("#campaign-step-1").click()
                    assert page.locator("#campaign-step-panel-1").is_visible()
                    page.locator("#campaign-step-2").click()
                    assert page.locator("#campaign-step-panel-2").is_visible()
                    page.locator("#campaign-step-2").focus()
                    page.locator("#campaign-step-2").press("ArrowRight")
                    assert page.locator("#campaign-step-3").evaluate("el => document.activeElement === el")
                    page.locator("#campaign-name").fill("Bounded unsaved stepper navigation")
                    page.locator("#campaign-channel").select_option("EMAIL")
                    page.locator("#campaign-step-next-2").click()
                    page.locator("#campaign-step-panel-3").wait_for(state="visible")
                    page.locator("#campaign-step-3").click()
                    assert page.locator("#campaign-step-3").get_attribute("aria-current") == "step"
                    page.locator("#campaign-step-next-3").click()
                    page.locator("#campaign-step-panel-4").wait_for(state="visible")
                    page.locator("#campaign-step-2").click()
                    assert page.locator("#campaign-step-panel-2").is_visible()
                    page.locator("#campaign-name").fill("")
                    page.locator("#campaign-step-4").click()
                    assert page.locator("#campaign-step-panel-2").is_visible()
                    assert "Campaign name is required" in page.locator(
                        "#campaign-step-error-summary").inner_text()
                    page.locator("#campaign-name").fill("Bounded unsaved stepper navigation")
                    page.locator("#campaign-step-4").click()
                    assert page.locator("#campaign-step-panel-4").is_visible()
                    assert page.locator("#campaign-create-draft").is_enabled()
                    report["cases"].append({"id": "CAMPAIGN_STEPPER_GUARDED_VISITED_NAVIGATION",
                                            "status": "PASS"})

                    row = page.locator("#campaign-recent-body tr").filter(has_text=finalized[1])
                    row.get_by_role("button", name="Open").click()
                    page.wait_for_function(
                        "id => document.querySelector('#campaigns-status-announcement')?.textContent"
                        ".includes(`Opened campaign #${id}`)", arg=finalized[0], timeout=30_000)
                    assert page.locator("#campaign-step-panel-4").is_visible()
                    assert finalized[1] in page.locator("#campaign-detail-summary").inner_text()
                    report["cases"].append({"id": "CAMPAIGN_RECENT_OPEN_FINALIZED",
                                            "status": "PASS", "campaign_id": finalized[0]})
                    page.locator("#campaign-new-draft").click()
                    page.locator("#campaign-audience-select").select_option(str(audience[0]))
                    page.locator("#campaign-step-next-1").click()
                    page.locator("#campaign-step-panel-2").wait_for(state="visible")
                    page.locator("#campaign-name").fill("Bounded post-fix campaign")
                    page.locator("#campaign-description").fill("Synthetic post-fix QA, no delivery")
                    page.locator("#campaign-channel").select_option("EMAIL")
                    page.locator("#campaign-step-next-2").click()
                    page.locator("#campaign-step-panel-3").wait_for(state="visible")
                    page.locator("#campaign-step-next-3").click()
                    page.locator("#campaign-step-panel-4").wait_for(state="visible")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/campaigns")
                        and response.request.method == "POST", timeout=30_000,
                    ) as draft_response:
                        page.locator("#campaign-create-draft").click()
                    assert draft_response.value.status == 201
                    new_id = int(draft_response.value.json()["campaign_id"])
                    page.wait_for_function(
                        "id => document.querySelector('#campaign-detail-summary')?.textContent"
                        ".includes(`(#${id})`) && !document.querySelector('#campaign-create-draft')?.disabled",
                        arg=new_id, timeout=90_000)
                    assert page.locator("#campaign-step-panel-3").is_visible()
                    page.locator("#campaign-step-2").click()
                    page.locator("#campaign-step-panel-2").wait_for(state="visible")
                    page.locator("#campaign-name").fill("Bounded updated campaign draft")
                    page.locator("#campaign-description").fill("Synthetic updated draft; no delivery")
                    page.locator("#campaign-step-4").click()
                    page.locator("#campaign-step-panel-4").wait_for(state="visible")
                    with page.expect_response(
                        lambda response: response.url.endswith(f"/api/campaigns/{new_id}")
                        and response.request.method == "PATCH", timeout=30_000,
                    ) as update_response:
                        page.locator("#campaign-create-draft").click()
                    assert update_response.value.status == 200
                    page.wait_for_function(
                        "id => document.querySelector('#campaign-detail-summary')?.textContent"
                        ".includes(`(#${id})`) && document.querySelector('#campaign-detail-summary')"
                        "?.textContent.includes('Bounded updated campaign draft')"
                        " && !document.querySelector('#campaign-create-draft')?.disabled",
                        arg=new_id, timeout=90_000)
                    with sqlite3.connect(database) as connection:
                        updated = connection.execute(
                            "SELECT campaign_name,description,status,saved_audience_id "
                            "FROM campaigns WHERE campaign_id=?", (new_id,),
                        ).fetchone()
                    assert updated == (
                        "Bounded updated campaign draft", "Synthetic updated draft; no delivery",
                        "DRAFT", audience[0],
                    )
                    report["cases"].append({"id": "CAMPAIGN_DRAFT_EDIT_SAVE_SAME_AUDIENCE",
                                            "status": "PASS", "campaign_id": new_id})
                    page.locator("#campaign-step-next-3").click()
                    page.locator("#campaign-step-panel-4").wait_for(state="visible")
                    with page.expect_response(
                        lambda response: response.url.endswith(f"/api/campaigns/{new_id}/finalize")
                        and response.request.method == "POST", timeout=30_000,
                    ) as finalize_response:
                        page.locator("#campaign-finalize").click()
                    assert finalize_response.value.status == 200
                    page.wait_for_function(
                        "id => document.querySelector('#campaigns-status-announcement')?.textContent"
                        ".includes(`Campaign #${id} finalized`)", arg=new_id, timeout=90_000)
                    page.locator("#campaign-pii-ack").check()
                    with page.expect_download(timeout=60_000) as download_info:
                        page.locator("#campaign-export").click()
                    download = download_info.value
                    destination = root / "campaign_stepper_downloads" / download.suggested_filename
                    download.save_as(destination)
                    with destination.open("r", encoding="utf-8-sig", newline="") as stream:
                        exported = list(csv.DictReader(stream))
                    with sqlite3.connect(database) as connection:
                        after = connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
                        row = connection.execute(
                            "SELECT status,saved_audience_id FROM campaigns WHERE campaign_id=?",
                            (new_id,),
                        ).fetchone()
                        event = connection.execute(
                            "SELECT status,selected_count,deliverable_count,undeliverable_count,"
                            "row_count,csv_sha256 FROM campaign_export_events "
                            "WHERE campaign_id=? ORDER BY export_event_id DESC LIMIT 1", (new_id,),
                        ).fetchone()
                    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                    assert after == before + 1 and row == ("FINALIZED", audience[0])
                    assert event and event[0] == "COMPLETED"
                    assert event[1] == event[2] + event[3]
                    assert event[2] == event[4] == len(exported)
                    assert event[5] == digest
                    report["cases"].append({"id": "CAMPAIGN_POST_FIX_DRAFT_FINALIZE_EXPORT",
                                            "status": "PASS", "campaign_id": new_id,
                                            "exported": len(exported), "csv_sha256": digest})
                    save_screenshot(page, root / "screenshots" / "campaign_stepper_reopen.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_RETAINED_CAMPAIGN_STEPPER",
                                   "browser": session.metadata.to_dict(),
                                   "campaigns_before_after": [before, after],
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_CAMPAIGN_STEPPER",
                       "error_type": type(exc).__name__, "error": str(exc)[:1700],
                       "traceback": traceback.format_exc()[-3500:]})
        if "capture" in locals():
            report["console_errors"] = capture.console_errors
            report["page_errors"] = capture.page_errors
            report["request_failures"] = capture.request_failures
        try:
            report["browser_failure_state"] = page.evaluate("""() => ({
              hash: location.hash,
              ready: !document.querySelector('#campaigns-state-ready')?.hidden,
              error: document.querySelector('#campaigns-error-message')?.textContent,
              noEligible: !document.querySelector('#campaigns-state-no-eligible')?.hidden,
              announcement: document.querySelector('#campaigns-status-announcement')?.textContent,
            })""")
        except Exception:
            pass
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_campaign_stepper.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] == "PASS_RETAINED_CAMPAIGN_STEPPER" else 1


if __name__ == "__main__":
    raise SystemExit(main())
