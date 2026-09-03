import { getCachedJSON, getJSON } from "./api.js";
import {
  formatDate,
  formatDecimal,
  formatExactInteger,
  formatId,
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
  scoringStatus: (modelRunId) => `/api/models/${modelRunId}/scoring-status`,
  scoringSubmit: (modelRunId) => `/api/models/${modelRunId}/score`,
  scoringRunDetail: (scoringRunId) => `/api/scoring-runs/${scoringRunId}`,
  jobDetail: (jobId) => `/api/jobs/${jobId}`,
};

let initialized = false;
let loadedOnce = false;
let optionsSnapshot = null;
let selectedAnalysis = null;
let selectedModelRunId = null;
let activeJobId = null;
let pollTimer = null;
let loadingJob = false;
let scoringStatusSnapshot = null;
let scoringStatusRequestToken = 0;
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
    option.textContent = `#${formatId(item.analysis_run_id)} · ${item.analysis_name}`;
    select.append(option);
  }
}

function updateSourceSummary(item) {
  selectedAnalysis = item || null;
  document.querySelector("#source-analysis-name").textContent = item?.analysis_name || "-";
  document.querySelector("#source-analysis-id").textContent = item ? `#${formatId(item.analysis_run_id)}` : "-";
  document.querySelector("#source-conversion-definition").textContent = item
    ? String(item.conversion_definition || "").replaceAll("_", " ")
    : "-";
  document.querySelector("#source-date-range").textContent = item ? "Loading date range..." : "-";
  document.querySelector("#source-selected-count").textContent = formatExactInteger(item?.selected_customer_count);
  document.querySelector("#source-positive-count").textContent = formatExactInteger(item?.positive_customer_count);
  document.querySelector("#source-unlabeled-count").textContent = formatExactInteger(item?.unlabeled_customer_count);
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

function setModelAnnouncement(text) {
  document.querySelector("#model-training-announcement").textContent = text;
}

function setScoringAnnouncement(text) {
  document.querySelector("#scoring-announcement").textContent = text;
}

function activeComputeJob() {
  const activeJob = optionsSnapshot?.active_job;
  if (!activeJob) return null;
  if (TERMINAL_JOB_STATUSES.has(activeJob.status)) return null;
  return activeJob;
}

function shortHash(value) {
  if (!value || typeof value !== "string") return "-";
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

function formatScore(value) {
  return formatDecimal(value, 2, 6);
}

function formatRowsPerSecond(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return `${formatExactInteger(Math.round(Number(value)))} rows/s`;
}

function formatSeconds(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const totalSeconds = Math.max(0, Number(value));
  return `${formatDecimal(totalSeconds, 2, 2)}s`;
}

function setScoringText(id, value) {
  document.querySelector(id).textContent = value;
}

function resetScoringSummary() {
  for (const selector of [
    "#scoring-summary-scored-count",
    "#scoring-summary-reconciliation",
    "#scoring-summary-min",
    "#scoring-summary-mean",
    "#scoring-summary-max",
    "#scoring-summary-runtime",
    "#scoring-summary-rows-per-second",
    "#scoring-summary-feature-contract",
    "#scoring-summary-artifact-sha",
  ]) {
    setScoringText(selector, "-");
  }
}

function hideScoringPanel() {
  document.querySelector("#prospect-scoring-panel").hidden = true;
  document.querySelector("#scoring-status-reason").hidden = true;
  document.querySelector("#scoring-completed-summary").hidden = true;
  document.querySelector("#score-prospect-submit").hidden = false;
  selectedModelRunId = null;
  scoringStatusSnapshot = null;
  resetScoringSummary();
  setScoringAnnouncement("Load a completed model to evaluate scoring readiness.");
}

function hasCurrentCanonicalScoring(statusSnapshot = scoringStatusSnapshot) {
  return Boolean(
    statusSnapshot?.completed_scoring_run
    && statusSnapshot?.demographic_source_verified === true,
  );
}

function hasStaleHistoricalScoring(statusSnapshot = scoringStatusSnapshot) {
  return Boolean(
    statusSnapshot?.completed_scoring_run
    && statusSnapshot?.demographic_source_verified === false,
  );
}

function applySubmitDisabledState() {
  const activeJob = activeComputeJob();
  const hasActiveJob = Boolean(activeJob);
  const trainingDisabled = Boolean(hasActiveJob || loadingJob);
  const trainSubmit = document.querySelector("#train-model-submit");
  trainSubmit.disabled = trainingDisabled;

  const scoringPanelVisible = !document.querySelector("#prospect-scoring-panel").hidden;
  const hasCompletedScoring = hasCurrentCanonicalScoring();
  const scoreReady = Boolean(scoringPanelVisible && scoringStatusSnapshot?.eligible);
  const scoreDisabled = Boolean(loadingJob || hasActiveJob || !scoreReady || hasCompletedScoring);
  const scoreSubmit = document.querySelector("#score-prospect-submit");
  scoreSubmit.disabled = scoreDisabled;
  scoreSubmit.hidden = hasCompletedScoring && scoringPanelVisible;

  if (hasActiveJob) {
    setModelAnnouncement(
      `Training is unavailable while job #${formatId(activeJob.job_id)} is ${activeJob.status.toLowerCase()}.`,
    );
    if (scoringPanelVisible) {
      setScoringAnnouncement(
        `Scoring is unavailable while job #${formatId(activeJob.job_id)} is ${activeJob.status.toLowerCase()}.`,
      );
    }
  } else if (!loadingJob) {
    setModelAnnouncement("Ready to train.");
    if (scoringPanelVisible) {
      if (!selectedModelRunId) {
        setScoringAnnouncement("Load a completed model to evaluate scoring readiness.");
      } else if (hasCompletedScoring) {
        setScoringAnnouncement("A completed scoring run already exists for the current demographics source.");
      } else if (hasStaleHistoricalScoring()) {
        setScoringAnnouncement("Historical scoring exists for a previous demographics source. Rescoring is available.");
      } else if (scoreReady) {
        setScoringAnnouncement("Ready to score prospect universe.");
      } else if (scoringStatusSnapshot?.reason) {
        setScoringAnnouncement(scoringStatusSnapshot.reason);
      } else {
        setScoringAnnouncement("Scoring is currently unavailable.");
      }
    }
  }
}

function setJobProgress(progressPercent) {
  const progress = Math.max(0, Math.min(100, Number(progressPercent) || 0));
  const fill = document.querySelector("#model-job-progress-fill");
  fill.style.width = `${progress}%`;
  const track = document.querySelector(".model-job-progress-track");
  track.setAttribute("aria-valuenow", String(progress));
  document.querySelector("#model-job-progress-percent").textContent = `${formatDecimal(progress, 0, 2)}%`;
}

function formatElapsed(createdAt, finishedAt) {
  if (!createdAt) return "-";
  const start = new Date(createdAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "-";
  const seconds = (end - start) / 1000;
  return `${formatDecimal(seconds, 2, 2)}s`;
}

function showJobPanel(job) {
  const isScoringJob = job.job_type === "PROSPECT_SCORING";
  document.querySelector("#model-job-empty").hidden = true;
  document.querySelector("#model-job-content").hidden = false;
  document.querySelector("#model-job-id").textContent = `#${formatId(job.job_id)}`;
  document.querySelector("#model-job-stage").textContent = job.stage || "-";
  document.querySelector("#model-job-message").textContent = job.message || (
    isScoringJob ? "Prospect scoring in progress." : "Model training in progress."
  );
  document.querySelector("#model-job-analysis").textContent = job.analysis_run_id ? `#${formatId(job.analysis_run_id)}` : "-";
  document.querySelector("#model-job-created").textContent = formatDate(job.created_at, true);
  document.querySelector("#model-job-started").textContent = formatDate(job.started_at, true);
  document.querySelector("#model-job-finished").textContent = formatDate(job.finished_at, true);
  document.querySelector("#model-job-elapsed").textContent = formatElapsed(job.created_at, job.finished_at);
  document.querySelector("#model-job-model-run").textContent = job.model_run_id ? `#${formatId(job.model_run_id)}` : "-";
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

function renderScoringSummaryFromDetail(detail) {
  const population = detail?.population || {};
  const contract = detail?.model_contract || {};
  const scoreSummary = detail?.score_summary || {};
  const summaryPayload = scoreSummary.summary_payload || {};

  const scoredCount = Number(population.scored_person_count);
  const snapshotCount = Number(population.demographic_snapshot_count);
  const reconciliation = (
    Number.isFinite(scoredCount)
    && Number.isFinite(snapshotCount)
    && scoredCount >= 0
    && snapshotCount >= 0
  )
    ? `${formatExactInteger(scoredCount)} / ${formatExactInteger(snapshotCount)}`
    : "-";

  setScoringText("#scoring-summary-scored-count", formatExactInteger(population.scored_person_count));
  setScoringText("#scoring-summary-reconciliation", reconciliation);
  setScoringText("#scoring-summary-min", formatScore(scoreSummary.score_min));
  setScoringText("#scoring-summary-mean", formatScore(scoreSummary.score_mean));
  setScoringText("#scoring-summary-max", formatScore(scoreSummary.score_max));
  setScoringText("#scoring-summary-runtime", formatSeconds(summaryPayload.total_seconds));
  setScoringText("#scoring-summary-rows-per-second", formatRowsPerSecond(summaryPayload.rows_per_second));
  setScoringText(
    "#scoring-summary-feature-contract",
    `${contract.feature_contract_version || "-"} · ${shortHash(contract.feature_contract_sha256)}`,
  );
  setScoringText("#scoring-summary-artifact-sha", shortHash(contract.artifact_sha256));
  document.querySelector("#scoring-completed-summary").hidden = false;
}

function renderScoringSummaryFromJobResult(resultPayload) {
  if (!resultPayload || typeof resultPayload !== "object") {
    return;
  }
  const demographicCount = Number(scoringStatusSnapshot?.demographic_count);
  const scoredCount = Number(resultPayload.scored_person_count);
  const reconciliation = (
    Number.isFinite(demographicCount)
    && Number.isFinite(scoredCount)
    && demographicCount >= 0
    && scoredCount >= 0
  )
    ? `${formatExactInteger(scoredCount)} / ${formatExactInteger(demographicCount)}`
    : "-";

  setScoringText("#scoring-summary-scored-count", formatExactInteger(resultPayload.scored_person_count));
  setScoringText("#scoring-summary-reconciliation", reconciliation);
  setScoringText("#scoring-summary-min", formatScore(resultPayload.score_min));
  setScoringText("#scoring-summary-mean", formatScore(resultPayload.score_mean));
  setScoringText("#scoring-summary-max", formatScore(resultPayload.score_max));
  setScoringText("#scoring-summary-runtime", formatSeconds(resultPayload.total_seconds));
  setScoringText("#scoring-summary-rows-per-second", formatRowsPerSecond(resultPayload.rows_per_second));
  setScoringText(
    "#scoring-summary-feature-contract",
    `${resultPayload.feature_contract_version || "-"} · ${shortHash(resultPayload.feature_contract_sha256)}`,
  );
  setScoringText("#scoring-summary-artifact-sha", shortHash(resultPayload.artifact_sha256));
  document.querySelector("#scoring-completed-summary").hidden = false;
}

function renderScoringStatus(status) {
  scoringStatusSnapshot = status;
  document.querySelector("#prospect-scoring-panel").hidden = false;

  setScoringText("#scoring-model-run-id", `#${formatId(status.model_run_id)}`);
  setScoringText("#scoring-selected-primary", status.selected_candidate || "-");
  setScoringText("#scoring-demographic-count", formatExactInteger(status.demographic_count));
  setScoringText("#scoring-availability", status.eligible ? "Eligible" : "Not eligible");
  setScoringText("#scoring-historical-source", status.historical_source_verified ? "Current" : "Stale");
  setScoringText("#scoring-model-artifact", status.artifact_feature_compatible ? "Verified" : "Verification required");
  setScoringText("#scoring-run-currentness", status.demographic_source_verified ? "Current" : "Historical");
  setScoringText("#scoring-availability-status", status.demographic_source_verified ? "Canonical" : "Historical");

  if (status.artifact_feature_compatible) {
    const compatibility = `${status.feature_contract_version || "-"} · ${shortHash(status.artifact_sha256)}`;
    setScoringText("#scoring-artifact-compatibility", `Compatible (${compatibility})`);
  } else {
    setScoringText("#scoring-artifact-compatibility", "Not compatible");
  }

  if (status.completed_scoring_run) {
    const completed = status.completed_scoring_run;
    const completionStamp = formatDate(completed.completed_at, true);
    if (status.demographic_source_verified) {
      setScoringText(
        "#scoring-completed-run",
        `#${formatId(completed.scoring_run_id)} · ${completionStamp}`,
      );
    } else {
      setScoringText(
        "#scoring-completed-run",
        `#${formatId(completed.scoring_run_id)} · Historical (${completionStamp})`,
      );
    }
  } else {
    setScoringText("#scoring-completed-run", "-");
  }

  const reason = document.querySelector("#scoring-status-reason");
  if (status.reason) {
    reason.textContent = status.reason;
    reason.hidden = false;
  } else {
    reason.hidden = true;
  }

  if (!status.demographic_source_verified) {
    document.querySelector("#scoring-completed-summary").hidden = true;
    resetScoringSummary();
  }

  const activeJob = status.active_job;
  if (activeJob && !TERMINAL_JOB_STATUSES.has(activeJob.status)) {
    showJobPanel(activeJob);
    activeJobId = activeJob.job_id;
    optionsSnapshot = {
      ...(optionsSnapshot || {}),
      active_job: activeJob,
    };
    schedulePoll();
  }

  applySubmitDisabledState();
}

async function loadScoringRunDetail(scoringRunId, { silent = false } = {}) {
  try {
    const detail = await getJSON(API_PATHS.scoringRunDetail(scoringRunId));
    renderScoringSummaryFromDetail(detail);
  } catch (error) {
    document.querySelector("#scoring-completed-summary").hidden = true;
    resetScoringSummary();
    if (!silent) {
      setScoringAnnouncement(error.message || "Scoring run detail could not be loaded.");
    }
  }
}

async function loadScoringStatus(modelRunId, { force = false } = {}) {
  const token = scoringStatusRequestToken + 1;
  scoringStatusRequestToken = token;
  setScoringAnnouncement("Loading scoring readiness.");

  try {
    const status = await getCachedJSON(API_PATHS.scoringStatus(modelRunId), { maxAgeMs: 10_000, force });
    if (token !== scoringStatusRequestToken) {
      return;
    }

    selectedModelRunId = modelRunId;
    renderScoringStatus(status);

    if (status.demographic_source_verified && status.completed_scoring_run?.scoring_run_id) {
      await loadScoringRunDetail(status.completed_scoring_run.scoring_run_id, { silent: true });
    }
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    if (token !== scoringStatusRequestToken) {
      return;
    }

    document.querySelector("#prospect-scoring-panel").hidden = false;
    setScoringText("#scoring-model-run-id", `#${formatId(modelRunId)}`);
    setScoringText("#scoring-selected-primary", "-");
    setScoringText("#scoring-artifact-compatibility", "Unavailable");
    setScoringText("#scoring-demographic-count", "-");
    setScoringText("#scoring-availability", "Unavailable");
    setScoringText("#scoring-completed-run", "-");
    const reason = document.querySelector("#scoring-status-reason");
    reason.textContent = "Scoring readiness could not be loaded.";
    reason.hidden = false;
    document.querySelector("#scoring-completed-summary").hidden = true;
    resetScoringSummary();
    scoringStatusSnapshot = null;
    applySubmitDisabledState();
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  }
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
  if (metric === "lift5") return formatDecimal(topSlices.top_05_percent?.known_positive_lift_at_k, 2, 2);
  if (metric === "lift10") return formatDecimal(topSlices.top_10_percent?.known_positive_lift_at_k, 2, 2);
  if (metric === "lift20") return formatDecimal(topSlices.top_20_percent?.known_positive_lift_at_k, 2, 2);
  if (metric === "rocAuc") return formatDecimal(observed.observed_label_roc_auc, 2, 4);
  if (metric === "avgPrecision") return formatDecimal(observed.observed_label_average_precision, 2, 4);
  if (metric === "ks") return formatDecimal(separation.observed_label_ks_statistic, 2, 4);
  if (metric === "fitSeconds") return `${formatDecimal(runtime.fit_seconds, 2, 2)}s`;
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
  appendComparisonRow(body, "Recall @ Top 5%", metricFromCandidate(primary, "recall5"), metricFromCandidate(challenger, "recall5"), metricFromCandidate(diagnostic, "recall5"));
  appendComparisonRow(body, "Recall @ Top 10%", metricFromCandidate(primary, "recall10"), metricFromCandidate(challenger, "recall10"), metricFromCandidate(diagnostic, "recall10"));
  appendComparisonRow(body, "Recall @ Top 20%", metricFromCandidate(primary, "recall20"), metricFromCandidate(challenger, "recall20"), metricFromCandidate(diagnostic, "recall20"));
  appendComparisonRow(body, "Lift @ Top 5%", metricFromCandidate(primary, "lift5"), metricFromCandidate(challenger, "lift5"), metricFromCandidate(diagnostic, "lift5"));
  appendComparisonRow(body, "Lift @ Top 10%", metricFromCandidate(primary, "lift10"), metricFromCandidate(challenger, "lift10"), metricFromCandidate(diagnostic, "lift10"));
  appendComparisonRow(body, "Lift @ Top 20%", metricFromCandidate(primary, "lift20"), metricFromCandidate(challenger, "lift20"), metricFromCandidate(diagnostic, "lift20"));
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

  document.querySelector("#summary-model-run-id").textContent = identity.model_run_id ? `#${formatId(identity.model_run_id)}` : "-";
  document.querySelector("#summary-analysis-run-id").textContent = identity.analysis_run_id ? `#${formatId(identity.analysis_run_id)}` : "-";
  document.querySelector("#summary-selected-primary").textContent = governance.primary_candidate || "BAGGING_PU";
  document.querySelector("#summary-policy-version").textContent = governance.model_role_policy_version || "legacy";
  document.querySelector("#summary-selected-count").textContent = formatExactInteger(cohort.selected_customer_count);
  document.querySelector("#summary-positive-count").textContent = formatExactInteger(cohort.positive_customer_count);
  document.querySelector("#summary-unlabeled-count").textContent = formatExactInteger(cohort.unlabeled_customer_count);
  document.querySelector("#summary-feature-count").textContent = formatExactInteger((contract.ordered_features || []).length);
  document.querySelector("#summary-top10-lift").textContent = formatDecimal(top10.known_positive_lift_at_k, 2, 2);
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
  title.textContent = `#${formatId(run.model_run_id)} · ${run.model_name}`;
  const meta = document.createElement("small");
  meta.textContent = `Analysis #${formatId(run.analysis_run_id)} · ${formatDate(run.completed_at || run.created_at, true)}`;
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
    liftCell.textContent = formatDecimal(run.validation_lift_at_10_percent, 2, 2);
    row.append(liftCell);

    const qualityCell = document.createElement("td");
      qualityCell.textContent = modelQualityCache.get(run.model_run_id) || "See details";
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

async function loadRecentRuns(force = false) {
  document.querySelector("#recent-model-runs-loading").hidden = false;
  try {
    const runs = await getCachedJSON(API_PATHS.models, { maxAgeMs: 20_000, force });
    renderRecentRuns(runs);
  } finally {
    document.querySelector("#recent-model-runs-loading").hidden = true;
  }
}

async function loadModelDetail(modelRunId, { focusSummary = false } = {}) {
  const detail = await getJSON(API_PATHS.modelDetail(modelRunId));
  renderSummary(detail);
  if (detail?.identity?.status === "COMPLETED") {
    await loadScoringStatus(modelRunId, { force: true });
  } else {
    hideScoringPanel();
  }
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
      if (job.status === "COMPLETED") {
        if (job.job_type === "MODEL_TRAINING" && job.model_run_id) {
          await Promise.all([loadModelDetail(job.model_run_id), loadRecentRuns(true)]);
          setModelAnnouncement(`Model training completed as run #${formatId(job.model_run_id)}.`);
        }
        if (job.job_type === "PROSPECT_SCORING") {
          if (job.model_run_id) {
            await loadScoringStatus(job.model_run_id, { force: true });
          } else if (selectedModelRunId) {
            await loadScoringStatus(selectedModelRunId, { force: true });
          }
          renderScoringSummaryFromJobResult(job.result);
          const scoringRunId = job.result?.scoring_run_id;
          if (Number.isFinite(Number(scoringRunId))) {
            await loadScoringRunDetail(Number(scoringRunId), { silent: true });
            setScoringAnnouncement(`Prospect scoring completed as run #${formatId(scoringRunId)}.`);
          } else {
            setScoringAnnouncement("Prospect scoring completed.");
          }
        }
      } else if (job.status === "FAILED") {
        if (job.job_type === "PROSPECT_SCORING") {
          setScoringAnnouncement("Prospect scoring failed safely.");
        } else {
          setModelAnnouncement("Model training failed safely.");
        }
      }
      optionsSnapshot = {
        ...(optionsSnapshot || {}),
        active_job: null,
      };
      applySubmitDisabledState();
      return;
    }

    if (!silent) {
      if (job.job_type === "PROSPECT_SCORING") {
        setScoringAnnouncement(`Scoring job #${formatId(job.job_id)} is ${job.status.toLowerCase()}.`);
      } else {
        setModelAnnouncement(`Job #${formatId(job.job_id)} is ${job.status.toLowerCase()}.`);
      }
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
  setModelAnnouncement("Submitting model training request.");

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
    setModelAnnouncement(`Job #${formatId(job.job_id)} accepted and queued.`);
    schedulePoll();
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    setFormError(error.message);
    setModelAnnouncement("Model training submission failed.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(submitButton, false, "Submitting...");
    applySubmitDisabledState();
  }
}

async function submitScoring() {
  hideFormError();
  if (!selectedModelRunId) {
    setScoringAnnouncement("Load a completed model before scoring prospects.");
    return;
  }
  if (!scoringStatusSnapshot) {
    setScoringAnnouncement("Scoring readiness is still loading.");
    return;
  }
  if (!scoringStatusSnapshot.eligible) {
    setScoringAnnouncement(scoringStatusSnapshot.reason || "Scoring is not eligible for this model.");
    applySubmitDisabledState();
    return;
  }

  const scoreButton = document.querySelector("#score-prospect-submit");
  setButtonLoading(scoreButton, true, "Submitting...");
  setScoringAnnouncement("Submitting prospect scoring request.");

  try {
    const job = await getJSON(API_PATHS.scoringSubmit(selectedModelRunId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    showJobPanel(job);
    activeJobId = job.job_id;
    optionsSnapshot = {
      ...(optionsSnapshot || {}),
      active_job: job,
    };
    document.querySelector("#scoring-completed-summary").hidden = true;
    resetScoringSummary();
    applySubmitDisabledState();
    setScoringAnnouncement(`Scoring job #${formatId(job.job_id)} accepted and queued.`);
    schedulePoll();
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    setScoringAnnouncement(error.message || "Prospect scoring submission failed.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(scoreButton, false, "Submitting...");
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
    hideScoringPanel();
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
  scoringStatusRequestToken += 1;
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
  document.querySelector("#score-prospect-submit").addEventListener("click", submitScoring);
}
