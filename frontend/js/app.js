import { getCachedJSON } from "./api.js";
import { initializeDataStatus, loadDataStatus } from "./data-status.js";
import { initializeAudienceExplorer, loadAudienceExplorer } from "./audience-explorer.js";
import { initializeHistoricalAnalysis, loadHistoricalAnalysis } from "./historical-analysis.js";
import { initializeModelTraining, loadModelTraining } from "./model-training.js";
import { initializeOverview, loadOverview } from "./overview.js";
import { initializeCampaigns, loadCampaigns } from "./campaigns.js";
import { initializeCampaignPlanner, loadCampaignPlanner } from "./campaign-planner-form.js";
import { initializeSavedTargetGroups, loadSavedTargetGroups } from "./saved-target-groups.js";
import { applyViewContract, resolveBusinessRoute, VIEW_DEFINITIONS, VIEW_GROUPS } from "./view-contract.js";
import { initializeBusinessSearchForm, loadBusinessSearchForm } from "./business-search-form.js";
import { initializeSearchStatus, loadSearchStatus, loadSearchHistory, stopSearchStatus } from "./business-search-status.js";
import { initializeSidebar } from "./sidebar.js?v=sidebar-layout-2";

// Explicit retained-wizard harness seam. Never enables the shell in normal routing.
export function initializeLegacyCampaignPlannerForHarness() {
  initializeCampaignPlanner();
  loadCampaignPlanner();
}

// Explicit regression/future-exposure seam, never called by normal hash routing.
// UI hiding is not security: this does not authorize access to any API.
export function loadLegacyWorkspace(viewName) {
  if (!Object.hasOwn(VIEW_DEFINITIONS, viewName)) return;
  const definition = VIEW_DEFINITIONS[viewName];
  if (!definition || definition.group === VIEW_GROUPS.BUSINESS_USER_VISIBLE) return;
  const loaders = {
    "saved-target-groups": loadSavedTargetGroups, "data-status": loadDataStatus,
    "historical-analysis": loadHistoricalAnalysis, "model-training": loadModelTraining,
    "audience-explorer": loadAudienceExplorer, campaigns: loadCampaigns,
  };
  return loaders[viewName]?.();
}

function setBackendStatus(state, text) {
  const status = document.querySelector("#backend-status");
  const label = document.querySelector("#backend-status-text");
  status.classList.remove("is-checking", "is-online", "is-offline");
  status.classList.add(state);
  label.textContent = text;
}

async function checkBackendHealth(force = false) {
  const statusButton = document.querySelector("#backend-status");
  statusButton.disabled = true;
  setBackendStatus("is-checking", "Checking system");
  try {
    const health = await getCachedJSON("/api/health", { maxAgeMs: 30_000, force });
    const healthy = health.status === "ok";
    const label = healthy ? `Database online · v${health.version}` : `System ${health.status}`;
    setBackendStatus(healthy ? "is-online" : "is-offline", label);
  } catch (error) {
    console.error(error);
    setBackendStatus("is-offline", "Backend unavailable");
  } finally {
    statusButton.disabled = false;
  }
}

function showView(route) {
  stopSearchStatus();
  const safeView = route.definition.domView;
  for (const view of document.querySelectorAll("[data-view]")) {
    view.hidden = view.dataset.view !== safeView;
  }
  for (const item of document.querySelectorAll("#business-navigation [data-view-target]")) {
    const active = item.dataset.viewTarget === (route.definition.parentNavigation || route.key);
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }

  const title = route.definition.title;
  document.querySelector("#page-title").textContent = title;
  document.title = `${title} | Campaign Implementation Intelligence`;
  if (safeView === "overview") loadOverview();
  else if (safeView === "campaign-planner") loadBusinessSearchForm();
  else if (safeView === "results") loadSearchHistory();
  else if (safeView === "result-detail") loadSearchStatus(route.runId);
  document.querySelector("#result-detail-view").dataset.searchRunId = route.runId || "";
}

function renderRequestedRoute() {
  const route = resolveBusinessRoute(window.location.hash);
  if (window.location.hash !== route.hash) {
    window.history.replaceState(null, "", route.hash);
  }
  showView(route);
}

function initializeNavigation() {
  for (const item of document.querySelectorAll("[data-view-target]")) {
    item.addEventListener("click", (event) => {
      event.preventDefault();
      const route = resolveBusinessRoute(`#${item.dataset.viewTarget}`);
      if (window.location.hash === route.hash) renderRequestedRoute();
      else window.location.hash = route.hash;
    });
  }
  window.addEventListener("hashchange", renderRequestedRoute);
}

document.addEventListener("DOMContentLoaded", () => {
  initializeSidebar();
  applyViewContract();
  initializeOverview();
  initializeBusinessSearchForm();
  initializeSearchStatus();
  initializeSavedTargetGroups();
  initializeDataStatus();
  initializeHistoricalAnalysis();
  initializeModelTraining();
  initializeAudienceExplorer();
  initializeCampaigns();
  initializeNavigation();
  document.querySelector("#backend-status").addEventListener("click", () => checkBackendHealth(true));
  window.addEventListener("backend-status", (event) => {
    setBackendStatus(event.detail.state, event.detail.text);
  });
  checkBackendHealth();
  renderRequestedRoute();
});
