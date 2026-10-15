"""Headed bounded QA of the real business form's interactive controls."""

from __future__ import annotations

import json
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


MULTISELECT_FIELDS = (
    "product_ids", "campaign_types", "campaign_categories", "offer_types",
    "historical_campaign_channels", "genders", "age_groups", "states", "regions",
    "income_groups", "marital_statuses", "education_levels", "employment_statuses",
    "resident_statuses", "resident_types", "employment_types",
)


def selected(page, field: str) -> list[str]:
    return page.locator(f"#business-{field}").evaluate(
        "e => [...e.selectedOptions].map(o => o.value)")


def exercise_dropdown(page, field: str) -> dict:
    prefix = f"#business-{field}"
    trigger = page.locator(f"{prefix}-trigger")
    panel = page.locator(f"{prefix}-panel")
    assert trigger.is_visible() and trigger.is_enabled(), field
    trigger.click()
    assert panel.is_visible() and trigger.get_attribute("aria-expanded") == "true"
    options = panel.locator(".multi-select-option input:not(:disabled)")
    option_count = options.count()
    assert option_count > 0, f"No available options for {field}"
    search = panel.locator(".multi-select-search")
    search.fill("__no_synthetic_option_matches__")
    assert panel.locator(".multi-select-empty").is_visible()
    assert panel.locator(".multi-select-option:visible").count() == 0
    search.fill("")
    assert panel.locator(".multi-select-option:visible").count() >= option_count
    first = options.first
    first_value = first.get_attribute("value")
    assert first_value
    first.check()
    assert first_value in selected(page, field)
    chip = page.locator(f'[data-multi-select-for="business-{field}"] .multi-select-remove').first
    chip.click()
    assert first_value not in selected(page, field)
    trigger.press("ArrowDown")
    assert panel.is_visible()
    focused = page.locator(":focus")
    keyboard_value = focused.get_attribute("value")
    assert keyboard_value and focused.get_attribute("type") == "checkbox"
    focused.press("Enter")
    assert keyboard_value in selected(page, field)
    focused.press("Escape")
    assert panel.is_hidden() and trigger.get_attribute("aria-expanded") == "false"
    trigger.click()
    panel.locator(".multi-select-actions button").first.click()
    assert len(selected(page, field)) == option_count
    panel.locator(".multi-select-actions button").nth(1).click()
    assert selected(page, field) == []
    page.locator("#business-campaign-name").click()  # outside-click closes the panel
    assert panel.is_hidden()
    mapped_states = []
    if field == "regions":
        mapped_states = selected(page, "states")
        assert mapped_states, "Region shortcut must add exact state values."
        states_trigger = page.locator("#business-states-trigger")
        states_trigger.click()
        page.locator("#business-states-panel .multi-select-actions button").nth(1).click()
        states_trigger.press("Escape")
        assert selected(page, "states") == []
    return {"field": field, "available_options": option_count,
            "search_no_result": True, "chip_remove": True,
            "keyboard_toggle_escape": True, "select_all_clear_all": True,
            "outside_click": True, "region_mapped_state_count": len(mapped_states)}


def main() -> int:
    root = prepare_qa_root(fixture_kind="UI_CATALOG_DIVERSE")
    print(f"Business controls QA root: {root}", flush=True)
    process = None
    report = {"scope": "BUSINESS_NATIVE_FORM_CONTROLS", "status": "NOT_RUN",
              "qa_root": str(root), "headless": False, "multiselects": []}
    try:
        process, port = start_qa_server(root)
        report["loopback_port"] = port
        database = root / "state" / "qa.db"
        responses: list[dict] = []
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
                        item = {"method": response.request.method,
                                "path": path, "status": response.status}
                        if path == "/api/potential-customer-search/preflight":
                            item["request"] = response.request.post_data_json
                        responses.append(item)

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/#find-potential-customers",
                              wait_until="domcontentloaded")
                    page.locator("#business-search-form").wait_for(
                        state="visible", timeout=30_000)
                    page.locator("#business-campaign-name").fill("Bounded form controls")
                    page.locator("#business-description").fill("Synthetic QA only")
                    page.locator("#business-launch-date").fill("2026-11-01")
                    # The native details/summary is part of the actual form.
                    page.locator("#business-more-fields").locator("xpath=../summary").click()
                    assert page.locator("#business-more-fields").is_visible()
                    for field in MULTISELECT_FIELDS:
                        report["multiselects"].append(exercise_dropdown(page, field))
                    assert len(report["multiselects"]) == len(MULTISELECT_FIELDS)
                    # The region shortcut expands into exact states. Clear through the real widget.
                    assert selected(page, "states") == []
                    assert page.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
                    minima = page.locator('input[name="business_similarity_minimum"]')
                    assert minima.count() == 5
                    tested_minima = []
                    for minimum in minima.all():
                        minimum.check()
                        tested_minima.append(minimum.input_value())
                    assert set(tested_minima) == {"0.5", "0.6", "0.7", "0.8", "0.9"}
                    page.locator('#business-selection-mode').select_option("TOP_N")
                    assert page.locator("#business-target-count").is_enabled()
                    assert page.locator("#business-target-count-field").is_visible()
                    page.locator('#business-selection-mode').select_option("ALL_MATCHING")
                    assert page.locator("#business-target-count").is_disabled()
                    assert page.locator("#business-target-count-field").is_hidden()
                    page.locator('input[name="business_score_mode"][value="probability"]').check()
                    assert page.locator("#business-probability-fieldset").is_visible()
                    assert page.locator("#business-similarity-fieldset").is_hidden()
                    assert page.locator("#business-top-percent").is_enabled()
                    assert minima.first.is_disabled()
                    buckets = page.locator('input[name="business_propensity_bucket"]')
                    assert buckets.count() >= 5
                    for bucket in buckets.all():
                        bucket.check()
                        assert bucket.is_checked()
                    page.locator('input[name="business_score_mode"][value="similarity"]').check()
                    assert page.locator("#business-top-percent").is_disabled()
                    assert page.locator("#business-probability-fieldset").is_hidden()
                    assert page.locator("#business-similarity-fieldset").is_visible()
                    # Exercise required-field and numeric guards without creating a run.
                    page.locator("#business-search-submit").click()
                    assert page.locator("#business-product_ids-trigger").get_attribute("aria-invalid") == "true"
                    product_trigger = page.locator("#business-product_ids-trigger")
                    product_trigger.click()
                    page.locator("#business-product_ids-panel input[value='P1']").check()
                    product_trigger.press("Escape")
                    profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                      .find(o => !o.disabled && o.value && o.value.includes('EMAIL') &&
                        o.value.includes('V3'))?.value || ''""")
                    if not profile:
                        profile = page.evaluate("""() => [...document.querySelector('#business-export-profile').options]
                          .find(o => !o.disabled && o.value && o.textContent.includes('Email'))?.value || ''""")
                    assert profile
                    page.locator("#business-export-profile").select_option(profile)
                    page.locator("#business-campaign-name").fill("   ")
                    page.locator("#business-search-submit").click()
                    assert page.locator("#business-campaign-name").evaluate(
                        "e => e.validationMessage.includes('campaign name')")
                    page.locator("#business-campaign-name").fill("Bounded form controls")
                    page.locator("#business-family-min").fill("5")
                    page.locator("#business-family-max").fill("2")
                    page.locator("#business-search-submit").click()
                    assert page.locator("#business-family-max").evaluate(
                        "e => e.validationMessage.includes('Maximum family size')")
                    page.locator("#business-family-max").fill("5")
                    page.locator('#business-selection-mode').select_option("TOP_N")
                    page.locator("#business-search-submit").click()
                    assert page.locator("#business-target-count").evaluate("e => !e.validity.valid")
                    page.locator("#business-target-count").fill("10")
                    page.locator("#business-family-min").fill("")
                    page.locator("#business-family-max").fill("")
                    page.locator("#business-search-preflight").click()
                    page.wait_for_function("() => !document.querySelector('#business-search-preflight').disabled",
                                           timeout=30_000)
                    preflights = [r for r in responses if r["method"] == "POST"
                                  and r["path"] == "/api/potential-customer-search/preflight"]
                    assert len(preflights) == 1 and preflights[0]["status"] == 200
                    request = preflights[0]["request"]
                    assert request["selection_contract_version"] == "3"
                    assert request["score_semantics"] == "PRODUCT_BUYER_SIMILARITY"
                    assert request["top_n"] == 10 and request["context"]["product_ids"] == ["P1"]
                    assert "propensity_bucket" not in request
                    assert "Not prepared" in page.locator("#business-search-preflight-result").inner_text()
                    save_screenshot(page, root / "screenshots" / "business_controls_complete.png")
                    with sqlite3.connect(database) as connection:
                        runs = connection.execute("SELECT COUNT(*) FROM campaign_search_runs").fetchone()[0]
                        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                    assert (runs, jobs) == (0, 0)
                    assert not capture.console_errors and not capture.page_errors
                    assert not capture.request_failures
                    report.update({
                        "status": "PASS_BUSINESS_FORM_CONTROLS",
                        "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "tested_similarity_minima": tested_minima,
                        "tested_probability_bucket_count": buckets.count(),
                        "required_and_numeric_guards": ["products", "campaign_name_whitespace",
                            "family_min_max", "top_n_required"],
                        "preflight_request": request,
                        "runs_after": runs, "jobs_after": jobs,
                        "api_responses": responses,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                    })
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_BUSINESS_FORM_CONTROLS",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_business_form_controls.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_BUSINESS_FORM_CONTROLS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
