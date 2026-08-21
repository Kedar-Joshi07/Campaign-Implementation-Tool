import { getCachedJSON, getJSON } from "./api.js";
import {
  formatDate,
  formatNumber,
  formatPercent,
  hideError,
  setButtonLoading,
  setStatusBadge,
  showError,
} from "./ui.js";

const POLL_INTERVAL_MS = 1500;
const TERMINAL_JOB_STATUSES = new Set(["COMPLETED", "FAILED"]);
const DEFAULTS = {
  random_seed: 42,
  validation_fraction: 0.2,
  run_elkan_challenger: true,
  model_name: "",
};
const API_PATHS = {
  options: "/api/models/training-options",
  submit: "/api/models/train",
  models: "/api/models?limit=20&offset=0",
  analysisDetail: (analysisRunId) => `/api/historical/analyses/${analysisRunId}`,
  modelDetail: (modelRunId) => `/api/models/${modelRunId}`,
  jobDetail: (jobId) => `/api/jobs/${jobId}`,
};

let initialized = false;
let loadedOnce = false;
let optionsSnapshot = null;
let selectedAnalysis = null;
let activeJobId = null;
let pollTimer = null;
let loadingJob = false;
const analysisDateRangeCache = new Map();
const modelQualityCache = new Map();

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", { detail: { state, text } }));
}

function clearPolling() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function schedulePoll() {
  clearPolling();
  if (!activeJobId) return;
  pollTimer = window.setTimeout(() => {
    loadJobDetail(activeJobId, { silent: true });
  }, POLL_INTERVAL_MS);
}

function setWorkspaceState({ loading = false, empty = false } = {}) {
  document.querySelector("#model-training-loading").hidden = !loading;
  document.querySelector("#model-training-empty").hidden = !empty;
  document.querySelector("#model-training-workspace").hidden = loading || empty;
}

function setFormError(message) {
  const error = document.querySelector("#model-training-form-error");
  error.textContent = message;
  error.hidden = false;
  error.focus();
}

function hideFormError() {
  document.querySelector("#model-training-form-error").hidden = true;
}

function selectedValue(selector) {
  return document.querySelector(selector).value;
}

function populateAnalysisOptions(analyses) {
  const select = document.querySelector("#source-analysis-select");
  select.replaceChildren();
  for (const item of analyses) {
    const option = document.createElement("option");
    option.value = String(item.analysis_run_id);
    option.textContent = `#${item.analysis_run_id} · ${item.analysis_name}`;
    select.append(option);
  }
}

function updateSourceSummary(item) {
  selectedAnalysis = item || null;
  document.querySelector("#source-analysis-name").textContent = item?.analysis_name || "-";
  document.querySelector("#source-analysis-id").textContent = item ? `#${item.analysis_run_id}` : "-";
  document.querySelector("#source-conversion-definition").textContent = item
    ? String(item.conversion_definition || "").replaceAll("_", " ")
    : "-";
  document.querySelector("#source-date-range").textContent = item ? "Loading date range..." : "-";
  document.querySelector("#source-selected-count").textContent = formatNumber(item?.selected_customer_count);
  document.querySelector("#source-positive-count").textContent = formatNumber(item?.positive_customer_count);
  document.querySelector("#source-unlabeled-count").textContent = formatNumber(item?.unlabeled_customer_count);
}

async function loadSourceDateRange(analysisRunId) {
  if (!analysisRunId) {
    document.querySelector("#source-date-range").textContent = "-";
    return;
  }

  if (analysisDateRangeCache.has(analysisRunId)) {
    document.querySelector("#source-date-range").textContent = analysisDateRangeCache.get(analysisRunId);
    return;
  }

  try {
    const detail = await getJSON(API_PATHS.analysisDetail(analysisRunId));
    const filters = detail?.filters || {};
    const value = filters.contact_date_from && filters.contact_date_to
      ? `${formatDate(filters.contact_date_from)} - ${formatDate(filters.contact_date_to)}`
      : "-";
    analysisDateRangeCache.set(analysisRunId, value);
    if (selectedAnalysis?.analysis_run_id === analysisRunId) {
      document.querySelector("#source-date-range").textContent = value;
    }
  } catch {
    if (selectedAnalysis?.analysis_run_id === analysisRunId) {
      document.querySelector("#source-date-range").textContent = "-";
    }
  }
}

function applyDefaults() {
  const defaults = optionsSnapshot?.defaults || DEFAULTS;
  document.querySelector("#model-name-input").value = defaults.model_name ?? "";
  document.querySelector("#random-seed-input").value = String(defaults.random_seed ?? DEFAULTS.random_seed);
  document.querySelector("#validation-fraction-input").value = String(
    defaults.validation_fraction ?? DEFAULTS.validation_fraction,
  );
  document.querySelector("#run-elkan-challenger-input").checked = (
    defaults.run_elkan_challenger ?? DEFAULTS.run_elkan_challenger
  ) === true;
}

function applySubmitDisabledState() {
  const hasActiveJob = optionsSnapshot?.active_job
    && !TERMINAL_JOB_STATUSES.has(optionsSnapshot.active_job.status);
  const disabled = Boolean(hasActiveJob || loadingJob);
  const submit = document.querySelector("#train-model-submit");
  submit.disabled = disabled;

  if (hasActiveJob) {
    document.querySelector("#model-training-announcement").textContent = (
      `Training is unavailable while job #${optionsSnapshot.active_job.job_id} is ${optionsSnapshot.active_job.status.toLowerCase()}.`
    );
  } else if (!loadingJob) {
    document.querySelector("#model-training-announcement").textContent = "Ready to train.";
  }
}

function setJobProgress(progressPercent) {
  const progress = Math.max(0, Math.min(100, Number(progressPercent) || 0));
  const fill = document.querySelector("#model-job-progress-fill");
  fill.style.width = `${progress}%`;
  const track = document.querySelector(".model-job-progress-track");
  track.setAttribute("aria-valuenow", String(progress));
  document.querySelector("#model-job-progress-percent").textContent = `${progress}%`;
}

function formatElapsed(createdAt, finishedAt) {
  if (!createdAt) return "-";
  const start = new Date(createdAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "-";
  const seconds = Math.floor((end - start) / 1000);
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}m ${rem}s`;
}

function showJobPanel(job) {
  document.querySelector("#model-job-empty").hidden = true;
  document.querySelector("#model-job-content").hidden = false;
  document.querySelector("#model-job-id").textContent = `#${job.job_id}`;
  document.querySelector("#model-job-stage").textContent = job.stage || "-";
  document.querySelector("#model-job-message").textContent = job.message || "Model training in progress.";
  document.querySelector("#model-job-analysis").textContent = job.analysis_run_id ? `#${job.analysis_run_id}` : "-";
  document.querySelector("#model-job-created").textContent = formatDate(job.created_at, true);
  document.querySelector("#model-job-started").textContent = formatDate(job.started_at, true);
  document.querySelector("#model-job-finished").textContent = formatDate(job.finished_at, true);
  document.querySelector("#model-job-elapsed").textContent = formatElapsed(job.created_at, job.finished_at);
  document.querySelector("#model-job-model-run").textContent = job.model_run_id ? `#${job.model_run_id}` : "-";
  setStatusBadge(document.querySelector("#model-job-status"), job.status);
  setJobProgress(job.progress_percent);

  const failure = document.querySelector("#model-job-failure");
  if (job.status === "FAILED") {
    failure.textContent = job.failure_message || "Model training could not be completed.";
    failure.hidden = false;
  } else {
    failure.hidden = true;
  }
}

function showJobEmpty() {
  document.querySelector("#model-job-empty").hidden = false;
  document.querySelector("#model-job-content").hidden = true;
  document.querySelector("#model-job-failure").hidden = true;
  setJobProgress(0);
}

function metricFromCandidate(candidate, metric) {
  if (!candidate || candidate.status !== "FITTED") return "-";
  const topSlices = candidate.top_slice_metrics || {};
  const observed = candidate.observed_label_diagnostics || {};
  const separation = candidate.separation_diagnostics || {};
  const runtime = candidate.runtime || {};
  if (metric === "recall5") return formatPercent(topSlices.top_05_percent?.known_positive_recall_at_k);
  if (metric === "recall10") return formatPercent(topSlices.top_10_percent?.known_positive_recall_at_k);
  if (metric === "recall20") return formatPercent(topSlices.top_20_percent?.known_positive_recall_at_k);
  if (metric === "lift5") return formatNumber(topSlices.top_05_percent?.known_positive_lift_at_k);
  if (metric === "lift10") return formatNumber(topSlices.top_10_percent?.known_positive_lift_at_k);
  if (metric === "lift20") return formatNumber(topSlices.top_20_percent?.known_positive_lift_at_k);
  if (metric === "rocAuc") return formatNumber(observed.observed_label_roc_auc);
  if (metric === "avgPrecision") return formatNumber(observed.observed_label_average_precision);
  if (metric === "ks") return formatNumber(separation.observed_label_ks_statistic);
  if (metric === "fitSeconds") return `${formatNumber(runtime.fit_seconds)}s`;
  return "-";
}

function appendComparisonRow(body, label, primary, challenger, diagnostic) {
  const row = document.createElement("tr");
  for (const value of [label, primary, challenger, diagnostic]) {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.append(cell);
  }
  body.append(row);
}

function renderCandidateComparison(detail) {
  const panel = document.querySelector("#candidate-comparison-panel");
  const body = document.querySelector("#candidate-comparison-body");
  body.replaceChildren();

  const candidates = detail.candidates || {};
  const primary = candidates.BAGGING_PU;
  const challenger = candidates.ELKAN_NOTO_LOGISTIC;
  const diagnostic = candidates.NAIVE_PU_LABEL_BASELINE;

  appendComparisonRow(body, "Status", primary?.status || "-", challenger?.status || "-", diagnostic?.status || "-");
  appendComparisonRow(body, "Recall @5", metricFromCandidate(primary, "recall5"), metricFromCandidate(challenger, "recall5"), metricFromCandidate(diagnostic, "recall5"));
  appendComparisonRow(body, "Recall @10", metricFromCandidate(primary, "recall10"), metricFromCandidate(challenger, "recall10"), metricFromCandidate(diagnostic, "recall10"));
  appendComparisonRow(body, "Recall @20", metricFromCandidate(primary, "recall20"), metricFromCandidate(challenger, "recall20"), metricFromCandidate(diagnostic, "recall20"));
  appendComparisonRow(body, "Lift @5", metricFromCandidate(primary, "lift5"), metricFromCandidate(challenger, "lift5"), metricFromCandidate(diagnostic, "lift5"));
  appendComparisonRow(body, "Lift @10", metricFromCandidate(primary, "lift10"), metricFromCandidate(challenger, "lift10"), metricFromCandidate(diagnostic, "lift10"));
  appendComparisonRow(body, "Lift @20", metricFromCandidate(primary, "lift20"), metricFromCandidate(challenger, "lift20"), metricFromCandidate(diagnostic, "lift20"));
  appendComparisonRow(body, "Observed-label ROC-AUC", metricFromCandidate(primary, "rocAuc"), metricFromCandidate(challenger, "rocAuc"), metricFromCandidate(diagnostic, "rocAuc"));
  appendComparisonRow(body, "Observed-label AP", metricFromCandidate(primary, "avgPrecision"), metricFromCandidate(challenger, "avgPrecision"), metricFromCandidate(diagnostic, "avgPrecision"));
  appendComparisonRow(body, "KS", metricFromCandidate(primary, "ks"), metricFromCandidate(challenger, "ks"), metricFromCandidate(diagnostic, "ks"));
  appendComparisonRow(body, "Fit time", metricFromCandidate(primary, "fitSeconds"), metricFromCandidate(challenger, "fitSeconds"), metricFromCandidate(diagnostic, "fitSeconds"));

  panel.hidden = false;
}

function renderSummary(detail) {
  const panel = document.querySelector("#model-summary-panel");
  panel.hidden = false;

  const identity = detail.identity || {};
  const cohort = detail.cohort || {};
  const governance = detail.governance || {};
  const artifact = detail.artifact || {};
  const contract = detail.feature_contract || {};
  const candidates = detail.candidates || {};
  const selected = governance.selected_candidate;
  const selectedCandidate = selected ? candidates[selected] : null;
  const top10 = selectedCandidate?.top_slice_metrics?.top_10_percent || {};

  document.querySelector("#summary-model-run-id").textContent = identity.model_run_id ? `#${identity.model_run_id}` : "-";
  document.querySelector("#summary-analysis-run-id").textContent = identity.analysis_run_id ? `#${identity.analysis_run_id}` : "-";
  document.querySelector("#summary-selected-primary").textContent = governance.primary_candidate || "BAGGING_PU";
  document.querySelector("#summary-policy-version").textContent = governance.model_role_policy_version || "legacy";
  document.querySelector("#summary-selected-count").textContent = formatNumber(cohort.selected_customer_count);
  document.querySelector("#summary-positive-count").textContent = formatNumber(cohort.positive_customer_count);
  document.querySelector("#summary-unlabeled-count").textContent = formatNumber(cohort.unlabeled_customer_count);
  document.querySelector("#summary-feature-count").textContent = formatNumber((contract.ordered_features || []).length);
  document.querySelector("#summary-top10-lift").textContent = formatNumber(top10.known_positive_lift_at_k);
  document.querySelector("#summary-top10-recall").textContent = formatPercent(top10.known_positive_recall_at_k);
  document.querySelector("#summary-quality-flags").textContent = (detail.quality_flags || []).join(", ") || "None";
  document.querySelector("#summary-artifact-verification").textContent = artifact.verified
    ? "Verified"
    : (artifact.verification_message || "Not verified");

  const advisory = document.querySelector("#challenger-advisory");
  const outperformed = Boolean(detail.challenger_comparison?.challenger_outperformed_primary)
    || (detail.quality_flags || []).includes("CHALLENGER_OUTPERFORMED_PRIMARY");
  advisory.hidden = !outperformed;

  renderCandidateComparison(detail);
}

function createRunCell(run) {
  const container = document.createElement("td");
  const title = document.createElement("strong");
  title.textContent = `#${run.model_run_id} · ${run.model_name}`;
  const meta = document.createElement("small");
  meta.textContent = `Analysis #${run.analysis_run_id} · ${formatDate(run.completed_at || run.created_at, true)}`;
  container.append(title, meta);
  return container;
}

function renderRecentRuns(runs) {
  const loading = document.querySelector("#recent-model-runs-loading");
  const empty = document.querySelector("#recent-model-runs-empty");
  const table = document.querySelector("#recent-model-runs-table");
  const body = document.querySelector("#recent-model-runs-body");

  loading.hidden = true;
  body.replaceChildren();

  if (!runs.length) {
    empty.hidden = false;
    table.hidden = true;
    return;
  }

  empty.hidden = true;
  table.hidden = false;

  for (const run of runs) {
    const row = document.createElement("tr");
    row.append(createRunCell(run));

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    setStatusBadge(badge, run.status);
    statusCell.append(badge);
    row.append(statusCell);

    const selectedCell = document.createElement("td");
    selectedCell.textContent = run.selected_candidate || "-";
    row.append(selectedCell);

    const liftCell = document.createElement("td");
    liftCell.textContent = formatNumber(run.validation_lift_at_10_percent);
    row.append(liftCell);

    const qualityCell = document.createElement("td");
    qualityCell.textContent = modelQualityCache.get(run.model_run_id) || "Loading...";
    row.append(qualityCell);

    const actionCell = document.createElement("td");
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "button button-secondary recent-reopen";
    openButton.textContent = "Load";
    openButton.addEventListener("click", () => loadModelDetail(run.model_run_id, { focusSummary: true }));
    actionCell.append(openButton);
    row.append(actionCell);

    body.append(row);
  }
}

async function hydrateRunQuality(runs) {
  const pending = runs.filter((run) => !modelQualityCache.has(run.model_run_id));
  await Promise.all(
    pending.map(async (run) => {
      try {
        const detail = await getJSON(API_PATHS.modelDetail(run.model_run_id));
        const flags = detail.quality_flags || [];
        modelQualityCache.set(run.model_run_id, flags.length ? flags.join(", ") : "None");
      } catch {
        modelQualityCache.set(run.model_run_id, "Unavailable");
      }
    }),
  );
}

async function loadRecentRuns(force = false) {
  document.querySelector("#recent-model-runs-loading").hidden = false;
  try {
    const runs = await getCachedJSON(API_PATHS.models, { maxAgeMs: 20_000, force });
    renderRecentRuns(runs);
    await hydrateRunQuality(runs);
    renderRecentRuns(runs);
  } finally {
    document.querySelector("#recent-model-runs-loading").hidden = true;
  }
}

async function loadModelDetail(modelRunId, { focusSummary = false } = {}) {
  const detail = await getJSON(API_PATHS.modelDetail(modelRunId));
  renderSummary(detail);
  if (focusSummary) {
    document.querySelector("#model-summary-title").focus();
  }
}

async function loadJobDetail(jobId, { silent = false } = {}) {
  if (!jobId) return;
  loadingJob = true;
  applySubmitDisabledState();

  try {
    const job = await getJSON(API_PATHS.jobDetail(jobId));
    showJobPanel(job);
    activeJobId = job.job_id;
    optionsSnapshot = {
      ...(optionsSnapshot || {}),
      active_job: TERMINAL_JOB_STATUSES.has(job.status) ? null : job,
    };
    applySubmitDisabledState();

    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      clearPolling();
      activeJobId = null;
      if (job.status === "COMPLETED" && job.model_run_id) {
        await Promise.all([loadModelDetail(job.model_run_id), loadRecentRuns(true)]);
        document.querySelector("#model-training-announcement").textContent = (
          `Model training completed as run #${job.model_run_id}.`
        );
      } else if (job.status === "FAILED") {
        document.querySelector("#model-training-announcement").textContent = "Model training failed safely.";
      }
      optionsSnapshot = {
        ...(optionsSnapshot || {}),
        active_job: null,
      };
      applySubmitDisabledState();
      return;
    }

    if (!silent) {
      document.querySelector("#model-training-announcement").textContent = (
        `Job #${job.job_id} is ${job.status.toLowerCase()}.`
      );
    }
    schedulePoll();
  } catch (error) {
    clearPolling();
    activeJobId = null;
    if (!silent) {
      setFormError(error.message);
    }
  } finally {
    loadingJob = false;
    applySubmitDisabledState();
  }
}

function validateRequest() {
  if (!selectedAnalysis) return "Select a completed analysis before training.";
  const randomSeed = Number(selectedValue("#random-seed-input"));
  if (!Number.isInteger(randomSeed)) {
    return "Random Seed must be a whole number.";
  }
  const validationFraction = Number(selectedValue("#validation-fraction-input"));
  if (!Number.isFinite(validationFraction) || validationFraction <= 0 || validationFraction >= 1) {
    return "Validation Fraction must be greater than 0 and less than 1.";
  }
  return null;
}

function requestPayload() {
  const modelName = selectedValue("#model-name-input").trim();
  return {
    analysis_run_id: Number(selectedValue("#source-analysis-select")),
    model_name: modelName || null,
    random_seed: Number(selectedValue("#random-seed-input")),
    validation_fraction: Number(selectedValue("#validation-fraction-input")),
    run_elkan_challenger: document.querySelector("#run-elkan-challenger-input").checked,
  };
}

async function submitTraining(event) {
  event.preventDefault();
  hideFormError();
  const validationMessage = validateRequest();
  if (validationMessage) {
    setFormError(validationMessage);
    return;
  }

  const submitButton = document.querySelector("#train-model-submit");
  setButtonLoading(submitButton, true, "Submitting...");
  document.querySelector("#model-training-announcement").textContent = "Submitting model training request.";

  try {
    const job = await getJSON(API_PATHS.submit, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload()),
    });
    showJobPanel(job);
    document.querySelector("#model-summary-panel").hidden = true;
    document.querySelector("#candidate-comparison-panel").hidden = true;
    activeJobId = job.job_id;
    optionsSnapshot = {
      ...(optionsSnapshot || {}),
      active_job: job,
    };
    applySubmitDisabledState();
    document.querySelector("#model-training-announcement").textContent = `Job #${job.job_id} accepted and queued.`;
    schedulePoll();
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    setFormError(error.message);
    document.querySelector("#model-training-announcement").textContent = "Model training submission failed.";
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(submitButton, false, "Submitting...");
    applySubmitDisabledState();
  }
}

function bindAnalysisSelection() {
  const select = document.querySelector("#source-analysis-select");
  const value = Number(select.value);
  const item = (optionsSnapshot?.completed_analyses || []).find((candidate) => candidate.analysis_run_id === value);
  updateSourceSummary(item || null);
  loadSourceDateRange(value);
}

function renderOptions(options) {
  optionsSnapshot = options;
  const completed = options.completed_analyses || [];
  if (!completed.length) {
    setWorkspaceState({ loading: false, empty: true });
    showJobEmpty();
    return;
  }

  setWorkspaceState({ loading: false, empty: false });
  populateAnalysisOptions(completed);
  applyDefaults();
  bindAnalysisSelection();

  if (options.active_job) {
    showJobPanel(options.active_job);
    activeJobId = options.active_job.job_id;
    if (!TERMINAL_JOB_STATUSES.has(options.active_job.status)) {
      schedulePoll();
    }
  } else {
    activeJobId = null;
    clearPolling();
    showJobEmpty();
  }

  applySubmitDisabledState();
}

export async function loadModelTraining(force = false) {
  if (loadedOnce && !force) return;
  loadedOnce = true;

  const errorBanner = document.querySelector("#model-training-error");
  const errorMessage = document.querySelector("#model-training-error-message");
  const refresh = document.querySelector("#model-training-refresh");

  hideError(errorBanner);
  setWorkspaceState({ loading: true, empty: false });
  setButtonLoading(refresh, true, "Refreshing...");

  const results = await Promise.allSettled([
    getCachedJSON(API_PATHS.options, { maxAgeMs: 20_000, force }),
    loadRecentRuns(force),
  ]);

  setButtonLoading(refresh, false, "Refreshing...");

  const optionsResult = results[0];
  const runsResult = results[1];

  if (optionsResult.status === "fulfilled") {
    renderOptions(optionsResult.value);
  } else {
    setWorkspaceState({ loading: false, empty: false });
    showError(errorBanner, errorMessage, optionsResult.reason);
    dispatchBackendStatus("is-offline", "Backend unavailable");
    return;
  }

  if (runsResult.status === "rejected") {
    showError(errorBanner, errorMessage, runsResult.reason);
    dispatchBackendStatus("is-offline", "Backend unavailable");
  } else {
    dispatchBackendStatus("is-online", "Backend online");
  }
}

function handleRefresh() {
  clearPolling();
  activeJobId = null;
  loadModelTraining(true);
}

export function initializeModelTraining() {
  if (initialized) return;
  initialized = true;

  document.querySelector("#model-training-form").addEventListener("submit", submitTraining);
  document.querySelector("#model-training-refresh").addEventListener("click", handleRefresh);
  document.querySelector("#model-training-retry").addEventListener("click", () => loadModelTraining(true));
  document.querySelector("#recent-model-runs-refresh").addEventListener("click", async () => {
    try {
      await loadRecentRuns(true);
      hideError(document.querySelector("#model-training-error"));
      dispatchBackendStatus("is-online", "Backend online");
    } catch (error) {
      showError(
        document.querySelector("#model-training-error"),
        document.querySelector("#model-training-error-message"),
        error,
      );
      dispatchBackendStatus("is-offline", "Backend unavailable");
    }
  });
  document.querySelector("#source-analysis-select").addEventListener("change", bindAnalysisSelection);
}
