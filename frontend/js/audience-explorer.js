import { clearCachedJSON, getCachedJSON, getJSON } from "./api.js";
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
const DEFAULT_PAGE_SIZE = 50;
const RANK_CONTRACT_VERSION = "1";
const SCORING_RUN_BOUND_OPTIONS_CACHE_MS = 300_000;
const RUN_SUMMARY_CACHE_MS = 300_000;
const TERMINAL_JOB_STATUSES = new Set(["COMPLETED", "FAILED"]);
const NOT_CANONICAL_MESSAGE = "not current for its model and source provenance";
const NOT_PREPARED_MESSAGE = "Audience rank boundaries are not prepared";
const ACTIVE_COMPUTE_CONFLICT_MESSAGE = "A compute job is already active";

const API_PATHS = {
  runs: "/api/audience/runs?limit=20&offset=0",
  options: (scoringRunId) => `/api/audience/options?scoring_run_id=${scoringRunId}`,
  prepare: (scoringRunId) => `/api/audience/runs/${scoringRunId}/prepare`,
  preparationStatus: (scoringRunId) => `/api/audience/runs/${scoringRunId}/preparation-status`,
  estimate: "/api/audience/estimate",
  search: "/api/audience/search",
  profile: "/api/audience/profile",
  job: (jobId) => `/api/jobs/${jobId}`,
  audiences: "/api/audiences?limit=20&offset=0",
  createAudience: "/api/audiences",
  audienceDetail: (audienceId) => `/api/audiences/${audienceId}`,
};

const PROFILE_DIMENSION_LABELS = {
  age_band: "Age band",
  individual_yearly_income_band: "Income band",
  family_member_count_band: "Family member count",
  gender: "Gender",
  state: "State",
  marital_status: "Marital status",
  education: "Education",
  employment_status: "Employment status",
  resident_status: "Resident status",
  resident_type: "Resident type",
  type_of_employment: "Type of employment",
};

const COMPARISON_LABELS = {
  selected_vs_universe: "Selected vs universe",
  selected_vs_historical_positives: "Selected vs historical known positives",
};

const CATEGORICAL_SELECTORS = {
  gender: "#audience-gender",
  state: "#audience-state",
  marital_status: "#audience-marital-status",
  education: "#audience-education",
  employment_status: "#audience-employment-status",
  resident_status: "#audience-resident-status",
  resident_type: "#audience-resident-type",
  type_of_employment: "#audience-type-of-employment",
};

let initialized = false;
let loadedOnce = false;
let activeScoringRunId = null;
let activeModelRunId = null;
let activeFilters = {};
let activeSelection = { mode: "ALL_MATCHING", target_count: null };
let activeEstimate = null;
let activeSearchCursor = null;
let activeHasMore = false;
let activeProfile = null;
let activeProfileDimension = "age_band";
let activeComparison = "selected_vs_universe";
let prepPollTimer = null;
let prepJobId = null;
let prepCandidateRun = null;
let lastPrepFailureMessage = "";
let staleReadOnly = false;
let selectedSavedAudienceDetail = null;
let inFlightSearch = false;
let inFlightProfile = false;

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", { detail: { state, text } }));
}

function clearPreparationPoll() {
  if (prepPollTimer !== null) {
    window.clearTimeout(prepPollTimer);
    prepPollTimer = null;
  }
}

function setScreenState(state) {
  const mapping = {
    loading: "#audience-explorer-loading",
    noRun: "#audience-explorer-no-run",
    prepNeeded: "#audience-explorer-prep-needed",
    prepRunning: "#audience-explorer-prep-running",
    prepFailed: "#audience-explorer-prep-failed",
    workspace: "#audience-explorer-workspace",
  };
  for (const [name, selector] of Object.entries(mapping)) {
    document.querySelector(selector).hidden = name !== state;
  }
}

function setAudienceAnnouncement(text) {
  document.querySelector("#audience-announcement").textContent = text;
}

function setLoadMoreStatus(text) {
  document.querySelector("#audience-load-more-status").textContent = text;
}

function showFormError(message) {
  const error = document.querySelector("#audience-form-error");
  error.textContent = message;
  error.hidden = false;
  error.focus();
}

function hideFormError() {
  document.querySelector("#audience-form-error").hidden = true;
}

function showSaveError(message) {
  const error = document.querySelector("#audience-save-error");
  error.textContent = message;
  error.hidden = false;
  error.focus();
}

function hideSaveError() {
  document.querySelector("#audience-save-error").hidden = true;
}

function selectedValues(selector) {
  return [...document.querySelector(selector).selectedOptions].map((option) => option.value);
}

function setSelectedValues(selector, values) {
  const selected = new Set(values || []);
  for (const option of document.querySelector(selector).options) {
    option.selected = selected.has(option.value);
  }
}

function createOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function formatScore(value) {
  return formatNumber(value);
}

function formatNumericMean(value) {
  return formatNumber(value);
}

function estimateScoreRangeText(estimate) {
  if (!estimate || estimate.score_min === null || estimate.score_max === null) {
    return "-";
  }
  return `${formatScore(estimate.score_min)} - ${formatScore(estimate.score_max)}`;
}

function updateSelectionModeState() {
  const mode = document.querySelector('input[name="audience_selection_mode"]:checked')?.value || "ALL_MATCHING";
  const targetInput = document.querySelector("#audience-target-count");
  targetInput.disabled = staleReadOnly || mode !== "TOP_N";
  if (mode !== "TOP_N") {
    targetInput.value = "";
  }
}

function parseOptionalNumber(selector, { integer = false } = {}) {
  const value = document.querySelector(selector).value.trim();
  if (!value) return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return Number.NaN;
  if (integer && !Number.isInteger(numeric)) return Number.NaN;
  return numeric;
}

function readFiltersFromForm() {
  return {
    score_min: parseOptionalNumber("#audience-score-min"),
    score_max: parseOptionalNumber("#audience-score-max"),
    top_percentile_max: parseOptionalNumber("#audience-top-percentile", { integer: true }),
    deciles: selectedValues("#audience-deciles").map((value) => Number(value)),
    rank_bands: selectedValues("#audience-rank-bands"),
    age_min: parseOptionalNumber("#audience-age-min", { integer: true }),
    age_max: parseOptionalNumber("#audience-age-max", { integer: true }),
    individual_yearly_income_min: parseOptionalNumber("#audience-income-min"),
    individual_yearly_income_max: parseOptionalNumber("#audience-income-max"),
    family_member_count_min: parseOptionalNumber("#audience-family-min", { integer: true }),
    family_member_count_max: parseOptionalNumber("#audience-family-max", { integer: true }),
    gender: selectedValues("#audience-gender"),
    state: selectedValues("#audience-state"),
    marital_status: selectedValues("#audience-marital-status"),
    education: selectedValues("#audience-education"),
    employment_status: selectedValues("#audience-employment-status"),
    resident_status: selectedValues("#audience-resident-status"),
    resident_type: selectedValues("#audience-resident-type"),
    type_of_employment: selectedValues("#audience-type-of-employment"),
  };
}

function readSelectionFromForm() {
  const mode = document.querySelector('input[name="audience_selection_mode"]:checked')?.value || "ALL_MATCHING";
  const targetCount = parseOptionalNumber("#audience-target-count", { integer: true });
  if (mode !== "TOP_N") {
    return { mode: "ALL_MATCHING", target_count: null };
  }
  return { mode: "TOP_N", target_count: targetCount };
}

function validateFiltersAndSelection(filters, selection) {
  if (staleReadOnly) {
    return "This stale saved audience is read-only until you reset to current canonical inputs.";
  }

  for (const [field, value] of Object.entries(filters)) {
    if (typeof value === "number" && Number.isNaN(value)) {
      return `${field.replaceAll("_", " ")} must be numeric.`;
    }
  }

  if (filters.score_min !== null && filters.score_max !== null && filters.score_min > filters.score_max) {
    return "Score min cannot exceed score max.";
  }
  if (filters.age_min !== null && filters.age_max !== null && filters.age_min > filters.age_max) {
    return "Age min cannot exceed age max.";
  }
  if (
    filters.individual_yearly_income_min !== null
    && filters.individual_yearly_income_max !== null
    && filters.individual_yearly_income_min > filters.individual_yearly_income_max
  ) {
    return "Income min cannot exceed income max.";
  }
  if (
    filters.family_member_count_min !== null
    && filters.family_member_count_max !== null
    && filters.family_member_count_min > filters.family_member_count_max
  ) {
    return "Family member count min cannot exceed max.";
  }

  if (filters.top_percentile_max !== null) {
    if (!Number.isInteger(filters.top_percentile_max) || filters.top_percentile_max < 1 || filters.top_percentile_max > 100) {
      return "Top percentile max must be an integer between 1 and 100.";
    }
  }

  if (selection.mode === "TOP_N") {
    if (!Number.isInteger(selection.target_count) || selection.target_count < 1) {
      return "Top N target count must be a positive whole number.";
    }
  }

  return null;
}

function setReadOnlyMode(enabled, message = "") {
  staleReadOnly = enabled;

  const filterForm = document.querySelector("#audience-filter-form");
  for (const control of filterForm.querySelectorAll("input, select, button")) {
    control.disabled = enabled;
  }

  const saveForm = document.querySelector("#audience-save-form");
  for (const control of saveForm.querySelectorAll("input, button")) {
    control.disabled = enabled;
  }

  document.querySelector("#audience-filter-reset").disabled = false;
  document.querySelector("#saved-audiences-refresh").disabled = false;
  document.querySelector("#saved-audience-reopen").disabled = false;
  document.querySelector("#saved-audience-use-campaign").disabled = true;

  const staleMessage = document.querySelector("#saved-audience-stale-message");
  if (enabled) {
    staleMessage.textContent = message || "This saved audience is stale and shown as read-only historical context.";
    staleMessage.hidden = false;
    setAudienceAnnouncement("Read-only stale saved audience loaded.");
    document.querySelector("#audience-save-status").textContent = "Read-only (stale saved audience).";
  } else {
    staleMessage.hidden = true;
  }

  updateSelectionModeState();
}

function resetEstimateView() {
  document.querySelector("#audience-estimate-matching").textContent = "-";
  document.querySelector("#audience-estimate-selected").textContent = "-";
  document.querySelector("#audience-estimate-score-range").textContent = "-";
  document.querySelector("#audience-estimate-score-mean").textContent = "-";
  document.querySelector("#audience-save-summary").textContent = "Selection summary will appear after estimate.";
}

function setSearchLoading(loading) {
  document.querySelector("#audience-search-loading").hidden = !loading;
}

function resetSearchResults() {
  document.querySelector("#audience-results-body").replaceChildren();
  document.querySelector("#audience-search-empty").hidden = true;
  document.querySelector("#audience-load-more").hidden = true;
  setLoadMoreStatus("");
  activeSearchCursor = null;
  activeHasMore = false;
}

function setContextHeader(run, options) {
  activeScoringRunId = run.scoring_run_id;
  activeModelRunId = run.model_run_id;

  document.querySelector("#audience-context-scoring-run").textContent = `#${formatNumber(run.scoring_run_id)}`;
  document.querySelector("#audience-context-model-run").textContent = `#${formatNumber(run.model_run_id)}`;
  document.querySelector("#audience-context-model-role").textContent = "BAGGING_PU";
  document.querySelector("#audience-context-population").textContent = formatNumber(options.population_count);
  document.querySelector("#audience-context-score-range").textContent = `${formatScore(options.score_summary?.score_min)} - ${formatScore(options.score_summary?.score_max)}`;
  document.querySelector("#audience-context-score-mean").textContent = formatScore(options.score_summary?.score_mean);

  const sourceVerified = document.querySelector("#audience-source-verified");
  setStatusBadge(sourceVerified, options.source_verified ? "OK" : "WARNING");
  sourceVerified.textContent = options.source_verified ? "Current source verified" : "Source verification warning";
}

function populateRankOptions(options) {
  const deciles = document.querySelector("#audience-deciles");
  deciles.replaceChildren();
  for (const value of options.rank_definitions?.deciles || []) {
    deciles.append(createOption(String(value), `Decile ${value}`));
  }

  const rankBands = document.querySelector("#audience-rank-bands");
  rankBands.replaceChildren();
  const bands = options.rank_definitions?.rank_bands || {};
  const orderedBands = ["ELITE", "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"];
  for (const band of orderedBands) {
    const range = bands[band];
    if (!range) continue;
    const label = `${band.replaceAll("_", " ")} (${range.start_percentile_bucket}-${range.end_percentile_bucket})`;
    rankBands.append(createOption(band, label));
  }
}

function populateCategoricalOptions(options) {
  for (const [field, selector] of Object.entries(CATEGORICAL_SELECTORS)) {
    const select = document.querySelector(selector);
    select.replaceChildren();
    for (const item of options.categorical_options?.[field] || []) {
      select.append(createOption(item.value, `${item.value} (${formatNumber(item.count)})`));
    }
  }
}

function applyRangeHints(options) {
  const ranges = options.numeric_ranges || {};
  const bindings = [
    ["#audience-age-min", ranges.age?.min],
    ["#audience-age-max", ranges.age?.max],
    ["#audience-income-min", ranges.individual_yearly_income?.min],
    ["#audience-income-max", ranges.individual_yearly_income?.max],
    ["#audience-family-min", ranges.family_member_count?.min],
    ["#audience-family-max", ranges.family_member_count?.max],
  ];
  for (const [selector, value] of bindings) {
    const element = document.querySelector(selector);
    element.placeholder = Number.isFinite(Number(value)) ? String(value) : "";
  }
}

function setFilterFormValues(filters, selection) {
  document.querySelector("#audience-score-min").value = filters.score_min ?? "";
  document.querySelector("#audience-score-max").value = filters.score_max ?? "";
  document.querySelector("#audience-top-percentile").value = filters.top_percentile_max ?? "";
  document.querySelector("#audience-age-min").value = filters.age_min ?? "";
  document.querySelector("#audience-age-max").value = filters.age_max ?? "";
  document.querySelector("#audience-income-min").value = filters.individual_yearly_income_min ?? "";
  document.querySelector("#audience-income-max").value = filters.individual_yearly_income_max ?? "";
  document.querySelector("#audience-family-min").value = filters.family_member_count_min ?? "";
  document.querySelector("#audience-family-max").value = filters.family_member_count_max ?? "";

  setSelectedValues("#audience-deciles", (filters.deciles || []).map((value) => String(value)));
  setSelectedValues("#audience-rank-bands", filters.rank_bands || []);

  for (const [field, selector] of Object.entries(CATEGORICAL_SELECTORS)) {
    setSelectedValues(selector, filters[field] || []);
  }

  const mode = selection.mode === "TOP_N" ? "TOP_N" : "ALL_MATCHING";
  const modeInput = document.querySelector(`input[name="audience_selection_mode"][value="${mode}"]`);
  if (modeInput) {
    modeInput.checked = true;
  }
  document.querySelector("#audience-target-count").value = selection.target_count ?? "";
  updateSelectionModeState();
}

function resetFormToEmpty() {
  setFilterFormValues(
    {
      score_min: null,
      score_max: null,
      top_percentile_max: null,
      deciles: [],
      rank_bands: [],
      age_min: null,
      age_max: null,
      individual_yearly_income_min: null,
      individual_yearly_income_max: null,
      family_member_count_min: null,
      family_member_count_max: null,
      gender: [],
      state: [],
      marital_status: [],
      education: [],
      employment_status: [],
      resident_status: [],
      resident_type: [],
      type_of_employment: [],
    },
    { mode: "ALL_MATCHING", target_count: null },
  );
}

function renderEstimate(estimate) {
  activeEstimate = estimate;
  activeFilters = estimate.normalized_filters;
  activeSelection = estimate.selection;

  document.querySelector("#audience-estimate-matching").textContent = formatNumber(estimate.matching_count);
  document.querySelector("#audience-estimate-selected").textContent = formatNumber(estimate.selected_count);
  document.querySelector("#audience-estimate-score-range").textContent = estimateScoreRangeText(estimate);
  document.querySelector("#audience-estimate-score-mean").textContent = formatScore(estimate.score_mean);

  const selectionText = estimate.selection.mode === "TOP_N"
    ? `Top ${formatNumber(estimate.selection.target_count)} of ${formatNumber(estimate.matching_count)} matching prospects.`
    : `All ${formatNumber(estimate.selected_count)} matching prospects.`;
  document.querySelector("#audience-save-summary").textContent = selectionText;
}

function activeFilterEntries(filters) {
  const entries = [];

  if (filters.score_min !== null) entries.push(["Score min", String(filters.score_min)]);
  if (filters.score_max !== null) entries.push(["Score max", String(filters.score_max)]);
  if (filters.top_percentile_max !== null) entries.push(["Top percentile", `<= ${filters.top_percentile_max}`]);
  if ((filters.deciles || []).length) entries.push(["Deciles", filters.deciles.join(", ")]);
  if ((filters.rank_bands || []).length) entries.push(["Rank bands", filters.rank_bands.join(", ")]);
  if (filters.age_min !== null) entries.push(["Age min", String(filters.age_min)]);
  if (filters.age_max !== null) entries.push(["Age max", String(filters.age_max)]);
  if (filters.individual_yearly_income_min !== null) {
    entries.push(["Income min", formatNumber(filters.individual_yearly_income_min)]);
  }
  if (filters.individual_yearly_income_max !== null) {
    entries.push(["Income max", formatNumber(filters.individual_yearly_income_max)]);
  }
  if (filters.family_member_count_min !== null) {
    entries.push(["Family min", String(filters.family_member_count_min)]);
  }
  if (filters.family_member_count_max !== null) {
    entries.push(["Family max", String(filters.family_member_count_max)]);
  }

  const categoricalLabels = {
    gender: "Gender",
    state: "State",
    marital_status: "Marital status",
    education: "Education",
    employment_status: "Employment status",
    resident_status: "Resident status",
    resident_type: "Resident type",
    type_of_employment: "Employment type",
  };

  for (const [field, label] of Object.entries(categoricalLabels)) {
    const values = filters[field] || [];
    if (!values.length) continue;
    entries.push([label, values.join(", ")]);
  }

  return entries;
}

function renderFilterSummary(filters, selection) {
  const chips = document.querySelector("#audience-filter-chips");
  chips.replaceChildren();

  const entries = activeFilterEntries(filters);
  for (const [label, value] of entries) {
    const chip = document.createElement("span");
    chip.className = "audience-chip";
    chip.textContent = `${label}: ${value}`;
    chips.append(chip);
  }

  const summary = document.querySelector("#audience-filter-summary-text");
  const selectionSummary = selection.mode === "TOP_N"
    ? `Selection: top ${formatNumber(selection.target_count)} matching prospects.`
    : "Selection: all matching prospects.";

  if (!entries.length) {
    summary.textContent = `No active filters. ${selectionSummary}`;
  } else {
    summary.textContent = `${entries.length} active filter${entries.length === 1 ? "" : "s"}. ${selectionSummary}`;
  }
}

function appendSearchCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = value;
  if (className) {
    cell.className = className;
  }
  row.append(cell);
}

function renderSearchRows(rows, { append = false } = {}) {
  const body = document.querySelector("#audience-results-body");
  if (!append) {
    body.replaceChildren();
  }

  for (const item of rows) {
    const row = document.createElement("tr");
    appendSearchCell(row, formatScore(item.propensity_score), "numeric");
    appendSearchCell(row, item.rank_band || "-");
    appendSearchCell(row, formatNumber(item.percentile_bucket), "numeric");
    appendSearchCell(row, formatNumber(item.decile), "numeric");
    appendSearchCell(row, item.person_id || "-");
    appendSearchCell(row, formatNumber(item.age), "numeric");
    appendSearchCell(row, item.gender || "Unknown/Other");
    appendSearchCell(row, item.state || "Unknown/Other");
    appendSearchCell(row, formatNumber(item.individual_yearly_income), "numeric");
    appendSearchCell(row, item.marital_status || "Unknown/Other");
    appendSearchCell(row, item.education || "Unknown/Other");
    appendSearchCell(row, item.employment_status || "Unknown/Other");
    appendSearchCell(row, item.resident_status || "Unknown/Other");
    appendSearchCell(row, item.resident_type || "Unknown/Other");
    appendSearchCell(row, formatNumber(item.family_member_count), "numeric");
    appendSearchCell(row, item.type_of_employment || "Unknown/Other");
    body.append(row);
  }
}

function renderTraitsRows(traits) {
  const body = document.querySelector("#audience-traits-body");
  body.replaceChildren();

  if (!traits.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-row";
    cell.textContent = "No over-indexed traits were identified for this selection.";
    row.append(cell);
    body.append(row);
    return;
  }

  for (const trait of traits) {
    const row = document.createElement("tr");
    appendSearchCell(row, COMPARISON_LABELS[trait.comparison] || trait.comparison);
    appendSearchCell(row, PROFILE_DIMENSION_LABELS[trait.dimension] || trait.dimension);
    appendSearchCell(row, trait.category || "Unknown/Other");
    appendSearchCell(row, formatPercent(trait.selected_share), "numeric");
    appendSearchCell(row, formatPercent(trait.reference_share), "numeric");
    appendSearchCell(row, formatNumber(trait.index), "numeric");
    body.append(row);
  }
}

function renderProfileComparisonBars(profilePayload) {
  const container = document.querySelector("#audience-profile-bars");
  container.replaceChildren();

  const rows = profilePayload?.comparisons?.[activeComparison]?.[activeProfileDimension] || [];
  const heading = document.querySelector("#audience-profile-summary");
  heading.textContent = `${COMPARISON_LABELS[activeComparison]} by ${PROFILE_DIMENSION_LABELS[activeProfileDimension]}`;

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "chart-empty-note";
    empty.textContent = "No comparison distribution data is available for this dimension.";
    container.append(empty);
    return;
  }

  const list = document.createElement("ol");
  list.className = "audience-comparison-list";
  list.setAttribute(
    "aria-label",
    `${COMPARISON_LABELS[activeComparison]} distribution for ${PROFILE_DIMENSION_LABELS[activeProfileDimension]}`,
  );

  for (const item of rows) {
    const entry = document.createElement("li");

    const top = document.createElement("div");
    top.className = "audience-comparison-head";
    const label = document.createElement("span");
    label.textContent = item.category || "Unknown/Other";
    const delta = document.createElement("strong");
    delta.textContent = `${formatPercent(item.selected_share)} vs ${formatPercent(item.reference_share)}`;
    top.append(label, delta);

    const selectedTrack = document.createElement("div");
    selectedTrack.className = "audience-comparison-track";
    const selectedFill = document.createElement("span");
    selectedFill.className = "audience-comparison-fill is-selected";
    selectedFill.style.width = `${Math.max(0, Math.min(100, Number(item.selected_share || 0) * 100))}%`;
    selectedTrack.append(selectedFill);

    const referenceTrack = document.createElement("div");
    referenceTrack.className = "audience-comparison-track";
    const referenceFill = document.createElement("span");
    referenceFill.className = "audience-comparison-fill is-reference";
    referenceFill.style.width = `${Math.max(0, Math.min(100, Number(item.reference_share || 0) * 100))}%`;
    referenceTrack.append(referenceFill);

    const note = document.createElement("small");
    const indexText = formatNumber(item.index);
    note.textContent = `Share-point delta: ${formatPercent(item.share_point_difference)} · Index: ${indexText}`;

    entry.append(top, selectedTrack, referenceTrack, note);
    list.append(entry);
  }

  container.append(list);
}

function renderProfileKpis(summary) {
  const universe = summary?.universe || {};
  const matching = summary?.matching || {};
  const selected = summary?.selected || {};
  const historicalPositives = summary?.historical_positives || {};

  document.querySelector("#audience-kpi-universe-count").textContent = formatNumber(universe.count);
  document.querySelector("#audience-kpi-matching-count").textContent = formatNumber(matching.count);
  document.querySelector("#audience-kpi-selected-count").textContent = formatNumber(selected.count);
  document.querySelector("#audience-kpi-positive-count").textContent = formatNumber(historicalPositives.count);
  document.querySelector("#audience-kpi-selected-age").textContent = formatNumericMean(selected.age_mean);
  document.querySelector("#audience-kpi-selected-income").textContent = formatNumber(
    Number.isFinite(Number(selected.individual_yearly_income_mean))
      ? Math.round(Number(selected.individual_yearly_income_mean))
      : null,
  );
  document.querySelector("#audience-kpi-selected-family").textContent = formatNumericMean(selected.family_member_count_mean);
  document.querySelector("#audience-kpi-selected-score").textContent = formatScore(selected.score_mean);
}

function renderProfile(profilePayload) {
  activeProfile = profilePayload;
  renderProfileKpis(profilePayload.summary || {});
  renderProfileComparisonBars(profilePayload);
  renderTraitsRows(profilePayload.top_overindexed_traits || []);
}

function renderSavedProfileSnapshot(profileSnapshot) {
  if (!profileSnapshot || typeof profileSnapshot !== "object") {
    return;
  }

  renderProfileKpis(profileSnapshot.summary || {});
  renderTraitsRows(profileSnapshot.top_overindexed_traits || []);

  const bars = document.querySelector("#audience-profile-bars");
  bars.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "chart-empty-note";
  empty.textContent = "Saved profile snapshot is available. Live comparison bars require current canonical inputs.";
  bars.append(empty);

  const summary = document.querySelector("#audience-profile-summary");
  summary.textContent = `Saved snapshot reference date: ${profileSnapshot.historical_reference_date || "-"}`;
}

function bootstrapProfileDimensionSelector() {
  const select = document.querySelector("#audience-profile-dimension");
  select.replaceChildren();
  for (const [value, label] of Object.entries(PROFILE_DIMENSION_LABELS)) {
    select.append(createOption(value, label));
  }
}

function setLoadMoreVisibility() {
  const button = document.querySelector("#audience-load-more");
  button.hidden = !activeHasMore;
}

async function runAudienceSearch({ append = false } = {}) {
  if (inFlightSearch || staleReadOnly || !activeScoringRunId) {
    return;
  }

  inFlightSearch = true;
  setSearchLoading(true);

  try {
    const payload = {
      scoring_run_id: activeScoringRunId,
      filters: activeFilters,
      page_size: DEFAULT_PAGE_SIZE,
    };
    if (append && activeSearchCursor) {
      payload.cursor = activeSearchCursor;
    }

    const response = await getJSON(API_PATHS.search, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    renderSearchRows(response.rows || [], { append });
    document.querySelector("#audience-search-empty").hidden = Boolean((response.rows || []).length || append);
    if (!append && !(response.rows || []).length) {
      document.querySelector("#audience-search-empty").hidden = false;
    }

    activeSearchCursor = response.next_cursor || null;
    activeHasMore = response.has_more === true;
    setLoadMoreVisibility();
    setLoadMoreStatus(activeHasMore ? "More results are available." : "End of results.");

    if (!append) {
      document.querySelector("#audience-results-title").focus();
    }

    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showError(
      document.querySelector("#audience-explorer-error"),
      document.querySelector("#audience-explorer-error-message"),
      error,
    );
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
    setLoadMoreStatus("Search could not be completed.");
  } finally {
    setSearchLoading(false);
    inFlightSearch = false;
  }
}

async function loadAudienceProfile() {
  if (staleReadOnly || !activeScoringRunId || inFlightProfile) {
    return;
  }

  inFlightProfile = true;
  document.querySelector("#audience-profile-summary").textContent = "Loading exact profile aggregates...";

  try {
    const response = await getJSON(API_PATHS.profile, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scoring_run_id: activeScoringRunId,
        filters: activeFilters,
        selection: activeSelection,
      }),
    });
    renderProfile(response);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showError(
      document.querySelector("#audience-explorer-error"),
      document.querySelector("#audience-explorer-error-message"),
      error,
    );
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    inFlightProfile = false;
  }
}

async function applyAudienceFilters(event) {
  event.preventDefault();
  hideFormError();
  hideSaveError();
  hideError(document.querySelector("#audience-explorer-error"));

  if (!activeScoringRunId) {
    showFormError("No active scoring run is available for Audience Explorer.");
    return;
  }

  const filters = readFiltersFromForm();
  const selection = readSelectionFromForm();
  const validation = validateFiltersAndSelection(filters, selection);
  if (validation) {
    showFormError(validation);
    return;
  }

  setAudienceAnnouncement("Applying audience filters.");
  setSearchLoading(true);
  document.querySelector("#audience-search-empty").hidden = true;

  try {
    const estimate = await getJSON(API_PATHS.estimate, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scoring_run_id: activeScoringRunId,
        filters,
        selection,
      }),
    });

    renderEstimate(estimate);
    renderFilterSummary(estimate.normalized_filters, estimate.selection);

    activeSearchCursor = null;
    activeHasMore = false;
    resetSearchResults();

    await runAudienceSearch({ append: false });
    loadAudienceProfile();

    setAudienceAnnouncement("Audience filters applied.");
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showFormError(error.message || "Audience estimate could not be computed.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setSearchLoading(false);
  }
}

function clearFilterChips() {
  if (staleReadOnly) {
    showFormError("This stale saved audience is read-only until you reset to current canonical inputs.");
    return;
  }

  resetFormToEmpty();
  renderFilterSummary(readFiltersFromForm(), readSelectionFromForm());
  setAudienceAnnouncement("Active filter chips cleared.");
}

function setPreparationRunningCopy(job) {
  const status = String(job?.status || "QUEUED").toLowerCase();
  const progress = Number(job?.progress_percent);
  const normalizedProgress = Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0;
  const progressText = `${formatNumber(normalizedProgress)}%`;
  const stage = job?.stage || "QUEUED";

  document.querySelector("#audience-prep-running-title").textContent = "Preparing audience rank boundaries";
  document.querySelector("#audience-prep-running-message").textContent = `Job #${formatNumber(job.job_id)} is ${status} at stage ${stage} (${progressText}).`;
}

function showPreparationFailed(message) {
  lastPrepFailureMessage = message || "Audience preparation could not be completed.";
  document.querySelector("#audience-prep-failed-message").textContent = lastPrepFailureMessage;
  setScreenState("prepFailed");
}

async function pollPreparationJob(jobId) {
  clearPreparationPoll();

  try {
    const job = await getJSON(API_PATHS.job(jobId));
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      prepJobId = null;
      if (job.status === "COMPLETED") {
        lastPrepFailureMessage = "";
        setAudienceAnnouncement("Audience preparation completed.");
        await loadAudienceExplorer(true);
      } else {
        const message = job.failure_message || "Audience preparation failed.";
        showPreparationFailed(message);
        dispatchBackendStatus("is-online", "Backend online");
      }
      return;
    }

    setScreenState("prepRunning");
    setPreparationRunningCopy(job);
    prepPollTimer = window.setTimeout(() => {
      pollPreparationJob(jobId);
    }, POLL_INTERVAL_MS);
  } catch (error) {
    showPreparationFailed(error.message || "Audience preparation status could not be loaded.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  }
}

async function submitPreparation() {
  hideError(document.querySelector("#audience-explorer-error"));
  hideFormError();

  if (!prepCandidateRun?.scoring_run_id) {
    showFormError("No scoring run is available to prepare.");
    return;
  }

  const submit = document.querySelector("#audience-prepare-submit");
  const retry = document.querySelector("#audience-prepare-retry");
  setButtonLoading(submit, true, "Submitting...");
  setButtonLoading(retry, true, "Retrying...");

  try {
    const job = await getJSON(API_PATHS.prepare(prepCandidateRun.scoring_run_id), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rank_contract_version: RANK_CONTRACT_VERSION }),
    });

    lastPrepFailureMessage = "";
    prepJobId = job.job_id;
    setScreenState("prepRunning");
    setPreparationRunningCopy(job);
    setAudienceAnnouncement(`Preparation job #${formatNumber(job.job_id)} accepted.`);
    await pollPreparationJob(job.job_id);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    const message = error.message || "Audience preparation could not be completed.";
    if (error.status === 409 && message.includes(ACTIVE_COMPUTE_CONFLICT_MESSAGE)) {
      showPreparationFailed("A compute job is already active. Retry after the active job completes.");
    } else if (error.status === 409 && message.includes("already exist")) {
      await loadAudienceExplorer(true);
    } else {
      showPreparationFailed(message);
    }
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(submit, false, "Submitting...");
    setButtonLoading(retry, false, "Retrying...");
  }
}

async function loadPreparationStatus(scoringRunId) {
  return getJSON(API_PATHS.preparationStatus(scoringRunId));
}

async function resolveCanonicalRun(runs, force = false) {
  if (!Array.isArray(runs) || runs.length === 0) {
    return { type: "no-run" };
  }

  const readyRun = runs.find((run) => run?.ready_for_current_audience_actions === true);
  if (readyRun) {
    try {
      const options = await getCachedJSON(API_PATHS.options(readyRun.scoring_run_id), {
        maxAgeMs: SCORING_RUN_BOUND_OPTIONS_CACHE_MS,
        force,
      });
      return { type: "ready", run: readyRun, options };
    } catch (error) {
      return { type: "error", error };
    }
  }

  const canonicalCandidates = runs.filter((run) => run?.is_canonical === true);
  if (!canonicalCandidates.length) {
    return { type: "no-run" };
  }

  const run = canonicalCandidates[0];
  try {
    const status = await loadPreparationStatus(run.scoring_run_id);
    if (status.ready_for_current_audience_actions === true) {
      const options = await getCachedJSON(API_PATHS.options(run.scoring_run_id), {
        maxAgeMs: SCORING_RUN_BOUND_OPTIONS_CACHE_MS,
        force: true,
      });
      return { type: "ready", run, options };
    }

    if (status.active_job && !TERMINAL_JOB_STATUSES.has(status.active_job.status)) {
      return { type: "prep-running", run, status };
    }

    if (lastPrepFailureMessage) {
      return {
        type: "prep-failed",
        run,
        message: lastPrepFailureMessage,
      };
    }

    if (status.prepared) {
      return { type: "no-run" };
    }

    return { type: "prep-needed", run, status };
  } catch (error) {
    const lowered = String(error.message || "").toLowerCase();
    if (error.status === 409 && lowered.includes(NOT_PREPARED_MESSAGE.toLowerCase())) {
      return { type: "prep-needed", run, status: null };
    }
    if (error.status === 409 && lowered.includes(NOT_CANONICAL_MESSAGE.toLowerCase())) {
      return { type: "no-run" };
    }
    if (error.status === 404) {
      return { type: "no-run" };
    }
    return { type: "error", error };
  }
}

function resetWorkspaceData() {
  activeEstimate = null;
  activeFilters = {};
  activeSelection = { mode: "ALL_MATCHING", target_count: null };
  activeSearchCursor = null;
  activeHasMore = false;
  activeProfile = null;
  resetEstimateView();
  resetSearchResults();
  renderTraitsRows([]);
  document.querySelector("#audience-profile-bars").replaceChildren();
  document.querySelector("#audience-profile-summary").textContent = "";
  document.querySelector("#saved-audience-detail").hidden = true;
  selectedSavedAudienceDetail = null;
  document.querySelector("#audience-save-status").textContent = "Not saved.";
}

async function bootstrapReadyWorkspace(run, options) {
  setContextHeader(run, options);
  populateRankOptions(options);
  populateCategoricalOptions(options);
  applyRangeHints(options);
  resetWorkspaceData();
  resetFormToEmpty();
  renderFilterSummary(readFiltersFromForm(), readSelectionFromForm());
  setReadOnlyMode(false);
  setScreenState("workspace");
  setAudienceAnnouncement("Audience Explorer ready.");

  await applyAudienceFilters(new Event("submit"));
}

async function loadSavedAudiences(force = false) {
  const loading = document.querySelector("#saved-audience-list-loading");
  const empty = document.querySelector("#saved-audience-list-empty");
  const list = document.querySelector("#saved-audience-list");

  loading.hidden = false;
  empty.hidden = true;

  try {
    const audiences = await getCachedJSON(API_PATHS.audiences, { maxAgeMs: 20_000, force });
    list.replaceChildren();

    if (!audiences.length) {
      empty.hidden = false;
      return;
    }

    for (const item of audiences) {
      const row = document.createElement("article");
      row.className = "saved-audience-item";

      const heading = document.createElement("div");
      heading.className = "saved-audience-item-heading";
      const name = document.createElement("strong");
      name.textContent = item.audience_name;
      const badge = document.createElement("span");
      badge.className = "status-badge";
      setStatusBadge(badge, item.is_current ? "COMPLETED" : "WARNING");
      badge.textContent = item.is_current
        ? "CURRENT - usable in Campaign Builder"
        : "STALE - historical/read-only";
      heading.append(name, badge);

      const meta = document.createElement("p");
      meta.className = "saved-audience-meta";
      const mode = item.selection_mode === "TOP_N"
        ? `Top ${formatNumber(item.target_count || 0)}`
        : "All matching";
      meta.textContent = `${formatDate(item.created_at, true)} · ${formatNumber(item.resolved_count)} selected · ${mode}`;

      const actions = document.createElement("div");
      actions.className = "saved-audience-item-actions";
      const viewButton = document.createElement("button");
      viewButton.type = "button";
      viewButton.className = "button button-secondary recent-reopen";
      viewButton.textContent = "View";
      viewButton.addEventListener("click", () => viewSavedAudience(item.audience_id, viewButton));
      actions.append(viewButton);

      row.append(heading, meta, actions);
      list.append(row);
    }
  } finally {
    loading.hidden = true;
  }
}

function renderSavedAudienceDetail(detail) {
  selectedSavedAudienceDetail = detail;
  const panel = document.querySelector("#saved-audience-detail");
  panel.hidden = false;

  document.querySelector("#saved-audience-detail-title").textContent = detail.audience_name;
  const mode = detail.definition.selection_mode === "TOP_N"
    ? `Top ${formatNumber(detail.definition.target_count || 0)}`
    : "All matching";
  document.querySelector("#saved-audience-detail-meta").textContent = `${formatDate(detail.created_at, true)} · ${formatNumber(detail.definition.resolved_count)} selected · ${mode}`;

  const currentness = document.querySelector("#saved-audience-currentness");
  setStatusBadge(currentness, detail.currentness?.is_current ? "COMPLETED" : "WARNING");
  currentness.textContent = detail.currentness?.is_current
    ? "CURRENT - usable in Campaign Builder"
    : "STALE - historical/read-only";

  const staleMessage = document.querySelector("#saved-audience-stale-message");
  if (detail.currentness?.is_current) {
    staleMessage.hidden = true;
  } else {
    staleMessage.textContent = detail.currentness.issues?.[0] || "Saved audience is stale.";
    staleMessage.hidden = false;
  }
}

async function viewSavedAudience(audienceId, button) {
  hideSaveError();
  hideFormError();

  setButtonLoading(button, true, "Opening...");
  try {
    const detail = await getJSON(API_PATHS.audienceDetail(audienceId));
    renderSavedAudienceDetail(detail);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showError(
      document.querySelector("#audience-explorer-error"),
      document.querySelector("#audience-explorer-error-message"),
      error,
    );
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(button, false, "Opening...");
  }
}

async function reopenSavedAudience() {
  hideFormError();
  hideSaveError();

  if (!selectedSavedAudienceDetail) {
    showFormError("Choose a saved audience to reopen.");
    return;
  }

  const detail = selectedSavedAudienceDetail;
  const filters = detail.definition?.filters || {};
  const selection = detail.definition?.selection || { mode: "ALL_MATCHING", target_count: null };

  setFilterFormValues(filters, selection);

  if (!detail.currentness?.is_current) {
    setReadOnlyMode(true, detail.currentness.issues?.[0]);
    renderSavedProfileSnapshot(detail.profile_snapshot);
    resetSearchResults();
    document.querySelector("#audience-search-empty").hidden = false;
    document.querySelector("#audience-search-empty h3").textContent = "Stale saved audience loaded";
    document.querySelector("#audience-search-empty p").textContent = "This definition is read-only historical context until current inputs are resolved.";
    setAudienceAnnouncement("Loaded stale saved audience in read-only mode.");
    return;
  }

  setReadOnlyMode(false);

  if (detail.definition.scoring_run_id !== activeScoringRunId) {
    const runs = await getCachedJSON(API_PATHS.runs, { maxAgeMs: RUN_SUMMARY_CACHE_MS, force: true });
    const matchingRun = runs.find((run) => run.scoring_run_id === detail.definition.scoring_run_id);
    if (!matchingRun) {
      showFormError("Saved audience scoring run is no longer available.");
      return;
    }

    const options = await getCachedJSON(API_PATHS.options(matchingRun.scoring_run_id), {
      maxAgeMs: SCORING_RUN_BOUND_OPTIONS_CACHE_MS,
      force: true,
    });
    setContextHeader(matchingRun, options);
    populateRankOptions(options);
    populateCategoricalOptions(options);
    applyRangeHints(options);
  }

  await applyAudienceFilters(new Event("submit"));
  setAudienceAnnouncement("Saved audience definition reopened.");
}

async function submitSaveAudience(event) {
  event.preventDefault();
  hideSaveError();
  hideError(document.querySelector("#audience-explorer-error"));

  if (staleReadOnly) {
    showSaveError("This stale saved audience is read-only and cannot be saved again.");
    return;
  }

  if (!activeScoringRunId) {
    showSaveError("No active scoring run is available.");
    return;
  }

  const nameInput = document.querySelector("#audience-save-name");
  const descriptionInput = document.querySelector("#audience-save-description");
  const audienceName = nameInput.value.trim();
  const description = descriptionInput.value.trim();

  if (!audienceName) {
    showSaveError("Audience name is required.");
    return;
  }

  if (!activeEstimate || !activeFilters || !activeSelection) {
    showSaveError("Apply filters first so selection count and profile can be saved.");
    return;
  }

  const submit = document.querySelector("#audience-save-submit");
  setButtonLoading(submit, true, "Saving...");
  document.querySelector("#audience-save-status").textContent = "Saving audience...";

  try {
    const saved = await getJSON(API_PATHS.createAudience, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audience_name: audienceName,
        description: description || null,
        scoring_run_id: activeScoringRunId,
        filters: activeFilters,
        selection: activeSelection,
        include_profile_snapshot: true,
      }),
    });

    document.querySelector("#audience-save-status").textContent = `Saved audience #${formatNumber(saved.audience_id)}.`;
    clearCachedJSON(API_PATHS.audiences);
    await loadSavedAudiences(true);
    renderSavedAudienceDetail(saved);
    nameInput.value = "";
    descriptionInput.value = "";
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showSaveError(error.message || "Audience could not be saved.");
    document.querySelector("#audience-save-status").textContent = "Save failed.";
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(submit, false, "Saving...");
  }
}

function updatePreparationCandidate(run) {
  prepCandidateRun = run;
}

async function enterPreparationState(run, { status = null, failed = false, message = "" } = {}) {
  updatePreparationCandidate(run);

  if (failed) {
    showPreparationFailed(message || "Audience preparation failed.");
    return;
  }

  if (status?.active_job && !TERMINAL_JOB_STATUSES.has(status.active_job.status)) {
    setScreenState("prepRunning");
    setPreparationRunningCopy(status.active_job);
    prepJobId = status.active_job.job_id;
    prepPollTimer = window.setTimeout(() => {
      pollPreparationJob(status.active_job.job_id);
    }, POLL_INTERVAL_MS);
    return;
  }

  setScreenState("prepNeeded");
  setAudienceAnnouncement("Audience rank preparation is required before exploring results.");
}

function clearAudienceErrorBanner() {
  hideError(document.querySelector("#audience-explorer-error"));
}

async function loadAudienceWorkspace(force = false) {
  clearAudienceErrorBanner();
  hideFormError();
  hideSaveError();
  clearPreparationPoll();

  setScreenState("loading");
  setButtonLoading(document.querySelector("#audience-explorer-refresh"), true, "Refreshing...");

  try {
    const [runsResult] = await Promise.allSettled([
      getCachedJSON(API_PATHS.runs, { maxAgeMs: RUN_SUMMARY_CACHE_MS, force }),
      loadSavedAudiences(force),
    ]);

    if (runsResult.status === "rejected") {
      showError(
        document.querySelector("#audience-explorer-error"),
        document.querySelector("#audience-explorer-error-message"),
        runsResult.reason,
      );
      setScreenState("noRun");
      dispatchBackendStatus("is-offline", "Backend unavailable");
      return;
    }

    const resolution = await resolveCanonicalRun(runsResult.value, force);

    if (resolution.type === "no-run") {
      setScreenState("noRun");
      setAudienceAnnouncement("No current canonical scored run is available.");
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    if (resolution.type === "prep-needed") {
      await enterPreparationState(resolution.run, { status: resolution.status });
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    if (resolution.type === "prep-running") {
      await enterPreparationState(resolution.run, { status: resolution.status });
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    if (resolution.type === "prep-failed") {
      await enterPreparationState(resolution.run, {
        failed: true,
        message: resolution.message,
      });
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    if (resolution.type === "error") {
      showError(
        document.querySelector("#audience-explorer-error"),
        document.querySelector("#audience-explorer-error-message"),
        resolution.error,
      );
      setScreenState("noRun");
      dispatchBackendStatus(
        resolution.error.status && resolution.error.status < 500 ? "is-online" : "is-offline",
        resolution.error.status && resolution.error.status < 500 ? "Backend online" : "Backend unavailable",
      );
      return;
    }

    if (resolution.type === "ready") {
      await bootstrapReadyWorkspace(resolution.run, resolution.options);
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }
  } finally {
    setButtonLoading(document.querySelector("#audience-explorer-refresh"), false, "Refreshing...");
  }
}

function initializeTablist(selector, dataAttribute, onActivate) {
  const buttons = [...document.querySelectorAll(`${selector} [role="tab"]`)];

  function activate(button) {
    for (const candidate of buttons) {
      const selected = candidate === button;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
    }
    onActivate(button.dataset[dataAttribute]);
  }

  buttons.forEach((button, index) => {
    button.addEventListener("click", () => activate(button));
    button.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = buttons.length - 1;

      if (nextIndex !== null) {
        event.preventDefault();
        activate(buttons[nextIndex]);
        buttons[nextIndex].focus();
      }
    });
  });
}

function resetFromStaleMode() {
  setReadOnlyMode(false);
  document.querySelector("#saved-audience-stale-message").hidden = true;
  document.querySelector("#audience-search-empty h3").textContent = "No prospects match current filters";
  document.querySelector("#audience-search-empty p").textContent = "Adjust score, rank, or demographic filters and try again.";
}

function handleFilterReset() {
  hideFormError();
  hideSaveError();
  resetFromStaleMode();
  resetFormToEmpty();
  renderFilterSummary(readFiltersFromForm(), readSelectionFromForm());
  resetEstimateView();
  resetSearchResults();
  setAudienceAnnouncement("Filters reset.");
}

export async function loadAudienceExplorer(force = false) {
  if (loadedOnce && !force) {
    return;
  }
  loadedOnce = true;
  await loadAudienceWorkspace(force);
}

export function initializeAudienceExplorer() {
  if (initialized) return;
  initialized = true;

  bootstrapProfileDimensionSelector();
  resetEstimateView();
  setAudienceAnnouncement("Ready to explore.");
  setLoadMoreStatus("");

  document.querySelector("#audience-filter-form").addEventListener("submit", applyAudienceFilters);
  document.querySelector("#audience-filter-reset").addEventListener("click", handleFilterReset);
  document.querySelector("#audience-clear-filter-chips").addEventListener("click", clearFilterChips);
  document.querySelector("#audience-load-more").addEventListener("click", () => runAudienceSearch({ append: true }));
  document.querySelector("#audience-explorer-refresh").addEventListener("click", () => loadAudienceWorkspace(true));
  document.querySelector("#audience-explorer-retry").addEventListener("click", () => loadAudienceWorkspace(true));
  document.querySelector("#audience-prepare-submit").addEventListener("click", submitPreparation);
  document.querySelector("#audience-prepare-retry").addEventListener("click", submitPreparation);
  document.querySelector("#audience-save-form").addEventListener("submit", submitSaveAudience);
  document.querySelector("#saved-audiences-refresh").addEventListener("click", async () => {
    clearCachedJSON(API_PATHS.audiences);
    await loadSavedAudiences(true);
  });
  document.querySelector("#saved-audience-reopen").addEventListener("click", reopenSavedAudience);
  document.querySelector("#audience-profile-dimension").addEventListener("change", () => {
    activeProfileDimension = document.querySelector("#audience-profile-dimension").value;
    if (activeProfile) {
      renderProfileComparisonBars(activeProfile);
    }
  });

  for (const input of document.querySelectorAll('input[name="audience_selection_mode"]')) {
    input.addEventListener("change", updateSelectionModeState);
  }

  initializeTablist("#audience-profile-comparison-tabs", "audienceProfileComparison", (value) => {
    activeComparison = value;
    if (activeProfile) {
      renderProfileComparisonBars(activeProfile);
    }
  });
}
