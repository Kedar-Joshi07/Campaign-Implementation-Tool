"""Step 12: bounded business result history and no-contact-PII detail UI."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services import potential_customer_search_submission_service as submission
from app.services.phase10_context_identity_service import (
    derive_modeling_context_from_campaign_context,
)
from app.services.phase11_result_snapshot_service import materialize_result_snapshot
from tests.test_phase10_schema_registry_repository import _generation_values, _seed_lineage
from tests.test_phase11_business_navigation import browser_session, open_route, page
from tests.test_phase11_business_search_form import (
    RUNS,
    client,
    database_path,
    request_payload,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = "/api/potential-customer-search/results"
PROHIBITED = {
    "first_name", "last_name", "name", "email", "phone", "phone_number",
    "address", "address_line_1", "address_line_2", "street", "postal_code",
    "push_token", "advertising_id", "web_visitor_id", "storage_uri",
}


def _keys(value):
    if isinstance(value, dict):
        yield from (str(key).lower() for key in value)
        for nested in value.values():
            yield from _keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _keys(nested)


def test_result_api_is_additive_newest_first_bounded_and_preserves_each_submission(
    client, database_path, monkeypatch,
):
    # This compatibility test owns immutable submission/history projection rather
    # than production execution. Keep both submissions queued so asynchronous
    # coordinator completion cannot race the byte-for-field status assertion.
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)
    first_payload = request_payload()
    first = client.post(RUNS, json=first_payload).json()
    second_payload = deepcopy(first_payload)
    second_payload["campaign_name"] = "Second intentional submission"
    second = client.post(RUNS, json=second_payload).json()

    # Lifecycle recovery metadata is additive and stable across create/list/status.
    assert client.get(RUNS).json() == [second, first]
    assert set(first) == {
        "search_run_id", "campaign_name", "status", "created_at", "completed_at",
        "selected_count", "delivery_channel", "export_profile", "safe_message",
        "selection_contract_version", "attempt_number", "queue_position",
        "propensity_bucket", "progress", "issue", "retry_eligible",
    }

    bulk_queue_calls: list[list[int]] = []
    real_queue_positions = CampaignResultRegistryRepository.queue_positions

    def record_bulk_queue_positions(repository, identifiers):
        bulk_queue_calls.append(list(identifiers))
        return real_queue_positions(repository, identifiers)

    def forbid_single_queue_position(*_args, **_kwargs):
        raise AssertionError("Result history must use the bulk queue-position projection.")

    monkeypatch.setattr(
        CampaignResultRegistryRepository,
        "queue_positions",
        record_bulk_queue_positions,
    )
    monkeypatch.setattr(
        CampaignResultRegistryRepository,
        "queue_position",
        forbid_single_queue_position,
    )

    response = client.get(RESULTS)
    assert response.status_code == 200, response.text
    history = response.json()
    assert [row["search_run_id"] for row in history] == [
        second["search_run_id"], first["search_run_id"],
    ]
    assert history[0]["campaign_name"] == "Second intentional submission"
    assert history[0]["selected_products"] == [{
        "product_id": "PRD-1", "product_name": "Savings", "product_category": "Banking",
    }]
    assert history[0]["campaign_types"] == ["Retention"]
    assert history[0]["campaign_categories"] == ["Lifecycle"]
    assert history[0]["offer_types"] == ["Loyalty"]
    assert history[0]["match_strength"] == "STRONG"
    assert history[0]["status"] == "QUEUED"
    assert history[0]["result_source_label"] == "Not available until completion"
    assert history[0]["currentness"] == "NOT_AVAILABLE"
    assert history[0]["download_eligible"] is False
    assert history[0]["safe_message"] == (
        "Saved and waiting to prepare targeting intelligence."
    )
    assert history[0]["progress"]["lifecycle_status"] == "QUEUED"
    assert history[0]["progress"]["progress_percent"] == 0
    assert history[0]["progress"]["estimate_confidence"] == "UNAVAILABLE"
    assert history[0]["issue"] is None
    assert not PROHIBITED.intersection(_keys(history))

    page_one = client.get(RESULTS, params={"limit": 1}).json()
    assert [row["search_run_id"] for row in page_one] == [second["search_run_id"]]
    page_two = client.get(
        RESULTS,
        params={"limit": 1, "before_search_run_id": second["search_run_id"]},
    ).json()
    assert [row["search_run_id"] for row in page_two] == [first["search_run_id"]]
    assert client.get(RESULTS, params={"limit": 101}).status_code == 422
    assert client.get(RESULTS, params={"before_search_run_id": 987654}).status_code == 404
    assert bulk_queue_calls == [
        [second["search_run_id"], first["search_run_id"]],
        [second["search_run_id"]],
        [first["search_run_id"]],
    ]


def test_result_source_business_labels_are_exact():
    from app.services.phase11_results_service import RESULT_SOURCE_LABELS

    assert RESULT_SOURCE_LABELS == {
        "EXACT_RESULT_REUSE": "Reused previous exact result",
        "INTELLIGENCE_REUSE": "Reused existing targeting intelligence",
        "NEW_INTELLIGENCE_BUILD": "Prepared new targeting intelligence",
    }


def test_result_detail_reopens_exact_saved_context_criteria_selection_and_safe_errors(
    client,
):
    payload = request_payload()
    status = client.post(RUNS, json=payload).json()
    response = client.get(f'{RUNS}/{status["search_run_id"]}/result')
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["campaign_context"] == payload["context"] | {
        "campaign_targeting_context_contract_version": "PHASE11_1",
    }
    assert detail["targeting_criteria"]["match_strength"] == "STRONG"
    assert detail["targeting_criteria"]["states"] == ["Ohio", "Texas"]
    assert len(detail["filter_branches"]) == 4
    assert detail["selection"] == {
        "mode": "TOP_N", "target_count": 250, "resolved_count": None,
    }
    assert detail["snapshot_provenance"] is None
    assert detail["score_summary"] is None
    assert detail["download_eligible"] is False
    assert not PROHIBITED.intersection(_keys(detail))
    assert client.get(f"{RUNS}/987654/result").status_code == 404
    assert client.get(f"{RUNS}/0/result").status_code == 422


def test_completed_result_detail_validates_materialized_snapshot_and_lineage(
    client, database_path, tmp_path, monkeypatch,
):
    # Keep submission queued so this test can attach a real, isolated snapshot.
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)
    payload = request_payload()
    created = client.post(RUNS, json=payload).json()
    run_id = created["search_run_id"]
    repository = CampaignResultRegistryRepository(database_path)
    run = repository.fetch_search_run(run_id)

    ids = _seed_lineage(database_path)
    values = _generation_values(ids)
    identity = derive_modeling_context_from_campaign_context(payload["context"])
    values["modeling_context_json"] = identity.canonical_json
    values["modeling_context_sha256"] = identity.modeling_context_sha256
    generation_id = Phase10IntelligenceRepository(database_path).insert_ready_generation(values)
    generation = Phase10IntelligenceRepository(database_path).fetch_generation(generation_id)
    cache_key = "d" * 64
    members = [
        {"person_id": "P-1", "propensity_score": 0.9, "percentile_bucket": 1,
         "decile": 1, "rank_band": "ELITE"},
        {"person_id": "P-2", "propensity_score": 0.7, "percentile_bucket": 2,
         "decile": 1, "rank_band": "VERY_HIGH"},
    ]
    snapshot_id = materialize_result_snapshot(
        database_path, run, generation, cache_key, None, members,
        project_root=tmp_path,
    )
    repository.mark_processing(run_id)
    repository.complete_search_run(
        run_id, result_snapshot_id=snapshot_id,
        result_source="INTELLIGENCE_REUSE",
    )

    # The API validates artifacts relative to the application root. Exercise the
    # service with the isolated root, while API coverage above owns HTTP projection.
    from app.services.phase11_results_service import get_result_detail

    detail = get_result_detail(database_path, run_id, project_root=tmp_path)
    assert detail["status"] == "COMPLETED"
    assert detail["selected_count"] == 2
    assert detail["result_source_label"] == "Reused existing targeting intelligence"
    assert detail["result_source_explanation"] == "Reused existing targeting intelligence"
    assert detail["currentness"] == "CURRENT"
    # Step 13 activates the governed engine only for completed, current results.
    assert detail["download_eligible"] is True
    assert detail["snapshot_provenance"]["result_snapshot_id"] == snapshot_id
    assert detail["snapshot_provenance"]["resolved_count"] == 2
    assert detail["score_summary"] == {
        "scope": "Scored potential-customer universe", "population_count": 1,
        "minimum": 0.5, "maximum": 0.5, "mean": 0.5,
    }
    assert not PROHIBITED.intersection(_keys(detail))


def _history_item(run_id, *, status="COMPLETED", name=None, eligible=False):
    progress_percent = {
        "QUEUED": 0, "PROCESSING": 68, "COMPLETED": 100,
        "BLOCKED": 22, "FAILED": 54,
    }[status]
    issue = None
    if status in {"BLOCKED", "FAILED"}:
        issue = {
            "code": "FIXTURE_BLOCKED" if status == "BLOCKED" else "FIXTURE_FAILED",
            "category": "TARGETING_INTELLIGENCE" if status == "BLOCKED" else "PROCESSING_FAILURE",
            "summary": "More verified campaign history is required." if status == "BLOCKED" else "The governed result could not be prepared.",
            "resolution_steps": ["Review the saved criteria.", "Submit again after correcting the condition."],
            "retryable": True,
            "affected_stage": "CHECKING_INTELLIGENCE",
            "technical_reference": "FIXTURE-BLOCKED-001",
            "user_action_required": status == "BLOCKED",
        }
    return {
        "search_run_id": run_id,
        "campaign_name": name or f"Campaign {run_id}",
        "created_at": f"2026-09-16T10:00:{run_id:02d}Z",
        "completed_at": None if status in {"QUEUED", "PROCESSING"} else "2026-09-16T10:01:00Z",
        "status": status,
        "selected_products": [{"product_id": "PRD-1", "product_name": "Savings", "product_category": "Banking"}],
        "campaign_types": ["Retention"], "campaign_categories": ["Lifecycle"],
        "offer_types": ["Loyalty"], "delivery_channel": "EMAIL",
        "export_profile": "EMAIL_CONTACT_V1", "delivery_profile_label": "Email",
        "match_strength": "STRONG", "targeting_summary": ["State: Ohio, Texas"],
        "selected_count": 125 if status == "COMPLETED" else None,
        "result_source": "EXACT_RESULT_REUSE" if status == "COMPLETED" else None,
        "result_source_label": "Reused previous exact result" if status == "COMPLETED" else "Not available until completion",
        "processing_seconds": 3.25 if status == "COMPLETED" else None,
        "currentness": "CURRENT" if status == "COMPLETED" else "NOT_AVAILABLE",
        "download_eligible": eligible,
        "safe_message": "Potential-customer results are ready." if status == "COMPLETED" else "Preparing potential-customer results.",
        "progress": {
            "contract_version": "1", "lifecycle_status": status,
            "stage_code": status, "stage_label": "Matching potential customers" if status == "PROCESSING" else status.title(),
            "progress_percent": progress_percent,
            "processed_count": 340 if status == "PROCESSING" else (125 if status == "COMPLETED" else 0),
            "total_count": 500 if status == "PROCESSING" else (125 if status == "COMPLETED" else None),
            "progress_unit": "potential customers",
            "status_message": "Matching the ranked potential-customer universe." if status == "PROCESSING" else "Saved lifecycle state.",
            "updated_at": "2026-09-16T10:00:30Z", "heartbeat_at": None,
            "state_version": 3,
            "estimated_seconds_remaining_low": 30 if status == "PROCESSING" else (0 if status == "COMPLETED" else None),
            "estimated_seconds_remaining_high": 90 if status == "PROCESSING" else (0 if status == "COMPLETED" else None),
            "estimated_completion_at": "2026-09-16T10:02:00Z" if status == "PROCESSING" else None,
            "estimate_confidence": "MEDIUM" if status == "PROCESSING" else ("HIGH" if status == "COMPLETED" else "UNAVAILABLE"),
            "estimate_basis": "CURRENT_RUN_OBSERVED_RATE" if status == "PROCESSING" else ("COMPLETED" if status == "COMPLETED" else "NOT_APPLICABLE"),
        },
        "issue": issue,
    }


def _detail_payload(run_id=42, *, status="COMPLETED"):
    return _history_item(run_id, name="Autumn savings", status=status) | {
        "description": "Retention campaign", "planned_launch_date": "2026-10-01",
        "campaign_context": {
            "product_ids": ["PRD-1"], "campaign_types": ["Retention"],
            "campaign_categories": ["Lifecycle"], "offer_types": ["Loyalty"],
            "campaign_channel": "EMAIL", "historical_campaign_channels": ["Email"],
            "campaign_targeting_context_contract_version": "PHASE11_1",
        },
        "targeting_criteria": {
            "match_strength": "STRONG", "genders": ["Female"],
            "age_groups": ["18-24"], "states": ["Ohio"], "income_groups": ["<25K"],
            "marital_statuses": [], "education_levels": [], "employment_statuses": [],
            "resident_statuses": [], "resident_types": [], "employment_types": [],
            "family_member_count_min": None, "family_member_count_max": None,
            "top_matching_percent": None, "selection_mode": "ALL_MATCHING",
            "target_count": None, "targeting_segment_contract_version": "1",
            "business_match_strength_contract_version": "1",
        },
        "filter_branches": [{"state": ["Ohio"]}],
        "selection": {"mode": "ALL_MATCHING", "target_count": None, "resolved_count": 125},
        "result_source_explanation": "Reused previous exact result",
        "score_summary": {"scope": "Scored potential-customer universe", "population_count": 500,
                          "minimum": 0.1, "maximum": 0.95, "mean": 0.55},
        "demographic_summary": {"genders": ["Female"], "age_groups": ["18-24"],
                                "states": ["Ohio"], "income_groups": ["<25K"]},
        "snapshot_provenance": {"result_snapshot_id": 9, "resolved_count": 125,
                                "currentness": "CURRENT"},
        "technical_details": {"targeting_context_id": 4, "generation_id": 3,
                              "targeting_criteria_sha256": "a" * 64},
    }


@pytest.mark.browser
def test_results_history_renders_deduplicates_paginates_and_only_polls_active(page):
    browser, errors, _requests = page
    calls = []

    def history(route):
        parsed = urlsplit(route.request.url)
        query = parse_qs(parsed.query)
        calls.append(query)
        if "before_search_run_id" in query:
            payload = [_history_item(2, name="Older result")]
        elif len(calls) == 1:
            payload = [
                _history_item(22, status="PROCESSING"),
                _history_item(21, status="BLOCKED"),
                _history_item(20, status="FAILED"),
            ] + [
                _history_item(run_id, eligible=run_id == 19)
                for run_id in range(19, 2, -1)
            ]
        else:
            # Overlap proves the client map does not append duplicate cards.
            payload = [
                _history_item(22, status="COMPLETED"),
                _history_item(21, status="BLOCKED"),
                _history_item(20, status="FAILED"),
            ] + [
                _history_item(run_id, eligible=run_id == 19)
                for run_id in range(19, 2, -1)
            ]
        route.fulfill(status=200, json=payload)

    browser.route("**/api/potential-customer-search/results?*", history)
    open_route(browser, "#results")
    browser.locator(".result-card").first.wait_for()
    assert browser.locator(".result-card").count() == 20
    assert browser.locator(".result-card").all_text_contents()[0].startswith("Search #22")
    assert browser.locator('[data-search-run-id="22"]').get_by_text(
        "Preparing potential-customer results.", exact=True,
    ).is_visible()
    active = browser.locator('[data-search-run-id="22"]')
    assert active.locator('[role="progressbar"]').get_attribute("aria-valuenow") == "68"
    assert active.get_by_text("Matching potential customers", exact=True).is_visible()
    assert active.get_by_text("340 of 500 potential customers processed", exact=True).is_visible()
    assert active.get_by_text("Approximately 30 sec to 2 min remaining", exact=True).is_visible()
    assert browser.locator('[data-search-run-id="21"] [data-status="BLOCKED"]').is_visible()
    assert browser.locator('[data-search-run-id="21"]').get_by_text(
        "Why this search is blocked", exact=True,
    ).is_visible()
    assert browser.locator('[data-search-run-id="21"]').get_by_role(
        "button", name="Retry Search",
    ).is_visible()
    assert browser.locator('[data-search-run-id="20"] [data-status="FAILED"]').is_visible()
    assert browser.locator('[data-search-run-id="20"]').get_by_role(
        "button", name="Retry Search",
    ).is_visible()
    assert browser.locator('[data-search-run-id="19"]').get_by_role(
        "link", name="Run Again",
    ).is_visible()
    assert browser.locator('[data-search-run-id="19"] a[download]').get_attribute("href") == "/api/potential-customer-search/runs/19/download"
    browser.wait_for_timeout(5200)
    assert len(calls) >= 2
    assert browser.locator(".result-card").count() == 20
    assert browser.locator('[data-search-run-id="22"] [data-status="COMPLETED"]').is_visible()
    browser.locator("#business-history-more").click()
    browser.get_by_text("Older result", exact=True).wait_for()
    assert browser.locator(".result-card").count() == 21
    assert "before_search_run_id" in calls[-1]
    assert errors == []


@pytest.mark.browser
def test_result_detail_pauses_and_resumes_bounded_live_updates(page):
    browser, errors, _requests = page
    calls = []
    browser.add_init_script(
        """
        (() => {
          const nativeSetTimeout = window.setTimeout.bind(window);
          window.setTimeout = (callback, delay, ...args) =>
            nativeSetTimeout(callback, delay === 5000 ? 1 : delay, ...args);
        })();
        """
    )

    def active_detail(route):
        calls.append(route.request.url)
        route.fulfill(status=200, json=_detail_payload(status="PROCESSING"))

    browser.route(
        "**/api/potential-customer-search/runs/42/result",
        active_detail,
    )
    open_route(browser, "#results/42")
    resume = browser.get_by_role("button", name="Resume Updates")
    resume.wait_for(timeout=10_000)
    first_cycle_calls = len(calls)
    assert first_cycle_calls >= 61
    assert "Live updates paused" in browser.locator("#result-detail-status").inner_text()

    resume.click()
    resume.wait_for(timeout=10_000)
    assert len(calls) >= first_cycle_calls + 61
    assert errors == []


@pytest.mark.browser
def test_result_detail_uploads_csv_and_json_feedback_with_governed_headers(page):
    browser, errors, _requests = page
    uploads = []
    browser.route(
        "**/api/potential-customer-search/runs/42/result",
        lambda route: route.fulfill(status=200, json=_detail_payload()),
    )

    def accept_feedback(route):
        uploads.append({
            "headers": route.request.headers,
            "body": route.request.post_data or "",
        })
        route.fulfill(
            status=201,
            json={
                "feedback_batch_id": len(uploads),
                "search_run_id": 42,
                "attempt_number": 1,
                "source_name": "browser-test",
                "row_count": 2 if len(uploads) == 1 else 1,
                "positive_count": 1,
                "negative_count": 1 if len(uploads) == 1 else 0,
                "status": "ACCEPTED",
                "created_at": "2026-09-28T10:00:00Z",
                "retraining_status": "WAITING_FOR_DATA",
                "retraining_reason": "Waiting for governed feedback.",
            },
        )

    browser.route(
        "**/api/potential-customer-search/runs/42/feedback",
        accept_feedback,
    )
    open_route(browser, "#results/42")
    feedback_file = browser.locator("#result-feedback-file")

    feedback_file.set_input_files({
        "name": "feedback.csv",
        "mimeType": "text/csv",
        "buffer": (
            b"person_id,outcome,outcome_at,outcome_value\n"
            b"P-1,1,2026-09-27T10:00:00Z,10\n"
            b"P-2,0,2026-09-27T10:00:00Z,\n"
        ),
    })
    browser.locator("#result-feedback-upload").click()
    browser.wait_for_timeout(1_000)
    feedback_status = browser.locator("#result-feedback-status").inner_text()
    assert uploads, feedback_status
    assert "2 outcomes accepted." in feedback_status

    feedback_file.set_input_files({
        "name": "feedback.json",
        "mimeType": "application/json",
        "buffer": (
            b'{"source_name":"browser-test","rows":['
            b'{"person_id":"P-3","outcome":1,'
            b'"outcome_at":"2026-09-27T10:00:00Z"}]}'
        ),
    })
    browser.locator("#result-feedback-upload").click()
    browser.wait_for_timeout(1_000)
    assert "1 outcomes accepted." in browser.locator("#result-feedback-status").inner_text()

    assert len(uploads) == 2
    assert uploads[0]["headers"]["content-type"] == "text/csv"
    assert uploads[1]["headers"]["content-type"] == "application/json"
    assert all(item["headers"]["idempotency-key"].startswith("browser-feedback-42-") for item in uploads)
    assert "person_id,outcome,outcome_at,outcome_value" in uploads[0]["body"]
    assert '"rows"' in uploads[1]["body"]
    assert errors == []


@pytest.mark.browser
def test_result_detail_is_responsive_progressively_disclosed_and_has_no_contact_pii(page):
    browser, errors, _requests = page
    browser.route(
        "**/api/potential-customer-search/runs/42/result",
        lambda route: route.fulfill(status=200, json=_detail_payload()),
    )
    browser.set_viewport_size({"width": 390, "height": 844})
    open_route(browser, "#results/42")
    browser.get_by_text("Autumn savings", exact=True).wait_for()
    assert browser.locator("#result-detail-progress [role='progressbar']").get_attribute("aria-valuenow") == "100"
    assert browser.locator("#result-detail-refresh").is_visible()
    assert browser.get_by_text("Reused previous exact result", exact=True).is_visible()
    assert browser.get_by_text("Contact information is never shown here.", exact=False).is_visible()
    assert browser.locator("#result-technical-disclosure").get_attribute("open") is None
    assert browser.locator("#result-detail-download").is_hidden()
    assert browser.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    visible = browser.locator("#result-detail-view").inner_text().lower()
    assert not {"first name", "last name", "phone number", "postal code"}.intersection(
        phrase for phrase in ("first name", "last name", "phone number", "postal code")
        if phrase in visible
    )
    browser.locator("#result-technical-disclosure summary").click()
    assert "TARGETING CONTEXT ID" in browser.locator("#result-technical-details").inner_text()
    assert errors == []


def test_step12_frontend_uses_bounded_active_only_refresh_and_safe_dom_rendering():
    source = (ROOT / "frontend/js/business-search-status.js").read_text(encoding="utf-8")
    assert "RESULT_REFRESH_INTERVAL_MS = 5000" in source
    assert "RESULT_REFRESH_MAX_CYCLES = 60" in source
    assert "isRunActive" in source
    progress_source = (ROOT / "frontend/js/run-progress.js").read_text(encoding="utf-8")
    assert '"QUEUED", "PROCESSING", "PAUSE_REQUESTED", "PAUSED"' in progress_source
    assert "new Map()" in source and "rows.set(run.search_run_id, run)" in source
    assert "before_search_run_id" in source
    assert "textContent" in source and ".innerHTML" not in source
    assert "Resume Updates" in source
    assert "refreshCycles >= RESULT_REFRESH_MAX_CYCLES" in source
    assert "crypto.getRandomValues" in source
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    for identifier in (
        "business-search-history", "business-history-more", "result-detail-overview",
        "result-targeting-details", "result-provenance-details", "result-technical-disclosure",
        "result-feedback-csv-template", "result-feedback-json-template",
        "result-feedback-format-guide",
    ):
        assert f'id="{identifier}"' in html
    assert "/api/potential-customer-search/feedback-template.csv" in html
    assert "/api/potential-customer-search/feedback-template.json" in html
    assert "Idempotency-Key" in html
    assert "Purchase outcome CSV or JSON" in html
    assert '"application/json"' in source
