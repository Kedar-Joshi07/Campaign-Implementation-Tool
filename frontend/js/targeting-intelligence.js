import { getJSON } from "./api.js";
import { getCampaignPlannerState } from "./campaign-planner-state.js";

let initialized = false;
let announce = () => {};

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

function renderResolution(resolution) {
  document.querySelector("#planner-intelligence-loading").hidden = true;
  const container = document.querySelector("#planner-intelligence-state");
  container.hidden = false;
  container.classList.toggle("is-ready", resolution.can_preview);
  container.classList.toggle("is-blocked", !resolution.can_preview);
  const badge = document.querySelector("#planner-intelligence-status");
  const businessStatuses = {
    READY: "Up to date",
    NEEDS_REFRESH: "Needs refresh",
    STALE: "Needs refresh",
    NOT_AVAILABLE: "Not available",
    INCOMPATIBLE_CONTEXT: "Not available",
  };
  badge.textContent = businessStatuses[resolution.status] || "Not available";
  badge.classList.toggle("is-ready", resolution.can_preview);
  badge.classList.toggle("is-neutral", !resolution.can_preview);
  document.querySelector("#planner-intelligence-message").textContent = resolution.message;
  document.querySelector("#planner-intelligence-explanation").textContent = resolution.explanation;
  document.querySelector("#planner-preview-block-note").textContent = resolution.can_preview
    ? "The verified source gate is open. The exact target-group preview below uses this source."
    : "Exact target counts and target-group saving are blocked. No estimated or fabricated count is shown.";
  document.querySelector("#planner-next-4").disabled = !resolution.can_preview;
  renderTechnicalDetails(resolution);
  document.dispatchEvent(new CustomEvent("targeting-intelligence-resolved", {
    detail: resolution,
  }));
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

export async function refreshTargetingIntelligence() {
  const state = getCampaignPlannerState();
  document.querySelector("#planner-intelligence-loading").hidden = false;
  document.querySelector("#planner-intelligence-state").hidden = true;
  if (!state.targetingContextId) {
    renderResolution(unavailableResolution(
      "Save campaign context and targeting preferences first. No targeting source has been selected automatically.",
    ));
    return false;
  }
  try {
    const resolution = await getJSON(
      `/api/campaign-planner/contexts/${state.targetingContextId}/targeting-intelligence`,
    );
    renderResolution(resolution);
    announce(resolution.message);
    return resolution.can_preview;
  } catch (error) {
    renderResolution(unavailableResolution(
      "Targeting intelligence could not be verified. Your campaign context and preferences remain saved.",
    ));
    announce(error.message);
    return false;
  }
}

export function initializeTargetingIntelligence(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  document.querySelector("#planner-intelligence-retry").addEventListener(
    "click",
    refreshTargetingIntelligence,
  );
  refreshTargetingIntelligence();
}
