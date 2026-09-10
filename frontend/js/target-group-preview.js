import { getJSON } from "./api.js";
import { getCampaignPlannerState } from "./campaign-planner-state.js";
import { renderPhase9TechnicalDetails } from "./targeting-intelligence.js";
import {
  formatCurrency,
  formatDecimal,
  formatExactInteger,
} from "./ui.js";

const PAGE_SIZE = 25;

let initialized = false;
let announce = () => {};
let nextCursor = null;
let activeContextId = null;
let requestGeneration = 0;
let renderedCustomerIds = new Set();

function setPreviewState(state, message = "") {
  document.querySelector("#planner-target-preview-loading").hidden = state !== "loading";
  document.querySelector("#planner-target-preview-error").hidden = state !== "error";
  document.querySelector("#planner-target-preview").hidden =
    !["ready", "empty"].includes(state);
  document.querySelector("#planner-target-preview-empty").hidden = state !== "empty";
  document.querySelector("#planner-next-4").disabled = state !== "ready";
  if (state === "error") {
    const error = document.querySelector("#planner-target-preview-error");
    error.querySelector("p").textContent = message;
    error.focus();
  }
}

function clearRows() {
  document.querySelector("#planner-preview-table-body").replaceChildren();
  renderedCustomerIds = new Set();
  nextCursor = null;
}

function addBar(container, item) {
  const row = document.createElement("div");
  row.className = "planner-preview-bar-row";
  const heading = document.createElement("div");
  heading.className = "planner-preview-bar-heading";
  const label = document.createElement("span");
  label.textContent = item.category;
  const count = document.createElement("strong");
  count.textContent =
    `${formatExactInteger(item.count)} (${formatDecimal(item.share * 100, 1, 1)}%)`;
  const track = document.createElement("span");
  track.className = "planner-preview-bar-track";
  const fill = document.createElement("span");
  fill.className = "planner-preview-bar-fill";
  fill.style.width = `${Math.max(0, Math.min(100, item.share * 100))}%`;
  track.append(fill);
  heading.append(label, count);
  row.append(heading, track);
  container.append(row);
}

function renderPreview(preview) {
  const kpis = preview.kpis;
  document.querySelector("#planner-target-preview-currentness").textContent =
    preview.currentness_label;
  document.querySelector("#planner-preview-available").textContent =
    formatExactInteger(kpis.potential_customers_available);
  document.querySelector("#planner-preview-matching").textContent =
    formatExactInteger(kpis.matching_your_preferences);
  document.querySelector("#planner-preview-selected").textContent =
    formatExactInteger(kpis.selected_for_target_group);
  document.querySelector("#planner-preview-percent").textContent =
    `${formatDecimal(kpis.percent_of_available_people, 2, 2)}%`;
  document.querySelector("#planner-preview-average-score").textContent =
    formatDecimal(kpis.average_targeting_match_score, 3, 3);
  document.querySelector("#planner-preview-strongest").textContent =
    formatDecimal(kpis.strongest_match, 3, 3);
  document.querySelector("#planner-preview-lowest").textContent =
    formatDecimal(kpis.lowest_selected_match, 3, 3);
  document.querySelector("#planner-preview-why").textContent = preview.why_these_people;
  renderPhase9TechnicalDetails(
    preview.technical_details,
    "#planner-intelligence-details",
  );

  const scoreBands = document.querySelector("#planner-preview-score-bands");
  scoreBands.replaceChildren();
  for (const item of preview.targeting_match_score_distribution) addBar(scoreBands, item);

  const demographicMix = document.querySelector("#planner-preview-demographic-mix");
  demographicMix.replaceChildren();
  for (const [label, items] of Object.entries(preview.demographic_mix)) {
    const group = document.createElement("section");
    group.className = "planner-demographic-group";
    const heading = document.createElement("h5");
    heading.textContent = label;
    const bars = document.createElement("div");
    bars.className = "planner-preview-bars";
    for (const item of items) addBar(bars, item);
    group.append(heading, bars);
    demographicMix.append(group);
  }
}

function comparisonChangeText(item) {
  if (item.change_from_current === 0) return "Same size as current choice";
  const absoluteChange = formatExactInteger(Math.abs(item.change_from_current));
  return item.change_from_current > 0
    ? `${absoluteChange} more people than current choice`
    : `${absoluteChange} fewer people than current choice`;
}

function renderMatchStrengthRecommendation(recommendation) {
  const status = document.querySelector("#planner-match-recommendation-status");
  const isRecommended = recommendation.recommendation_status === "RECOMMENDED";
  status.textContent = isRecommended ? "Recommended" : "Review needed";
  status.classList.toggle("is-ready", isRecommended);
  status.classList.toggle("is-warning", !isRecommended);
  status.classList.remove("is-neutral");
  document.querySelector("#planner-match-recommendation-heading").textContent =
    recommendation.recommendation_heading;
  document.querySelector("#planner-match-recommendation-explanation").textContent =
    recommendation.recommendation_explanation;
  document.querySelector("#planner-match-recommendation-rule").textContent =
    `Recommendation rule v${recommendation.recommendation_rule_version} · `
    + `practical minimum ${formatExactInteger(recommendation.practical_minimum_count)} people · `
    + "Very Strong considered at "
    + `${formatExactInteger(recommendation.very_strong_minimum_count)} people`;
  document.querySelector("#planner-match-strength-disclaimer").textContent =
    recommendation.disclaimer;

  const container = document.querySelector("#planner-match-strength-comparisons");
  container.replaceChildren();
  for (const item of recommendation.comparisons) {
    const card = document.createElement("article");
    card.className = "planner-match-strength-card";
    card.classList.toggle("is-recommended", item.recommended);
    card.classList.toggle("is-current", item.relationship_to_current === "CURRENT");
    const relationship = document.createElement("span");
    relationship.className = "planner-match-strength-relationship";
    relationship.textContent = item.recommended
      ? "Recommended"
      : item.relationship_to_current.charAt(0)
        + item.relationship_to_current.slice(1).toLowerCase();
    const heading = document.createElement("h5");
    heading.textContent = item.label;
    const count = document.createElement("strong");
    count.textContent = formatExactInteger(item.exact_matching_count);
    const countLabel = document.createElement("small");
    countLabel.textContent = "Matching people";
    const population = document.createElement("p");
    population.textContent =
      `${formatDecimal(item.percent_of_available_population, 2, 2)}% of available people`;
    const change = document.createElement("p");
    change.textContent = comparisonChangeText(item);
    card.append(relationship, heading, count, countLabel, population, change);
    container.append(card);
  }
}

function addCustomerRow(row) {
  if (renderedCustomerIds.has(row.potential_customer_id)) return;
  renderedCustomerIds.add(row.potential_customer_id);
  const tr = document.createElement("tr");
  const values = [
    row.potential_customer_id,
    formatDecimal(row.targeting_match_score, 3, 3),
    `Top ${formatExactInteger(row.top_matching_percent)}%`,
    row.match_strength,
    formatExactInteger(row.age),
    row.gender,
    row.state,
    formatCurrency(row.individual_yearly_income),
  ];
  for (const value of values) {
    const cell = document.createElement("td");
    cell.textContent = value;
    tr.append(cell);
  }
  document.querySelector("#planner-preview-table-body").append(tr);
}

async function fetchPage(contextId, cursor = null) {
  return getJSON(`/api/campaign-planner/contexts/${contextId}/target-group-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_size: PAGE_SIZE, cursor }),
  });
}

function renderPage(page) {
  for (const row of page.rows) addCustomerRow(row);
  nextCursor = page.next_cursor;
  const count = renderedCustomerIds.size;
  document.querySelector("#planner-preview-page-status").textContent =
    `${formatExactInteger(count)} potential customer${count === 1 ? "" : "s"} shown`;
  document.querySelector("#planner-preview-table-empty").hidden = count !== 0;
  const loadMore = document.querySelector("#planner-preview-load-more");
  loadMore.hidden = !page.has_more;
  loadMore.disabled = false;
  loadMore.textContent = "Load more potential customers";
}

export async function loadTargetGroupPreview() {
  const contextId = getCampaignPlannerState().targetingContextId;
  const generation = ++requestGeneration;
  activeContextId = contextId;
  clearRows();
  if (!contextId) {
    setPreviewState("hidden");
    return false;
  }
  setPreviewState("loading");
  try {
    const preview = await getJSON(
      `/api/campaign-planner/contexts/${contextId}/target-group-preview`,
    );
    if (generation !== requestGeneration || contextId !== activeContextId) return false;
    renderPreview(preview);
    const recommendation = await getJSON(
      `/api/campaign-planner/contexts/${contextId}/match-strength-recommendation`,
    );
    if (generation !== requestGeneration || contextId !== activeContextId) return false;
    renderMatchStrengthRecommendation(recommendation);
    const page = await fetchPage(contextId);
    if (generation !== requestGeneration || contextId !== activeContextId) return false;
    renderPage(page);
    const isEmpty = preview.kpis.selected_for_target_group === 0;
    setPreviewState(isEmpty ? "empty" : "ready");
    document.dispatchEvent(new CustomEvent("target-group-preview-loaded", {
      detail: { preview, recommendation },
    }));
    announce(
      isEmpty
        ? "No people match these targeting preferences. The exact result is zero."
        : "Exact target-group preview is up to date.",
    );
    return !isEmpty;
  } catch (error) {
    if (generation !== requestGeneration) return false;
    setPreviewState("error", error.message);
    announce(error.message);
    return false;
  }
}

async function loadMore() {
  if (!nextCursor || !activeContextId) return;
  const button = document.querySelector("#planner-preview-load-more");
  button.disabled = true;
  button.textContent = "Loading…";
  try {
    renderPage(await fetchPage(activeContextId, nextCursor));
  } catch (error) {
    button.disabled = false;
    button.textContent = "Try loading more again";
    announce(error.message);
  }
}

function handleResolution(event) {
  const resolution = event.detail;
  if (resolution?.can_preview) {
    loadTargetGroupPreview();
    return;
  }
  requestGeneration += 1;
  activeContextId = null;
  clearRows();
  setPreviewState("hidden");
}

export function initializeTargetGroupPreview(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  document.addEventListener("targeting-intelligence-resolved", handleResolution);
  document.querySelector("#planner-target-preview-retry").addEventListener(
    "click",
    loadTargetGroupPreview,
  );
  document.querySelector("#planner-preview-load-more").addEventListener("click", loadMore);
}
