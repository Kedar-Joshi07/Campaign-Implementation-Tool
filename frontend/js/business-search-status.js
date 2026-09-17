import { getJSON } from "./api.js";

export const RESULT_REFRESH_INTERVAL_MS = 5000;
export const RESULT_REFRESH_MAX_CYCLES = 60;
const ACTIVE = new Set(["QUEUED", "PROCESSING"]);
const rows = new Map();
let token = 0;
let timer = null;
let cursor = null;
let historyRequest = 0;
let refreshCycles = 0;
const find = (id) => document.querySelector(`#${id}`);
const make = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};
const label = (value) => String(value ?? "").replaceAll("_", " ").toLowerCase()
  .replace(/\b\w/g, (character) => character.toUpperCase());
const valueText = (value) => {
  if (value === null || value === undefined || value === "") return "Not available";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "Any";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return String(value);
};
const timeText = (value) => value ? new Date(value).toLocaleString() : "Not completed";
const durationText = (value) => value === null || value === undefined
  ? "Not completed"
  : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} seconds`;

function clearTimer() {
  if (timer) window.clearTimeout(timer);
  timer = null;
}

export function stopSearchStatus() {
  token += 1;
  clearTimer();
  refreshCycles = 0;
}

function definitionList(container, entries) {
  const fragment = document.createDocumentFragment();
  for (const [term, value] of entries) {
    fragment.append(make("dt", null, term), make("dd", null, valueText(value)));
  }
  container.replaceChildren(fragment);
}

function statusBadge(status) {
  const badge = make(
    "span",
    `result-status-badge is-${status.toLowerCase()}`,
    label(status),
  );
  badge.dataset.status = status;
  return badge;
}

function resultCard(run) {
  const item = make("li", "result-card");
  item.dataset.searchRunId = String(run.search_run_id);
  const article = make("article");
  const header = make("header", "result-card-header");
  const identity = make("div");
  identity.append(
    make("p", "eyebrow", `Search #${run.search_run_id}`),
    make("h3", null, run.campaign_name),
  );
  header.append(identity, statusBadge(run.status));

  const products = run.selected_products
    .map((product) => product.product_name || product.product_id).join(", ");
  const context = [
    ...run.campaign_types, ...run.campaign_categories, ...run.offer_types,
  ].join(" · ") || "No historical campaign filters";
  const facts = make("dl", "result-card-facts");
  definitionList(facts, [
    ["Created", timeText(run.created_at)],
    ["Completed", timeText(run.completed_at)],
    ["Products", products],
    ["Campaign / Offer", context],
    ["Delivery Profile", `${run.delivery_profile_label} · ${run.export_profile}`],
    ["Match Strength", label(run.match_strength)],
    ["Potential Customers", run.selected_count === null
      ? "Pending" : Number(run.selected_count).toLocaleString()],
    ["Result Source", run.result_source_label],
    ["Processing Duration", durationText(run.processing_seconds)],
  ]);
  const targeting = make(
    "p", "result-card-targeting", run.targeting_summary.join(" · "),
  );
  const message = make("p", "panel-note", run.safe_message);
  const actions = make("div", "result-card-actions");
  const view = make("a", "button button-secondary", "View Result");
  view.href = `#results/${run.search_run_id}`;
  actions.append(view);
  if (run.download_eligible) {
    const download = make(
      "a", "button button-primary", "Download Potential Customers",
    );
    download.href = `/api/potential-customer-search/runs/${run.search_run_id}/download`;
    download.setAttribute("download", "");
    actions.append(download);
  }
  article.append(header, facts, targeting, message, actions);
  item.append(article);
  return item;
}

function renderHistory() {
  const ordered = [...rows.values()].sort((left, right) =>
    right.created_at.localeCompare(left.created_at)
      || right.search_run_id - left.search_run_id);
  find("business-search-history").replaceChildren(...ordered.map(resultCard));
  find("results-empty").hidden = ordered.length !== 0;
  cursor = ordered.at(-1)?.search_run_id || null;
  return ordered;
}

function scheduleHistoryRefresh(ordered, request) {
  clearTimer();
  const active = ordered.some((run) => ACTIVE.has(run.status));
  if (!active || refreshCycles >= RESULT_REFRESH_MAX_CYCLES) return;
  refreshCycles += 1;
  timer = window.setTimeout(() => {
    if (request === token && window.location.hash === "#results") {
      loadSearchHistory({ automated: true });
    }
  }, RESULT_REFRESH_INTERVAL_MS);
}

export async function loadSearchHistory({ older = false, automated = false } = {}) {
  const request = token;
  const generation = ++historyRequest;
  if (!automated) {
    clearTimer();
    find("results-status").textContent = older
      ? "Loading older searches…" : "Loading saved searches…";
  }
  try {
    const query = older && cursor ? `&before_search_run_id=${cursor}` : "";
    const runs = await getJSON(
      `/api/potential-customer-search/results?limit=20${query}`,
    );
    if (
      request !== token || generation !== historyRequest
      || window.location.hash !== "#results"
    ) return;
    if (!older && !automated) rows.clear();
    for (const run of runs) rows.set(run.search_run_id, run);
    const ordered = renderHistory();
    find("business-history-more").hidden = runs.length < 20;
    const activeCount = ordered.filter((run) => ACTIVE.has(run.status)).length;
    find("results-status").textContent = activeCount
      ? `${activeCount} search${activeCount === 1 ? " is" : "es are"} still active. Results refresh every ${RESULT_REFRESH_INTERVAL_MS / 1000} seconds.`
      : `${ordered.length.toLocaleString()} saved search${ordered.length === 1 ? "" : "es"}, newest first.`;
    scheduleHistoryRefresh(ordered, request);
  } catch (error) {
    if (request === token && generation === historyRequest) {
      clearTimer();
      find("results-status").textContent =
        "Saved searches could not be loaded. Refresh Results to try again.";
    }
  }
}

function detailEntries(payload) {
  return Object.entries(payload).map(([key, value]) => [label(key), value]);
}

function renderDetail(run) {
  find("result-detail-error").hidden = true;
  find("result-detail-content").hidden = false;
  find("result-detail-run-id").textContent = `Search #${run.search_run_id}`;
  find("result-detail-title").textContent = run.campaign_name;
  find("result-detail-description").textContent = run.description
    || "No campaign description was provided.";
  const oldBadge = find("result-detail-badge");
  const badge = statusBadge(run.status);
  badge.id = "result-detail-badge";
  oldBadge.replaceWith(badge);
  definitionList(find("result-detail-overview"), [
    ["Created", timeText(run.created_at)],
    ["Completed", timeText(run.completed_at)],
    ["Potential Customers", run.selected_count === null
      ? "Pending" : Number(run.selected_count).toLocaleString()],
    ["Currentness", label(run.currentness)],
    ["Processing Duration", durationText(run.processing_seconds)],
    ["Planned Launch", run.planned_launch_date],
  ]);
  const products = run.selected_products.map(
    (product) => `${product.product_name} (${product.product_id})`,
  );
  definitionList(find("result-context-details"), [
    ["Products", products],
    ["Campaign Types", run.campaign_types],
    ["Campaign Categories", run.campaign_categories],
    ["Offers", run.offer_types],
    ["Historical Channels", run.campaign_context.historical_campaign_channels],
    ["Delivery Channel", label(run.delivery_channel)],
  ]);
  definitionList(
    find("result-targeting-details"),
    detailEntries(run.targeting_criteria)
      .filter(([term]) => !term.includes("Contract Version")),
  );
  definitionList(find("result-selection-details"), [
    ["Selection Mode", label(run.selection.mode)],
    ["Requested Count", run.selection.target_count],
    ["Resolved Count", run.selection.resolved_count],
    ["Result Source", run.result_source_explanation],
    ["Currentness", label(run.currentness)],
  ]);
  const score = run.score_summary ? [
    ["Score Scope", run.score_summary.scope],
    ["Scored Population", run.score_summary.population_count],
    ["Minimum Score", run.score_summary.minimum],
    ["Mean Score", run.score_summary.mean],
    ["Maximum Score", run.score_summary.maximum],
  ] : [["Score Summary", "Available after targeting intelligence completes"]];
  definitionList(
    find("result-profile-details"),
    [...score, ...detailEntries(run.demographic_summary)],
  );
  definitionList(
    find("result-provenance-details"),
    run.snapshot_provenance
      ? detailEntries(run.snapshot_provenance)
      : [["Snapshot", "Available after completion"]],
  );
  definitionList(find("result-download-details"), [
    ["Delivery Profile", run.delivery_profile_label],
    ["Profile Code", run.export_profile],
    ["Download Status", run.download_eligible ? "Ready" : "Not available"],
  ]);
  find("result-download-help").textContent = run.download_eligible
    ? "The governed download is ready. Downloading does not activate or send a campaign."
    : "A governed download appears only when the result is completed, current, and export-ready.";
  definitionList(find("result-technical-details"), [
    ...detailEntries(run.technical_details),
    ...detailEntries(run.campaign_context)
      .filter(([term]) => term.includes("Contract Version")),
    ...detailEntries(run.targeting_criteria)
      .filter(([term]) => term.includes("Contract Version")),
    ["Filter Branches", JSON.stringify(run.filter_branches)],
  ]);
  const download = find("result-detail-download");
  download.hidden = !run.download_eligible;
  if (run.download_eligible) {
    download.href = `/api/potential-customer-search/runs/${run.search_run_id}/download`;
    download.setAttribute("download", "");
  } else {
    download.removeAttribute("href");
    download.removeAttribute("download");
  }
  find("result-detail-status").textContent = run.safe_message;
}

export async function loadSearchStatus(runId) {
  const request = token;
  clearTimer();
  find("result-detail-content").hidden = true;
  find("result-detail-error").hidden = true;
  find("result-detail-status").textContent = "Loading saved result…";
  const poll = async () => {
    try {
      const run = await getJSON(
        `/api/potential-customer-search/runs/${runId}/result`,
      );
      if (request !== token || window.location.hash !== `#results/${runId}`) return;
      renderDetail(run);
      if (ACTIVE.has(run.status) && refreshCycles < RESULT_REFRESH_MAX_CYCLES) {
        refreshCycles += 1;
        timer = window.setTimeout(poll, RESULT_REFRESH_INTERVAL_MS);
      }
    } catch (error) {
      if (request === token) {
        clearTimer();
        find("result-detail-content").hidden = true;
        find("result-detail-error").hidden = false;
        find("result-detail-status").textContent =
          "Saved result details could not be loaded.";
      }
    }
  };
  await poll();
}

export function initializeSearchStatus() {
  find("business-history-more").addEventListener(
    "click", () => loadSearchHistory({ older: true }),
  );
  find("business-history-refresh").addEventListener("click", () => {
    refreshCycles = 0;
    loadSearchHistory();
  });
  find("result-detail-retry").addEventListener("click", () => {
    refreshCycles = 0;
    loadSearchStatus(find("result-detail-view").dataset.searchRunId);
  });
}
