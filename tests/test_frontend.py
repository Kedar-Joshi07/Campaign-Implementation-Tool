from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "frontend.db"
    initialize_database(database_path)
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_frontend_contains_functional_phase_one_views(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'data-view="overview"' in response.text
    assert 'data-view="data-status"' in response.text
    assert "Historical customers" in response.text
    assert "Recent runs" in response.text
    assert "Campaign readiness, grounded in real data." in response.text
    assert response.text.count('data-field="policy"') == 3
    assert "125,000" not in response.text
    assert "5,000,000" not in response.text


@pytest.mark.parametrize(
    "asset_path",
    (
        "/static/css/main.css",
        "/static/css/components.css",
        "/static/js/api.js",
        "/static/js/ui.js",
        "/static/js/overview.js",
        "/static/js/historical-overview.js",
        "/static/js/historical-analysis.js",
        "/static/js/model-training.js",
        "/static/js/audience-explorer.js",
        "/static/js/data-status.js",
        "/static/js/app.js",
    ),
)
def test_frontend_assets_are_served(client: TestClient, asset_path: str) -> None:
    response = client.get(asset_path)

    assert response.status_code == 200
    assert response.text


def test_later_phase_navigation_is_visibly_disabled(client: TestClient) -> None:
    html = client.get("/").text

    assert html.count('class="navigation-item is-disabled"') == 1
    assert html.count("Later phase</small>") == 1
    assert 'data-view-target="model-training"' in html
    assert 'data-view-target="audience-explorer"' in html
    assert "Phase 4</small>" in html
    assert "Phase 6</small>" in html
    assert "Model Training" in html
    assert "Audience Explorer" in html
    assert "Campaigns" in html


def test_historical_analysis_navigation_and_workspace_are_enabled(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert html.count('data-view-target="historical-analysis"') == 2
    assert 'id="historical-analysis-cta"' in html
    assert "Analyze historical campaigns" in html
    assert 'data-view="historical-analysis"' in html
    assert 'id="historical-analysis-form"' in html
    assert "Analyze Population" in html
    assert "Recent Analyses" in html


def test_historical_overview_has_three_accessible_visuals_and_all_states(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert html.count('class="historical-chart-card"') == 3
    assert 'id="historical-overview-loading"' in html
    assert 'id="historical-overview-empty"' in html
    assert 'id="historical-overview-unavailable"' in html
    assert 'id="historical-monthly-data" class="visually-hidden"' in html
    assert "Monthly attributed purchases" in html
    assert "Campaign channel performance" in html
    assert "Product-category performance" in html
    assert 'id="overview-retry"' in html


def test_historical_overview_script_uses_api_cache_and_safe_dom_rendering(
    client: TestClient,
) -> None:
    historical_script = client.get("/static/js/historical-overview.js").text
    overview_script = client.get("/static/js/overview.js").text

    assert 'import { getCachedJSON } from "./api.js"' in historical_script
    assert 'getCachedJSON("/api/historical/overview"' in historical_script
    assert "loadHistoricalOverview(force)" in overview_script
    assert "textContent" in historical_script
    assert "document.createElement" in historical_script
    assert "document.createElementNS" in historical_script
    assert "replaceChildren" in historical_script
    assert "innerHTML" not in historical_script
    assert "Unknown/Other" in historical_script
    assert "setVisibility({ loading: true })" in historical_script
    assert "setVisibility({ empty: true })" in historical_script
    assert "setVisibility({ unavailable: true })" in historical_script
    assert "570000" not in historical_script
    assert "34273" not in historical_script


def test_overview_retry_restores_global_backend_status_after_success(
    client: TestClient,
) -> None:
    overview_script = client.get("/static/js/overview.js").text

    assert 'querySelector("#overview-retry")' in overview_script
    assert "loadOverview(true)" in overview_script
    assert 'state: "is-offline"' in overview_script
    assert 'state: "is-online"' in overview_script
    assert "hideError(errorBanner)" in overview_script


def test_data_status_script_renders_exact_and_approximate_policy_labels(
    client: TestClient,
) -> None:
    script = client.get("/static/js/data-status.js").text

    assert 'return "Exact target"' in script
    assert "Approximate target (±${displayTolerance}%)" in script
    assert "dataset.count_tolerance_percent" in script
    assert "125,000" not in script
    assert "5,000,000" not in script


def test_model_training_workspace_contains_required_sections_and_controls(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert 'data-view="model-training"' in html
    for control_id in (
        "source-analysis-select",
        "model-name-input",
        "random-seed-input",
        "validation-fraction-input",
        "run-elkan-challenger-input",
        "train-model-submit",
        "model-training-refresh",
        "model-training-retry",
        "recent-model-runs-refresh",
        "candidate-comparison-body",
        "prospect-scoring-panel",
        "score-prospect-submit",
        "scoring-model-run-id",
        "scoring-selected-primary",
        "scoring-artifact-compatibility",
        "scoring-demographic-count",
        "scoring-availability",
        "scoring-completed-run",
        "scoring-announcement",
        "scoring-completed-summary",
        "scoring-summary-scored-count",
        "scoring-summary-runtime",
    ):
        assert f'id="{control_id}"' in html
    assert "Train Look-alike Model" in html
    assert "Score Prospect Universe" in html
    assert "Completion aggregate" in html
    assert "Reconciliation" in html
    assert "Rows per second" in html
    assert "PU Bagging + Logistic Regression" in html
    assert "Elkan-Noto + Logistic Regression" in html
    assert "Naive Logistic Regression" in html
    assert "Active Compute Job / Progress" in html
    assert "No active compute job." in html
    assert "Propensity scores are relative look-alike affinity scores, not guaranteed purchase probabilities." in html
    assert "DIAGNOSTIC Naive is diagnostic-only and non-selection-eligible." in html
    assert "Challenger exceeded the primary on one or more validation diagnostics." in html


def test_model_training_script_uses_expected_endpoints_and_polling_contract(
    client: TestClient,
) -> None:
    script = client.get("/static/js/model-training.js").text

    assert 'getCachedJSON(API_PATHS.options' in script
    assert 'API_PATHS.options = "/api/models/training-options"' not in script
    assert 'options: "/api/models/training-options"' in script
    assert 'submit: "/api/models/train"' in script
    assert 'models: "/api/models?limit=20&offset=0"' in script
    assert 'jobDetail: (jobId) => `/api/jobs/${jobId}`' in script
    assert 'analysisDetail: (analysisRunId) => `/api/historical/analyses/${analysisRunId}`' in script
    assert 'scoringStatus: (modelRunId) => `/api/models/${modelRunId}/scoring-status`' in script
    assert 'scoringSubmit: (modelRunId) => `/api/models/${modelRunId}/score`' in script
    assert 'scoringRunDetail: (scoringRunId) => `/api/scoring-runs/${scoringRunId}`' in script
    assert "window.setTimeout" in script
    assert "POLL_INTERVAL_MS = 1500" in script
    assert 'TERMINAL_JOB_STATUSES = new Set(["COMPLETED", "FAILED"])' in script
    assert "if (TERMINAL_JOB_STATUSES.has(job.status))" in script
    assert "loadScoringStatus(modelRunId, { force: true })" in script
    assert "loadScoringRunDetail" in script
    assert 'querySelector("#score-prospect-submit").addEventListener("click", submitScoring)' in script
    assert "clearPolling();" in script


def test_model_training_script_handles_active_job_failure_advisory_and_safety(
    client: TestClient,
) -> None:
    script = client.get("/static/js/model-training.js").text
    html = client.get("/").text

    assert "trainSubmit.disabled = trainingDisabled" in script
    assert "scoreSubmit.disabled = scoreDisabled" in script
    assert "statusSnapshot?.demographic_source_verified === true" in script
    assert "statusSnapshot?.demographic_source_verified === false" in script
    assert "scoreSubmit.hidden = hasCompletedScoring && scoringPanelVisible" in script
    assert "Training is unavailable while job #" in script
    assert "Scoring is unavailable while job #" in script
    assert "A completed scoring run already exists for the current demographics source." in script
    assert "Historical scoring exists for a previous demographics source. Rescoring is available." in script
    assert "if (status.demographic_source_verified && status.completed_scoring_run?.scoring_run_id)" in script
    assert "Model training failed safely." in script
    assert "Prospect scoring failed safely." in script
    assert "CHALLENGER_OUTPERFORMED_PRIMARY" in script
    assert "diagnostic-only and non-selection-eligible" in html
    assert "textContent" in script
    assert "document.createElement" in script
    assert "replaceChildren" in script
    assert "innerHTML" not in script
    assert "person_id" not in script
    assert "propensity_scores" not in script
    assert "audience export" not in script.casefold()
    assert "csv export" not in script.casefold()


def test_audience_explorer_workspace_contains_required_sections_and_controls(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert 'data-view="audience-explorer"' in html
    assert 'data-view-target="audience-explorer"' in html
    for control_id in (
        "audience-explorer-refresh",
        "audience-explorer-retry",
        "audience-prepare-submit",
        "audience-prepare-retry",
        "audience-filter-form",
        "audience-apply-filters",
        "audience-filter-reset",
        "audience-clear-filter-chips",
        "audience-selection-all",
        "audience-selection-topn",
        "audience-target-count",
        "audience-estimate-matching",
        "audience-estimate-selected",
        "audience-results-body",
        "audience-load-more",
        "audience-profile-dimension",
        "audience-profile-bars",
        "audience-traits-body",
        "audience-save-form",
        "audience-save-name",
        "audience-save-description",
        "audience-save-submit",
        "saved-audience-list",
        "saved-audience-detail",
        "saved-audience-reopen",
        "saved-audience-use-campaign",
    ):
        assert f'id="{control_id}"' in html

    assert "Prepare Audience Explorer" in html
    assert "Selected vs Universe" in html
    assert "Selected vs Historical Positives" in html
    assert "Aggregate demographic comparison only. No prospect is matched to a historical customer." in html
    assert "Percentile 1 = top 1%. Decile 1 = top 10%. Propensity score is a relative model affinity score, not a purchase probability." in html
    assert "Use in Campaign - Phase 7" in html
    assert "No names/email/phone/address/city/postal/ethnicity/religion" not in html


def test_audience_explorer_script_uses_required_endpoints_and_state_contracts(
    client: TestClient,
) -> None:
    script = client.get("/static/js/audience-explorer.js").text

    assert 'runs: "/api/audience/runs?limit=20&offset=0"' in script
    assert 'options: (scoringRunId) => `/api/audience/options?scoring_run_id=${scoringRunId}`' in script
    assert 'prepare: (scoringRunId) => `/api/audience/runs/${scoringRunId}/prepare`' in script
    assert 'preparationStatus: (scoringRunId) => `/api/audience/runs/${scoringRunId}/preparation-status`' in script
    assert 'estimate: "/api/audience/estimate"' in script
    assert 'search: "/api/audience/search"' in script
    assert 'profile: "/api/audience/profile"' in script
    assert 'audiences: "/api/audiences?limit=20&offset=0"' in script
    assert 'createAudience: "/api/audiences"' in script
    assert 'audienceDetail: (audienceId) => `/api/audiences/${audienceId}`' in script
    assert "setScreenState(\"loading\")" in script
    assert "setScreenState(\"noRun\")" in script
    assert "setScreenState(\"prepNeeded\")" in script
    assert "setScreenState(\"prepRunning\")" in script
    assert "setScreenState(\"prepFailed\")" in script
    assert "setScreenState(\"workspace\")" in script
    assert "POLL_INTERVAL_MS = 1500" in script
    assert "window.setTimeout" in script
    assert "ready_for_current_audience_actions" in script
    assert "runs.find((run) => run?.ready_for_current_audience_actions === true)" in script
    assert "run?.is_canonical === true" in script
    assert 'querySelector("#audience-load-more").addEventListener("click"' in script
    assert 'querySelector("#audience-save-form").addEventListener("submit", submitSaveAudience)' in script


def test_audience_explorer_script_enforces_safe_fields_and_dom_patterns(
    client: TestClient,
) -> None:
    script = client.get("/static/js/audience-explorer.js").text
    html = client.get("/").text
    combined = f"{script}\n{html}".casefold()

    assert "textContent" in script
    assert "document.createElement" in script
    assert "replaceChildren" in script
    assert "SCORING_RUN_BOUND_OPTIONS_CACHE_MS = 300_000" in script
    assert "RUN_SUMMARY_CACHE_MS = 300_000" in script
    assert "innerHTML" not in script
    assert "first_name" not in combined
    assert "last_name" not in combined
    assert "email" not in combined
    assert "phone_number" not in combined
    assert "address_line_1" not in combined
    assert "address_line_2" not in combined
    assert "postal_code" not in combined
    assert "ethnicity" not in combined
    assert "religion" not in combined
    assert "86% chance to buy" not in combined
    assert "csv export" not in combined
    assert "audiences/export" not in combined
