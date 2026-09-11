import { clearCachedJSON, getCachedJSON } from "./api.js";
import { formatDate, formatExactInteger, setStatusBadge } from "./ui.js";

const LIST_URL = "/api/audiences?limit=100&offset=0";
let initialized = false;
let loadPromise = null;

function setState(state) {
  document.querySelector("#business-target-groups-loading").hidden = state !== "loading";
  document.querySelector("#business-target-groups-error").hidden = state !== "error";
  document.querySelector("#business-target-groups-empty").hidden = state !== "empty";
  document.querySelector("#business-target-groups-list").hidden = state !== "ready";
}

function renderTargetGroups(groups) {
  const list = document.querySelector("#business-target-groups-list");
  list.replaceChildren();
  for (const group of groups) {
    const row = document.createElement("article");
    row.className = "saved-audience-item";

    const heading = document.createElement("div");
    heading.className = "saved-audience-item-heading";
    const name = document.createElement("strong");
    name.textContent = group.audience_name;
    const badge = document.createElement("span");
    badge.className = "status-badge";
    setStatusBadge(badge, group.is_current ? "COMPLETED" : "WARNING");
    badge.textContent = group.is_current ? "Up to date" : "Needs refresh";
    heading.append(name, badge);

    const meta = document.createElement("p");
    meta.className = "saved-audience-meta";
    meta.textContent = `${formatExactInteger(group.resolved_count)} people · Saved ${formatDate(group.created_at, true)}`;

    const actions = document.createElement("div");
    actions.className = "saved-audience-item-actions";
    const advanced = document.createElement("button");
    advanced.type = "button";
    advanced.className = "button button-secondary";
    advanced.textContent = "View advanced definition";
    advanced.addEventListener("click", () => {
      window.location.hash = "audience-explorer";
    });
    actions.append(advanced);
    row.append(heading, meta, actions);
    list.append(row);
  }
}

async function fetchTargetGroups(force = false) {
  setState("loading");
  try {
    const groups = await getCachedJSON(LIST_URL, { maxAgeMs: 20_000, force });
    renderTargetGroups(groups);
    setState(groups.length ? "ready" : "empty");
  } catch (error) {
    document.querySelector("#business-target-groups-error p").textContent = error.message;
    setState("error");
    document.querySelector("#business-target-groups-error").focus();
    throw error;
  }
}

export function initializeSavedTargetGroups() {
  if (initialized) return;
  initialized = true;
  const refresh = () => {
    clearCachedJSON(LIST_URL);
    loadPromise = fetchTargetGroups(true);
    loadPromise.catch(() => {});
  };
  document.querySelector("#business-target-groups-refresh").addEventListener("click", refresh);
  document.querySelector("#business-target-groups-retry").addEventListener("click", refresh);
}

export function loadSavedTargetGroups() {
  if (!loadPromise) {
    loadPromise = fetchTargetGroups();
    loadPromise.catch(() => {});
  }
  return loadPromise;
}
