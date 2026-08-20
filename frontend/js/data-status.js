import { getCachedJSON } from "./api.js";
import { datasetLabel, formatDate, formatNumber, hideError, setButtonLoading, setStatusBadge, showError } from "./ui.js";

let initialized = false;
let loadedOnce = false;

function setCardsLoading() {
  for (const card of document.querySelectorAll("[data-dataset-card]")) {
    card.classList.add("is-loading");
    setStatusBadge(card.querySelector('[data-field="status"]'), "Checking");
  }
}

function targetPolicyLabel(dataset) {
  if (dataset.exact_match_required) {
    return "Exact target";
  }
  const tolerance = Number(dataset.count_tolerance_percent);
  const displayTolerance = Number.isInteger(tolerance)
    ? tolerance.toFixed(0)
    : tolerance.toString();
  return `Approximate target (±${displayTolerance}%)`;
}

function renderDatasetStatus(datasets) {
  for (const dataset of datasets) {
    const card = document.querySelector(`[data-dataset-card="${dataset.dataset_name}"]`);
    if (!card) continue;
    card.classList.remove("is-loading");
    setStatusBadge(card.querySelector('[data-field="status"]'), dataset.reconciliation_status);
    card.querySelector('[data-field="actual"]').textContent = dataset.actual_rows > 0 ? formatNumber(dataset.actual_rows) : "Not loaded";
    card.querySelector('[data-field="expected"]').textContent = dataset.expected_rows === null ? "Not configured" : formatNumber(dataset.expected_rows);
    card.querySelector('[data-field="policy"]').textContent = targetPolicyLabel(dataset);
    const importStatus = dataset.last_import_status
      ? `${dataset.last_import_status.toLowerCase()} · ${formatDate(dataset.last_import_completed_at || dataset.last_import_started_at, true)}`
      : "No import recorded";
    card.querySelector('[data-field="last-import"]').textContent = importStatus;
    card.querySelector('[data-field="source"]').textContent = dataset.source_path || "—";
    card.querySelector('[data-field="source"]').title = dataset.source_path || "";
    card.querySelector('[data-field="rejected"]').textContent = dataset.rows_rejected === null ? "—" : formatNumber(dataset.rows_rejected);
  }
}

function renderDatasetError() {
  for (const card of document.querySelectorAll("[data-dataset-card]")) {
    card.classList.remove("is-loading");
    setStatusBadge(card.querySelector('[data-field="status"]'), "ERROR");
    card.querySelector('[data-field="actual"]').textContent = "Unavailable";
    card.querySelector('[data-field="expected"]').textContent = "—";
    card.querySelector('[data-field="policy"]').textContent = "Target policy";
  }
}

function createCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function renderImports(imports) {
  const body = document.querySelector("#import-history-body");
  body.replaceChildren();
  if (!imports.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = createCell("No import history is available.");
    cell.colSpan = 6;
    row.append(cell);
    body.append(row);
    return;
  }
  for (const item of imports) {
    const row = document.createElement("tr");
    row.append(createCell(datasetLabel(item.dataset_name)));
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    setStatusBadge(badge, item.status);
    statusCell.append(badge);
    row.append(statusCell);
    row.append(createCell(formatDate(item.completed_at || item.started_at, true)));
    const sourceCell = createCell(item.source_path || "—");
    sourceCell.title = item.source_path || "";
    row.append(sourceCell);
    row.append(createCell(formatNumber(item.rows_inserted), "numeric"));
    row.append(createCell(formatNumber(item.rows_rejected), "numeric"));
    body.append(row);
  }
}

function renderImportsError() {
  const body = document.querySelector("#import-history-body");
  body.replaceChildren();
  const row = document.createElement("tr");
  row.className = "empty-row";
  const cell = createCell("Import history could not be loaded.");
  cell.colSpan = 6;
  row.append(cell);
  body.append(row);
}

function setImportsLoading() {
  const body = document.querySelector("#import-history-body");
  body.replaceChildren();
  const row = document.createElement("tr");
  row.className = "loading-row";
  const cell = document.createElement("td");
  cell.colSpan = 6;
  const spinner = document.createElement("span");
  spinner.className = "spinner";
  spinner.setAttribute("aria-hidden", "true");
  cell.append(spinner, " Loading import history");
  row.append(cell);
  body.append(row);
}

export function initializeDataStatus() {
  if (initialized) return;
  initialized = true;
  document.querySelector("#data-status-refresh").addEventListener("click", () => loadDataStatus(true));
  document.querySelector("#data-status-retry").addEventListener("click", () => loadDataStatus(true));
}

export async function loadDataStatus(force = false) {
  if (loadedOnce && !force) return;
  loadedOnce = true;
  const errorBanner = document.querySelector("#data-status-error");
  const errorMessage = document.querySelector("#data-status-error-message");
  const refreshButton = document.querySelector("#data-status-refresh");
  hideError(errorBanner);
  setButtonLoading(refreshButton, true, "Running checks…");
  setCardsLoading();
  setImportsLoading();
  const errors = [];
  await Promise.all([
    getCachedJSON("/api/data/status", { maxAgeMs: 300_000, force }).then(renderDatasetStatus).catch((error) => {
      renderDatasetError();
      errors.push(error);
    }),
    getCachedJSON("/api/data/imports?limit=20&offset=0", { maxAgeMs: 60_000, force }).then(renderImports).catch((error) => {
      renderImportsError();
      errors.push(error);
    }),
  ]);
  setButtonLoading(refreshButton, false, "Running checks…");
  if (errors.length) {
    showError(errorBanner, errorMessage, errors[0]);
    window.dispatchEvent(new CustomEvent("backend-status", {
      detail: { state: "is-offline", text: "Backend unavailable" },
    }));
  }
}
