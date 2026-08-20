import { getCachedJSON } from "./api.js";
import { initializeDataStatus, loadDataStatus } from "./data-status.js";
import { initializeOverview, loadOverview } from "./overview.js";

const viewTitles = {
  overview: "Overview",
  "data-status": "Data Status",
};

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

function showView(viewName) {
  const safeView = Object.hasOwn(viewTitles, viewName) ? viewName : "overview";
  for (const view of document.querySelectorAll("[data-view]")) {
    view.hidden = view.dataset.view !== safeView;
  }
  for (const item of document.querySelectorAll("[data-view-target]")) {
    const active = item.dataset.viewTarget === safeView;
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }

  const title = viewTitles[safeView];
  document.querySelector("#page-title").textContent = title;
  document.title = `${title} | Campaign Implementation Intelligence`;
  if (safeView === "overview") loadOverview();
  else loadDataStatus();
}

function requestedView() {
  return window.location.hash.replace(/^#/, "") || "overview";
}

function initializeNavigation() {
  for (const item of document.querySelectorAll("[data-view-target]")) {
    item.addEventListener("click", () => {
      const target = item.dataset.viewTarget;
      if (window.location.hash === `#${target}`) showView(target);
      else window.location.hash = target;
    });
  }
  window.addEventListener("hashchange", () => showView(requestedView()));
}

document.addEventListener("DOMContentLoaded", () => {
  initializeOverview();
  initializeDataStatus();
  initializeNavigation();
  document.querySelector("#backend-status").addEventListener("click", () => checkBackendHealth(true));
  window.addEventListener("backend-status", (event) => {
    setBackendStatus(event.detail.state, event.detail.text);
  });
  checkBackendHealth();
  showView(requestedView());
});
