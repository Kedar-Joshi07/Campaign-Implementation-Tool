import { getCachedJSON, getJSON } from "./api.js";
import {
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  hideError,
  setButtonLoading,
  setStatusBadge,
  showError,
} from "./ui.js";

const FILTER_FIELDS = {
  campaign_ids: { selector: "#campaign-filter", maximum: 25 },
  product_ids: { selector: "#product-filter", maximum: 50 },
  product_categories: { selector: "#product-category-filter", maximum: 25 },
  campaign_channels: { selector: "#channel-filter", maximum: 20 },
  campaign_types: { selector: "#campaign-type-filter", maximum: 20 },
};

const CONVERSION_HELP = {
  ATTRIBUTED_PURCHASE: "Confirmed attributed purchasers are known positive.",
  ANY_PURCHASE: "Any observed purchaser inside the selected cohort is known positive.",
  RESPONSE: "Any responder inside the selected cohort is known positive.",
};

const PROFILE_DIMENSIONS = {
  age_band: "Age band",
  gender: "Gender",
  state: "State",
  individual_income_band: "Individual income band",
  marital_status: "Marital status",
  education: "Education",
  employment_status: "Employment status",
  resident_status: "Resident status",
  resident_type: "Resident type",
  family_member_count_band: "Family member count",
  type_of_employment: "Type of employment",
};

const PROFILE_GROUP_LABELS = {
  selected: "Selected customers",
  positive: "Known-positive customers",
  unlabeled: "Unlabeled customers",
  historical_baseline: "Historical-customer baseline",
};

const BREAKDOWN_LABELS = {
  channel_performance: "Campaign channels",
  product_category_performance: "Product categories",
  top_campaigns: "Top campaigns",
  top_products: "Top products",
};

let initialized = false;
let loadedOnce = false;
let analysisRunning = false;
let optionsSnapshot = null;
let currentResult = null;
let activeBreakdown = "channel_performance";
let activeProfileGroup = "selected";

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", { detail: { state, text } }));
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

function populateSelect(selector, items, valueKey, labelBuilder) {
  const select = document.querySelector(selector);
  select.replaceChildren();
  for (const item of items) {
    const value = valueKey ? item[valueKey] : item;
    select.append(createOption(value, labelBuilder(item)));
  }
}

function populateFilterOptions(options) {
  populateSelect(
    "#campaign-filter",
    options.campaigns,
    "campaign_id",
    (item) => `${item.campaign_id} · ${item.campaign_name}`,
  );
  populateSelect(
    "#product-filter",
    options.products,
    "product_id",
    (item) => `${item.product_id} · ${item.product_name} · ${item.product_category}`,
  );
  populateSelect("#product-category-filter", options.product_categories, null, (item) => item);
  populateSelect("#channel-filter", options.campaign_channels, null, (item) => item);
  populateSelect("#campaign-type-filter", options.campaign_types, null, (item) => item);
}

function renderConversionDefinitions(definitions) {
  const container = document.querySelector("#conversion-definition-options");
  container.replaceChildren();
  for (const definition of definitions) {
    const label = document.createElement("label");
    label.className = "conversion-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "conversion_definition";
    input.value = definition.value;
    input.id = `conversion-${definition.value.toLowerCase().replaceAll("_", "-")}`;
    const copy = document.createElement("span");
    const heading = document.createElement("strong");
    heading.textContent = definition.label;
    const description = document.createElement("small");
    description.textContent = CONVERSION_HELP[definition.value] || definition.description;
    copy.append(heading, description);
    label.append(input, copy);
    container.append(label);
  }
}

function applyFiltersToForm(filters, analysisName = "") {
  document.querySelector("#analysis-name").value = analysisName || "";
  for (const [field, config] of Object.entries(FILTER_FIELDS)) {
    setSelectedValues(config.selector, filters[field]);
  }
  document.querySelector("#contact-date-from").value = filters.contact_date_from || "";
  document.querySelector("#contact-date-to").value = filters.contact_date_to || "";
  document.querySelector("#contacted-only").checked = filters.contacted_only !== false;
  const conversion = document.querySelector(
    `input[name="conversion_definition"][value="${filters.conversion_definition}"]`,
  );
  if (conversion) conversion.checked = true;
}

function resetToDefaults() {
  if (!optionsSnapshot) return;
  applyFiltersToForm(optionsSnapshot.defaults);
  hideFormError();
  document.querySelector("#analysis-run-announcement").textContent = "Defaults restored.";
}

function showFormError(message) {
  const error = document.querySelector("#historical-form-error");
  error.textContent = message;
  error.hidden = false;
  error.focus();
}

function hideFormError() {
  document.querySelector("#historical-form-error").hidden = true;
}

function validateForm() {
  const name = document.querySelector("#analysis-name").value.trim();
  if (name.length > 120) return "Analysis name must be 120 characters or fewer.";
  const dateFrom = document.querySelector("#contact-date-from").value;
  const dateTo = document.querySelector("#contact-date-to").value;
  if (!dateFrom || !dateTo) return "Choose both inclusive contact dates.";
  if (dateFrom > dateTo) return "Contact date from must be on or before contact date to.";
  if (
    optionsSnapshot
    && (dateFrom < optionsSnapshot.available_date_from || dateTo > optionsSnapshot.available_date_to)
  ) {
    return `Choose dates from ${optionsSnapshot.available_date_from} through ${optionsSnapshot.available_date_to}.`;
  }
  for (const [field, config] of Object.entries(FILTER_FIELDS)) {
    if (selectedValues(config.selector).length > config.maximum) {
      const label = field.replaceAll("_", " ");
      return `Choose no more than ${config.maximum} ${label}.`;
    }
  }
  if (!document.querySelector('input[name="conversion_definition"]:checked')) {
    return "Choose a known-positive definition.";
  }
  return null;
}

function analysisPayload() {
  const name = document.querySelector("#analysis-name").value.trim();
  return {
    analysis_name: name || null,
    campaign_ids: selectedValues("#campaign-filter"),
    product_ids: selectedValues("#product-filter"),
    product_categories: selectedValues("#product-category-filter"),
    campaign_channels: selectedValues("#channel-filter"),
    campaign_types: selectedValues("#campaign-type-filter"),
    contact_date_from: document.querySelector("#contact-date-from").value,
    contact_date_to: document.querySelector("#contact-date-to").value,
    contacted_only: document.querySelector("#contacted-only").checked,
    conversion_definition: document.querySelector('input[name="conversion_definition"]:checked').value,
  };
}

function setAnalysisRunning(running) {
  analysisRunning = running;
  const button = document.querySelector("#analyze-population");
  setButtonLoading(button, running, "Analyzing population…");
  document.querySelector("#historical-analysis-form").setAttribute("aria-busy", String(running));
  const results = document.querySelector("#historical-analysis-results");
  const runningState = document.querySelector("#analysis-running-state");
  const content = document.querySelector("#analysis-results-content");
  if (running) {
    results.hidden = false;
    runningState.hidden = false;
    content.hidden = true;
    document.querySelector("#analysis-run-announcement").textContent = "Analysis is running.";
  } else {
    runningState.hidden = true;
    content.hidden = currentResult === null;
  }
}

function createCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function appendEmptyTableRow(body, message, columns) {
  const row = document.createElement("tr");
  row.className = "empty-row";
  const cell = createCell(message);
  cell.colSpan = columns;
  row.append(cell);
  body.append(row);
}

function renderMonthlyRows(rows) {
  const body = document.querySelector("#analysis-monthly-body");
  body.replaceChildren();
  if (!rows.length) {
    appendEmptyTableRow(body, "No monthly performance is available.", 5);
    return;
  }
  for (const item of rows) {
    const row = document.createElement("tr");
    row.append(
      createCell(item.month || "Unknown/Other"),
      createCell(formatNumber(item.observation_count), "numeric"),
      createCell(formatNumber(item.response_count), "numeric"),
      createCell(formatNumber(item.purchase_count), "numeric"),
      createCell(formatNumber(item.attributed_purchase_count), "numeric"),
    );
    body.append(row);
  }
}

function breakdownItemLabel(item) {
  if (activeBreakdown === "top_campaigns") {
    return `${item.campaign_name || "Unknown campaign"} · ${item.campaign_id}`;
  }
  if (activeBreakdown === "top_products") {
    return `${item.product_name || "Unknown product"} · ${item.product_id}`;
  }
  return item.label || "Unknown/Other";
}

function renderBreakdown() {
  const list = document.querySelector("#analysis-breakdown-bars");
  list.replaceChildren();
  if (!currentResult) return;
  const rows = currentResult[activeBreakdown] || [];
  list.setAttribute("aria-label", BREAKDOWN_LABELS[activeBreakdown]);
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.className = "chart-empty-note";
    empty.textContent = "No performance breakdown is available.";
    list.append(empty);
    return;
  }
  const maximum = Math.max(...rows.map((item) => Number(item.observation_count) || 0), 1);
  for (const item of rows) {
    const row = document.createElement("li");
    row.className = "performance-bar-row";
    const heading = document.createElement("div");
    heading.className = "performance-bar-heading";
    const label = document.createElement("span");
    label.className = "performance-bar-label";
    label.textContent = breakdownItemLabel(item);
    label.title = label.textContent;
    const value = document.createElement("strong");
    value.textContent = formatNumber(item.observation_count);
    heading.append(label, value);
    const track = document.createElement("div");
    track.className = "performance-bar-track";
    const fill = document.createElement("span");
    fill.className = "performance-bar-fill";
    fill.style.width = `${Math.max(2, (item.observation_count / maximum) * 100)}%`;
    fill.setAttribute("aria-hidden", "true");
    track.append(fill);
    const context = document.createElement("small");
    context.textContent = `${formatNumber(item.response_count)} responses · ${formatNumber(item.purchase_count)} purchases · ${formatCurrency(item.net_sales_amount)} net sales`;
    row.append(heading, track, context);
    list.append(row);
  }
}

function renderProfile() {
  const chart = document.querySelector("#profile-chart");
  const summary = document.querySelector("#profile-group-summary");
  chart.replaceChildren();
  if (!currentResult?.profiles) return;
  const dimension = document.querySelector("#profile-dimension").value;
  const profile = currentResult.profiles[activeProfileGroup]?.[dimension];
  if (!profile) {
    summary.textContent = "Profile data is unavailable.";
    return;
  }
  summary.textContent = `${PROFILE_GROUP_LABELS[activeProfileGroup]} · ${formatNumber(profile.group_count)} customers · ${PROFILE_DIMENSIONS[dimension]}`;
  const list = document.createElement("ol");
  list.className = "profile-bars";
  list.setAttribute("aria-label", `${PROFILE_GROUP_LABELS[activeProfileGroup]} by ${PROFILE_DIMENSIONS[dimension]}`);
  if (!profile.categories.length) {
    const empty = document.createElement("li");
    empty.className = "chart-empty-note";
    empty.textContent = "No profile categories are available.";
    list.append(empty);
  }
  for (const category of profile.categories) {
    const item = document.createElement("li");
    const heading = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = category.label || "Unknown/Other";
    const value = document.createElement("strong");
    value.textContent = `${formatNumber(category.count)} · ${formatPercent(category.share)}`;
    heading.append(label, value);
    const track = document.createElement("div");
    track.className = "profile-bar-track";
    const fill = document.createElement("span");
    fill.className = "profile-bar-fill";
    fill.style.width = `${Math.max(category.share > 0 ? 2 : 0, category.share * 100)}%`;
    fill.setAttribute("aria-hidden", "true");
    track.append(fill);
    item.append(heading, track);
    list.append(item);
  }
  chart.append(list);
}

function addNormalizedFilter(container, label, value) {
  const group = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  group.append(term, description);
  container.append(group);
}

function renderNormalizedFilters(filters) {
  const list = document.querySelector("#normalized-filter-list");
  list.replaceChildren();
  addNormalizedFilter(list, "Campaigns", filters.campaign_ids.join(", ") || "All campaigns");
  addNormalizedFilter(list, "Products", filters.product_ids.join(", ") || "All products");
  addNormalizedFilter(list, "Categories", filters.product_categories.join(", ") || "All categories");
  addNormalizedFilter(list, "Channels", filters.campaign_channels.join(", ") || "All channels");
  addNormalizedFilter(list, "Campaign types", filters.campaign_types.join(", ") || "All campaign types");
  addNormalizedFilter(list, "Contact dates", `${formatDate(filters.contact_date_from)} — ${formatDate(filters.contact_date_to)}`);
  addNormalizedFilter(list, "Exposure", filters.contacted_only ? "Contacted observations only" : "All matching observations");
  addNormalizedFilter(list, "Positive definition", filters.conversion_definition.replaceAll("_", " "));
}

function renderAnalysisResult(result, { focus = true } = {}) {
  if (result.status !== "COMPLETED" || !result.summary) {
    showFormError(result.failure_message || "The saved historical analysis could not be completed.");
    return;
  }
  currentResult = result;
  const summary = result.summary;
  document.querySelector("#analysis-results-name").textContent = result.analysis_name;
  document.querySelector("#analysis-run-id").textContent = `#${formatNumber(result.analysis_run_id)}`;
  document.querySelector("#result-run-id").textContent = `#${formatNumber(result.analysis_run_id)}`;
  setStatusBadge(document.querySelector("#analysis-results-status"), result.status);
  document.querySelector("#result-observations").textContent = formatNumber(summary.observation_count);
  document.querySelector("#result-selected").textContent = formatNumber(summary.selected_customer_count);
  document.querySelector("#result-positive").textContent = formatNumber(summary.positive_customer_count);
  document.querySelector("#result-unlabeled").textContent = formatNumber(summary.unlabeled_customer_count);
  document.querySelector("#result-positive-rate").textContent = formatPercent(summary.positive_customer_rate);
  document.querySelector("#result-net-sales").textContent = formatCurrency(summary.net_sales_amount);
  document.querySelector("#result-gross-margin").textContent = formatCurrency(summary.gross_margin_amount);
  renderNormalizedFilters(result.filters);
  renderMonthlyRows(result.monthly_trend || []);
  renderBreakdown();
  renderProfile();
  applyFiltersToForm(result.filters, result.analysis_name);
  setAnalysisRunning(false);
  document.querySelector("#historical-analysis-results").hidden = false;
  document.querySelector("#analysis-results-content").hidden = false;
  document.querySelector("#analysis-run-announcement").textContent = `Analysis run ${result.analysis_run_id} completed.`;
  if (focus) document.querySelector("#analysis-results-title").focus();
}

function conversionLabel(value) {
  return {
    ATTRIBUTED_PURCHASE: "Attributed purchase",
    ANY_PURCHASE: "Any purchase",
    RESPONSE: "Response",
  }[value] || value;
}

function renderRecentAnalyses(items) {
  const loading = document.querySelector("#recent-analyses-loading");
  const empty = document.querySelector("#recent-analyses-empty");
  const table = document.querySelector("#recent-analyses-table");
  const body = document.querySelector("#recent-analyses-body");
  loading.hidden = true;
  body.replaceChildren();
  if (!items.length) {
    empty.hidden = false;
    table.hidden = true;
    return;
  }
  empty.hidden = true;
  table.hidden = false;
  for (const item of items) {
    const row = document.createElement("tr");
    const identity = document.createElement("td");
    const name = document.createElement("strong");
    name.textContent = item.analysis_name;
    const metadata = document.createElement("small");
    metadata.textContent = `Run #${item.analysis_run_id} · ${formatDate(item.completed_at || item.created_at, true)} · ${conversionLabel(item.conversion_definition)}`;
    identity.append(name, metadata);

    const customers = document.createElement("td");
    const selected = document.createElement("strong");
    selected.textContent = formatNumber(item.selected_customer_count);
    const customerDetail = document.createElement("small");
    customerDetail.textContent = `${formatNumber(item.positive_customer_count)} positive · ${formatNumber(item.unlabeled_customer_count)} unlabeled`;
    customers.append(selected, customerDetail);

    const outcome = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    setStatusBadge(badge, item.status);
    const rate = document.createElement("small");
    rate.textContent = item.status === "COMPLETED"
      ? `${formatPercent(item.positive_customer_rate)} positive`
      : (item.failure_message || "Analysis failed safely");
    outcome.append(badge, rate);

    const action = document.createElement("td");
    if (item.status === "COMPLETED") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-secondary recent-reopen";
      button.textContent = "Reopen";
      button.addEventListener("click", () => reopenAnalysis(item.analysis_run_id, button));
      action.append(button);
    } else {
      const label = document.createElement("span");
      label.className = "table-caption";
      label.textContent = "Unavailable";
      action.append(label);
    }
    row.append(identity, customers, outcome, action);
    body.append(row);
  }
}

async function loadRecentAnalyses(force = false) {
  const loading = document.querySelector("#recent-analyses-loading");
  loading.hidden = false;
  try {
    const items = await getCachedJSON("/api/historical/analyses?limit=20&offset=0", {
      maxAgeMs: 30_000,
      force,
    });
    renderRecentAnalyses(items);
    return items;
  } finally {
    loading.hidden = true;
  }
}

async function reopenAnalysis(analysisRunId, button) {
  if (analysisRunning) return;
  hideFormError();
  setButtonLoading(button, true, "Opening…");
  document.querySelector("#analysis-run-announcement").textContent = `Opening analysis run ${analysisRunId}.`;
  try {
    const result = await getJSON(`/api/historical/analyses/${analysisRunId}`);
    renderAnalysisResult(result);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showFormError(error.message);
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(button, false, "Opening…");
  }
}

async function submitAnalysis(event) {
  event.preventDefault();
  if (analysisRunning) return;
  hideFormError();
  const validationMessage = validateForm();
  if (validationMessage) {
    showFormError(validationMessage);
    return;
  }

  setAnalysisRunning(true);
  try {
    const result = await getJSON("/api/historical/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(analysisPayload()),
    });
    renderAnalysisResult(result);
    await loadRecentAnalyses(true);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    setAnalysisRunning(false);
    const message = error.message.includes("No campaign observations match")
      ? "No campaign observations match the selected filters. Adjust the cohort and try again."
      : error.message;
    showFormError(message);
    document.querySelector("#analysis-run-announcement").textContent = "Analysis was not completed.";
    if (error.status && error.status < 500) {
      try {
        await loadRecentAnalyses(true);
      } catch {
        // The primary stable domain message remains actionable if list refresh fails.
      }
    }
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
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
      let targetIndex = null;
      if (event.key === "ArrowRight") targetIndex = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") targetIndex = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") targetIndex = 0;
      if (event.key === "End") targetIndex = buttons.length - 1;
      if (targetIndex !== null) {
        event.preventDefault();
        activate(buttons[targetIndex]);
        buttons[targetIndex].focus();
      }
    });
  });
}

function populateProfileDimensions() {
  const select = document.querySelector("#profile-dimension");
  select.replaceChildren();
  for (const [value, label] of Object.entries(PROFILE_DIMENSIONS)) {
    select.append(createOption(value, label));
  }
}

async function loadOptions(force = false) {
  const options = await getCachedJSON("/api/historical/options", {
    maxAgeMs: 300_000,
    force,
  });
  optionsSnapshot = options;
  if (!options.available_date_from || !options.available_date_to) {
    document.querySelector("#historical-analysis-empty").hidden = false;
    document.querySelector("#historical-analysis-workspace").hidden = true;
    return options;
  }
  populateFilterOptions(options);
  renderConversionDefinitions(options.conversion_definitions);
  applyFiltersToForm(options.defaults);
  document.querySelector("#historical-analysis-empty").hidden = true;
  document.querySelector("#historical-analysis-workspace").hidden = false;
  return options;
}

export async function loadHistoricalAnalysis(force = false) {
  if (loadedOnce && !force) return;
  loadedOnce = true;
  const loading = document.querySelector("#historical-options-loading");
  const errorBanner = document.querySelector("#historical-analysis-error");
  const errorMessage = document.querySelector("#historical-analysis-error-message");
  const refresh = document.querySelector("#historical-analysis-refresh");
  hideError(errorBanner);
  loading.hidden = false;
  setButtonLoading(refresh, true, "Refreshing…");
  const results = await Promise.allSettled([loadOptions(force), loadRecentAnalyses(force)]);
  loading.hidden = true;
  setButtonLoading(refresh, false, "Refreshing…");
  const failures = results.filter((result) => result.status === "rejected");
  if (failures.length) {
    showError(errorBanner, errorMessage, failures[0].reason);
    dispatchBackendStatus("is-offline", "Backend unavailable");
  } else {
    dispatchBackendStatus("is-online", "Backend online");
  }
}

export function initializeHistoricalAnalysis() {
  if (initialized) return;
  initialized = true;
  populateProfileDimensions();
  document.querySelector("#historical-analysis-form").addEventListener("submit", submitAnalysis);
  document.querySelector("#historical-analysis-reset").addEventListener("click", resetToDefaults);
  document.querySelector("#historical-analysis-refresh").addEventListener("click", () => loadHistoricalAnalysis(true));
  document.querySelector("#historical-analysis-retry").addEventListener("click", () => loadHistoricalAnalysis(true));
  document.querySelector("#recent-analyses-refresh").addEventListener("click", async () => {
    try {
      await loadRecentAnalyses(true);
      hideError(document.querySelector("#historical-analysis-error"));
      dispatchBackendStatus("is-online", "Backend online");
    } catch (error) {
      const banner = document.querySelector("#historical-analysis-error");
      showError(banner, document.querySelector("#historical-analysis-error-message"), error);
      dispatchBackendStatus("is-offline", "Backend unavailable");
    }
  });
  document.querySelector("#profile-dimension").addEventListener("change", renderProfile);
  initializeTablist("#analysis-breakdown-tabs", "breakdown", (value) => {
    activeBreakdown = value;
    renderBreakdown();
  });
  initializeTablist("#profile-group-tabs", "profileGroup", (value) => {
    activeProfileGroup = value;
    renderProfile();
  });
}
