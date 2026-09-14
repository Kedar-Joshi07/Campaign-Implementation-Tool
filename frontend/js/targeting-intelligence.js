import { getJSON } from "./api.js";
import {
  getCampaignPlannerState,
  setCampaignPlannerStep,
} from "./campaign-planner-state.js";

const POLL_DELAY_MS = 1250;

const PREPARATION_STAGE_LABELS = {
  QUEUED: "Targeting intelligence",
  CHECKING_COMPATIBILITY: "Targeting intelligence",
  RESOLVING_HISTORICAL_CONTEXT: "Past campaign history",
  CHECKING_TRAINING_ELIGIBILITY: "Past campaign history",
  RESOLVING_MODEL: "Preparing targeting intelligence",
  VALIDATING_MODEL: "Verifying results",
  RESOLVING_SCORING: "Potential customers",
  SCORING_POTENTIAL_CUSTOMERS: "Potential customers",
  PREPARING_TARGET_GROUP: "Preparing your Target Group",
  VERIFYING_FINAL_CURRENTNESS: "Verifying results",
  READY: "Up to date",
  BLOCKED: "Not enough past campaign history",
  FAILED: "Preparation could not finish",
  STALE: "Needs refresh",
  NOT_STARTED: "Not started",
};

let initialized = false;
let announce = () => {};
let requestGeneration = 0;

function addDetail(list, label, value) {
  if (value === null || value === undefined || value === "") return;
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = String(value);
  list.append(term, description);
}

function renderTechnicalDetails(resolution) {
  const list = document.querySelector("#planner-intelligence-details");
  list.replaceChildren();
  addDetail(list, "Boundary status", resolution.status.replaceAll("_", " "));
  addDetail(list, "Explicitly linked", resolution.explicitly_linked ? "Yes" : "No");
  addDetail(list, "Context-specific", resolution.context_specific ? "Yes" : "No");
  addDetail(list, "Context changed source", "No");
  const details = resolution.technical_details || {};
  addDetail(list, "Analysis run", details.analysis_run_id);
  addDetail(list, "Model run", details.model_run_id);
  addDetail(list, "Scoring run", details.scoring_run_id);
  addDetail(list, "Selected candidate", details.selected_candidate);
  addDetail(list, "Model policy", details.model_role_policy_version);
  addDetail(list, "Feature contract", details.feature_contract_version);
  addDetail(list, "Feature contract SHA-256", details.feature_contract_sha256);
  addDetail(list, "Artifact SHA-256", details.artifact_sha256);
  addDetail(list, "Customer source checksum", details.customer_source_checksum);
  addDetail(list, "Campaign source checksum", details.campaign_sales_source_checksum);
  addDetail(list, "Demographic source checksum", details.demographic_source_checksum);
  if (resolution.compatibility_checked_dimensions.length) {
    addDetail(
      list,
      "Compatibility checked",
      resolution.compatibility_checked_dimensions.join(", "),
    );
  }
  if (resolution.issues.length) addDetail(list, "Blocking checks", resolution.issues.join("; "));
}

function renderPreparationTechnicalDetails(preparation) {
  const list = document.querySelector("#planner-intelligence-details");
  list.replaceChildren();
  addDetail(list, "Preparation status", preparation.status.replaceAll("_", " "));
  addDetail(list, "Preparation stage", preparation.stage.replaceAll("_", " "));
  addDetail(list, "Progress", `${preparation.progress_percent}%`);
  const details = preparation.technical_details || {};
  addDetail(list, "Orchestration", details.orchestration_id);
  addDetail(list, "Modeling Context SHA-256", details.modeling_context_sha256);
  addDetail(list, "Intelligence key SHA-256", details.intelligence_key_sha256);
  addDetail(list, "Generation", details.generation_id);
  addDetail(list, "Analysis run", details.analysis_run_id);
  addDetail(list, "Model run", details.model_run_id);
  addDetail(list, "Scoring run", details.scoring_run_id);
  addDetail(list, "Training job", details.training_job_id);
  addDetail(list, "Scoring job", details.scoring_job_id);
  addDetail(list, "Technical message", details.technical_message);
}

export function renderPhase9TechnicalDetails(details, selector) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  addDetail(list, "Targeting source status", details.source_status);
  addDetail(
    list,
    "Source currentness",
    details.source_currentness?.replaceAll("_", " "),
  );
  addDetail(list, "Targeting / scoring run", details.scoring_run_id);
  addDetail(list, "Source analysis", details.analysis_run_id);
  addDetail(list, "Model run", details.model_run_id);
  addDetail(list, "Selected candidate", details.selected_candidate);
  addDetail(list, "Feature contract version", details.feature_contract_version);
  addDetail(list, "Feature contract SHA-256", details.feature_contract_sha256);
  addDetail(list, "Model policy", details.model_role_policy_version);
  addDetail(list, "Customer source checksum", details.customer_source_checksum);
  addDetail(list, "Campaign source checksum", details.campaign_sales_source_checksum);
  addDetail(list, "Demographic source checksum", details.demographic_source_checksum);
  addDetail(list, "Artifact SHA-256", details.artifact_sha256);
  addDetail(list, "Audience filter hash", details.audience_filter_hash);
  addDetail(list, "Saved Audience ID", details.saved_audience_id);
  addDetail(
    list,
    "Targeting-intelligence resolution contract",
    details.targeting_intelligence_resolution_contract_version,
  );
  addDetail(
    list,
    "Campaign-context contract",
    details.campaign_targeting_context_contract_version,
  );
  addDetail(list, "Targeting-segment contract", details.targeting_segment_contract_version);
  addDetail(
    list,
    "Business match-strength contract",
    details.business_match_strength_contract_version,
  );
  addDetail(list, "Audience-filter contract", details.audience_filter_contract_version);
  addDetail(list, "Target Group preview contract", details.target_group_preview_contract_version);
  addDetail(
    list,
    "Target Group / Campaign contract",
    details.target_group_campaign_contract_version,
  );
  addDetail(
    list,
    "Saved Target Group contract",
    details.saved_target_group_contract_version,
  );
}

function reuseMessage(summary) {
  if (!summary) return "Checking whether verified targeting intelligence can be reused.";
  const decisions = Object.values(summary);
  if (decisions.length && decisions.every((decision) => decision === "REUSE")) {
    return "Existing verified targeting intelligence matches this campaign and is ready.";
  }
  if (
    summary.analysis === "REUSE"
    && summary.model === "REUSE"
    && (summary.scoring === "BUILD" || summary.rank === "BUILD")
  ) {
    return "Campaign history is still valid; refreshing matches for current potential-customer data.";
  }
  if (summary.analysis === "BUILD") {
    return "Preparing new targeting intelligence for this campaign.";
  }
  return "Preparing targeting intelligence while reusing verified work where possible.";
}

function showState() {
  document.querySelector("#planner-intelligence-loading").hidden = true;
  document.querySelector("#planner-intelligence-state").hidden = false;
}

function setProgress(preparation) {
  const visible = ["QUEUED", "RUNNING"].includes(preparation.status);
  const container = document.querySelector("#planner-intelligence-progress");
  container.hidden = !visible;
  if (!visible) return;
  const progress = Math.max(0, Math.min(100, preparation.progress_percent));
  const label = PREPARATION_STAGE_LABELS[preparation.stage] || "Preparing";
  const bar = document.querySelector("#planner-intelligence-progressbar");
  bar.setAttribute("aria-valuenow", String(progress));
  bar.setAttribute("aria-valuetext", `${progress}% complete — ${label}`);
  document.querySelector("#planner-intelligence-progress-fill").style.width = `${progress}%`;
  document.querySelector("#planner-intelligence-progress-percent").textContent = `${progress}%`;
  document.querySelector("#planner-intelligence-progress-label").textContent = label;
}

function unavailableResolution(explanation) {
  return {
    status: "NOT_AVAILABLE",
    message: "Targeting is not yet available for this campaign",
    explanation,
    explicitly_linked: false,
    can_preview: false,
    context_specific: false,
    compatibility_checked_dimensions: [],
    issues: [],
    technical_details: null,
  };
}

function dispatchPreviewBlocked(explanation) {
  document.dispatchEvent(new CustomEvent("targeting-intelligence-resolved", {
    detail: unavailableResolution(explanation),
  }));
}

function renderPreparation(preparation) {
  showState();
  const container = document.querySelector("#planner-intelligence-state");
  const badge = document.querySelector("#planner-intelligence-status");
  const retry = document.querySelector("#planner-intelligence-retry");
  const back = document.querySelector("#planner-intelligence-back-context");
  const active = ["QUEUED", "RUNNING"].includes(preparation.status);
  const blocked = preparation.status === "BLOCKED";
  const failed = preparation.status === "FAILED";

  container.classList.toggle("is-ready", false);
  container.classList.toggle("is-blocked", blocked);
  container.classList.toggle("is-failed", failed);
  container.classList.toggle("is-preparing", active);
  container.setAttribute("role", failed ? "alert" : "status");
  container.setAttribute("aria-busy", String(active));
  badge.textContent = blocked
    ? "Not enough history"
    : failed
      ? "Could not finish"
      : preparation.status === "STALE"
        ? "Needs refresh"
        : "Preparing";
  badge.className = `status-badge ${failed ? "is-warning" : "is-neutral"}`;

  document.querySelector("#planner-intelligence-message").textContent = blocked
    ? "There is not enough verified past campaign history for this combination yet."
    : failed
      ? "We could not finish preparing targeting intelligence. Your campaign inputs are saved."
      : "Preparing your Target Group";
  document.querySelector("#planner-intelligence-explanation").textContent = blocked
    ? "Review your Campaign Context. Your choices remain unchanged and will never be removed automatically."
    : failed
      ? "Try again from the last verified step, or go back to review your Campaign Context."
      : preparation.business_message;
  document.querySelector("#planner-intelligence-reuse-message").textContent =
    reuseMessage(preparation.reuse_summary);
  document.querySelector("#planner-preview-block-note").textContent = active
    ? "Your exact preview will open automatically when verification is complete."
    : "Exact target counts and target-group saving remain blocked until targeting intelligence is up to date.";
  retry.hidden = !failed;
  retry.textContent = "Try again";
  back.hidden = !(blocked || failed);
  document.querySelector("#planner-next-4").disabled = true;
  setProgress(preparation);
  renderPreparationTechnicalDetails(preparation);
  dispatchPreviewBlocked(document.querySelector("#planner-intelligence-explanation").textContent);
  announce(document.querySelector("#planner-intelligence-message").textContent);
  if (blocked || failed) container.focus();
}

function renderResolution(resolution, reuseSummary = null) {
  showState();
  const container = document.querySelector("#planner-intelligence-state");
  container.classList.toggle("is-ready", resolution.can_preview);
  container.classList.toggle("is-blocked", !resolution.can_preview);
  container.classList.remove("is-failed", "is-preparing");
  container.setAttribute("role", "status");
  container.setAttribute("aria-busy", "false");
  const badge = document.querySelector("#planner-intelligence-status");
  const businessStatuses = {
    READY: "Up to date",
    NEEDS_REFRESH: "Needs refresh",
    STALE: "Needs refresh",
    NOT_AVAILABLE: "Not available",
    INCOMPATIBLE_CONTEXT: "Not available",
  };
  badge.textContent = businessStatuses[resolution.status] || "Not available";
  badge.className = `status-badge ${resolution.can_preview ? "is-ready" : "is-neutral"}`;
  document.querySelector("#planner-intelligence-message").textContent = resolution.message;
  document.querySelector("#planner-intelligence-explanation").textContent = resolution.explanation;
  document.querySelector("#planner-intelligence-reuse-message").textContent =
    resolution.can_preview ? reuseMessage(reuseSummary) : "";
  document.querySelector("#planner-preview-block-note").textContent = resolution.can_preview
    ? "Targeting intelligence is up to date. Loading your exact Target Group preview."
    : "Exact target counts and target-group saving are blocked. No estimated or fabricated count is shown.";
  document.querySelector("#planner-intelligence-progress").hidden = true;
  document.querySelector("#planner-intelligence-retry").hidden = resolution.can_preview;
  document.querySelector("#planner-intelligence-retry").textContent = "Check again";
  document.querySelector("#planner-intelligence-back-context").hidden = resolution.can_preview;
  document.querySelector("#planner-next-4").disabled = !resolution.can_preview;
  renderTechnicalDetails(resolution);
  document.dispatchEvent(new CustomEvent("targeting-intelligence-resolved", {
    detail: resolution,
  }));
}

async function loadReadyPhase9(contextId, reuseSummary, generation) {
  const resolution = await getJSON(
    `/api/campaign-planner/contexts/${contextId}/targeting-intelligence`,
  );
  if (generation !== requestGeneration) return false;
  renderResolution(resolution, reuseSummary);
  announce(resolution.can_preview
    ? "Targeting intelligence is up to date. Loading the exact Target Group preview."
    : resolution.message);
  return resolution.can_preview;
}

async function pollPreparation(contextId, generation) {
  if (generation !== requestGeneration) return false;
  try {
    const preparation = await getJSON(
      `/api/campaign-planner/contexts/${contextId}/targeting-intelligence/preparation`,
    );
    if (generation !== requestGeneration) return false;
    if (preparation.status === "READY") {
      return loadReadyPhase9(contextId, preparation.reuse_summary, generation);
    }
    renderPreparation(preparation);
    if (["QUEUED", "RUNNING"].includes(preparation.status)) {
      window.setTimeout(() => pollPreparation(contextId, generation), POLL_DELAY_MS);
    }
    return false;
  } catch (error) {
    if (generation !== requestGeneration) return false;
    renderFailedRequest(error);
    return false;
  }
}

function renderFailedRequest(error) {
  renderPreparation({
    status: "FAILED",
    stage: "FAILED",
    progress_percent: 0,
    business_message: error.message,
    reuse_summary: null,
    technical_details: {},
  });
}

async function beginPreparation(contextId, generation) {
  try {
    const preparation = await getJSON(
      `/api/campaign-planner/contexts/${contextId}/targeting-intelligence/prepare`,
      { method: "POST" },
    );
    if (generation !== requestGeneration) return false;
    if (preparation.status === "READY") {
      return loadReadyPhase9(contextId, preparation.reuse_summary, generation);
    }
    renderPreparation(preparation);
    if (["QUEUED", "RUNNING"].includes(preparation.status)) {
      window.setTimeout(() => pollPreparation(contextId, generation), POLL_DELAY_MS);
    }
    return false;
  } catch (error) {
    if (generation !== requestGeneration) return false;
    renderFailedRequest(error);
    return false;
  }
}

export async function refreshTargetingIntelligence() {
  const state = getCampaignPlannerState();
  const generation = ++requestGeneration;
  document.querySelector("#planner-intelligence-loading").hidden = false;
  document.querySelector("#planner-intelligence-state").hidden = true;
  if (!state.targetingContextId) {
    renderResolution(unavailableResolution(
      "Save Campaign Context and targeting preferences first.",
    ));
    return false;
  }
  const contextId = state.targetingContextId;
  try {
    const plan = await getJSON(
      `/api/campaign-planner/contexts/${contextId}/intelligence-plan`,
    );
    if (generation !== requestGeneration) return false;
    if (plan.readiness === "READY") {
      return loadReadyPhase9(contextId, plan.reuse_summary, generation);
    }
    if (["PREPARING", "BLOCKED", "FAILED"].includes(plan.readiness)) {
      return pollPreparation(contextId, generation);
    }
    return beginPreparation(contextId, generation);
  } catch (error) {
    if (generation !== requestGeneration) return false;
    renderFailedRequest(error);
    return false;
  }
}

async function retryTargetingIntelligence() {
  const state = getCampaignPlannerState();
  if (!state.targetingContextId) return refreshTargetingIntelligence();
  const generation = ++requestGeneration;
  document.querySelector("#planner-intelligence-retry").disabled = true;
  try {
    const preparation = await getJSON(
      `/api/campaign-planner/contexts/${state.targetingContextId}/targeting-intelligence/preparation/retry`,
      { method: "POST" },
    );
    if (generation !== requestGeneration) return false;
    if (preparation.status === "READY") {
      return loadReadyPhase9(
        state.targetingContextId,
        preparation.reuse_summary,
        generation,
      );
    }
    renderPreparation(preparation);
    if (["QUEUED", "RUNNING"].includes(preparation.status)) {
      window.setTimeout(
        () => pollPreparation(state.targetingContextId, generation),
        POLL_DELAY_MS,
      );
    }
    return false;
  } catch (error) {
    if (error.status === 409) return refreshTargetingIntelligence();
    renderFailedRequest(error);
    return false;
  } finally {
    document.querySelector("#planner-intelligence-retry").disabled = false;
  }
}

function returnToCampaignContext() {
  requestGeneration += 1;
  setCampaignPlannerStep(2);
  announce("Returned to Campaign Context. Your choices have been retained.");
  document.querySelector("#planner-step-2-title").focus();
}

export function initializeTargetingIntelligence(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  document.querySelector("#planner-intelligence-retry").addEventListener(
    "click",
    retryTargetingIntelligence,
  );
  document.querySelector("#planner-intelligence-back-context").addEventListener(
    "click",
    returnToCampaignContext,
  );
  refreshTargetingIntelligence();
}
