import { getCachedJSON } from "./api.js";
import { loadHistoricalOverview } from "./historical-overview.js";
import { formatDate, formatExactInteger, hideError, setButtonLoading, setStatusBadge, showError } from "./ui.js";

const metricIds = [
  "customer-count", "campaign-sales-count", "demographic-count",
  "distinct-campaigns", "distinct-products", "known-positive-count",
];
let initialized = false;
let loadedOnce = false;

function setMetric(id, value, loaded) {
  const element = document.querySelector(`#${id}`);
  element.classList.remove("is-loading");
  element.textContent = loaded ? formatExactInteger(value) : "Not loaded";
}

function setSummaryLoading() {
  for (const id of metricIds) {
    const element = document.querySelector(`#${id}`);
    element.textContent = "—";
    element.classList.add("is-loading");
  }
  const dateRange = document.querySelector("#campaign-date-range");
  dateRange.textContent = "—";
  dateRange.classList.add("is-loading");
}

function setSummaryError() {
  for (const id of metricIds) {
    const element = document.querySelector(`#${id}`);
    element.classList.remove("is-loading");
    element.textContent = "Unavailable";
  }
  const dateRange = document.querySelector("#campaign-date-range");
  dateRange.classList.remove("is-loading");
  dateRange.textContent = "Unavailable";
}

function renderSummary(summary) {
  const customersLoaded = summary.customer_count > 0;
  const campaignsLoaded = summary.campaign_sales_count > 0;
  const demographicsLoaded = summary.demographic_count > 0;
  setMetric("customer-count", summary.customer_count, customersLoaded);
  setMetric("campaign-sales-count", summary.campaign_sales_count, campaignsLoaded);
  setMetric("demographic-count", summary.demographic_count, demographicsLoaded);
  setMetric("distinct-campaigns", summary.distinct_campaigns, campaignsLoaded);
  setMetric("distinct-products", summary.distinct_products, campaignsLoaded);
  setMetric("known-positive-count", summary.known_positive_count, campaignsLoaded);

  const dateRange = document.querySelector("#campaign-date-range");
  dateRange.classList.remove("is-loading");
  dateRange.textContent = campaignsLoaded
    ? `${formatDate(summary.campaign_contact_date_min)} — ${formatDate(summary.campaign_contact_date_max)}`
    : "Not loaded";
  document.querySelector("#attributed-purchase-count").textContent = campaignsLoaded
    ? formatExactInteger(summary.attributed_purchase_count)
    : "Not loaded";
  document.querySelector("#database-name").textContent = summary.database_path || "—";
  document.querySelector("#schema-version").textContent = summary.schema_version
    ? `Version ${summary.schema_version}`
    : "—";
}

function renderHealth(health) {
  document.querySelector("#application-health").textContent = health.application_status === "ok" ? "Operational" : "Degraded";
  document.querySelector("#database-health").textContent = health.database_status === "connected" ? "Connected" : "Unavailable";
  document.querySelector("#schema-health").textContent = health.schema_status === "ready" ? "Ready" : health.schema_status;
  setStatusBadge(document.querySelector("#overview-health-badge"), health.status === "ok" ? "OK" : "ERROR");
}

function renderHealthError() {
  document.querySelector("#application-health").textContent = "Unavailable";
  document.querySelector("#database-health").textContent = "Unavailable";
  document.querySelector("#schema-health").textContent = "Unknown";
  setStatusBadge(document.querySelector("#overview-health-badge"), "ERROR");
  window.dispatchEvent(new CustomEvent("backend-status", {
    detail: { state: "is-offline", text: "Backend unavailable" },
  }));
}

function setReadinessLoading() {
  document.querySelector("#readiness-spinner").hidden = false;
  document.querySelector("#readiness-note").textContent = "Overview remains interactive while complete integrity reconciliation runs. Exact checks may take 60-180 seconds on full volumes.";
  for (const id of ["customers-readiness", "campaign-sales-readiness", "demographics-readiness"]) {
    setStatusBadge(document.querySelector(`#${id}`), "Checking");
  }
}

function renderReadiness(datasets) {
  const statusElements = {
    customers: "customers-readiness",
    campaign_sales: "campaign-sales-readiness",
    demographics: "demographics-readiness",
  };
  for (const dataset of datasets) {
    const id = statusElements[dataset.dataset_name];
    if (id) {
      setStatusBadge(document.querySelector(`#${id}`), dataset.reconciliation_status);
    }
  }
  document.querySelector("#readiness-spinner").hidden = true;
  document.querySelector("#readiness-note").textContent = "Counts and structural integrity reflect the latest complete database check. Heavy exact validation runs independently from summary cards.";
}

export function initializeOverview() {
  if (initialized) return;
  initialized = true;
  document.querySelector("#overview-refresh").addEventListener("click", () => loadOverview(true));
  document.querySelector("#overview-retry").addEventListener("click", () => loadOverview(true));
}

export async function loadOverview(force = false) {
  if (loadedOnce && !force) return;
  loadedOnce = true;
  const errorBanner = document.querySelector("#overview-error");
  const errorMessage = document.querySelector("#overview-error-message");
  const refreshButton = document.querySelector("#overview-refresh");
  hideError(errorBanner);
  setButtonLoading(refreshButton, true, "Refreshing…");
  if (force || !document.querySelector("#customer-count").textContent.match(/[0-9]/)) setSummaryLoading();
  setReadinessLoading();

  const errors = [];
  let healthResult = null;
  await Promise.all([
    getCachedJSON("/api/data/summary", { maxAgeMs: 300_000, force }).then(renderSummary).catch((error) => {
      setSummaryError();
      errors.push(error);
    }),
    getCachedJSON("/api/health", { maxAgeMs: 30_000, force }).then((health) => {
      healthResult = health;
      renderHealth(health);
    }).catch((error) => {
      renderHealthError();
      errors.push(error);
    }),
    getCachedJSON("/api/data/status", { maxAgeMs: 300_000, force }).then(renderReadiness).catch((error) => {
      document.querySelector("#readiness-spinner").hidden = true;
      document.querySelector("#readiness-note").textContent = "Reconciliation could not be completed. Summary counts remain available.";
      for (const id of ["customers-readiness", "campaign-sales-readiness", "demographics-readiness"]) {
        setStatusBadge(document.querySelector(`#${id}`), "ERROR");
      }
      errors.push(error);
    }),
    loadHistoricalOverview(force).catch((error) => {
      errors.push(error);
    }),
  ]);
  setButtonLoading(refreshButton, false, "Refreshing…");
  if (errors.length) {
    showError(errorBanner, errorMessage, errors[0]);
    window.dispatchEvent(new CustomEvent("backend-status", {
      detail: { state: "is-offline", text: "Backend unavailable" },
    }));
  } else if (healthResult) {
    window.dispatchEvent(new CustomEvent("backend-status", {
      detail: {
        state: "is-online",
        text: `Database online · v${healthResult.version}`,
      },
    }));
  }
}
