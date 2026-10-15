"""Exercise retained five-step planner through the real isolated app and API."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
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
    parser.add_argument("--positive", action="store_true")
    args = parser.parse_args()
    positive = args.positive or args.qa_root is None
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root(
        fixture_kind="PLANNER_TRAINABLE")
    if root.parent != QA_PARENT.resolve() or not (root / "qa_fixture_manifest.json").is_file():
        raise ValueError("Retained planner requires an existing isolated QA root.")
    print(f"Retained planner QA root: {root}", flush=True)
    report = {"scope": "RETAINED_COMPONENT_NATIVE_PLANNER", "status": "NOT_RUN",
              "qa_root": str(root), "cases": []}
    process = None
    try:
        process, port = start_qa_server(root)
        database = root / "state" / "qa.db"
        responses = []
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "planner_browser_profile",
                downloads_dir=root / "planner_downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)

                def on_response(response):
                    if "/api/" in response.url:
                        responses.append({"method": response.request.method,
                                          "path": response.url.split("/api/", 1)[-1].split("?", 1)[0],
                                          "status": response.status})

                page.on("response", on_response)
                try:
                    base = f"http://127.0.0.1:{port}/"
                    page.goto(base + "qa-retained#find-potential-customers",
                              wait_until="domcontentloaded", timeout=60_000)
                    page.locator("#business-search-form").wait_for(state="visible", timeout=30_000)
                    assert page.locator("#legacy-campaign-planner-shell").is_hidden()
                    # Only the disposable retained harness exposes the unchanged
                    # planner markup and exported controller; production routing does not.
                    page.evaluate("""async () => {
                      document.querySelector('#business-search-form').hidden = true;
                      document.querySelector('#business-search-error').hidden = true;
                      document.querySelector('#business-search-loading').hidden = true;
                      document.querySelector('#legacy-campaign-planner-shell').hidden = false;
                      const {initializeLegacyCampaignPlannerForHarness} = await import('/static/js/app.js');
                      initializeLegacyCampaignPlannerForHarness();
                    }""")
                    page.locator("#planner-step-panel-1").wait_for(state="visible")
                    page.locator("#planner-next-1").click()
                    assert page.locator("#planner-step-panel-1").is_visible()
                    assert "campaign name" in page.locator("#planner-status-announcement").inner_text().lower()
                    report["cases"].append({"id": "PLANNER_REQUIRED_NAME_GUARD", "status": "PASS"})
                    page.locator("#planner-campaign-name").fill("Bounded retained planner")
                    page.locator("#planner-campaign-description").fill("Synthetic QA only")
                    page.locator("#planner-save-draft").click()
                    assert "Draft saved" in page.locator("#planner-draft-status").inner_text()
                    page.locator("#planner-next-1").click()
                    page.locator("#planner-step-panel-2").wait_for(state="visible")
                    page.locator("#planner-context-form").wait_for(state="visible", timeout=30_000)
                    page.locator("#planner-back-2").click()
                    assert page.locator("#planner-step-panel-1").is_visible()
                    assert page.locator("#planner-campaign-name").input_value() == "Bounded retained planner"
                    page.locator("#planner-step-2").click()
                    page.locator("#planner-step-panel-2").wait_for(state="visible")
                    report["cases"].append({"id": "PLANNER_DRAFT_BACK_STEPPER", "status": "PASS"})
                    product = page.locator("#planner-context-products-trigger")
                    product.click()
                    page.locator("#planner-context-products-panel input[value='P1']").check()
                    product.press("Escape")
                    if positive:
                        campaign_type = page.locator("#planner-context-types-trigger")
                        campaign_type.click()
                        page.locator(
                            "#planner-context-types-panel input[value='Training Fixture']"
                        ).check()
                        campaign_type.press("Escape")
                    page.locator("#planner-context-delivery-channel").select_option("EMAIL")
                    with page.expect_response(
                        lambda response: response.request.method in ("POST", "PUT") and
                        "/api/campaign-planner/" in response.url,
                        timeout=30_000,
                    ) as context_response:
                        page.locator("#planner-next-2").click()
                    assert context_response.value.status in (200, 201)
                    page.locator("#planner-step-panel-3").wait_for(state="visible", timeout=30_000)
                    page.locator("#planner-targeting-form").wait_for(state="visible", timeout=30_000)
                    report["cases"].append({"id": "PLANNER_CONTEXT_SAVE", "status": "PASS",
                                            "api_status": context_response.value.status})
                    page.locator("#planner-targeting-more summary").click()
                    assert page.locator("#planner-targeting-family-min").is_visible()
                    page.locator("#planner-targeting-family-min").fill("5")
                    page.locator("#planner-targeting-family-max").fill("2")
                    page.locator("#planner-next-3").click()
                    assert page.locator("#planner-step-panel-3").is_visible()
                    page.locator("#planner-targeting-family-min").fill("")
                    page.locator("#planner-targeting-family-max").fill("")
                    report["cases"].append({"id": "PLANNER_INVALID_RANGE_GUARD", "status": "PASS"})
                    with page.expect_response(
                        lambda response: response.request.method in ("POST", "PUT") and
                        "/api/campaign-planner/" in response.url,
                        timeout=30_000,
                    ) as targeting_response:
                        page.locator("#planner-next-3").click()
                    assert targeting_response.value.status in (200, 201)
                    page.locator("#planner-step-panel-4").wait_for(state="visible", timeout=30_000)
                    page.wait_for_function("""() => {
                      const text = document.querySelector('#planner-intelligence-status')?.textContent || '';
                      return /ready|up to date|blocked|failed|not enough|could not/i.test(text);
                    }""", timeout=240_000 if positive else 150_000)
                    report["cases"].append({"id": "PLANNER_TARGETING_TO_INTELLIGENCE", "status": "PASS",
                                            "api_status": targeting_response.value.status})
                    report["intelligence_visible_state"] = page.locator(
                        "#planner-step-panel-4").inner_text()[:3000]
                    if positive:
                        page.wait_for_function("""() =>
                          !document.querySelector('#planner-target-preview').hidden ||
                          !document.querySelector('#planner-target-preview-error').hidden
                        """, timeout=90_000)
                        report["preview_selected"] = page.locator(
                            "#planner-preview-selected").inner_text()
                        if page.locator("#planner-target-preview-empty").is_visible():
                            assert page.locator("#planner-next-4").is_disabled()
                            report["cases"].append({"id": "PLANNER_READY_EXACT_ZERO_GUARD",
                                                    "status": "PASS"})
                        else:
                            assert page.locator("#planner-target-preview-error").is_hidden()
                            assert page.locator("#planner-next-4").is_enabled()
                            page.locator("#planner-next-4").click()
                            page.locator("#planner-step-panel-5").wait_for(state="visible")
                            report["cases"].append({"id": "PLANNER_PREVIEW_TO_REVIEW",
                                                    "status": "PASS"})
                            page.locator("#planner-target-group-name").fill(
                                "Bounded trained target group")
                            with sqlite3.connect(database) as connection:
                                prior_groups = connection.execute(
                                    "SELECT COUNT(*) FROM phase9_saved_target_groups"
                                ).fetchone()[0]
                                prior_campaigns = connection.execute(
                                    "SELECT COUNT(*) FROM campaigns"
                                ).fetchone()[0]
                            page.locator("#planner-save-target-group").click()
                            page.locator("#planner-save-success").wait_for(
                                state="visible", timeout=60_000)
                            with sqlite3.connect(database) as connection:
                                new_groups = connection.execute(
                                    "SELECT COUNT(*) FROM phase9_saved_target_groups"
                                ).fetchone()[0]
                                new_campaigns = connection.execute(
                                    "SELECT COUNT(*) FROM campaigns"
                                ).fetchone()[0]
                                saved_campaign = connection.execute(
                                    "SELECT status,saved_audience_resolved_count FROM campaigns "
                                    "ORDER BY campaign_id DESC LIMIT 1"
                                ).fetchone()
                            assert new_groups == prior_groups + 1
                            assert new_campaigns == prior_campaigns + 1
                            assert saved_campaign == ("DRAFT", 200)
                            assert any(item["method"] == "POST" and
                                       "save-target-group-and-create-draft" in item["path"]
                                       and item["status"] in (200, 201) for item in responses)
                            report["cases"].append({"id": "PLANNER_TARGET_GROUP_CAMPAIGN_DRAFT",
                                                    "status": "PASS",
                                                    "new_groups": new_groups,
                                                    "new_campaigns": new_campaigns})
                    with sqlite3.connect(database) as connection:
                        report["database_counts"] = {
                            "contexts": connection.execute(
                                "SELECT COUNT(*) FROM campaign_targeting_contexts").fetchone()[0],
                            "orchestrations": connection.execute(
                                "SELECT COUNT(*) FROM phase10_orchestration_runs").fetchone()[0],
                            "jobs": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                            "saved_target_groups": connection.execute(
                                "SELECT COUNT(*) FROM phase9_saved_target_groups").fetchone()[0],
                        }
                    save_screenshot(page, root / "screenshots" / "retained_planner_intelligence.png")
                    assert not capture.page_errors and not capture.request_failures
                    report.update({"status": (
                                       "PASS_RETAINED_PLANNER_READY_ZERO_GUARD"
                                       if positive and page.locator(
                                           "#planner-target-preview-empty").is_visible()
                                       else "PASS_RETAINED_PLANNER_FIVE_STEPS"
                                       if positive else "PASS_RETAINED_PLANNER_TO_INTELLIGENCE"),
                                   "browser": session.metadata.to_dict(),
                                   "api_responses": responses,
                                   "console_errors": capture.console_errors,
                                   "page_errors": capture.page_errors,
                                   "request_failures": capture.request_failures})
                except Exception:
                    try:
                        report["failure_state"] = page.evaluate("""() => ({
                          hash: location.hash,
                          step: document.querySelector('#planner-progress-label')?.textContent,
                          announcement: document.querySelector('#planner-status-announcement')?.textContent,
                          intelligenceStatus: document.querySelector('#planner-intelligence-status')?.textContent,
                          contextError: document.querySelector('#planner-context-error')?.textContent,
                          targetingError: document.querySelector('#planner-targeting-error')?.textContent,
                        })""")
                        report["failure_page_errors"] = capture.page_errors
                        report["failure_api_responses"] = responses
                    except Exception:
                        pass
                    raise
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_RETAINED_PLANNER_TO_INTELLIGENCE",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3500:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / ("native_retained_planner_positive_resume.json" if positive and args.qa_root
                       else "native_retained_planner_positive.json" if positive
                       else "native_retained_planner.json")
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)}), flush=True)
    return 0 if report["status"] in {
        "PASS_RETAINED_PLANNER_TO_INTELLIGENCE", "PASS_RETAINED_PLANNER_FIVE_STEPS",
        "PASS_RETAINED_PLANNER_READY_ZERO_GUARD",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
