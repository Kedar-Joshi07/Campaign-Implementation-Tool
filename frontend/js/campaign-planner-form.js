import {
  STEP_COUNT,
  completePlannerStep,
  getCampaignPlannerState,
  initializeCampaignPlannerState,
  markCampaignPlannerDraftSaved,
  setCampaignPlannerStep,
  subscribeCampaignPlanner,
  updateCampaignDetails,
} from "./campaign-planner-state.js";
import {
  initializeCampaignContext,
  loadCampaignContext,
  validateAndSaveCampaignContext,
} from "./campaign-context.js";
import {
  initializeBusinessTargeting,
  loadBusinessTargeting,
  validateAndSaveBusinessTargeting,
} from "./business-targeting.js";
import {
  initializeTargetingIntelligence,
  refreshTargetingIntelligence,
} from "./targeting-intelligence.js";
import { initializeTargetGroupPreview } from "./target-group-preview.js";
import {
  initializeCampaignReview,
  loadCampaignDraftReview,
} from "./campaign-review.js";

const STEP_NAMES = {
  1: "Campaign Details",
  2: "Campaign Context",
  3: "Targeting Preferences",
  4: "Target Group Preview",
  5: "Review & Save",
};

let initialized = false;

function announce(message) {
  document.querySelector("#planner-status-announcement").textContent = message;
}

function populateDetails(details) {
  document.querySelector("#planner-campaign-name").value = details.campaignName;
  document.querySelector("#planner-campaign-description").value = details.description;
  document.querySelector("#planner-planned-launch-date").value = details.plannedLaunchDate;
}

function renderPlanner(state) {
  for (const panel of document.querySelectorAll("[data-planner-panel]")) {
    panel.hidden = Number(panel.dataset.plannerPanel) !== state.currentStep;
  }
  for (const button of document.querySelectorAll("[data-planner-step]")) {
    const step = Number(button.dataset.plannerStep);
    const current = step === state.currentStep;
    const completed = state.completedSteps.includes(step);
    button.classList.toggle("is-active", current);
    button.classList.toggle("is-complete", completed && !current);
    button.disabled = step > state.furthestStep;
    if (current) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
    const status = button.querySelector("[data-planner-step-status]");
    status.textContent = current ? "Current" : completed ? "Completed" : "Not started";
  }
  document.querySelector("#planner-progress-label").textContent =
    `Step ${state.currentStep} of ${STEP_COUNT}`;
  document.querySelector("#planner-current-step-name").textContent = STEP_NAMES[state.currentStep];
  const draftStatus = document.querySelector("#planner-draft-status");
  draftStatus.textContent = state.savedAt ? "Draft saved" : "Draft not saved";
  draftStatus.classList.toggle("is-ready", Boolean(state.savedAt));
  draftStatus.classList.toggle("is-neutral", !state.savedAt);
}

function captureCampaignDetails() {
  updateCampaignDetails({
    campaignName: document.querySelector("#planner-campaign-name").value,
    description: document.querySelector("#planner-campaign-description").value,
    plannedLaunchDate: document.querySelector("#planner-planned-launch-date").value,
  });
}

async function continueFrom(step) {
  if (step === 1) {
    const form = document.querySelector("#planner-campaign-details-form");
    if (!form.reportValidity()) {
      announce("Enter a campaign name before continuing.");
      return;
    }
    captureCampaignDetails();
  }
  if (step === 2 && !(await validateAndSaveCampaignContext())) return;
  if (step === 3 && !(await validateAndSaveBusinessTargeting())) return;
  if (step === 3) await refreshTargetingIntelligence();
  completePlannerStep(step);
  announce(`${STEP_NAMES[step]} completed. ${STEP_NAMES[Math.min(step + 1, STEP_COUNT)]} is ready.`);
  document.querySelector(`[data-planner-panel="${Math.min(step + 1, STEP_COUNT)}"] h3`).focus?.();
}

function moveBack(fromStep) {
  const target = Math.max(1, fromStep - 1);
  setCampaignPlannerStep(target);
  announce(`Returned to ${STEP_NAMES[target]}. Your entries have been retained.`);
  document.querySelector(`[data-planner-panel="${target}"] h3`).focus?.();
}

function bindActions() {
  for (const input of document.querySelectorAll(
    "#planner-campaign-name, #planner-campaign-description, #planner-planned-launch-date",
  )) {
    input.addEventListener("input", captureCampaignDetails);
    input.addEventListener("change", captureCampaignDetails);
  }
  for (let step = 1; step < STEP_COUNT; step += 1) {
    document.querySelector(`#planner-next-${step}`).addEventListener("click", () => continueFrom(step));
  }
  for (let step = 2; step <= STEP_COUNT; step += 1) {
    document.querySelector(`#planner-back-${step}`).addEventListener("click", () => moveBack(step));
  }
  for (const button of document.querySelectorAll("[data-planner-step]")) {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.plannerStep);
      if (setCampaignPlannerStep(step)) announce(`${STEP_NAMES[step]} opened.`);
    });
  }
  document.querySelector("#planner-save-draft").addEventListener("click", () => {
    captureCampaignDetails();
    const saved = markCampaignPlannerDraftSaved();
    announce(saved ? "Draft saved in this browser session." : "Draft could not be saved in this browser session.");
  });
}

export function initializeCampaignPlanner() {
  if (initialized) return;
  initialized = true;
  const state = initializeCampaignPlannerState();
  populateDetails(state.campaignDetails);
  subscribeCampaignPlanner(renderPlanner);
  initializeCampaignContext(announce);
  initializeBusinessTargeting(announce);
  initializeTargetGroupPreview(announce);
  initializeTargetingIntelligence(announce);
  initializeCampaignReview(announce);
  bindActions();
  renderPlanner(getCampaignPlannerState());
}

export function loadCampaignPlanner() {
  renderPlanner(getCampaignPlannerState());
  loadCampaignContext().catch(() => {});
  loadBusinessTargeting().catch(() => {});
  refreshTargetingIntelligence();
  loadCampaignDraftReview().catch(() => {});
}
