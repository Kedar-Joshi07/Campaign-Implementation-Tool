import { getJSON } from "./api.js";
import {
  getCampaignPlannerState,
  markCampaignPlannerDraftSaved,
  subscribeCampaignPlanner,
} from "./campaign-planner-state.js";
import { formatExactInteger } from "./ui.js";
import { renderPhase9TechnicalDetails } from "./targeting-intelligence.js";

let initialized = false;
let announce = () => {};
let latestPreview = null;
let latestResolution = null;
let savedResponse = null;
let suggestedNameWasEdited = false;
let saveInFlight = false;

function textOrNotSet(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "Not set";
  if (value === null || value === undefined || value === "") return "Not set";
  return String(value);
}

function businessCurrentnessLabel(status) {
  if (status === "READY" || status === "UP_TO_DATE") return "Up to date";
  if (status === "NOT_AVAILABLE" || status === "INCOMPATIBLE_CONTEXT") {
    return "Not available";
  }
  if (status) return "Needs refresh";
  return "Not checked";
}

function addFact(container, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = textOrNotSet(value);
  wrapper.append(term, detail);
  container.append(wrapper);
}

function suggestedTargetGroupName(campaignName) {
  const base = campaignName.trim() || "Campaign";
  return `${base} Target Group`.slice(0, 120);
}

function renderLocalReview(state) {
  const campaign = document.querySelector("#planner-review-campaign");
  campaign.replaceChildren();
  addFact(campaign, "Campaign name", state.campaignDetails.campaignName);
  addFact(campaign, "Description", state.campaignDetails.description);
  addFact(campaign, "Products", state.campaignContext.product_ids);
  addFact(campaign, "Campaign type", state.campaignContext.campaign_types);
  addFact(campaign, "Campaign category", state.campaignContext.campaign_categories);
  addFact(campaign, "Offer", state.campaignContext.offer_types);
  addFact(campaign, "Delivery channel", state.campaignContext.campaign_channel);
  addFact(campaign, "Planned launch date", state.campaignDetails.plannedLaunchDate);

  const criteria = state.targetingCriteria;
  const targeting = document.querySelector("#planner-review-targeting");
  targeting.replaceChildren();
  addFact(targeting, "Targeting match", criteria.match_strength);
  addFact(targeting, "Age groups", criteria.age_groups);
  addFact(targeting, "Gender", criteria.genders);
  addFact(targeting, "Location", criteria.states);
  addFact(targeting, "Income groups", criteria.income_groups);
  const advanced = [
    ...criteria.marital_statuses,
    ...criteria.education_levels,
    ...criteria.employment_statuses,
    ...criteria.resident_statuses,
    ...criteria.resident_types,
    ...criteria.employment_types,
  ];
  if (criteria.family_member_count_min || criteria.family_member_count_max) {
    advanced.push(
      `Family size ${criteria.family_member_count_min || "any"}–${criteria.family_member_count_max || "any"}`,
    );
  }
  if (criteria.top_matching_percent) {
    advanced.push(`Top matching ${criteria.top_matching_percent}%`);
  }
  addFact(targeting, "More targeting options", advanced);

  const group = document.querySelector("#planner-review-group");
  group.replaceChildren();
  addFact(
    group,
    "Selected people",
    latestPreview
      ? formatExactInteger(latestPreview.kpis.selected_for_target_group)
      : "Preview required",
  );
  addFact(group, "Targeting source", businessCurrentnessLabel(latestResolution?.status));
  addFact(
    group,
    "Current status",
    latestPreview?.currentness_label || "Preview required",
  );

  const nameInput = document.querySelector("#planner-target-group-name");
  if (!suggestedNameWasEdited && !savedResponse) {
    nameInput.value = suggestedTargetGroupName(state.campaignDetails.campaignName);
  }
}

function renderImmutableReview(result) {
  const context = result.campaign_context;
  const criteria = result.targeting_criteria;
  const campaign = document.querySelector("#planner-review-campaign");
  campaign.replaceChildren();
  addFact(campaign, "Campaign name", result.campaign.campaign_name);
  addFact(campaign, "Description", result.campaign.description);
  addFact(campaign, "Products", context.product_ids);
  addFact(campaign, "Campaign type", context.campaign_types);
  addFact(campaign, "Campaign category", context.campaign_categories);
  addFact(campaign, "Offer", context.offer_types);
  addFact(campaign, "Delivery channel", context.campaign_channel);
  addFact(campaign, "Planned launch date", result.campaign.planned_launch_date);

  const targeting = document.querySelector("#planner-review-targeting");
  targeting.replaceChildren();
  addFact(targeting, "Targeting match", criteria.match_strength);
  addFact(targeting, "Age groups", criteria.age_groups);
  addFact(targeting, "Gender", criteria.genders);
  addFact(targeting, "Location", criteria.states);
  addFact(targeting, "Income groups", criteria.income_groups);
  addFact(
    targeting,
    "More targeting options",
    [
      ...criteria.marital_statuses,
      ...criteria.education_levels,
      ...criteria.employment_statuses,
      ...criteria.resident_statuses,
      ...criteria.resident_types,
      ...criteria.employment_types,
    ],
  );

  const group = document.querySelector("#planner-review-group");
  group.replaceChildren();
  addFact(group, "Selected people", formatExactInteger(result.saved_target_group.selected_count));
  addFact(group, "Targeting source", businessCurrentnessLabel(result.targeting_source_status));
  addFact(group, "Current status", result.saved_target_group.currentness_label);
}

function renderSavedResult(result) {
  const targetGroup = result.saved_target_group;
  const campaign = result.campaign;
  const list = document.querySelector("#planner-save-result");
  list.replaceChildren();
  addFact(list, "Saved Target Group", `${targetGroup.name} (#${targetGroup.saved_target_group_id})`);
  addFact(list, "Selected people", formatExactInteger(targetGroup.selected_count));
  addFact(list, "Target Group status", targetGroup.currentness_label);
  addFact(list, "Campaign", `${campaign.campaign_name} (#${campaign.campaign_id})`);
  addFact(list, "Campaign status", campaign.status);
  addFact(list, "Delivery channel", campaign.channel);
  addFact(list, "Planned launch date", campaign.planned_launch_date);
  const status = document.querySelector("#planner-saved-currentness");
  status.textContent = targetGroup.currentness_label;
  status.classList.toggle("is-ready", targetGroup.currentness === "UP_TO_DATE");
  status.classList.toggle("is-warning", targetGroup.currentness !== "UP_TO_DATE");
  let successTitle = "Campaign draft updated with a new Target Group";
  if (result.idempotent_replay) successTitle = "Already saved — Campaign draft reopened";
  else if (result.campaign_created) successTitle = "Campaign draft created";
  document.querySelector("#planner-save-success-title").textContent = successTitle;
  document.querySelector("#planner-save-success").hidden = false;
  document.querySelector("#planner-save-success").focus();
  renderPhase9TechnicalDetails(
    result.technical_details,
    "#planner-review-technical-details",
  );
}

function requestPayload(state) {
  return {
    target_group_name: document.querySelector("#planner-target-group-name").value,
    target_group_description:
      document.querySelector("#planner-target-group-description").value || null,
    campaign_name: state.campaignDetails.campaignName,
    campaign_description: state.campaignDetails.description || null,
    planned_launch_date: state.campaignDetails.plannedLaunchDate || null,
  };
}

async function saveTargetGroup(event) {
  event.preventDefault();
  if (saveInFlight) {
    announce("Save is already in progress.");
    return;
  }
  const form = document.querySelector("#planner-save-target-group-form");
  if (!form.reportValidity()) return;
  const state = getCampaignPlannerState();
  if (!state.targetingContextId || !latestPreview) {
    announce("Open Target Group Preview and confirm it is up to date before saving.");
    return;
  }
  const button = document.querySelector("#planner-save-target-group");
  const error = document.querySelector("#planner-review-error");
  saveInFlight = true;
  button.disabled = true;
  button.textContent = "Saving Target Group…";
  error.hidden = true;
  try {
    const result = await getJSON(
      `/api/campaign-planner/contexts/${state.targetingContextId}/save-target-group-and-create-draft`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload(state)),
      },
    );
    markCampaignPlannerDraftSaved();
    savedResponse = result;
    renderSavedResult(result);
    announce(
      result.idempotent_replay
        ? `Target Group ${result.saved_target_group.name} was already saved. Campaign ${result.campaign.campaign_name} remains a draft.`
        : `Saved Target Group ${result.saved_target_group.name}. Campaign ${result.campaign.campaign_name} remains a draft.`,
    );
  } catch (saveError) {
    document.querySelector("#planner-review-error-title").textContent =
      saveError.message.includes("Campaign draft")
        ? "Campaign draft could not be created"
        : "Target Group could not be saved";
    error.querySelector("p").textContent = saveError.message;
    error.hidden = false;
    error.focus();
    announce(saveError.message);
  } finally {
    saveInFlight = false;
    button.disabled = false;
    button.textContent = "Save Target Group & Create Campaign Draft";
  }
}

export async function loadCampaignDraftReview() {
  const state = getCampaignPlannerState();
  renderLocalReview(state);
  if (!state.targetingContextId) return false;
  try {
    const result = await getJSON(
      `/api/campaign-planner/contexts/${state.targetingContextId}/campaign-draft`,
    );
    savedResponse = result;
    suggestedNameWasEdited = true;
    document.querySelector("#planner-target-group-name").value = result.saved_target_group.name;
    document.querySelector("#planner-target-group-description").value =
      result.saved_target_group.description || "";
    renderImmutableReview(result);
    renderSavedResult(result);
    return true;
  } catch (error) {
    if (error.status !== 404) {
      const container = document.querySelector("#planner-review-error");
      container.querySelector("p").textContent = error.message;
      container.hidden = false;
      container.focus();
    }
    return false;
  }
}

export function initializeCampaignReview(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  document.querySelector("#planner-target-group-name").addEventListener("input", () => {
    suggestedNameWasEdited = true;
  });
  document.querySelector("#planner-save-target-group-form").addEventListener(
    "submit",
    saveTargetGroup,
  );
  document.addEventListener("target-group-preview-loaded", (event) => {
    latestPreview = event.detail?.preview || null;
    if (latestPreview?.technical_details) {
      renderPhase9TechnicalDetails(
        savedResponse?.technical_details || latestPreview.technical_details,
        "#planner-review-technical-details",
      );
    }
    if (savedResponse) renderImmutableReview(savedResponse);
    else renderLocalReview(getCampaignPlannerState());
  });
  document.addEventListener("targeting-intelligence-resolved", (event) => {
    latestResolution = event.detail || null;
    if (!latestResolution.can_preview) latestPreview = null;
    if (savedResponse) renderImmutableReview(savedResponse);
    else renderLocalReview(getCampaignPlannerState());
  });
  subscribeCampaignPlanner((state) => {
    if (savedResponse) {
      savedResponse = null;
      document.querySelector("#planner-save-success").hidden = true;
    }
    renderLocalReview(state);
  });
  renderLocalReview(getCampaignPlannerState());
}
