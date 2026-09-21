"""Step 8: isolated real API + intercepted system-Chrome form integration.

No canonical database, imports, training, scoring, or invented ready snapshots.
Disconnected behavior is covered explicitly; lifespan-backed form tests exercise
the production runtime coordinator composition.
"""
from copy import deepcopy
import json
from urllib.parse import urlsplit

import pytest

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.services import potential_customer_search_submission_service as service
from app.services.campaign_targeting_context_service import get_business_targeting_criteria
from app.schemas.campaign_targeting import CampaignTargetingContextContract
from pydantic import ValidationError
from app.services.phase10_context_identity_service import derive_modeling_context_from_campaign_context
from tests.test_phase9_business_targeting import database_path, client, _criteria
from tests.test_phase11_business_navigation import browser_session, page, open_route

RUNS = "/api/potential-customer-search/runs"
OPTIONS = "/api/potential-customer-search/options"


def request_payload():
    profile = next(p for p in service.OMNICHANNEL_PROFILE_REGISTRY.values() if p.channel_code == "EMAIL")
    return dict(campaign_name="Savings outreach", description="Optional description", planned_launch_date="2026-12-01",
                context=dict(product_ids=["PRD-1"], campaign_types=["Retention"], campaign_categories=["Lifecycle"],
                             offer_types=["Loyalty"], historical_campaign_channels=["Email"], campaign_channel="EMAIL"),
                criteria=_criteria(), export_profile=profile.export_profile)


def counts(path):
    with get_connection(path) as connection:
        return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ("campaign_search_runs", "campaign_targeting_contexts", "campaign_result_snapshots",
                             "campaign_result_export_events", "model_runs", "scoring_runs")}


def test_options_are_live_registry_owned_and_executor_boundary_is_explicit(client):
    # This service-boundary test intentionally disconnects the production
    # lifespan seam. Real app composition is covered by the runtime tests.
    service.reset_phase11_search_executor()
    payload = client.get(OPTIONS).json()
    assert payload["workflow_available"] is False
    assert payload["context"]["products"][0]["product_id"] == "PRD-1"
    assert payload["targeting"]["states"] == ["Ohio", "Texas"]
    profiles = client.get("/api/export-profiles").json()
    assert payload["profiles"] == profiles
    assert len(profiles) == 10
    assert all(p["availability"] == "AVAILABLE" for p in profiles)
    assert not any("email" in p or "phone" in p for p in profiles)


def test_submission_persists_exact_lineage_and_default_blocked_status(client, database_path):
    # Preserve explicit coverage of the fail-closed disconnected boundary.
    service.reset_phase11_search_executor()
    before = counts(database_path)
    payload = request_payload()
    response = client.post(RUNS, json=payload)
    assert response.status_code == 201, response.text
    status = response.json()
    assert status["status"] == "BLOCKED" and status["selected_count"] is None
    assert "not connected" in status["safe_message"]
    assert client.get(f'{RUNS}/{status["search_run_id"]}/status').json() == status
    assert client.get(RUNS).json() == [status]
    row = CampaignResultRegistryRepository(database_path).fetch_search_run(status["search_run_id"])
    saved = get_business_targeting_criteria(database_path, targeting_context_id=row["targeting_context_id"])
    assert json.loads(row["targeting_criteria_json"]) == saved["criteria"]
    assert json.loads(row["filter_branches_json"]) == saved["audience_filter_branches"]
    assert row["targeting_criteria_sha256"] == saved["targeting_criteria_sha256"]
    assert row["modeling_context_sha256"] == derive_modeling_context_from_campaign_context(payload["context"]).modeling_context_sha256
    assert len(saved["audience_filter_branches"]) == 4  # two disjoint ages x two disjoint income ranges
    assert row["description"] == payload["description"] and row["planned_launch_date"] == payload["planned_launch_date"]
    after = counts(database_path)
    assert after == before | {"campaign_search_runs": 1, "campaign_targeting_contexts": 1}
    assert set(status) == {"search_run_id", "campaign_name", "status", "created_at", "completed_at", "selected_count",
                           "delivery_channel", "export_profile", "safe_message"}


def test_repeated_intentional_submissions_are_independent_and_profile_filters_do_not_retrain(client, database_path):
    # This test owns submission/history semantics, not production composition.
    service.reset_phase11_search_executor()
    original = request_payload()
    first = client.post(RUNS, json=original).json()
    changed = deepcopy(original)
    profile = next(p for p in service.OMNICHANNEL_PROFILE_REGISTRY.values() if p.channel_code == "SMS")
    changed.update(campaign_name="Different campaign", export_profile=profile.export_profile)
    changed["context"]["campaign_channel"] = "SMS"
    changed["criteria"].update(genders=["Male"], states=["Ohio"], selection_mode="ALL_MATCHING", target_count=None,
                               top_matching_percent=None)
    second = client.post(RUNS, json=changed)
    assert second.status_code == 201, second.text
    repository = CampaignResultRegistryRepository(database_path)
    one = repository.fetch_search_run(first["search_run_id"])
    two = repository.fetch_search_run(second.json()["search_run_id"])
    assert one["targeting_context_id"] != two["targeting_context_id"]
    assert one["modeling_context_sha256"] == two["modeling_context_sha256"]
    assert one["targeting_criteria_sha256"] != two["targeting_criteria_sha256"]
    assert repository.fetch_search_run(first["search_run_id"]) == one
    assert two["target_count"] is None
    assert [r["search_run_id"] for r in client.get(RUNS).json()] == [two["search_run_id"], one["search_run_id"]]
    assert client.get(RUNS, params={"limit": 1, "before_search_run_id": two["search_run_id"]}).json() == [first]
    assert counts(database_path)["scoring_runs"] == 0 and counts(database_path)["model_runs"] == 0


@pytest.mark.parametrize("section,field,value", [
    (None, "campaign_name", "   "), (None, "planned_launch_date", "not-a-date"),
    (None, "export_profile", "invented"), (None, "email", "private@example.test"),
    ("context", "product_ids", []), ("context", "product_ids", ["missing"]),
    ("context", "campaign_channel", "SMS"), ("context", "historical_campaign_channels", ["invented"]),
    ("criteria", "genders", ["invented"]), ("criteria", "states", ["invented"]),
    ("criteria", "age_groups", ["invented"]), ("criteria", "income_groups", ["invented"]),
    ("criteria", "top_matching_percent", 0), ("criteria", "top_matching_percent", 101),
    ("criteria", "target_count", 0), ("criteria", "family_member_count_min", 6),
    ("criteria", "selection_mode", "invented"), ("criteria", "match_strength", "invented"),
])
def test_invalid_request_has_no_context_run_or_heavy_side_effects(client, database_path, section, field, value):
    payload = request_payload()
    (payload if section is None else payload[section])[field] = value
    before = counts(database_path)
    response = client.post(RUNS, json=payload)
    assert response.status_code == 422, response.text
    assert counts(database_path) == before


def test_unavailable_profile_is_gated_before_writes(client, database_path, monkeypatch):
    monkeypatch.setattr(service, "resolve_profile_availability", lambda *args, **kwargs: "BLOCKED")
    assert client.get(OPTIONS).json()["profiles"][0]["unavailable_reason"]
    before = counts(database_path)
    assert client.post(RUNS, json=request_payload()).status_code == 422
    assert counts(database_path) == before


def test_executor_handoff_sees_durable_exact_run_and_processing_survives_new_client(client, database_path, monkeypatch):
    calls = []
    def execute(path, identifier):
        repository = CampaignResultRegistryRepository(path)
        row = repository.fetch_search_run(identifier)
        assert row["status"] == "QUEUED"
        assert json.loads(row["targeting_criteria_json"])["match_strength"] == "STRONG"
        assert get_business_targeting_criteria(path, targeting_context_id=row["targeting_context_id"])
        calls.append(identifier)
        repository.mark_processing(identifier)
    monkeypatch.setattr(service, "PHASE11_SEARCH_EXECUTOR", execute)
    assert client.get(OPTIONS).json()["workflow_available"] is True
    response = client.post(RUNS, json=request_payload())
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PROCESSING"
    assert calls == [response.json()["search_run_id"]]
    # Independent repository read, not request/session-local state.
    assert CampaignResultRegistryRepository(database_path).fetch_search_run(calls[0])["status"] == "PROCESSING"
    assert client.get(f"{RUNS}/{calls[0]}/status").json() == response.json()


def test_executor_failure_preserves_run_with_safe_failure(client, database_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("private@example.test secret engine failure")
    monkeypatch.setattr(service, "PHASE11_SEARCH_EXECUTOR", fail)
    response = client.post(RUNS, json=request_payload())
    assert response.status_code == 201 and response.json()["status"] == "FAILED"
    assert "secret" not in response.text and "private@" not in response.text
    assert counts(database_path)["campaign_search_runs"] == 1


@pytest.mark.parametrize("url", [f"{RUNS}/0/status", f"{RUNS}/999999999999999999999999/status",
                               f"{RUNS}?before_search_run_id=999999999999999999999999", f"{RUNS}?limit=101"])
def test_invalid_id_and_page_bounds_return_validation_not_database_overflow(client, url):
    assert client.get(url).status_code == 422


def test_missing_history_cursor_and_status_are_safe_404(client):
    assert client.get(f"{RUNS}/987/status").status_code == 404
    assert client.get(RUNS, params={"before_search_run_id": 987}).status_code == 404


@pytest.mark.parametrize("channel", [p.channel_code for p in service.OMNICHANNEL_PROFILE_REGISTRY.values()])
def test_every_available_profile_saves_actual_channel_under_additive_context_contract(client, database_path, channel):
    payload = request_payload()
    profile = service.get_omnichannel_profile_for_channel(channel)
    payload["export_profile"] = profile.export_profile
    payload["context"]["campaign_channel"] = channel
    response = client.post(RUNS, json=payload)
    assert response.status_code == 201, response.text
    row = CampaignResultRegistryRepository(database_path).fetch_search_run(response.json()["search_run_id"])
    with get_connection(database_path) as connection:
        context = connection.execute("SELECT * FROM campaign_targeting_contexts WHERE targeting_context_id=?",
                                     (row["targeting_context_id"],)).fetchone()
    stored = json.loads(context["campaign_context_json"])
    assert stored["campaign_channel"] == channel
    assert stored["campaign_targeting_context_contract_version"] == "PHASE11_1"
    assert context["campaign_targeting_context_contract_version"] == "PHASE11_1"
    assert row["modeling_context_sha256"] == derive_modeling_context_from_campaign_context(payload["context"]).modeling_context_sha256
    if channel not in {"EMAIL", "DIRECT_MAIL"}:
        with pytest.raises(ValidationError): CampaignTargetingContextContract.model_validate(payload["context"])


@pytest.fixture
def form_page(page, client):
    browser, errors, requests = page
    bodies = []
    def api(route):
        request = route.request
        parsed = urlsplit(request.url)
        requests.append((request.method, parsed.path))
        body = request.post_data
        if request.method == "POST": bodies.append(json.loads(body))
        response = client.request(request.method, parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                                  content=body, headers={"Content-Type": "application/json"})
        route.fulfill(status=response.status_code, content_type="application/json", body=response.content)
    # More specific route overrides the static fixture's unavailable API fallback.
    browser.route("**/api/potential-customer-search/**", api)
    open_route(browser, "#find-potential-customers")
    browser.locator("#business-search-form").wait_for(state="visible")
    yield browser, errors, requests, bodies


def choose(browser, field, values):
    # Use public component API in the many-field integration setup. Dedicated Step 7 tests
    # separately cover real checkbox/search/chip and keyboard interaction.
    browser.evaluate("""async ({field, values}) => {
      const {enhanceMultiSelect} = await import('/static/js/components/multi-select-dropdown.js');
      const select = document.querySelector(`#business-${field}`);
      enhanceMultiSelect(select).setValues(values);
      select.dispatchEvent(new Event('change', {bubbles:true}));
    }""", dict(field=field, values=values))


def fill_minimum(browser):
    browser.locator("#business-campaign-name").fill("Savings outreach")
    choose(browser, "product_ids", ["PRD-1"])
    browser.locator("#business-export-profile").select_option(request_payload()["export_profile"])


@pytest.mark.browser
def test_single_business_form_live_options_default_disclosure_and_no_wizard(form_page):
    browser, errors, requests, bodies = form_page
    assert browser.locator("#business-search-form > fieldset > legend").all_text_contents() == [
        "Campaign Details", "Campaign Context", "Targeting Preferences", "Delivery / Download Profile"]
    assert browser.locator("#legacy-campaign-planner-shell").is_hidden()
    assert browser.locator("#business-search-form .multi-select-dropdown").count() == 16
    assert browser.locator("#business-search-form button[type=submit]:visible").all_text_contents() == ["Find Potential Customers"]
    assert browser.locator("#business-more-fields").is_hidden()
    assert browser.locator("#business-target-count").is_disabled()
    assert browser.locator("#business-search-workflow-note").is_hidden()
    assert bodies == [] and errors == []
    assert not any(method != "GET" for method, _ in requests)
    assert all(not path.startswith(("/api/models", "/api/intelligence/prepare", "/api/audience")) for _, path in requests)


@pytest.mark.browser
def test_form_real_submission_exact_preferences_status_history_and_reload(form_page, database_path):
    browser, errors, requests, bodies = form_page
    fill_minimum(browser)
    browser.locator("#business-description").fill("Optional description")
    browser.locator("#business-launch-date").fill("2026-12-01")
    payload = request_payload()
    for field in ("campaign_types", "campaign_categories", "offer_types", "historical_campaign_channels"):
        choose(browser, field, payload["context"][field])
    for field in ("genders", "age_groups", "income_groups"):
        choose(browser, field, payload["criteria"][field])
    choose(browser, "regions", ["SOUTH"])
    choose(browser, "states", ["Ohio", "Texas"])
    browser.locator("input[name=business_match_strength][value=STRONG]").check()
    browser.locator("#business-search-form details summary").click()
    for field in ("marital_statuses", "education_levels", "employment_statuses", "resident_statuses", "resident_types", "employment_types"):
        choose(browser, field, payload["criteria"][field])
    browser.locator("#business-family-min").fill("2")
    browser.locator("#business-family-max").fill("5")
    browser.locator("#business-top-percent").fill("20")
    browser.locator("#business-selection-mode").select_option("TOP_N")
    browser.locator("#business-target-count").fill("250")
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    # The production coordinator is connected under the real app lifespan. This
    # isolated database has no completed import provenance, so it must fail
    # closed with the public safe message rather than remain BLOCKED.
    browser.wait_for_function("document.querySelector('#result-detail-status').textContent.includes('could not be completed')")
    expected = deepcopy(payload)
    expected["criteria"]["match_strength"] = "STRONG"
    expected["criteria"]["states"] = ["Ohio", "Texas"]
    expected["criteria"]["age_groups"] = ["18-24", "35-44"]
    expected["criteria"]["income_groups"] = ["<25K", "50K-74,999"]
    assert bodies == [expected]
    browser.locator("#result-detail-back").click()
    browser.locator("#business-search-history a").wait_for()
    assert browser.locator("#business-search-history h3").inner_text() == "Savings outreach"
    browser.reload(wait_until="networkidle")
    assert browser.locator("#business-search-history a").get_attribute("href") == "#results/1"
    browser.locator("#nav-find-potential-customers").click()
    assert browser.locator("#business-campaign-name").input_value() == "Savings outreach"
    assert browser.locator("#business-target-count").input_value() == "250"
    assert counts(database_path)["campaign_search_runs"] == 1
    assert errors == []


@pytest.mark.browser
@pytest.mark.parametrize("invalid", ["name", "products", "profile", "percent-low", "percent-high", "count", "family"])
def test_form_invalid_inputs_do_not_submit(form_page, invalid):
    browser, errors, _, bodies = form_page
    fill_minimum(browser)
    if invalid == "name": browser.locator("#business-campaign-name").fill("   ")
    if invalid == "products": choose(browser, "product_ids", [])
    if invalid == "profile": browser.locator("#business-export-profile").select_option("")
    if invalid.startswith("percent-"): browser.locator("#business-top-percent").fill("0" if invalid.endswith("low") else "101")
    if invalid == "count":
        browser.locator("#business-selection-mode").select_option("TOP_N")
        browser.locator("#business-target-count").fill("0")
    if invalid == "family":
        browser.locator("#business-search-form details summary").click()
        browser.locator("#business-family-min").fill("5")
        browser.locator("#business-family-max").fill("2")
    browser.locator("#business-search-submit").click()
    assert bodies == [] and browser.evaluate("location.hash") == "#find-potential-customers"
    assert errors == []


@pytest.mark.browser
def test_top_n_reset_region_shortcut_and_profile_edits_do_not_execute(form_page):
    browser, errors, requests, bodies = form_page
    fill_minimum(browser)
    choose(browser, "regions", ["SOUTH"])
    assert browser.locator("#business-states").evaluate("el => [...el.selectedOptions].map(o=>o.value)") == ["Texas"]
    browser.locator("#business-selection-mode").select_option("TOP_N")
    browser.locator("#business-target-count").fill("25")
    browser.locator("#business-selection-mode").select_option("ALL_MATCHING")
    assert browser.locator("#business-target-count").input_value() == ""
    profile = next(p for p in service.OMNICHANNEL_PROFILE_REGISTRY.values() if p.channel_code == "SMS")
    browser.locator("#business-export-profile").select_option(profile.export_profile)
    assert bodies == [] and all(method == "GET" for method, _ in requests)
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    assert bodies[0]["context"]["campaign_channel"] == "SMS"
    assert bodies[0]["criteria"]["target_count"] is None
    assert "regions" not in bodies[0]["criteria"]
    assert errors == []


@pytest.mark.browser
def test_failed_options_can_retry_without_creating_work(page, client):
    browser, errors, requests = page
    attempts = []
    def options(route):
        attempts.append(True)
        if len(attempts) == 1: route.fulfill(status=503, json={"detail": "Unavailable"})
        else: route.fulfill(status=200, json=client.get(OPTIONS).json())
    browser.route("**/api/potential-customer-search/options", options)
    open_route(browser, "#find-potential-customers")
    assert browser.locator("#business-search-error").is_visible()
    assert browser.locator("#business-search-form").is_hidden()
    browser.locator("#business-search-retry").click()
    browser.locator("#business-search-form").wait_for(state="visible")
    assert len(attempts) == 2 and errors == []
    assert all(method == "GET" for method, _ in requests)


@pytest.mark.browser
def test_unavailable_draft_choices_are_explicit_and_prevent_silent_submission(form_page):
    browser, errors, _, bodies = form_page
    fill_minimum(browser)
    browser.evaluate("""() => {
      const key='phase11-business-search-draft-v1'; const draft=JSON.parse(sessionStorage.getItem(key));
      draft.request.context.product_ids=['removed-product']; sessionStorage.setItem(key,JSON.stringify(draft));
    }""")
    browser.reload(wait_until="networkidle")
    browser.locator("#business-search-form").wait_for(state="visible")
    assert browser.locator('#business-product_ids option[value="removed-product"]').is_disabled()
    assert browser.locator("#business-product_ids").evaluate("el => el.selectedOptions[0].value") == "removed-product"
    browser.locator("#business-search-submit").click()
    assert bodies == []
    choose(browser, "product_ids", ["PRD-1"])
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    assert len(bodies) == 1 and errors == []


@pytest.mark.browser
def test_navigation_during_acknowledgement_and_duplicate_submit_lock(form_page, client, database_path):
    browser, errors, requests, bodies = form_page
    fill_minimum(browser)
    pending = []
    def defer(route):
        if route.request.method != "POST": return route.fallback()
        bodies.append(json.loads(route.request.post_data))
        response = client.post(RUNS, json=bodies[-1])
        assert response.status_code == 201
        pending.append((route, response))
    browser.route("**/api/potential-customer-search/runs", defer)
    browser.locator("#business-search-submit").click()
    browser.wait_for_function("document.querySelector('#business-search-submit').disabled")
    # Even programmatic repeated submit events cannot make a second request.
    browser.evaluate("document.querySelector('#business-search-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
    assert len(pending) == 1 and len(bodies) == 1
    assert browser.locator("#business-search-form > fieldset").evaluate_all("els=>els.every(el=>el.disabled)")
    browser.locator("#nav-results").click()
    browser.locator("#business-search-history a").wait_for()
    route, response = pending[0]
    route.fulfill(status=201, content_type="application/json", body=response.content)
    browser.wait_for_function("!document.querySelector('#business-search-submit').disabled")
    assert browser.evaluate("location.hash") == "#results"
    assert counts(database_path)["campaign_search_runs"] == 1
    assert errors == []


@pytest.mark.browser
def test_corrected_custom_errors_and_intentional_new_submission(form_page, database_path):
    browser, errors, _, bodies = form_page
    fill_minimum(browser)
    browser.locator("#business-campaign-name").fill("   ")
    browser.locator("#business-search-submit").click()
    assert bodies == []
    browser.locator("#business-campaign-name").fill("Corrected name")
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    browser.locator("#nav-find-potential-customers").click()
    browser.locator("#business-campaign-name").fill("Intentional second search")
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/2")
    assert len(bodies) == 2 and counts(database_path)["campaign_targeting_contexts"] == 2
    assert errors == []


@pytest.mark.browser
def test_unavailable_profiles_hidden_by_default_and_empty_products_disable_action(page, client):
    browser, errors, _ = page
    payload = client.get(OPTIONS).json()
    payload["profiles"][0].update(availability="BLOCKED", unavailable_reason="Missing identifiers")
    payload["context"]["products"] = []
    browser.route("**/api/potential-customer-search/options", lambda route: route.fulfill(status=200, json=payload))
    open_route(browser, "#find-potential-customers")
    browser.locator("#business-search-form").wait_for(state="visible")
    assert browser.locator("#business-export-profile option").count() == 10  # placeholder + 9 AVAILABLE
    assert browser.locator("#business-search-submit").is_disabled()
    assert browser.locator("#business-search-error-message").inner_text().startswith("No products")
    assert errors == []


@pytest.mark.browser
@pytest.mark.parametrize("width", [390, 1280])
def test_single_form_fits_mobile_and_desktop(form_page, width):
    browser, errors, _, _ = form_page
    browser.set_viewport_size(dict(width=width, height=900))
    browser.locator("#business-search-form details summary").click()
    assert browser.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
