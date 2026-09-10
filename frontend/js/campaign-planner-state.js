const STORAGE_KEY = "phase9-campaign-planner-draft-v1";
const STEP_COUNT = 5;

const listeners = new Set();
let initialized = false;
let plannerState = createInitialState();

function createInitialState() {
  return {
    contractVersion: "1",
    currentStep: 1,
    furthestStep: 1,
    completedSteps: [],
    campaignDetails: {
      campaignName: "",
      description: "",
      plannedLaunchDate: "",
    },
    targetingContextId: null,
    campaignContext: {
      product_ids: [],
      campaign_types: [],
      campaign_categories: [],
      offer_types: [],
      campaign_channel: "",
      historical_campaign_channels: [],
    },
    targetingCriteria: createInitialTargetingCriteria(),
    savedAt: null,
  };
}

function createInitialTargetingCriteria() {
  return {
    match_strength: "",
    genders: [],
    age_groups: [],
    states: [],
    income_groups: [],
    marital_statuses: [],
    education_levels: [],
    employment_statuses: [],
    resident_statuses: [],
    resident_types: [],
    employment_types: [],
    family_member_count_min: null,
    family_member_count_max: null,
    top_matching_percent: null,
    selection_mode: "ALL_MATCHING",
    target_count: null,
  };
}

function boundedText(value, maximum) {
  return typeof value === "string" ? value.slice(0, maximum) : "";
}

function boundedStep(value, fallback = 1) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= STEP_COUNT ? parsed : fallback;
}

function boundedStringList(value, maximum = 50) {
  if (!Array.isArray(value)) return [];
  const unique = new Map();
  for (const item of value.slice(0, maximum)) {
    const text = boundedText(item, 200).trim();
    if (text && !unique.has(text.toLocaleLowerCase())) {
      unique.set(text.toLocaleLowerCase(), text);
    }
  }
  return [...unique.values()].sort((left, right) => left.localeCompare(right));
}

function optionalPositiveInteger(value, maximum = null) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1) return null;
  return maximum === null ? parsed : Math.min(parsed, maximum);
}

function sanitizeState(candidate) {
  if (!candidate || typeof candidate !== "object" || candidate.contractVersion !== "1") {
    return createInitialState();
  }
  const currentStep = boundedStep(candidate.currentStep);
  const furthestStep = Math.max(currentStep, boundedStep(candidate.furthestStep));
  const completedSteps = Array.isArray(candidate.completedSteps)
    ? [...new Set(candidate.completedSteps.map((step) => boundedStep(step, 0)).filter(Boolean))]
        .filter((step) => step < STEP_COUNT)
        .sort((left, right) => left - right)
    : [];
  const details = candidate.campaignDetails || {};
  const context = candidate.campaignContext || {};
  const criteria = candidate.targetingCriteria || {};
  const parsedContextId = Number.parseInt(candidate.targetingContextId, 10);
  return {
    contractVersion: "1",
    currentStep,
    furthestStep,
    completedSteps,
    campaignDetails: {
      campaignName: boundedText(details.campaignName, 120),
      description: boundedText(details.description, 500),
      plannedLaunchDate: boundedText(details.plannedLaunchDate, 10),
    },
    targetingContextId: Number.isInteger(parsedContextId) && parsedContextId > 0
      ? parsedContextId
      : null,
    campaignContext: {
      product_ids: boundedStringList(context.product_ids),
      campaign_types: boundedStringList(context.campaign_types),
      campaign_categories: boundedStringList(context.campaign_categories),
      offer_types: boundedStringList(context.offer_types),
      campaign_channel: boundedText(context.campaign_channel, 30).trim().toUpperCase(),
      historical_campaign_channels: boundedStringList(context.historical_campaign_channels),
    },
    targetingCriteria: {
      match_strength: boundedText(criteria.match_strength, 24).trim().toUpperCase(),
      genders: boundedStringList(criteria.genders, 100),
      age_groups: boundedStringList(criteria.age_groups, 7),
      states: boundedStringList(criteria.states, 100),
      income_groups: boundedStringList(criteria.income_groups, 7),
      marital_statuses: boundedStringList(criteria.marital_statuses, 100),
      education_levels: boundedStringList(criteria.education_levels, 100),
      employment_statuses: boundedStringList(criteria.employment_statuses, 100),
      resident_statuses: boundedStringList(criteria.resident_statuses, 100),
      resident_types: boundedStringList(criteria.resident_types, 100),
      employment_types: boundedStringList(criteria.employment_types, 100),
      family_member_count_min: optionalPositiveInteger(criteria.family_member_count_min),
      family_member_count_max: optionalPositiveInteger(criteria.family_member_count_max),
      top_matching_percent: optionalPositiveInteger(criteria.top_matching_percent, 100),
      selection_mode: criteria.selection_mode === "TOP_N" ? "TOP_N" : "ALL_MATCHING",
      target_count: optionalPositiveInteger(criteria.target_count),
    },
    savedAt: typeof candidate.savedAt === "string" ? candidate.savedAt : null,
  };
}

function cloneState() {
  return {
    ...plannerState,
    completedSteps: [...plannerState.completedSteps],
    campaignDetails: { ...plannerState.campaignDetails },
    campaignContext: {
      ...plannerState.campaignContext,
      product_ids: [...plannerState.campaignContext.product_ids],
      campaign_types: [...plannerState.campaignContext.campaign_types],
      campaign_categories: [...plannerState.campaignContext.campaign_categories],
      offer_types: [...plannerState.campaignContext.offer_types],
      historical_campaign_channels: [
        ...plannerState.campaignContext.historical_campaign_channels,
      ],
    },
    targetingCriteria: {
      ...plannerState.targetingCriteria,
      genders: [...plannerState.targetingCriteria.genders],
      age_groups: [...plannerState.targetingCriteria.age_groups],
      states: [...plannerState.targetingCriteria.states],
      income_groups: [...plannerState.targetingCriteria.income_groups],
      marital_statuses: [...plannerState.targetingCriteria.marital_statuses],
      education_levels: [...plannerState.targetingCriteria.education_levels],
      employment_statuses: [...plannerState.targetingCriteria.employment_statuses],
      resident_statuses: [...plannerState.targetingCriteria.resident_statuses],
      resident_types: [...plannerState.targetingCriteria.resident_types],
      employment_types: [...plannerState.targetingCriteria.employment_types],
    },
  };
}

function persist() {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(plannerState));
    return true;
  } catch (error) {
    console.warn("Campaign planner session state could not be saved.", error);
    return false;
  }
}

function publish({ persistState = true } = {}) {
  if (persistState) persist();
  const snapshot = cloneState();
  for (const listener of listeners) listener(snapshot);
}

export function initializeCampaignPlannerState() {
  if (initialized) return cloneState();
  initialized = true;
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    plannerState = stored ? sanitizeState(JSON.parse(stored)) : createInitialState();
  } catch (error) {
    console.warn("Campaign planner session state could not be restored.", error);
    plannerState = createInitialState();
  }
  return cloneState();
}

export function getCampaignPlannerState() {
  return cloneState();
}

export function subscribeCampaignPlanner(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function updateCampaignDetails(changes) {
  plannerState = {
    ...plannerState,
    campaignDetails: {
      ...plannerState.campaignDetails,
      campaignName: boundedText(
        changes.campaignName ?? plannerState.campaignDetails.campaignName,
        120,
      ),
      description: boundedText(
        changes.description ?? plannerState.campaignDetails.description,
        500,
      ),
      plannedLaunchDate: boundedText(
        changes.plannedLaunchDate ?? plannerState.campaignDetails.plannedLaunchDate,
        10,
      ),
    },
    savedAt: null,
  };
  publish();
}

export function updateCampaignContext(changes) {
  const current = plannerState.campaignContext;
  plannerState = {
    ...plannerState,
    campaignContext: {
      product_ids: boundedStringList(changes.product_ids ?? current.product_ids),
      campaign_types: boundedStringList(changes.campaign_types ?? current.campaign_types),
      campaign_categories: boundedStringList(
        changes.campaign_categories ?? current.campaign_categories,
      ),
      offer_types: boundedStringList(changes.offer_types ?? current.offer_types),
      campaign_channel: boundedText(
        changes.campaign_channel ?? current.campaign_channel,
        30,
      ).trim().toUpperCase(),
      historical_campaign_channels: boundedStringList(
        changes.historical_campaign_channels ?? current.historical_campaign_channels,
      ),
    },
    savedAt: null,
  };
  publish();
}

export function setTargetingContextId(targetingContextId) {
  const parsed = Number.parseInt(targetingContextId, 10);
  plannerState = {
    ...plannerState,
    targetingContextId: Number.isInteger(parsed) && parsed > 0 ? parsed : null,
  };
  publish();
}

export function updateTargetingCriteria(changes) {
  const current = plannerState.targetingCriteria;
  const selectionMode = changes.selection_mode === "TOP_N"
    ? "TOP_N"
    : changes.selection_mode === "ALL_MATCHING"
      ? "ALL_MATCHING"
      : current.selection_mode;
  plannerState = {
    ...plannerState,
    targetingCriteria: {
      match_strength: boundedText(
        changes.match_strength ?? current.match_strength,
        24,
      ).trim().toUpperCase(),
      genders: boundedStringList(changes.genders ?? current.genders, 100),
      age_groups: boundedStringList(changes.age_groups ?? current.age_groups, 7),
      states: boundedStringList(changes.states ?? current.states, 100),
      income_groups: boundedStringList(changes.income_groups ?? current.income_groups, 7),
      marital_statuses: boundedStringList(
        changes.marital_statuses ?? current.marital_statuses,
        100,
      ),
      education_levels: boundedStringList(
        changes.education_levels ?? current.education_levels,
        100,
      ),
      employment_statuses: boundedStringList(
        changes.employment_statuses ?? current.employment_statuses,
        100,
      ),
      resident_statuses: boundedStringList(
        changes.resident_statuses ?? current.resident_statuses,
        100,
      ),
      resident_types: boundedStringList(changes.resident_types ?? current.resident_types, 100),
      employment_types: boundedStringList(
        changes.employment_types ?? current.employment_types,
        100,
      ),
      family_member_count_min: optionalPositiveInteger(
        Object.hasOwn(changes, "family_member_count_min")
          ? changes.family_member_count_min
          : current.family_member_count_min,
      ),
      family_member_count_max: optionalPositiveInteger(
        Object.hasOwn(changes, "family_member_count_max")
          ? changes.family_member_count_max
          : current.family_member_count_max,
      ),
      top_matching_percent: optionalPositiveInteger(
        Object.hasOwn(changes, "top_matching_percent")
          ? changes.top_matching_percent
          : current.top_matching_percent,
        100,
      ),
      selection_mode: selectionMode,
      target_count: selectionMode === "TOP_N"
        ? optionalPositiveInteger(
            Object.hasOwn(changes, "target_count")
              ? changes.target_count
              : current.target_count,
          )
        : null,
    },
    savedAt: null,
  };
  publish();
}

export function completePlannerStep(step) {
  const completedStep = boundedStep(step);
  const completedSteps = [...new Set([...plannerState.completedSteps, completedStep])]
    .filter((value) => value < STEP_COUNT)
    .sort((left, right) => left - right);
  plannerState = {
    ...plannerState,
    currentStep: Math.min(completedStep + 1, STEP_COUNT),
    furthestStep: Math.max(plannerState.furthestStep, Math.min(completedStep + 1, STEP_COUNT)),
    completedSteps,
  };
  publish();
}

export function setCampaignPlannerStep(step) {
  const nextStep = boundedStep(step, plannerState.currentStep);
  if (nextStep > plannerState.furthestStep) return false;
  plannerState = { ...plannerState, currentStep: nextStep };
  publish();
  return true;
}

export function markCampaignPlannerDraftSaved() {
  plannerState = { ...plannerState, savedAt: new Date().toISOString() };
  const saved = persist();
  publish({ persistState: false });
  return saved;
}

export { STEP_COUNT, STORAGE_KEY };
