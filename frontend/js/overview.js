import { getCachedJSON } from "./api.js";
import { formatExactInteger, hideError, setButtonLoading } from "./ui.js";
import { createRunIssue, createRunProgress } from "./run-progress.js";

const metricIds = [
  "home-potential-customers",
  "home-search-runs",
  "home-completed-results",
  "home-latest-result-count",
];
let initialized = false;
let loadedOnce = false;

const find = (id) => document.querySelector(`#${id}`);
const make = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", {
    detail: { state, text },
  }));
}

function setMetric(id, value, emptyLabel = "No completed result") {
  const element = find(id);
  element.classList.remove("is-loading");
  element.textContent = value === null || value === undefined
    ? emptyLabel
    : formatExactInteger(value);
}

function setLoading() {
  for (const id of metricIds) {
    const element = find(id);
    element.textContent = "—";
    element.classList.add("is-loading");
  }
  find("home-results-status").textContent = "Loading recent results…";
  find("home-results-empty").hidden = true;
  find("home-recent-results").replaceChildren();
}

function renderOverview(payload) {
  setMetric("home-potential-customers", payload.potential_customers_available);
  setMetric("home-search-runs", payload.search_runs);
  setMetric("home-completed-results", payload.completed_results);
  setMetric("home-latest-result-count", payload.latest_result_count);
}

function statusLabel(value) {
  return String(value).replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function resultCard(run) {
  const item = make("li", "home-result-card");
  const header = make("div", "home-result-card-header");
  header.append(
    make("h3", null, run.campaign_name),
    make(
      "span",
      `result-status-badge is-${run.status.toLowerCase()}`,
      statusLabel(run.status),
    ),
  );
  const facts = make("dl", "home-result-facts");
  const entries = [
    ["Potential Customers", run.selected_count === null
      ? "Pending" : Number(run.selected_count).toLocaleString()],
    ["Delivery Profile", run.delivery_profile_label],
  ];
  for (const [term, value] of entries) {
    facts.append(make("dt", null, term), make("dd", null, value));
  }
  const action = make("a", "button button-secondary", "View Result");
  action.href = `#results/${run.search_run_id}`;
  item.append(header, facts, createRunProgress(run, { compact: true }), make("p", "panel-note", run.safe_message));
  const issue = createRunIssue(run);
  if (issue) item.append(issue);
  item.append(action);
  return item;
}

function renderRecentResults(results) {
  find("home-recent-results").replaceChildren(...results.map(resultCard));
  find("home-results-empty").hidden = results.length !== 0;
  find("home-results-status").textContent = results.length
    ? `${results.length} recent search${results.length === 1 ? "" : "es"}, newest first.`
    : "No recent searches.";
}

function showUnavailable(error) {
  for (const id of metricIds) setMetric(id, null, "Unavailable");
  find("home-recent-results").replaceChildren();
  find("home-results-empty").hidden = true;
  find("home-results-status").textContent =
    "Recent results are unavailable. Try again when the service is available.";
  find("overview-error-message").textContent =
    "We could not load the latest campaign overview. Please try again.";
  find("overview-error").hidden = false;
  console.error(error);
  dispatchBackendStatus("is-offline", "Backend unavailable");
}

export function initializeOverview() {
  if (initialized) return;
  initialized = true;
  find("overview-retry").addEventListener("click", () => loadOverview(true));
}

export async function loadOverview(force = false) {
  if (loadedOnce && !force) return;
  loadedOnce = true;
  const retry = find("overview-retry");
  hideError(find("overview-error"));
  setButtonLoading(retry, true, "Trying again…");
  setLoading();
  try {
    const overview = await getCachedJSON("/api/business/overview", {
      maxAgeMs: 60_000,
      force,
    });
    renderOverview(overview);
    const results = await getCachedJSON("/api/business/recent-results?limit=5", {
      maxAgeMs: 30_000,
      force,
    });
    renderRecentResults(results);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showUnavailable(error);
  } finally {
    setButtonLoading(retry, false, "Trying again…");
  }
}
