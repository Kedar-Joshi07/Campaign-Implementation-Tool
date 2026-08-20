import { getJSON } from "./api.js";

function setBackendStatus(state, text) {
  const status = document.querySelector("#backend-status");
  const label = document.querySelector("#backend-status-text");

  status.classList.remove("is-checking", "is-online", "is-offline");
  status.classList.add(state);
  label.textContent = text;
}

async function checkBackendHealth() {
  try {
    const health = await getJSON("/api/health");
    const label = health.status === "ok" ? `Backend online · v${health.version}` : "Backend unavailable";
    setBackendStatus(health.status === "ok" ? "is-online" : "is-offline", label);
  } catch (error) {
    console.error(error);
    setBackendStatus("is-offline", "Backend unavailable");
  }
}

document.addEventListener("DOMContentLoaded", checkBackendHealth);

