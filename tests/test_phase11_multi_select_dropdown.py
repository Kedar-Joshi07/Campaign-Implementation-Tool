from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_phase11_business_navigation import browser_session, open_route, page
from tests.test_phase9_business_targeting import database_path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_IDS = (
    "planner-context-products", "planner-context-types", "planner-context-categories",
    "planner-context-offers", "planner-context-historical-channels",
)
TARGET_IDS = (
    "planner-targeting-genders", "planner-targeting-age-groups", "planner-targeting-states",
    "planner-targeting-income-groups", "planner-targeting-marital-statuses",
    "planner-targeting-education-levels", "planner-targeting-employment-statuses",
    "planner-targeting-resident-statuses", "planner-targeting-resident-types",
    "planner-targeting-employment-types", "planner-targeting-regions",
)


def test_generic_component_and_all_required_field_adapters_are_present():
    component = (ROOT / "frontend/js/components/multi-select-dropdown.js").read_text(encoding="utf-8")
    assert "innerHTML" not in component
    assert "MutationObserver" not in component
    assert "new WeakMap()" in component
    for business_value in ("PRD", "Female", "Texas", "EMAIL", "BROAD"):
        assert business_value not in component
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    for control_id in (*CONTEXT_IDS, *TARGET_IDS):
        tag = html.split(f'<select id="{control_id}"', 1)[1].split(">", 1)[0]
        assert "multiple" in tag
    for module in ("campaign-context", "business-targeting"):
        script = (ROOT / f"frontend/js/{module}.js").read_text(encoding="utf-8")
        assert 'from "./components/multi-select-dropdown.js"' in script
        assert "enhanceMultiSelect(" in script
        assert "refreshMultiSelect(" in script
        assert "setMultiSelectState(" in script


@pytest.fixture
def component_page(page):
    browser, errors, requests = page
    open_route(browser, "#results")
    browser.evaluate("""async () => {
      const {enhanceMultiSelect} = await import('/static/js/components/multi-select-dropdown.js');
      const form = document.createElement('form'); form.id = 'component-test-form'; form.style.width = '380px';
      const label = document.createElement('label'); label.htmlFor = 'component-test'; label.textContent = 'Test choices';
      const select = document.createElement('select'); select.id = 'component-test'; select.name = 'choices'; select.multiple = true;
      const outside = document.createElement('button'); outside.type = 'button'; outside.id = 'component-outside'; outside.textContent = 'Outside';
      outside.style.marginTop = '400px'; // Place a genuinely outside target below the overlay.
      form.append(label, select, outside); document.querySelector('main').append(form);
      window.dropdown = enhanceMultiSelect(select);
      dropdown.setOptions([{value: 'a', label: 'Alpha'}, {value: 'b', label: 'Beta'},
        {value: 'c', label: 'Alpine'}, {value: 'd', label: 'Unavailable option', disabled: true}]);
      window.formEvents = {change: 0, input: 0, submit: 0};
      for (const type of ['change', 'input', 'submit']) form.addEventListener(type, event => {
        formEvents[type]++; if (type === 'submit') event.preventDefault();
      });
    }""")
    yield browser, errors, requests
    assert errors == []


def values(browser):
    return browser.evaluate("dropdown.values()")


def enable_legacy_planner(browser):
    browser.evaluate("""async () => {
      document.querySelector('#business-search-form').hidden = true;
      document.querySelector('#business-search-error').hidden = true;
      document.querySelector('#business-search-loading').hidden = true;
      document.querySelector('#legacy-campaign-planner-shell').hidden = false;
      const {initializeLegacyCampaignPlannerForHarness} = await import('/static/js/app.js');
      initializeLegacyCampaignPlannerForHarness();
    }""")
    browser.wait_for_load_state("networkidle")


@pytest.mark.browser
def test_filtered_select_all_clear_all_chips_and_authoritative_form_values(component_page):
    browser, _, _ = component_page
    browser.locator("#component-test-trigger").click()
    browser.locator("#component-test-search").fill("AL")
    assert browser.locator("#component-test-panel .multi-select-option:visible").count() == 2
    browser.get_by_role("button", name="Select All visible (2)", exact=True).click()
    assert values(browser) == ["a", "c"]
    browser.locator("#component-test-search").fill("Beta")
    browser.get_by_role("button", name="Select All visible (1)", exact=True).click()
    assert values(browser) == ["a", "b", "c"]
    assert browser.evaluate("formEvents") == {"change": 2, "input": 0, "submit": 0}
    assert browser.evaluate("new FormData(document.querySelector('#component-test-form')).getAll('choices')") == ["a", "b", "c"]
    browser.get_by_role("button", name="Clear All", exact=True).click()
    assert values(browser) == []
    assert browser.locator("#component-test-selection-summary").inner_text() == "0 selected"
    browser.locator("#component-test-search").fill("a")
    browser.get_by_role("checkbox", name="Alpha", exact=True).check()
    browser.get_by_role("checkbox", name="Alpha", exact=True).press("Escape")
    browser.get_by_role("button", name="Remove Alpha from Test choices", exact=True).click()
    assert values(browser) == []
    assert browser.locator("#component-test-trigger").evaluate("element => element === document.activeElement")


@pytest.mark.browser
def test_keyboard_space_enter_arrows_escape_tab_and_outside_focus(component_page):
    browser, _, _ = component_page
    trigger = browser.locator("#component-test-trigger")
    trigger.focus()
    trigger.press("Enter")
    assert trigger.get_attribute("aria-expanded") == "true"
    assert browser.locator("#component-test-search").evaluate("element => element === document.activeElement")
    browser.locator("#component-test-search").press("ArrowDown")
    alpha = browser.get_by_role("checkbox", name="Alpha", exact=True)
    alpha.press("Space")
    assert values(browser) == ["a"]
    alpha.press("ArrowDown")
    beta = browser.get_by_role("checkbox", name="Beta", exact=True)
    assert beta.evaluate("element => element === document.activeElement")
    beta.press("Enter")
    assert values(browser) == ["a", "b"]
    beta.press("End")
    alpine = browser.get_by_role("checkbox", name="Alpine", exact=True)
    assert alpine.evaluate("element => element === document.activeElement")
    alpine.press("Home")
    alpha.press("ArrowUp")
    assert alpine.evaluate("element => element === document.activeElement")
    alpine.press("Escape")
    assert trigger.evaluate("element => element === document.activeElement")
    assert browser.locator("#component-test-panel").is_hidden()
    trigger.press("Space")
    browser.locator("#component-outside").click()
    assert browser.locator("#component-test-panel").is_hidden()
    assert browser.locator("#component-outside").evaluate("element => element === document.activeElement")
    trigger.press("ArrowUp")
    assert alpine.evaluate("element => element === document.activeElement")
    alpine.press("Tab")
    assert browser.locator("#component-test-panel").is_hidden()
    assert browser.evaluate("formEvents.submit") == 0


@pytest.mark.browser
@pytest.mark.parametrize("state,copy", [
    ({"loading": True}, "Loading choices…"),
    ({"disabled": True}, "Choices disabled."),
    ({"error": "Choices could not be loaded. Try again."}, "Choices could not be loaded. Try again."),
])
def test_disabled_loading_error_and_recovery(component_page, state, copy):
    browser, _, _ = component_page
    browser.locator("#component-test-trigger").click()
    browser.evaluate("state => dropdown.setState(state)", state)
    assert browser.locator("#component-test-panel").is_hidden()
    assert browser.locator("#component-test-trigger").is_disabled()
    assert browser.locator("#component-test-status").inner_text() == copy
    assert browser.locator("[data-multi-select-for=component-test]").evaluate("element => element === document.activeElement")
    assert browser.locator("[data-multi-select-for=component-test]").get_attribute("aria-busy") == str(bool(state.get("loading"))).lower()
    browser.evaluate("dropdown.setState({loading: false, disabled: false, error: ''})")
    assert browser.locator("#component-test-trigger").is_enabled()
    browser.locator("#component-test-trigger").click()
    browser.get_by_role("checkbox", name="Alpha", exact=True).check()
    assert values(browser) == ["a"]


@pytest.mark.browser
def test_empty_no_matches_option_disabled_native_disabled_and_safe_labels(component_page):
    browser, _, _ = component_page
    browser.locator("#component-test-trigger").click()
    assert browser.get_by_role("checkbox", name="Unavailable option Unavailable", exact=True).is_disabled()
    browser.locator("#component-test-search").fill("missing")
    assert browser.locator("#component-test-panel .multi-select-empty").inner_text() == "No matching options."
    assert browser.get_by_role("button", name="Select All visible (0)", exact=True).is_disabled()
    browser.evaluate("dropdown.setOptions([])")
    assert browser.locator("#component-test-panel .multi-select-empty").inner_text() == "No options available."
    browser.evaluate("dropdown.setOptions([{value: 'raw-value', label: '<img src=x onerror=alert(1)>'}])")
    browser.locator("#component-test-search").fill("raw-value")
    assert browser.locator("#component-test-panel img").count() == 0
    browser.get_by_role("checkbox").check()
    assert values(browser) == ["raw-value"]
    browser.evaluate("dropdown.select.disabled = true; dropdown.refresh()")
    assert browser.locator("#component-test-trigger").is_disabled()


@pytest.mark.browser
def test_required_validation_restoration_native_change_reset_and_destroy(component_page):
    browser, _, _ = component_page
    browser.evaluate("dropdown.select.required = true")
    assert browser.evaluate("document.querySelector('#component-test-form').reportValidity()") is False
    assert browser.locator("#component-test-trigger").get_attribute("aria-invalid") == "true"
    assert browser.locator("#component-test-trigger").evaluate("element => element === document.activeElement")
    browser.evaluate("dropdown.setValues(['b']);")
    assert browser.evaluate("document.querySelector('#component-test-form').reportValidity()") is True
    assert browser.locator("#component-test-selection-summary").inner_text() == "1 selected"
    browser.evaluate("dropdown.select.options[0].selected = true; dropdown.select.dispatchEvent(new Event('change', {bubbles: true}))")
    assert values(browser) == ["a", "b"]
    browser.locator("#component-test-trigger").click()
    assert browser.get_by_role("checkbox", name="Alpha", exact=True).is_checked()
    browser.evaluate("document.querySelector('#component-test-form').reset()")
    assert values(browser) == []
    assert browser.locator("#component-test-selection-summary").inner_text() == "0 selected"
    browser.evaluate("dropdown.destroy()")
    assert browser.locator("[data-multi-select-for=component-test]").count() == 0
    assert browser.locator("#component-test").is_visible()
    assert browser.locator('label[for="component-test"]').count() == 1
    assert browser.locator("#component-test").get_attribute("aria-hidden") is None


@pytest.mark.browser
def test_instance_idempotency_option_validation_and_selected_value_preservation(component_page):
    browser, _, _ = component_page
    result = browser.evaluate("""async () => {
      const {enhanceMultiSelect} = await import('/static/js/components/multi-select-dropdown.js');
      const same = dropdown === enhanceMultiSelect(dropdown.select);
      dropdown.setValues(['b']);
      dropdown.setOptions([{value: 'b', label: 'Renamed'}, {value: 'new', label: 'New'}]);
      const preserved = dropdown.values();
      let duplicateRejected = false, unknownRejected = false;
      try { dropdown.setOptions(['x', 'x']); } catch (_) { duplicateRejected = true; }
      try { dropdown.setValues(['not-supplied']); } catch (_) { unknownRejected = true; }
      return {same, preserved, duplicateRejected, unknownRejected, values: dropdown.values()};
    }""")
    assert result == {"same": True, "preserved": ["b"], "duplicateRejected": True, "unknownRejected": True, "values": ["b"]}
    assert browser.locator("[data-multi-select-for=component-test]").count() == 1


@pytest.mark.browser
def test_aria_label_focus_association_and_only_one_open_dropdown(component_page):
    browser, _, _ = component_page
    assert browser.locator("#component-test-trigger").get_attribute("aria-label") == "Test choices"
    assert browser.locator("#component-test-trigger").get_attribute("aria-haspopup") == "dialog"
    assert browser.locator("#component-test-trigger").get_attribute("aria-controls") == "component-test-panel"
    browser.locator('label[for="component-test-trigger"]').click()
    # Native button-label activation opens the panel and transfers focus to its search.
    assert browser.locator("#component-test-search").evaluate("element => element === document.activeElement")
    browser.evaluate("""async () => {
      const {enhanceMultiSelect} = await import('/static/js/components/multi-select-dropdown.js');
      const select = document.createElement('select'); select.id = 'second-component'; select.multiple = true;
      document.querySelector('#component-test-form').prepend(select);
      enhanceMultiSelect(select, {label: 'Second choices'}).setOptions(['supplied']);
    }""")
    # Clicking an associated button label may activate it; make the open state explicit.
    if browser.locator("#component-test-panel").is_hidden():
        browser.locator("#component-test-trigger").click()
    assert browser.get_by_role("dialog", name="Choose Test choices").is_visible()
    assert browser.get_by_role("searchbox", name="Search Test choices").is_visible()
    browser.locator("#second-component-trigger").click()
    assert browser.locator("#component-test-panel").is_hidden()
    assert browser.get_by_role("dialog", name="Choose Second choices").is_visible()


@pytest.fixture
def options_payloads(database_path):
    from app.services.campaign_targeting_context_service import get_business_targeting_options, get_campaign_context_options

    return get_campaign_context_options(database_path), get_business_targeting_options(database_path)


@pytest.mark.browser
def test_all_16_fields_form_state_payloads_region_chips_clear_and_reopen(page, options_payloads):
    browser, errors, _ = page
    context_options, targeting_options = options_payloads
    saved_payloads = []

    def context_api(route):
        path = urlsplit(route.request.url).path
        if path.endswith("context-options"):
            route.fulfill(json=context_options)
        elif path.endswith("targeting-options"):
            route.fulfill(json=targeting_options)
        elif not (re.fullmatch(r"/api/campaign-planner/contexts(?:/1)?", path)
                  or path == "/api/campaign-planner/contexts/1/targeting-criteria"):
            route.fulfill(status=503, json={"detail": "Preparation/results are outside this component harness"})
        elif route.request.method in {"POST", "PUT"}:
            body = route.request.post_data_json
            saved_payloads.append(body)
            if "context" in body:
                route.fulfill(json={"targeting_context_id": 1, "context": body["context"]})
            else:
                route.fulfill(json={"criteria": body["criteria"], "audience_filter_branches": [{}]})
        else:
            key = "criteria" if path.endswith("targeting-criteria") else "context"
            previous = next(payload[key] for payload in reversed(saved_payloads) if key in payload)
            route.fulfill(json={key: previous, "targeting_context_id": 1})

    browser.route("**/api/campaign-planner/**", context_api)
    open_route(browser, "#find-potential-customers")
    enable_legacy_planner(browser)
    assert browser.locator("#legacy-campaign-planner-shell .multi-select-dropdown").count() == 16
    browser.locator("#planner-campaign-name").fill("Component fixture")
    browser.locator("#planner-next-1").click()
    for control_id in CONTEXT_IDS:
        browser.locator(f"#{control_id}-trigger").click()
        checkbox = browser.locator(f"#{control_id}-panel input[type=checkbox]").first
        checkbox.check()
        checkbox.press("Escape")
    browser.locator("#planner-context-delivery-channel").select_option("EMAIL")
    context_values = browser.evaluate("""async () => {
      const {getCampaignPlannerState} = await import('/static/js/campaign-planner-state.js');
      return getCampaignPlannerState().campaignContext;
    }""")
    browser.locator("#planner-next-2").click()
    browser.locator("#planner-step-panel-3").wait_for(state="visible")
    assert saved_payloads[0] == {"context": context_values}
    browser.locator("#planner-targeting-more summary").click()
    for control_id in TARGET_IDS:
        browser.locator(f"#{control_id}-trigger").click()
        checkbox = browser.locator(f"#{control_id}-panel input[type=checkbox]").first
        checkbox.check()
        checkbox.press("Escape")
    state = browser.evaluate("""async () => {
      const {getCampaignPlannerState} = await import('/static/js/campaign-planner-state.js');
      return getCampaignPlannerState();
    }""")
    browser.locator("#planner-targeting-states-trigger").click()
    browser.locator("#planner-targeting-states-search").fill("no matching state")
    browser.locator("#planner-targeting-states-search").press("Escape")
    assert browser.evaluate("""async () => {
      const {getCampaignPlannerState} = await import('/static/js/campaign-planner-state.js');
      return getCampaignPlannerState();
    }""") == state
    for control_id in TARGET_IDS:
        assert browser.locator(f"#{control_id}-selection-summary").inner_text() != "0 selected"
        assert browser.locator(f"#{control_id}").is_hidden()
    for value in targeting_options["regions"][0]["states"]:
        assert value in state["targetingCriteria"]["states"]
    browser.locator("#planner-targeting-save").click()
    browser.wait_for_function("document.querySelector('#planner-targeting-save-summary').hidden === false")
    assert saved_payloads[-1] == {"criteria": state["targetingCriteria"]}
    chip = browser.locator('#planner-targeting-chips button[data-targeting-field="genders"]').first
    chip.click()
    assert browser.locator("#planner-targeting-genders-selection-summary").inner_text() == "0 selected"
    assert browser.locator("#planner-targeting-genders-trigger").evaluate("element => element === document.activeElement")
    browser.locator("#planner-targeting-clear-all").click()
    for control_id in TARGET_IDS:
        assert browser.locator(f"#{control_id}-selection-summary").inner_text() == "0 selected"
    browser.locator("#planner-targeting-save").click()
    browser.wait_for_function("!document.querySelector('#planner-targeting-save').disabled")
    # Session-based state reopen: no server run/result is fabricated or persisted.
    browser.reload(wait_until="networkidle")
    enable_legacy_planner(browser)
    assert browser.locator("#planner-context-products-selection-summary").inner_text() == "1 selected"
    assert browser.locator("#planner-targeting-genders-selection-summary").inner_text() == "0 selected"
    assert errors == []


@pytest.mark.browser
def test_adapter_load_error_and_retry_recover_existing_components(page, options_payloads):
    browser, errors, _ = page
    open_route(browser, "#find-potential-customers")
    enable_legacy_planner(browser)
    assert browser.locator("#planner-context-products-trigger").is_disabled()
    assert browser.locator("#planner-targeting-genders-trigger").is_disabled()
    context_options, targeting_options = options_payloads
    browser.route("**/api/campaign-planner/context-options", lambda route: route.fulfill(json=context_options))
    browser.route("**/api/campaign-planner/targeting-options", lambda route: route.fulfill(json=targeting_options))
    browser.locator("#planner-campaign-name").fill("Retry fixture")
    browser.locator("#planner-next-1").click()
    browser.locator("#planner-context-retry").click()
    browser.wait_for_function("!document.querySelector('#planner-context-products-trigger').disabled")
    browser.evaluate("document.querySelector('#planner-targeting-retry').click()")
    browser.wait_for_function("!document.querySelector('#planner-targeting-genders-trigger').disabled")
    assert browser.locator("#legacy-campaign-planner-shell .multi-select-dropdown").count() == 16
    assert errors == []


@pytest.mark.browser
@pytest.mark.parametrize("kind,count", [("products", 48), ("states", 51), ("stress", 500)])
def test_realistic_option_counts_filter_selection_node_stability_and_latency(component_page, kind, count):
    browser, _, _ = component_page
    if kind == "products":
        import numpy as np
        from data_generation_scripts.generate_campaign_sales import product_catalog
        supplied = [{"value": item.product_id, "label": item.product_name} for item in product_catalog(np.random.default_rng(0))]
    elif kind == "states":
        from app.services.campaign_targeting_context_service import _STATE_REGIONS
        supplied = sorted({state for states in _STATE_REGIONS.values() for state in states})
    else:
        supplied = [{"value": f"option-{index}", "label": f"Stress option {index}"} for index in range(count)]
    assert len(supplied) == count
    metrics = browser.evaluate("""async options => {
      const start = performance.now(); dropdown.setOptions(options); const setupMs = performance.now() - start;
      const nodes = [...dropdown.options.querySelectorAll('input')];
      let mutations = 0; const observer = new MutationObserver(records => mutations += records.length);
      observer.observe(dropdown.options, {childList: true, subtree: true});
      const samples = [];
      for (let index = 0; index < 100; index++) {
        const start = performance.now(); dropdown.search.value = index % 2 ? '' : 'a';
        dropdown.search.dispatchEvent(new Event('input', {bubbles: true})); samples.push(performance.now() - start);
      }
      const afterSearch = {...formEvents};
      const selectStart = performance.now(); dropdown.selectAll.click(); const selectMs = performance.now() - selectStart;
      const selected = dropdown.values().length;
      dropdown.clearAll.click();
      await new Promise(resolve => requestAnimationFrame(resolve)); observer.disconnect();
      const stable = nodes.every((node, index) => node === dropdown.options.querySelectorAll('input')[index]);
      samples.sort((a, b) => a - b);
      return {setupMs, p95FilterMs: samples[94], maxFilterMs: samples[99], selectMs, selected,
        mutations, stable, afterSearch, events: formEvents, chipCount: dropdown.chips.children.length};
    }""", supplied)
    print(f"\nStep7 {kind} ({count} options): {metrics}")
    assert metrics["setupMs"] < 500
    assert metrics["p95FilterMs"] < 50
    assert metrics["maxFilterMs"] < 250
    assert metrics["selectMs"] < 250
    assert metrics["selected"] == count
    assert metrics["stable"] is True
    assert metrics["mutations"] == 0
    assert metrics["afterSearch"] == {"change": 0, "input": 0, "submit": 0}
    assert metrics["events"] == {"change": 2, "input": 0, "submit": 0}
    assert metrics["chipCount"] == 0
