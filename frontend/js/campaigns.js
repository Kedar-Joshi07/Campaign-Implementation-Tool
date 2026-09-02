import { clearCachedJSON, getCachedJSON } from "./api.js";
import {
  formatDate,
  formatNumber,
  hideError,
  setButtonLoading,
  setStatusBadge,
  showError,
} from "./ui.js";

const API_PATHS = {
  audiences: "/api/audiences?limit=20&offset=0",
  audienceDetail: (audienceId) => `/api/audiences/${audienceId}`,
};

const STEP_IDS = ["1", "2", "3", "4"];
const EXPORT_PROFILES = {
  EMAIL: {
    profile: "EMAIL_CONTACT_V1",
    fields: [
      "person_id",
      "propensity_score",
      "percentile_bucket",
      "decile",
      "rank_band",
      "first_name",
      "last_name",
      "email",
    ],
  },
  DIRECT_MAIL: {
    profile: "DIRECT_MAIL_CONTACT_V1",
    fields: [
      "person_id",
      "propensity_score",
      "percentile_bucket",
      "decile",
      "rank_band",
      "first_name",
      "last_name",
      "address_line_1",
      "address_line_2",
      "city",
      "state",
      "postal_code",
    ],
  },
};

let initialized = false;
let loadedOnce = false;
let selectedAudience = null;
let selectedAudienceDetail = null;
let activeStep = "1";

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", { detail: { state, text } }));
}

function setCampaignAnnouncement(message) {
  document.querySelector("#campaigns-status-announcement").textContent = message;
}

function setState(state) {
  const mapping = {
    loading: "#campaigns-state-loading",
    backendUnavailable: "#campaigns-state-backend-unavailable",
    noEligible: "#campaigns-state-no-eligible",
    ready: "#campaigns-state-ready",
  };
  for (const [key, selector] of Object.entries(mapping)) {
    document.querySelector(selector).hidden = key !== state;
  }
  setCampaignAnnouncement(`Campaign Builder state: ${state}.`);
}

function showStepError(message) {
  const summary = document.querySelector("#campaign-step-error-summary");
  summary.textContent = message;
  summary.hidden = false;
  summary.focus();
}

function hideStepError() {
  document.querySelector("#campaign-step-error-summary").hidden = true;
}

function clearReviewSummary() {
  document.querySelector("#campaign-review-summary").replaceChildren();
}

function addSummaryRow(container, label, value) {
  const wrap = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  wrap.append(term, description);
  container.append(wrap);
}

function setStep(step) {
  activeStep = step;
  for (const stepId of STEP_IDS) {
    const button = document.querySelector(`#campaign-step-${stepId}`);
    const panel = document.querySelector(`#campaign-step-panel-${stepId}`);
    const selected = stepId === step;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-current", selected ? "step" : "false");
    button.setAttribute("aria-selected", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
    if (panel) {
      panel.hidden = !selected;
    }
  }
  setCampaignAnnouncement(`Campaign Builder step ${step} active.`);
}

function normalizeChannel() {
  return document.querySelector("#campaign-channel").value;
}

function renderExportProfile(channel) {
  const profile = EXPORT_PROFILES[channel] || null;
  const list = document.querySelector("#campaign-export-profile-fields");
  list.replaceChildren();
  if (!profile) {
    document.querySelector("#campaign-profile-summary").textContent = "Choose channel to resolve export profile.";
    addSummaryRow(list, "Profile", "Not selected");
    return;
  }

  document.querySelector("#campaign-profile-summary").textContent = `${profile.profile} enforced by selected channel.`;
  addSummaryRow(list, "Profile", profile.profile);
  addSummaryRow(list, "Fields", profile.fields.join(", "));
  addSummaryRow(list, "Privacy", "No arbitrary field picker. Restricted contract only.");
}

function formatAudienceOption(item) {
  const mode = item.selection_mode === "TOP_N"
    ? `Top ${formatNumber(item.target_count || 0)}`
    : "All matching";
  const status = item.is_current ? "CURRENT" : "STALE";
  return `#${formatNumber(item.audience_id)} · ${item.audience_name} · ${formatNumber(item.resolved_count)} selected · ${mode} · ${status}`;
}

function renderAudienceSelector(audiences) {
  const select = document.querySelector("#campaign-audience-select");
  select.replaceChildren();

  for (const item of audiences) {
    const option = document.createElement("option");
    option.value = String(item.audience_id);
    option.textContent = formatAudienceOption(item);
    select.append(option);
  }
}

function renderAudienceSummary(detail) {
  const summary = document.querySelector("#campaign-audience-summary");
  summary.replaceChildren();

  const selection = detail.definition || {};
  const selectionMode = selection.selection_mode === "TOP_N"
    ? `TOP_N (${formatNumber(selection.target_count || 0)})`
    : "ALL_MATCHING";
  addSummaryRow(summary, "Audience", `${detail.audience_name} (#${formatNumber(detail.audience_id)})`);
  addSummaryRow(summary, "Selected count", formatNumber(selection.resolved_count));
  addSummaryRow(summary, "Selection mode", selectionMode);
  addSummaryRow(summary, "Scoring run", selection.scoring_run_id ? `#${formatNumber(selection.scoring_run_id)}` : "-");
  addSummaryRow(summary, "Model run", detail.provenance?.model_run_id ? `#${formatNumber(detail.provenance.model_run_id)}` : "-");
  addSummaryRow(summary, "Created", formatDate(detail.created_at, true));

  const traitCount = Array.isArray(detail.profile_snapshot?.top_overindexed_traits)
    ? detail.profile_snapshot.top_overindexed_traits.length
    : 0;
  addSummaryRow(summary, "Top traits", traitCount > 0 ? `${traitCount} bounded over-index traits` : "No traits in snapshot");

  const currentness = detail.currentness?.is_current ? "CURRENT - usable in Campaign Builder" : "STALE - historical/read-only";
  addSummaryRow(summary, "Currentness", currentness);
}

function renderReviewSummary() {
  clearReviewSummary();
  const review = document.querySelector("#campaign-review-summary");
  const name = document.querySelector("#campaign-name").value.trim();
  const description = document.querySelector("#campaign-description").value.trim();
  const channel = normalizeChannel();
  const launchDate = document.querySelector("#campaign-launch-date").value;

  addSummaryRow(review, "Campaign name", name || "-");
  addSummaryRow(review, "Description", description || "-");
  addSummaryRow(review, "Channel", channel || "-");
  addSummaryRow(review, "Planned launch", launchDate || "Not set");

  if (selectedAudienceDetail) {
    const definition = selectedAudienceDetail.definition;
    const selectionMode = definition.selection_mode === "TOP_N"
      ? `TOP_N (${formatNumber(definition.target_count || 0)})`
      : "ALL_MATCHING";
    addSummaryRow(review, "Resolved audience count", formatNumber(definition.resolved_count));
    addSummaryRow(review, "Immutable audience selection", selectionMode);
    addSummaryRow(review, "Filter hash", selectedAudienceDetail.replay_request?.filter_hash || "-");
    addSummaryRow(review, "Historical source", selectedAudienceDetail.currentness?.is_current ? "Current" : "Stale");
    addSummaryRow(review, "Scoring run", definition.scoring_run_id ? `#${formatNumber(definition.scoring_run_id)}` : "-");
    addSummaryRow(review, "Model/artifact", "Verified");
    addSummaryRow(review, "Scoring run status", "Canonical");
  }

  const profile = EXPORT_PROFILES[channel];
  addSummaryRow(review, "Export profile", profile ? profile.profile : "Not selected");
  addSummaryRow(review, "Privacy", "No PII shown in UI preview; export stream only when enabled in Section 2.");
}

function currentAudienceFromSelect() {
  const audienceId = Number(document.querySelector("#campaign-audience-select").value);
  return Number.isInteger(audienceId) ? audienceId : null;
}

async function loadSelectedAudienceDetail(force = false) {
  const audienceId = currentAudienceFromSelect();
  if (!audienceId) {
    selectedAudienceDetail = null;
    document.querySelector("#campaign-audience-summary").replaceChildren();
    return;
  }

  if (force) {
    clearCachedJSON(API_PATHS.audienceDetail(audienceId));
  }

  const detail = await getCachedJSON(API_PATHS.audienceDetail(audienceId), {
    maxAgeMs: 15_000,
    force,
  });

  selectedAudienceDetail = detail;
  renderAudienceSummary(detail);
}

function validateStep1() {
  if (!selectedAudienceDetail) {
    return "Select a current eligible saved audience before continuing.";
  }
  if (!selectedAudienceDetail.currentness?.is_current) {
    return "Selected audience is stale and cannot be used for Campaign Builder draft setup.";
  }
  return null;
}

function validateStep2() {
  const name = document.querySelector("#campaign-name").value.trim();
  const channel = normalizeChannel();
  if (!name) {
    return "Campaign name is required.";
  }
  if (!channel || (channel !== "EMAIL" && channel !== "DIRECT_MAIL")) {
    return "Channel is required and must be EMAIL or DIRECT_MAIL.";
  }
  return null;
}

function validateStep3() {
  if (!selectedAudienceDetail?.currentness?.is_current) {
    return "Audience currentness changed to stale; review cannot continue.";
  }
  return null;
}

function validateStep4() {
  const acknowledged = document.querySelector("#campaign-pii-ack").checked;
  if (!acknowledged) {
    return "Export privacy acknowledgement is required before finalization/export actions.";
  }
  return null;
}

function bindStepperKeyboard() {
  const buttons = STEP_IDS.map((id) => document.querySelector(`#campaign-step-${id}`));
  buttons.forEach((button, index) => {
    button.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = buttons.length - 1;
      if (nextIndex !== null) {
        event.preventDefault();
        buttons[nextIndex].focus();
      }
    });
  });
}

function markShellReady() {
  const status = document.querySelector("#campaign-shell-status");
  setStatusBadge(status, "COMPLETED");
  status.textContent = "Ready";
}

function onAudienceSelectionChanged() {
  hideStepError();
  loadSelectedAudienceDetail(true).catch((error) => {
    showError(
      document.querySelector("#campaigns-error"),
      document.querySelector("#campaigns-error-message"),
      error,
    );
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  });
}

function bindActions() {
  document.querySelector("#campaign-audience-select").addEventListener("change", onAudienceSelectionChanged);

  document.querySelector("#campaign-step-next-1").addEventListener("click", () => {
    hideStepError();
    const error = validateStep1();
    if (error) {
      showStepError(error);
      return;
    }
    setStep("2");
  });

  document.querySelector("#campaign-step-back-2").addEventListener("click", () => {
    hideStepError();
    setStep("1");
  });

  document.querySelector("#campaign-step-next-2").addEventListener("click", () => {
    hideStepError();
    const error = validateStep2();
    if (error) {
      showStepError(error);
      return;
    }
    renderReviewSummary();
    setStep("3");
  });

  document.querySelector("#campaign-step-back-3").addEventListener("click", () => {
    hideStepError();
    setStep("2");
  });

  document.querySelector("#campaign-step-next-3").addEventListener("click", () => {
    hideStepError();
    const error = validateStep3();
    if (error) {
      showStepError(error);
      return;
    }
    setStep("4");
  });

  document.querySelector("#campaign-step-back-4").addEventListener("click", () => {
    hideStepError();
    setStep("3");
  });

  document.querySelector("#campaign-channel").addEventListener("change", () => {
    renderExportProfile(normalizeChannel());
  });

  for (const actionId of ["#campaign-create-draft", "#campaign-review-draft", "#campaign-finalize", "#campaign-export"]) {
    document.querySelector(actionId).addEventListener("click", () => {
      hideStepError();
      if (actionId === "#campaign-finalize" || actionId === "#campaign-export") {
        const error = validateStep4();
        if (error) {
          showStepError(error);
          return;
        }
      }
      showStepError("This action is feature-gated in Section 1. Backend create/finalize/export is enabled in Section 2.");
    });
  }
}

function eligibleAudiences(items) {
  return (items || []).filter((item) => item?.is_current === true);
}

function updateCampaignReadyState(eligibleItems) {
  if (!eligibleItems.length) {
    selectedAudience = null;
    selectedAudienceDetail = null;
    setState("noEligible");
    return;
  }

  setState("ready");
  renderAudienceSelector(eligibleItems);
  selectedAudience = eligibleItems[0];
  document.querySelector("#campaign-audience-select").value = String(selectedAudience.audience_id);
  markShellReady();
}

export async function loadCampaigns(force = false) {
  if (loadedOnce && !force) {
    return;
  }
  loadedOnce = true;

  hideError(document.querySelector("#campaigns-error"));
  setButtonLoading(document.querySelector("#campaigns-refresh"), true, "Refreshing...");
  setState("loading");

  try {
    const audiences = await getCachedJSON(API_PATHS.audiences, {
      maxAgeMs: 20_000,
      force,
    });

    const eligible = eligibleAudiences(audiences);
    updateCampaignReadyState(eligible);

    if (eligible.length) {
      await loadSelectedAudienceDetail(force);
      renderExportProfile(normalizeChannel());
      renderReviewSummary();
      setStep("1");
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showError(
      document.querySelector("#campaigns-error"),
      document.querySelector("#campaigns-error-message"),
      error,
    );
    setState("backendUnavailable");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    setButtonLoading(document.querySelector("#campaigns-refresh"), false, "Refreshing...");
  }
}

export function initializeCampaigns() {
  if (initialized) return;
  initialized = true;

  bindActions();
  bindStepperKeyboard();

  document.querySelector("#campaigns-refresh").addEventListener("click", () => {
    clearCachedJSON(API_PATHS.audiences);
    if (selectedAudience?.audience_id) {
      clearCachedJSON(API_PATHS.audienceDetail(selectedAudience.audience_id));
    }
    loadCampaigns(true);
  });

  document.querySelector("#campaigns-retry").addEventListener("click", () => loadCampaigns(true));
  renderExportProfile("");
  clearReviewSummary();
  setStep("1");
}
