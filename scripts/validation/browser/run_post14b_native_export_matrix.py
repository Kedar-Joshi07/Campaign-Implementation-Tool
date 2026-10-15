"""Native headed-browser download matrix for all available v3 export profiles."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import traceback
from importlib.metadata import version
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


ANALYTICAL = (
    "person_id", "buyer_similarity_score", "similarity_tier", "matched_product_id",
    "score_method_version", "feature_coverage", "similarity_generation_id",
)
CONTACT_ONLY = ("person_id",)
CHANNEL_FIELDS = {
    "EMAIL_CONTACT": ("first_name", "last_name", "email"),
    "DIRECT_MAIL_CONTACT": ("first_name", "last_name", "address_line_1", "address_line_2",
                            "city", "state", "postal_code"),
    "SMS_CONTACT": ("first_name", "last_name", "phone_number"),
    "WHATSAPP_CONTACT": ("first_name", "last_name", "phone_number"),
    "TELEMARKETING_CONTACT": ("first_name", "last_name", "phone_number"),
    "PAID_SOCIAL_AUDIENCE": ("sha256_email", "sha256_phone"),
    "PAID_SEARCH_AUDIENCE": ("sha256_email", "sha256_phone"),
    "MOBILE_PUSH_CONTACT": ("push_token",),
    "DISPLAY_AUDIENCE": ("advertising_id",),
    "WEBSITE_AUDIENCE": ("web_visitor_id",),
}
EXPECTED_PROFILES = {
    f"{channel}{suffix}" for channel in CHANNEL_FIELDS
    for suffix in ("_V2", "_CONTACT_ONLY_V2")
}
assert len(EXPECTED_PROFILES) == 20


def expected_header(profile: str) -> tuple[str, ...]:
    contact_only = profile.endswith("_CONTACT_ONLY_V2")
    channel = profile.removesuffix("_CONTACT_ONLY_V2" if contact_only else "_V2")
    return (* (CONTACT_ONLY if contact_only else ANALYTICAL), *CHANNEL_FIELDS[channel])


def assert_contactability(profile: str, rows: list[dict], sources: dict[str, dict]) -> None:
    channel = profile.removesuffix("_CONTACT_ONLY_V2").removesuffix("_V2")
    for row in rows:
        source = sources[row["person_id"]]
        if channel == "EMAIL_CONTACT":
            assert str(source["email_contactable"]) == "1" and row["email"].endswith("@example.test")
        elif channel == "DIRECT_MAIL_CONTACT":
            assert str(source["direct_mail_contactable"]) == "1"
            assert all(row[key] for key in ("address_line_1", "city", "state", "postal_code"))
        elif channel == "SMS_CONTACT":
            assert str(source["sms_opt_in"]) == "1"
            assert re.fullmatch(r"'\+1[2-9]\d{2}[2-9]\d{6}", row["phone_number"])
        elif channel == "WHATSAPP_CONTACT":
            assert str(source["whatsapp_opt_in"]) == "1"
            assert re.fullmatch(r"'\+1[2-9]\d{2}[2-9]\d{6}", row["phone_number"])
        elif channel == "TELEMARKETING_CONTACT":
            assert str(source["telemarketing_contactable"]) == "1" and str(source["do_not_call"]) == "0"
            assert re.fullmatch(r"'\+1[2-9]\d{2}[2-9]\d{6}", row["phone_number"])
        elif channel == "MOBILE_PUSH_CONTACT":
            assert str(source["push_opt_in"]) == "1" and row["push_token"]
        elif channel == "DISPLAY_AUDIENCE":
            assert str(source["advertising_targetable"]) == "1" and row["advertising_id"]
        elif channel == "WEBSITE_AUDIENCE":
            assert str(source["onsite_targetable"]) == "1" and row["web_visitor_id"]
        else:
            assert channel in {"PAID_SOCIAL_AUDIENCE", "PAID_SEARCH_AUDIENCE"}
            assert any(re.fullmatch(r"[0-9a-f]{64}", row[field])
                       for field in ("sha256_email", "sha256_phone") if row[field])


def main() -> int:
    root = prepare_qa_root()
    print(f"Export matrix QA root: {root}", flush=True)
    process = None
    report = {"scope": "BUSINESS_NATIVE_V3_EXPORT_PROFILE_MATRIX",
              "status": "NOT_RUN", "qa_root": str(root), "headless": False,
              "profiles": []}
    try:
        process, port = start_qa_server(root)
        report["loopback_port"] = port
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            sources = {row["person_id"]: dict(row) for row in connection.execute(
                "SELECT * FROM demographics")}
        assert len(sources) == 200
        responses = []
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)

                def on_response(response):
                    path = urlsplit(response.url).path
                    if path.startswith("/api/"):
                        responses.append({"method": response.request.method,
                                          "path": path, "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                              wait_until="domcontentloaded")
                    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                    available = set(page.locator("#business-export-profile option").evaluate_all(
                        "options => options.filter(o => o.value && !o.disabled).map(o => o.value)"))
                    assert EXPECTED_PROFILES <= available, (
                        f"Missing expected v3 profiles: {sorted(EXPECTED_PROFILES - available)}")
                    ordered = sorted(EXPECTED_PROFILES)
                    for index, profile in enumerate(ordered, 1):
                        if index > 1:
                            page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                                      wait_until="domcontentloaded")
                            page.locator("#business-search-form").wait_for(
                                state="visible", timeout=30_000)
                        page.locator("#business-campaign-name").fill(
                            f"Bounded export {index:02d} {profile}"[:120])
                        if not page.locator("#business-product_ids").evaluate(
                            "e => [...e.selectedOptions].some(o => o.value === 'P1')"):
                            trigger = page.locator("#business-product_ids-trigger")
                            trigger.click()
                            page.locator("#business-product_ids-panel input[value='P1']").check()
                            trigger.press("Escape")
                        page.locator('input[name="business_score_mode"][value="similarity"]').check()
                        page.locator("#business-export-profile").select_option(profile)
                        page.locator("#business-search-submit").click()
                        page.wait_for_url("**/#results/*", timeout=30_000)
                        run_id = int(page.url.rsplit("/", 1)[-1])
                        page.wait_for_function(
                            "id => document.querySelector('#result-detail-run-id')?.textContent"
                            ".includes(`Search #${id}`) && "
                            "['COMPLETED','FAILED','BLOCKED'].includes("
                            "document.querySelector('#result-detail-badge')?.dataset.status)",
                            arg=run_id, timeout=240_000,
                        )
                        status = page.locator("#result-detail-badge").get_attribute("data-status")
                        assert status == "COMPLETED", (profile, status,
                            page.locator("#result-detail-status").inner_text()[:300])
                        with sqlite3.connect(database) as connection:
                            selected = connection.execute(
                                "SELECT selected_count FROM campaign_search_runs WHERE search_run_id=?",
                                (run_id,)).fetchone()[0]
                        assert selected == 200
                        with page.expect_download(timeout=30_000) as download_info:
                            page.locator("#result-detail-download").click()
                        download = download_info.value
                        assert download.suggested_filename.startswith(f"potential_customers_{run_id}_")
                        assert download.suggested_filename.endswith(".csv")
                        path = root / "downloads" / f"{index:02d}_{download.suggested_filename}"
                        download.save_as(path)
                        with path.open("r", encoding="utf-8-sig", newline="") as file:
                            reader = csv.DictReader(file)
                            header = tuple(reader.fieldnames or ())
                            rows = list(reader)
                        assert header == expected_header(profile), (profile, header)
                        assert len(rows) == len({row["person_id"] for row in rows})
                        assert all(row["person_id"] in sources for row in rows)
                        assert_contactability(profile, rows, sources)
                        sha = hashlib.sha256(path.read_bytes()).hexdigest()
                        with sqlite3.connect(database) as connection:
                            audit = connection.execute(
                                "SELECT export_profile,status,selected_count,deliverable_count,"
                                "undeliverable_count,row_count,csv_sha256 "
                                "FROM buyer_similarity_export_events WHERE search_run_id=? "
                                "ORDER BY export_event_id DESC LIMIT 1", (run_id,)).fetchone()
                            profile_count = connection.execute(
                                "SELECT COUNT(*) FROM buyer_similarity_profiles").fetchone()[0]
                            generation_count = connection.execute(
                                "SELECT COUNT(*) FROM buyer_similarity_score_generations").fetchone()[0]
                        assert audit is not None and audit[0:3] == (profile, "COMPLETED", 200)
                        assert audit[3] + audit[4] == 200 and audit[3] == audit[5] == len(rows)
                        assert audit[6] == sha
                        assert (profile_count, generation_count) == (1, 1)
                        report["profiles"].append({
                            "profile": profile, "run_id": run_id, "selected": selected,
                            "deliverable": len(rows), "excluded": audit[4],
                            "header": header, "csv_sha256": sha,
                            "profile_count": profile_count, "generation_count": generation_count,
                        })
                        print(f"Export profile {index}/20 verified: {profile}, {len(rows)} contacts",
                              flush=True)
                    save_screenshot(page, root / "screenshots" / "last_export_detail.png")
                    assert len(report["profiles"]) == 20
                    assert not capture.console_errors and not capture.page_errors
                    assert not capture.request_failures
                    report.update({
                        "status": "PASS_V3_ALL_AVAILABLE_EXPORT_PROFILES",
                        "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "api_responses": responses,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                    })
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_V3_EXPORT_PROFILE_MATRIX",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_export_matrix.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_V3_ALL_AVAILABLE_EXPORT_PROFILES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
