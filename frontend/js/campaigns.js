import { clearCachedJSON, getCachedJSON, getJSON } from "./api.js";
import {
  formatDate,
  formatNumber,
  hideError,
  setButtonLoading,
  setStatusBadge,
  showError,
} from "./ui.js";

const API_PATHS = {
  options: "/api/campaigns/options",
  campaigns: "/api/campaigns?limit=20&offset=0",
  createCampaign: "/api/campaigns",
  campaignDetail: (campaignId) => `/api/campaigns/${campaignId}`,
  campaignCurrentness: (campaignId) => `/api/campaigns/${campaignId}/currentness`,
  campaignFinalize: (campaignId) => `/api/campaigns/${campaignId}/finalize`,
  campaignExports: (campaignId) => `/api/campaigns/${campaignId}/exports?limit=50`,
  campaignExportCsv: (campaignId) => `/api/campaigns/${campaignId}/export.csv?acknowledge_pii=true`,
  audienceDetail: (audienceId) => `/api/audiences/${audienceId}`,
};

const STEP_IDS = ["1", "2", "3", "4"];
const PREFILL_AUDIENCE_STORAGE_KEY = "campaign_prefill_audience_id";
const HISTORY_POLL_INTERVAL_MS = 2_000;
const HISTORY_POLL_MAX_ATTEMPTS = 60;
const OPTIONS_CACHE_MS = 10_000;
const CAMPAIGNS_CACHE_MS = 10_000;
const AUDIENCE_DETAIL_CACHE_MS = 10_000;

const PROFILE_FIELDS = {
  EMAIL_CONTACT_V1: [
    "person_id",
    "propensity_score",
    "percentile_bucket",
    "decile",
    "rank_band",
    "first_name",
    "last_name",
    "email",
  ],
  DIRECT_MAIL_CONTACT_V1: [
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
};

let initialized = false;
let loadedOnce = false;
let activeStep = "1";
let optionsPayload = null;
let recentCampaigns = [];
let selectedAudienceId = null;
let selectedAudienceDetail = null;
let activeCampaignDetail = null;
let loadRequestToken = 0;
let audienceDetailRequestToken = 0;
let campaignDetailRequestToken = 0;
let exportHistoryPollTimer = null;
let exportHistoryPollAttempts = 0;
let pendingPrefillAudienceId = null;
let mutationInFlight = false;

function dispatchBackendStatus(state, text) {
  window.dispatchEvent(new CustomEvent("backend-status", { detail: { state, text } }));
}

function setCampaignAnnouncement(message) {
  document.querySelector("#campaigns-status-announcement").textContent = message;
}

function clearStepError() {
  document.querySelector("#campaign-step-error-summary").hidden = true;
}

function showStepError(message) {
  const summary = document.querySelector("#campaign-step-error-summary");
  summary.textContent = message;
  summary.hidden = false;
  summary.focus();
}

function setState(state) {
  const mapping = {
    loading: "#campaigns-state-loading",
    backendUnavailable: "#campaigns-state-backend-unavailable",
    noEligible: "#campaigns-state-no-eligible",
    ready: "#campaigns-state-ready",
  };
  for (const [name, selector] of Object.entries(mapping)) {
    document.querySelector(selector).hidden = name !== state;
  }
  setCampaignAnnouncement(`Campaign Builder state: ${state}.`);
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
    panel.hidden = !selected;
  }
  setCampaignAnnouncement(`Campaign Builder step ${step} active.`);
}

function setActionHelp(message) {
  document.querySelector("#campaign-action-disabled-help").textContent = message;
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

function normalizeChannel() {
  return document.querySelector("#campaign-channel").value;
}

function normalizeAudienceId(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function getSelectedAudienceIdFromControl() {
  return normalizeAudienceId(document.querySelector("#campaign-audience-select").value);
}

function activeCampaignId() {
  return normalizeAudienceId(activeCampaignDetail?.campaign_id);
}

function updateShellStatus() {
  const badge = document.querySelector("#campaign-shell-status");
  if (!activeCampaignDetail) {
    setStatusBadge(badge, "OK");
    badge.textContent = "Ready";
    return;
  }

  const status = String(activeCampaignDetail.status || "").toUpperCase();
  const isCurrent = activeCampaignDetail.currentness?.is_current === true;

  if (status === "DRAFT") {
    setStatusBadge(badge, isCurrent ? "RUNNING" : "WARNING");
    badge.textContent = isCurrent ? "DRAFT" : "DRAFT (STALE)";
    return;
  }

  if (status === "FINALIZED") {
    setStatusBadge(badge, isCurrent ? "COMPLETED" : "WARNING");
    badge.textContent = isCurrent ? "FINALIZED" : "FINALIZED (STALE)";
    return;
  }

  setStatusBadge(badge, "WARNING");
  badge.textContent = status || "Unknown";
}

function renderChannelOptions() {
  const select = document.querySelector("#campaign-channel");
  const previous = select.value;
  select.replaceChildren();

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose channel";
  select.append(placeholder);

  const channels = Array.isArray(optionsPayload?.supported_channels)
    ? optionsPayload.supported_channels
    : ["EMAIL", "DIRECT_MAIL"];

  for (const channel of channels) {
    const option = document.createElement("option");
    option.value = channel;
    option.textContent = channel;
    select.append(option);
  }

  if (channels.includes(previous)) {
    select.value = previous;
  }
}

function renderExportProfile(channel) {
  const list = document.querySelector("#campaign-export-profile-fields");
  list.replaceChildren();

  const profilesByChannel = optionsPayload?.profiles_by_channel || {};
  const profile = profilesByChannel[channel] || null;
  if (!profile) {
    document.querySelector("#campaign-profile-summary").textContent = "Choose channel to resolve export profile.";
    addSummaryRow(list, "Profile", "Not selected");
    return;
  }

  const fields = PROFILE_FIELDS[profile] || [];
  document.querySelector("#campaign-profile-summary").textContent = `${profile} enforced by selected channel.`;
  addSummaryRow(list, "Profile", profile);
  addSummaryRow(list, "Fields", fields.join(", "));
  addSummaryRow(list, "Privacy", "No arbitrary field picker. Restricted contract only.");
}

function formatAudienceOption(item) {
  const mode = item.selection_mode === "TOP_N"
    ? `Top ${formatNumber(item.target_count || 0)}`
    : "All matching";
  const status = item.is_current ? "CURRENT" : "STALE";
  return `#${formatNumber(item.audience_id)} · ${item.audience_name} · ${formatNumber(item.resolved_count)} selected · ${mode} · ${status}`;
}

function renderAudienceSelector() {
  const select = document.querySelector("#campaign-audience-select");
  select.replaceChildren();

  const eligible = Array.isArray(optionsPayload?.eligible_saved_audiences)
    ? optionsPayload.eligible_saved_audiences
    : [];

  if (!eligible.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No current eligible saved audiences";
    option.disabled = true;
    option.selected = true;
    select.append(option);
    selectedAudienceId = null;
    selectedAudienceDetail = null;
    document.querySelector("#campaign-audience-summary").replaceChildren();
    return;
  }

  for (const item of eligible) {
    const option = document.createElement("option");
    option.value = String(item.audience_id);
    option.textContent = formatAudienceOption(item);
    select.append(option);
  }

  if (selectedAudienceId && eligible.some((item) => item.audience_id === selectedAudienceId)) {
    select.value = String(selectedAudienceId);
  } else {
    selectedAudienceId = normalizeAudienceId(select.value);
  }
}

function renderAudienceSummary(detail) {
  const summary = document.querySelector("#campaign-audience-summary");
  summary.replaceChildren();

  if (!detail) {
    addSummaryRow(summary, "Audience", "Not selected");
    return;
  }

  const definition = detail.definition || {};
  const selectionMode = definition.selection_mode === "TOP_N"
    ? `TOP_N (${formatNumber(definition.target_count || 0)})`
    : "ALL_MATCHING";

  addSummaryRow(summary, "Audience", `${detail.audience_name} (#${formatNumber(detail.audience_id)})`);
  addSummaryRow(summary, "Selected count", formatNumber(definition.resolved_count));
  addSummaryRow(summary, "Selection mode", selectionMode);
  addSummaryRow(summary, "Scoring run", definition.scoring_run_id ? `#${formatNumber(definition.scoring_run_id)}` : "-");
  addSummaryRow(summary, "Model run", detail.provenance?.model_run_id ? `#${formatNumber(detail.provenance.model_run_id)}` : "-");
  addSummaryRow(summary, "Currentness", detail.currentness?.is_current ? "CURRENT" : "STALE");
  addSummaryRow(summary, "Created", formatDate(detail.created_at, true));
}

function renderCampaignDetailSummary() {
  const detailSummary = document.querySelector("#campaign-detail-summary");
  detailSummary.replaceChildren();

  if (!activeCampaignDetail) {
    addSummaryRow(detailSummary, "Campaign", "No campaign selected");
    return;
  }

  addSummaryRow(detailSummary, "Campaign", `${activeCampaignDetail.campaign_name} (#${formatNumber(activeCampaignDetail.campaign_id)})`);
  addSummaryRow(detailSummary, "Status", activeCampaignDetail.status);
  addSummaryRow(detailSummary, "Channel", activeCampaignDetail.channel || "-");
  addSummaryRow(detailSummary, "Saved audience", `#${formatNumber(activeCampaignDetail.saved_audience_id)}`);
  addSummaryRow(detailSummary, "Resolved count", formatNumber(activeCampaignDetail.saved_audience_resolved_count));
  addSummaryRow(detailSummary, "Created", formatDate(activeCampaignDetail.created_at, true));
  addSummaryRow(detailSummary, "Updated", formatDate(activeCampaignDetail.updated_at, true));
  addSummaryRow(detailSummary, "Finalized", activeCampaignDetail.finalized_at ? formatDate(activeCampaignDetail.finalized_at, true) : "-");
}

function renderCurrentnessSummary(currentness) {
  const list = document.querySelector("#campaign-currentness-summary");
  const badge = document.querySelector("#campaign-currentness-badge");
  const note = document.querySelector("#campaign-currentness-note");

  list.replaceChildren();

  if (!currentness) {
    setStatusBadge(badge, "NOT_LOADED");
    badge.textContent = "Not evaluated";
    note.textContent = "Open or create a campaign to evaluate currentness and export eligibility.";
    addSummaryRow(list, "Current", "Unknown");
    return;
  }

  const isCurrent = currentness.is_current === true;
  setStatusBadge(badge, isCurrent ? "COMPLETED" : "WARNING");
  badge.textContent = isCurrent ? "CURRENT" : "STALE";

  addSummaryRow(list, "Current", isCurrent ? "Yes" : "No");
  addSummaryRow(list, "Ready for finalize", currentness.ready_for_finalize ? "Yes" : "No");
  addSummaryRow(list, "Ready for export", currentness.ready_for_export ? "Yes" : "No");
  addSummaryRow(list, "Saved audience current", currentness.saved_audience_current ? "Yes" : "No");
  addSummaryRow(list, "Scoring current", currentness.scoring_current ? "Yes" : "No");
  addSummaryRow(list, "Rank boundaries", currentness.rank_ready ? "Prepared" : "Missing");
  addSummaryRow(list, "Analytics snapshot", currentness.analytics_ready ? "Prepared" : "Missing");

  if (Array.isArray(currentness.issues) && currentness.issues.length) {
    note.textContent = currentness.issues[0];
  } else {
    note.textContent = "Campaign is current for immutable audience and source/model provenance.";
  }
}

function renderReviewSummary() {
  const review = document.querySelector("#campaign-review-summary");
  review.replaceChildren();

  const campaignName = document.querySelector("#campaign-name").value.trim();
  const description = document.querySelector("#campaign-description").value.trim();
  const channel = normalizeChannel();
  const launchDate = document.querySelector("#campaign-launch-date").value;

  addSummaryRow(review, "Campaign name", campaignName || "-");
  addSummaryRow(review, "Description", description || "-");
  addSummaryRow(review, "Channel", channel || "-");
  addSummaryRow(review, "Planned launch", launchDate || "Not set");

  if (selectedAudienceDetail) {
    const definition = selectedAudienceDetail.definition || {};
    const selectionMode = definition.selection_mode === "TOP_N"
      ? `TOP_N (${formatNumber(definition.target_count || 0)})`
      : "ALL_MATCHING";

    addSummaryRow(review, "Selected audience", `${selectedAudienceDetail.audience_name} (#${formatNumber(selectedAudienceDetail.audience_id)})`);
    addSummaryRow(review, "Resolved audience count", formatNumber(definition.resolved_count));
    addSummaryRow(review, "Immutable audience selection", selectionMode);
    addSummaryRow(review, "Scoring run", definition.scoring_run_id ? `#${formatNumber(definition.scoring_run_id)}` : "-");
    addSummaryRow(review, "Currentness", selectedAudienceDetail.currentness?.is_current ? "CURRENT" : "STALE");
  }

  if (activeCampaignDetail?.currentness) {
    addSummaryRow(review, "Campaign currentness", activeCampaignDetail.currentness.is_current ? "CURRENT" : "STALE");
  }

  const profile = optionsPayload?.profiles_by_channel?.[channel] || "Not selected";
  addSummaryRow(review, "Export profile", profile);
  addSummaryRow(review, "Privacy", "No PII preview is shown in UI. Contact PII appears only in export stream.");
}

function renderRecentCampaigns() {
  const tbody = document.querySelector("#campaign-recent-body");
  tbody.replaceChildren();

  if (!recentCampaigns.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = "No campaigns yet. Create a draft from a current saved audience.";
    row.append(cell);
    tbody.append(row);
    return;
  }

  for (const item of recentCampaigns) {
    const row = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.textContent = `#${formatNumber(item.campaign_id)}`;

    const nameCell = document.createElement("td");
    nameCell.textContent = item.campaign_name;

    const statusCell = document.createElement("td");
    const statusBadge = document.createElement("span");
    statusBadge.className = "status-badge";
    setStatusBadge(statusBadge, item.status === "FINALIZED" ? "COMPLETED" : "RUNNING");
    statusBadge.textContent = item.status;
    statusCell.append(statusBadge);

    const channelCell = document.createElement("td");
    channelCell.textContent = item.channel;

    const countCell = document.createElement("td");
    countCell.className = "numeric";
    countCell.textContent = formatNumber(item.saved_audience_resolved_count);

    const updatedCell = document.createElement("td");
    updatedCell.textContent = formatDate(item.updated_at, true);

    const currentnessCell = document.createElement("td");
    currentnessCell.textContent = item.currentness?.is_current ? "CURRENT" : "STALE";

    const actionCell = document.createElement("td");
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "button button-secondary";
    openButton.textContent = "Open";
    openButton.addEventListener("click", () => {
      openCampaign(item.campaign_id).catch((error) => {
        showStepError(error.message || "Unable to open campaign.");
      });
    });
    actionCell.append(openButton);

    row.append(
      idCell,
      nameCell,
      statusCell,
      channelCell,
      countCell,
      updatedCell,
      currentnessCell,
      actionCell,
    );
    tbody.append(row);
  }
}

function renderExportHistory(events) {
  const body = document.querySelector("#campaign-export-history-body");
  body.replaceChildren();

  if (!events.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No export events yet for this campaign.";
    row.append(cell);
    body.append(row);
    return;
  }

  for (const event of events) {
    const row = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.textContent = `#${formatNumber(event.export_event_id)}`;

    const timeCell = document.createElement("td");
    timeCell.textContent = formatDate(event.completed_at || event.started_at, true);

    const profileCell = document.createElement("td");
    profileCell.textContent = event.export_profile;

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    if (event.status === "COMPLETED") {
      setStatusBadge(badge, "COMPLETED");
    } else if (event.status === "STARTED") {
      setStatusBadge(badge, "RUNNING");
    } else if (event.status === "ABORTED") {
      setStatusBadge(badge, "WARNING");
    } else {
      setStatusBadge(badge, "FAILED");
    }
    badge.textContent = event.status;
    statusCell.append(badge);

    const rowsCell = document.createElement("td");
    rowsCell.className = "numeric";
    rowsCell.textContent = formatNumber(event.row_count);

    const checksumCell = document.createElement("td");
    checksumCell.textContent = event.csv_sha256 || "-";

    row.append(idCell, timeCell, profileCell, statusCell, rowsCell, checksumCell);
    body.append(row);
  }
}

function applyCampaignToForm(campaign) {
  if (!campaign) {
    return;
  }
  document.querySelector("#campaign-name").value = campaign.campaign_name || "";
  document.querySelector("#campaign-description").value = campaign.description || "";
  document.querySelector("#campaign-channel").value = campaign.channel || "";
  document.querySelector("#campaign-launch-date").value = campaign.planned_launch_date || "";
}

function clearCampaignDetail() {
  activeCampaignDetail = null;
  renderCampaignDetailSummary();
  renderCurrentnessSummary(null);
  renderExportHistory([]);
  updateShellStatus();
}

function stopExportHistoryPolling() {
  if (exportHistoryPollTimer !== null) {
    window.clearTimeout(exportHistoryPollTimer);
    exportHistoryPollTimer = null;
  }
  exportHistoryPollAttempts = 0;
}

function synchronizeActionState() {
  const createButton = document.querySelector("#campaign-create-draft");
  const reviewButton = document.querySelector("#campaign-review-draft");
  const finalizeButton = document.querySelector("#campaign-finalize");
  const exportButton = document.querySelector("#campaign-export");
  const piiAcknowledged = document.querySelector("#campaign-pii-ack").checked;

  const hasCurrentAudience = selectedAudienceDetail?.currentness?.is_current === true;
  const campaignStatus = String(activeCampaignDetail?.status || "").toUpperCase();
  const readyForFinalize = activeCampaignDetail?.currentness?.ready_for_finalize === true;
  const readyForExport = activeCampaignDetail?.currentness?.ready_for_export === true;

  createButton.dataset.defaultLabel = campaignStatus === "DRAFT" ? "Save Draft" : "Create Draft";
  createButton.textContent = createButton.dataset.defaultLabel;

  createButton.disabled = mutationInFlight || !hasCurrentAudience;
  reviewButton.disabled = mutationInFlight;
  finalizeButton.disabled = mutationInFlight || campaignStatus !== "DRAFT" || !readyForFinalize;
  exportButton.disabled = mutationInFlight || campaignStatus !== "FINALIZED" || !readyForExport || !piiAcknowledged;

  if (!activeCampaignDetail) {
    setActionHelp("Create or open a campaign to enable finalize and export checks.");
  } else if (campaignStatus === "DRAFT" && !readyForFinalize) {
    const issue = activeCampaignDetail.currentness?.issues?.[0] || "Campaign is not current for finalize.";
    setActionHelp(`Finalize blocked: ${issue}`);
  } else if (campaignStatus === "FINALIZED" && !readyForExport) {
    const issue = activeCampaignDetail.currentness?.issues?.[0] || "Campaign is not current for export.";
    setActionHelp(`Export blocked: ${issue}`);
  } else if (campaignStatus === "FINALIZED" && readyForExport && !piiAcknowledged) {
    setActionHelp("Check the PII acknowledgement to enable export streaming.");
  } else {
    setActionHelp("Finalize and export are governed by campaign status, currentness, and PII acknowledgement.");
  }

  updateShellStatus();
}

function validateStep1() {
  if (!selectedAudienceDetail) {
    return "Select a current saved audience before continuing.";
  }
  if (selectedAudienceDetail.currentness?.is_current !== true) {
    return "Selected audience is stale and cannot be used for new draft setup.";
  }
  return null;
}

function validateStep2() {
  const campaignName = document.querySelector("#campaign-name").value.trim();
  const channel = normalizeChannel();

  if (!campaignName) {
    return "Campaign name is required.";
  }
  if (!channel || (channel !== "EMAIL" && channel !== "DIRECT_MAIL")) {
    return "Channel is required and must be EMAIL or DIRECT_MAIL.";
  }
  return null;
}

function validateStep3() {
  if (!selectedAudienceDetail || selectedAudienceDetail.currentness?.is_current !== true) {
    return "Audience currentness is stale; refresh and select a current audience.";
  }
  return null;
}

function validatePiiAcknowledgement() {
  if (!document.querySelector("#campaign-pii-ack").checked) {
    return "Export privacy acknowledgement is required before download.";
  }
  return null;
}

function buildDraftPayload() {
  const payload = {
    campaign_name: document.querySelector("#campaign-name").value.trim(),
    description: document.querySelector("#campaign-description").value.trim() || null,
    channel: normalizeChannel(),
    planned_launch_date: document.querySelector("#campaign-launch-date").value || null,
    saved_audience_id: selectedAudienceId,
  };
  return payload;
}

function clearCampaignCaches(campaignId = null, audienceId = null) {
  clearCachedJSON(API_PATHS.options);
  clearCachedJSON(API_PATHS.campaigns);
  if (campaignId) {
    clearCachedJSON(API_PATHS.campaignDetail(campaignId));
    clearCachedJSON(API_PATHS.campaignCurrentness(campaignId));
    clearCachedJSON(API_PATHS.campaignExports(campaignId));
  }
  if (audienceId) {
    clearCachedJSON(API_PATHS.audienceDetail(audienceId));
  }
}

async function loadSelectedAudienceDetail({ force = false } = {}) {
  const token = audienceDetailRequestToken + 1;
  audienceDetailRequestToken = token;

  const audienceId = getSelectedAudienceIdFromControl();
  selectedAudienceId = audienceId;
  if (!audienceId) {
    selectedAudienceDetail = null;
    renderAudienceSummary(null);
    synchronizeActionState();
    return;
  }

  if (force) {
    clearCachedJSON(API_PATHS.audienceDetail(audienceId));
  }

  const detail = await getCachedJSON(API_PATHS.audienceDetail(audienceId), {
    maxAgeMs: AUDIENCE_DETAIL_CACHE_MS,
    force,
  });

  if (token !== audienceDetailRequestToken) {
    return;
  }

  selectedAudienceDetail = detail;
  renderAudienceSummary(detail);
  renderReviewSummary();
  synchronizeActionState();
}

async function loadCampaignDetail(campaignId, { force = false } = {}) {
  const token = campaignDetailRequestToken + 1;
  campaignDetailRequestToken = token;

  if (!campaignId) {
    clearCampaignDetail();
    return;
  }

  if (force) {
    clearCachedJSON(API_PATHS.campaignDetail(campaignId));
    clearCachedJSON(API_PATHS.campaignCurrentness(campaignId));
  }

  const [detail, currentness] = await Promise.all([
    getCachedJSON(API_PATHS.campaignDetail(campaignId), { maxAgeMs: CAMPAIGNS_CACHE_MS, force }),
    getCachedJSON(API_PATHS.campaignCurrentness(campaignId), { maxAgeMs: CAMPAIGNS_CACHE_MS, force }),
  ]);

  if (token !== campaignDetailRequestToken) {
    return;
  }

  activeCampaignDetail = {
    ...detail,
    currentness,
  };

  applyCampaignToForm(activeCampaignDetail);
  renderCampaignDetailSummary();
  renderCurrentnessSummary(activeCampaignDetail.currentness);
  renderReviewSummary();
  renderExportProfile(activeCampaignDetail.channel || normalizeChannel());

  await loadExportHistory(campaignId, { force });
  synchronizeActionState();
}

async function loadRecentCampaigns({ force = false } = {}) {
  if (force) {
    clearCachedJSON(API_PATHS.campaigns);
  }

  const campaigns = await getCachedJSON(API_PATHS.campaigns, {
    maxAgeMs: CAMPAIGNS_CACHE_MS,
    force,
  });

  recentCampaigns = Array.isArray(campaigns) ? campaigns : [];
  renderRecentCampaigns();
}

async function loadExportHistory(campaignId, { force = false } = {}) {
  if (!campaignId) {
    renderExportHistory([]);
    return;
  }

  if (force) {
    clearCachedJSON(API_PATHS.campaignExports(campaignId));
  }

  const events = await getCachedJSON(API_PATHS.campaignExports(campaignId), {
    maxAgeMs: CAMPAIGNS_CACHE_MS,
    force,
  });
  renderExportHistory(Array.isArray(events) ? events : []);
}

function chooseAudienceFromPrefill() {
  if (pendingPrefillAudienceId) {
    const audienceId = pendingPrefillAudienceId;
    pendingPrefillAudienceId = null;
    return audienceId;
  }

  const stored = window.sessionStorage.getItem(PREFILL_AUDIENCE_STORAGE_KEY);
  if (!stored) {
    return null;
  }

  window.sessionStorage.removeItem(PREFILL_AUDIENCE_STORAGE_KEY);
  return normalizeAudienceId(stored);
}

async function openCampaign(campaignId) {
  clearStepError();
  hideError(document.querySelector("#campaigns-error"));

  await loadCampaignDetail(campaignId, { force: true });
  if (activeCampaignDetail?.status === "FINALIZED") {
    setStep("4");
  } else {
    setStep("2");
  }
  setCampaignAnnouncement(`Opened campaign #${formatNumber(campaignId)}.`);
}

async function submitDraft() {
  clearStepError();

  const stepError = validateStep2();
  if (stepError) {
    showStepError(stepError);
    return;
  }

  if (!selectedAudienceId) {
    showStepError("Select a current saved audience before creating a draft.");
    return;
  }

  const payload = buildDraftPayload();
  const draftCampaignId = activeCampaignDetail?.status === "DRAFT" ? activeCampaignId() : null;

  mutationInFlight = true;
  synchronizeActionState();
  setButtonLoading(document.querySelector("#campaign-create-draft"), true, draftCampaignId ? "Saving..." : "Creating...");

  try {
    let detail;
    if (draftCampaignId) {
      detail = await getJSON(API_PATHS.campaignDetail(draftCampaignId), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      detail = await getJSON(API_PATHS.createCampaign, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    clearCampaignCaches(detail.campaign_id, selectedAudienceId);
    await loadRecentCampaigns({ force: true });
    await loadCampaignDetail(detail.campaign_id, { force: true });

    setStep("3");
    dispatchBackendStatus("is-online", "Backend online");
    setCampaignAnnouncement(
      draftCampaignId
        ? `Campaign draft #${formatNumber(detail.campaign_id)} updated.`
        : `Campaign draft #${formatNumber(detail.campaign_id)} created.`,
    );
  } catch (error) {
    showStepError(error.message || "Unable to save campaign draft.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    mutationInFlight = false;
    synchronizeActionState();
    setButtonLoading(document.querySelector("#campaign-create-draft"), false, "Creating...");
  }
}

async function refreshActiveCampaign() {
  clearStepError();
  const campaignId = activeCampaignId();
  if (!campaignId) {
    showStepError("Create or open a campaign before running review checks.");
    return;
  }

  mutationInFlight = true;
  synchronizeActionState();
  setButtonLoading(document.querySelector("#campaign-review-draft"), true, "Refreshing...");

  try {
    await loadCampaignDetail(campaignId, { force: true });
    await loadRecentCampaigns({ force: true });
    setStep("3");
    setCampaignAnnouncement(`Campaign #${formatNumber(campaignId)} refreshed.`);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showStepError(error.message || "Unable to refresh campaign detail.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    mutationInFlight = false;
    synchronizeActionState();
    setButtonLoading(document.querySelector("#campaign-review-draft"), false, "Refreshing...");
  }
}

async function finalizeActiveCampaign() {
  clearStepError();

  const campaignId = activeCampaignId();
  if (!campaignId) {
    showStepError("Create or open a draft campaign before finalizing.");
    return;
  }

  mutationInFlight = true;
  synchronizeActionState();
  setButtonLoading(document.querySelector("#campaign-finalize"), true, "Finalizing...");

  try {
    await getJSON(API_PATHS.campaignFinalize(campaignId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    clearCampaignCaches(campaignId, selectedAudienceId);
    await loadRecentCampaigns({ force: true });
    await loadCampaignDetail(campaignId, { force: true });
    setStep("4");
    setCampaignAnnouncement(`Campaign #${formatNumber(campaignId)} finalized and immutable.`);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showStepError(error.message || "Unable to finalize campaign.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    mutationInFlight = false;
    synchronizeActionState();
    setButtonLoading(document.querySelector("#campaign-finalize"), false, "Finalizing...");
  }
}

function triggerDownload(url, filename) {
  const anchor = document.createElement("a");
  anchor.href = `${url}&_=${Date.now()}`;
  anchor.download = filename;
  anchor.target = "_blank";
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

function startExportHistoryPolling(campaignId) {
  stopExportHistoryPolling();
  exportHistoryPollAttempts = 0;

  const poll = async () => {
    exportHistoryPollAttempts += 1;
    try {
      await loadExportHistory(campaignId, { force: true });
      const latest = document.querySelector("#campaign-export-history-body tr td:nth-child(4) span")?.textContent || "";
      if (["COMPLETED", "FAILED", "ABORTED"].includes(latest)) {
        setCampaignAnnouncement(`Latest export finished with status ${latest}.`);
        synchronizeActionState();
        stopExportHistoryPolling();
        return;
      }
    } catch {
      stopExportHistoryPolling();
      return;
    }

    if (exportHistoryPollAttempts >= HISTORY_POLL_MAX_ATTEMPTS) {
      stopExportHistoryPolling();
      return;
    }

    exportHistoryPollTimer = window.setTimeout(poll, HISTORY_POLL_INTERVAL_MS);
  };

  exportHistoryPollTimer = window.setTimeout(poll, HISTORY_POLL_INTERVAL_MS);
}

async function exportCampaignCsv() {
  clearStepError();

  const campaignId = activeCampaignId();
  if (!campaignId) {
    showStepError("Open a finalized campaign before exporting.");
    return;
  }

  const piiError = validatePiiAcknowledgement();
  if (piiError) {
    showStepError(piiError);
    return;
  }

  if (activeCampaignDetail?.status !== "FINALIZED") {
    showStepError("Only FINALIZED campaigns can be exported.");
    return;
  }

  mutationInFlight = true;
  synchronizeActionState();
  setButtonLoading(document.querySelector("#campaign-export"), true, "Starting...");

  try {
    await loadCampaignDetail(campaignId, { force: true });
    if (activeCampaignDetail?.currentness?.ready_for_export !== true) {
      const issue = activeCampaignDetail?.currentness?.issues?.[0] || "Campaign is not current for export.";
      showStepError(issue);
      return;
    }

    const profile = activeCampaignDetail.export_profile || "target_list";
    const filename = `campaign_${campaignId}_${String(profile).toLowerCase()}.csv`;
    triggerDownload(API_PATHS.campaignExportCsv(campaignId), filename);

    clearCampaignCaches(campaignId);
    await loadExportHistory(campaignId, { force: true });
    startExportHistoryPolling(campaignId);
    setCampaignAnnouncement(`Export started for campaign #${formatNumber(campaignId)}.`);
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showStepError(error.message || "Unable to start campaign export.");
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  } finally {
    mutationInFlight = false;
    synchronizeActionState();
    setButtonLoading(document.querySelector("#campaign-export"), false, "Starting...");
  }
}

async function onAudienceSelectionChanged() {
  clearStepError();
  hideError(document.querySelector("#campaigns-error"));

  try {
    await loadSelectedAudienceDetail({ force: true });
    renderReviewSummary();
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    showError(
      document.querySelector("#campaigns-error"),
      document.querySelector("#campaigns-error-message"),
      error,
    );
    dispatchBackendStatus(
      error.status && error.status < 500 ? "is-online" : "is-offline",
      error.status && error.status < 500 ? "Backend online" : "Backend unavailable",
    );
  }
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

function bindActions() {
  document.querySelector("#campaign-audience-select").addEventListener("change", onAudienceSelectionChanged);

  document.querySelector("#campaign-step-next-1").addEventListener("click", () => {
    clearStepError();
    const error = validateStep1();
    if (error) {
      showStepError(error);
      return;
    }
    setStep("2");
  });

  document.querySelector("#campaign-step-back-2").addEventListener("click", () => {
    clearStepError();
    setStep("1");
  });

  document.querySelector("#campaign-step-next-2").addEventListener("click", () => {
    clearStepError();
    const error = validateStep2();
    if (error) {
      showStepError(error);
      return;
    }
    renderReviewSummary();
    setStep("3");
  });

  document.querySelector("#campaign-step-back-3").addEventListener("click", () => {
    clearStepError();
    setStep("2");
  });

  document.querySelector("#campaign-step-next-3").addEventListener("click", () => {
    clearStepError();
    const error = validateStep3();
    if (error) {
      showStepError(error);
      return;
    }
    setStep("4");
  });

  document.querySelector("#campaign-step-back-4").addEventListener("click", () => {
    clearStepError();
    setStep("3");
  });

  document.querySelector("#campaign-channel").addEventListener("change", () => {
    renderExportProfile(normalizeChannel());
    renderReviewSummary();
  });

  document.querySelector("#campaign-pii-ack").addEventListener("change", () => {
    synchronizeActionState();
  });

  document.querySelector("#campaign-create-draft").addEventListener("click", () => {
    submitDraft();
  });

  document.querySelector("#campaign-review-draft").addEventListener("click", () => {
    refreshActiveCampaign();
  });

  document.querySelector("#campaign-finalize").addEventListener("click", () => {
    finalizeActiveCampaign();
  });

  document.querySelector("#campaign-export").addEventListener("click", () => {
    exportCampaignCsv();
  });
}

function consumeAudiencePrefillSelection() {
  const prefill = chooseAudienceFromPrefill();
  if (!prefill) {
    return;
  }
  selectedAudienceId = prefill;
}

export async function loadCampaigns(force = false) {
  if (loadedOnce && !force) {
    return;
  }
  loadedOnce = true;

  const token = loadRequestToken + 1;
  loadRequestToken = token;

  stopExportHistoryPolling();
  clearStepError();
  hideError(document.querySelector("#campaigns-error"));
  setButtonLoading(document.querySelector("#campaigns-refresh"), true, "Refreshing...");
  setState("loading");

  if (force) {
    clearCampaignCaches(activeCampaignId(), selectedAudienceId);
  }

  try {
    const [optionsResult, campaignsResult] = await Promise.all([
      getCachedJSON(API_PATHS.options, { maxAgeMs: OPTIONS_CACHE_MS, force }),
      getCachedJSON(API_PATHS.campaigns, { maxAgeMs: CAMPAIGNS_CACHE_MS, force }),
    ]);

    if (token !== loadRequestToken) {
      return;
    }

    optionsPayload = optionsResult;
    recentCampaigns = Array.isArray(campaignsResult) ? campaignsResult : [];

    consumeAudiencePrefillSelection();

    renderChannelOptions();
    renderAudienceSelector();
    renderRecentCampaigns();

    const hasEligibleAudiences = Array.isArray(optionsPayload?.eligible_saved_audiences)
      && optionsPayload.eligible_saved_audiences.length > 0;
    const hasCampaigns = recentCampaigns.length > 0;

    if (!hasEligibleAudiences && !hasCampaigns) {
      clearCampaignDetail();
      setState("noEligible");
      setCampaignAnnouncement("No current saved audience is available for campaign draft setup.");
      dispatchBackendStatus("is-online", "Backend online");
      return;
    }

    setState("ready");

    await loadSelectedAudienceDetail({ force });

    if (hasCampaigns) {
      await loadCampaignDetail(recentCampaigns[0].campaign_id, { force });
    } else {
      clearCampaignDetail();
      renderExportProfile(normalizeChannel());
      renderReviewSummary();
      synchronizeActionState();
    }

    setStep("1");
    dispatchBackendStatus("is-online", "Backend online");
  } catch (error) {
    if (token !== loadRequestToken) {
      return;
    }

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
  if (initialized) {
    return;
  }
  initialized = true;

  bindActions();
  bindStepperKeyboard();

  document.querySelector("#campaigns-refresh").addEventListener("click", () => {
    loadCampaigns(true);
  });
  document.querySelector("#campaigns-retry").addEventListener("click", () => {
    loadCampaigns(true);
  });

  window.addEventListener("campaign-prefill-audience", (event) => {
    const candidate = normalizeAudienceId(event?.detail?.audienceId);
    if (!candidate) {
      return;
    }
    pendingPrefillAudienceId = candidate;
    window.sessionStorage.setItem(PREFILL_AUDIENCE_STORAGE_KEY, String(candidate));
    if (window.location.hash === "#campaigns") {
      loadCampaigns(true);
    }
  });

  renderChannelOptions();
  renderAudienceSelector();
  renderExportProfile("");
  renderReviewSummary();
  renderCampaignDetailSummary();
  renderCurrentnessSummary(null);
  renderExportHistory([]);
  synchronizeActionState();
  setStep("1");
}
