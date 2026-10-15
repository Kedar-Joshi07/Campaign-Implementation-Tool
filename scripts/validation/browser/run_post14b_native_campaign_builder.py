"""Retained Campaign Builder UI-to-durable-state/export bounded browser slice."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, REPOSITORY_ROOT, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "native_retained_historical.json").is_file():
        raise ValueError("Campaign Builder requires the owned trainable retained QA root.")
    prior = json.loads((root / "native_retained_historical.json").read_text(encoding="utf-8"))
    assert prior["status"] == "PASS_RETAINED_TRAINABLE_MODEL"
    for relative in ("frontend/js/campaigns.js", "app/repositories/campaign_repository.py"):
        assert hashlib.sha256((root / "source" / relative).read_bytes()).digest() == hashlib.sha256(
            (REPOSITORY_ROOT / relative).read_bytes()).digest(), relative
    report = {"scope": "RETAINED_COMPONENT_NATIVE_CAMPAIGN_BUILDER",
              "status": "NOT_RUN", "qa_root": str(root), "cases": []}
    previous_path = root / "native_campaign_builder.json"
    if previous_path.is_file():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        if previous.get("status") == "FAIL_CAMPAIGN_BUILDER_SLICE":
            report["cases"] = [item for item in previous.get("cases", [])
                               if item.get("status") == "PASS"]
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            before_campaigns = connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
            audiences = dict(connection.execute(
                "SELECT audience_id,resolved_count FROM saved_audiences").fetchall())
        completed_channels = {item["id"] for item in report["cases"]
                              if item["id"].endswith("_DRAFT_FINALIZE_EXPORT")}
        assert before_campaigns == len(completed_channels)
        assert sorted(audiences.values()) == [10, 200]
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "campaign_browser_profile",
                downloads_dir=root / "campaign_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#campaigns",
                              wait_until="domcontentloaded")
                    page.locator("#campaigns-state-ready").wait_for(state="visible", timeout=30_000)
                    page.wait_for_function(
                        "document.querySelector('#campaign-audience-select')?.options.length > 1",
                        timeout=30_000)
                    eligible_ids = [int(value) for value in page.locator(
                        "#campaign-audience-select option").evaluate_all(
                        "nodes => nodes.map(node => node.value).filter(Boolean)")]
                    assert eligible_ids and all(item in audiences for item in eligible_ids), eligible_ids
                    report["eligible_audience_ids"] = eligible_ids
                    for index, channel in enumerate(("EMAIL", "DIRECT_MAIL"), 1):
                        if f"CAMPAIGN_{channel}_DRAFT_FINALIZE_EXPORT" in completed_channels:
                            continue
                        audience_id = eligible_ids[(index - 1) % len(eligible_ids)]
                        selected_count = audiences[audience_id]
                        page.locator("#campaign-new-draft").click()
                        page.locator("#campaign-step-panel-1").wait_for(state="visible")
                        page.locator("#campaign-audience-select").select_option(str(audience_id))
                        page.wait_for_function("""expected => {
                          const summary = document.querySelector('#campaign-audience-summary')?.textContent || '';
                          return summary.includes(`(#${expected.id})`)
                            && summary.includes(String(expected.count)) && summary.includes('CURRENT');
                        }""", arg={"id": audience_id, "count": selected_count}, timeout=30_000)
                        page.locator("#campaign-step-next-1").click()
                        page.locator("#campaign-step-panel-2").wait_for(state="visible")
                        if index == 1:
                            page.locator("#campaign-step-next-2").click()
                            assert "Campaign name is required" in page.locator(
                                "#campaign-step-error-summary").inner_text()
                            report["cases"].append({"id": "CAMPAIGN_NAME_REQUIRED", "status": "PASS"})
                        page.locator("#campaign-name").fill(f"Bounded retained {channel} campaign")
                        page.locator("#campaign-description").fill("Synthetic QA campaign; no delivery")
                        page.locator("#campaign-channel").select_option(channel)
                        page.locator("#campaign-step-next-2").click()
                        page.locator("#campaign-step-panel-3").wait_for(state="visible")
                        assert str(selected_count) in page.locator("#campaign-review-summary").inner_text()
                        page.locator("#campaign-step-back-3").click()
                        page.locator("#campaign-step-panel-2").wait_for(state="visible")
                        page.locator("#campaign-step-next-2").click()
                        page.locator("#campaign-step-next-3").click()
                        page.locator("#campaign-step-panel-4").wait_for(state="visible")
                        assert page.locator("#campaign-finalize").is_disabled()
                        assert page.locator("#campaign-export").is_disabled()
                        page.locator("#campaign-create-draft").click()
                        page.wait_for_function(
                            "() => document.querySelector('#campaigns-status-announcement')?.textContent"
                            ".includes('created')", timeout=30_000)
                        with sqlite3.connect(database) as connection:
                            record = connection.execute(
                                "SELECT campaign_id,status,channel,saved_audience_id,"
                                "saved_audience_resolved_count FROM campaigns ORDER BY campaign_id DESC LIMIT 1"
                            ).fetchone()
                        assert record[1:] == ("DRAFT", channel, audience_id, selected_count)
                        campaign_id = record[0]
                        assert page.locator("#campaign-export").is_disabled()
                        page.locator("#campaign-step-next-3").click()
                        page.locator("#campaign-step-panel-4").wait_for(state="visible")
                        page.locator("#campaign-review-draft").click()
                        page.wait_for_function(
                            "id => document.querySelector('#campaigns-status-announcement')?.textContent"
                            ".includes(`Campaign #${id} refreshed`)", arg=campaign_id, timeout=30_000)
                        page.locator("#campaign-step-next-3").click()
                        page.locator("#campaign-step-panel-4").wait_for(state="visible")
                        assert page.locator("#campaign-finalize").is_enabled()
                        page.locator("#campaign-finalize").click()
                        page.wait_for_function(
                            "id => document.querySelector('#campaigns-status-announcement')?.textContent"
                            ".includes(`Campaign #${id} finalized`)", arg=campaign_id, timeout=30_000)
                        assert page.locator("#campaign-export").is_disabled()
                        assert page.locator("#campaign-name").is_disabled()
                        page.locator("#campaign-pii-ack").check()
                        assert page.locator("#campaign-export").is_enabled()
                        with page.expect_download(timeout=60_000) as download_info:
                            page.locator("#campaign-export").click()
                        download = download_info.value
                        path = root / "campaign_downloads" / f"{channel.lower()}_{download.suggested_filename}"
                        download.save_as(path)
                        with path.open("r", encoding="utf-8-sig", newline="") as source:
                            reader = csv.DictReader(source)
                            header = tuple(reader.fieldnames or ())
                            rows = list(reader)
                        with sqlite3.connect(database) as connection:
                            event = connection.execute(
                                "SELECT status,export_profile,selected_count,deliverable_count,"
                                "undeliverable_count,row_count,csv_sha256 FROM campaign_export_events "
                                "WHERE campaign_id=? ORDER BY export_event_id DESC LIMIT 1",
                                (campaign_id,),
                            ).fetchone()
                            final = connection.execute(
                                "SELECT status,finalized_at FROM campaigns WHERE campaign_id=?",
                                (campaign_id,),
                            ).fetchone()
                        sha = hashlib.sha256(path.read_bytes()).hexdigest()
                        assert final[0] == "FINALIZED" and final[1]
                        assert event is not None and event[0] == "COMPLETED"
                        assert event[1] == f"{channel}_CONTACT_V1"
                        assert event[2] == selected_count == event[3] + event[4]
                        assert event[3] == event[5] == len(rows)
                        assert event[6] == sha and len({row["person_id"] for row in rows}) == len(rows)
                        assert "person_id" in header
                        page.locator("#campaign-export-history-refresh").click()
                        page.wait_for_function(
                            "() => document.querySelector('#campaign-export-history-body')?.textContent"
                            ".includes('COMPLETED')", timeout=30_000)
                        save_screenshot(page, root / "screenshots" / f"campaign_{channel.lower()}_finalized.png")
                        report["cases"].append({"id": f"CAMPAIGN_{channel}_DRAFT_FINALIZE_EXPORT",
                                                "status": "PASS", "campaign_id": campaign_id,
                                                "audience_id": audience_id, "selected": selected_count,
                                                "deliverable": len(rows), "excluded": event[4],
                                                "csv_sha256": sha, "header": header})
                        print(f"Campaign {channel}: finalized and exported {len(rows)} contacts", flush=True)
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": "PASS_CAMPAIGN_BUILDER_SLICE",
                                   "browser": session.metadata.to_dict(),
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_CAMPAIGN_BUILDER_SLICE",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_campaign_builder.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_CAMPAIGN_BUILDER_SLICE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
