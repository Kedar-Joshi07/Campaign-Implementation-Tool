import { getCachedJSON, getJSON } from "./api.js";
import {
  getCampaignPlannerState,
  updateTargetingCriteria,
} from "./campaign-planner-state.js";

const OPTIONS_URL = "/api/campaign-planner/targeting-options";
const MULTI_FIELDS = {
  genders: { selector: "#planner-targeting-genders", optionKey: "genders", label: "Gender" },
  age_groups: { selector: "#planner-targeting-age-groups", optionKey: "age_groups", label: "Age" },
  states: { selector: "#planner-targeting-states", optionKey: "states", label: "State" },
  income_groups: { selector: "#planner-targeting-income-groups", optionKey: "income_groups", label: "Income" },
  marital_statuses: { selector: "#planner-targeting-marital-statuses", optionKey: "marital_statuses", label: "Marital status" },
  education_levels: { selector: "#planner-targeting-education-levels", optionKey: "education_levels", label: "Education" },
  employment_statuses: { selector: "#planner-targeting-employment-statuses", optionKey: "employment_statuses", label: "Employment status" },
  resident_statuses: { selector: "#planner-targeting-resident-statuses", optionKey: "resident_statuses", label: "Resident status" },
  resident_types: { selector: "#planner-targeting-resident-types", optionKey: "resident_types", label: "Resident type" },
  employment_types: { selector: "#planner-targeting-employment-types", optionKey: "employment_types", label: "Employment type" },
};

let initialized = false;
let loadPromise = null;
let targetingOptions = null;
let announce = () => {};

function selectedValues(selector) {
  return [...document.querySelector(selector).selectedOptions].map((option) => option.value);
}

function optionalInteger(selector) {
  const value = document.querySelector(selector).value;
  return value === "" ? null : Number.parseInt(value, 10);
}

function appendOption(select, value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function populateOptions(options) {
  const strengthContainer = document.querySelector("#planner-targeting-strength-options");
  strengthContainer.replaceChildren();
  for (const strength of options.match_strengths) {
    const label = document.createElement("label");
    label.className = "planner-strength-choice";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "match_strength";
    radio.value = strength.value;
    radio.required = true;
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = strength.label;
    const help = document.createElement("small");
    help.textContent = strength.recommended ? "Recommended starting point" : "Available option";
    copy.append(title, help);
    label.append(radio, copy);
    strengthContainer.append(label);
  }

  for (const { selector, optionKey } of Object.values(MULTI_FIELDS)) {
    const select = document.querySelector(selector);
    select.replaceChildren();
    for (const item of options[optionKey]) {
      if (typeof item === "string") appendOption(select, item);
      else appendOption(select, item.value, item.label);
    }
  }

  for (const selector of ["#planner-targeting-family-min", "#planner-targeting-family-max"]) {
    const input = document.querySelector(selector);
    input.min = options.family_size_minimum || 1;
    if (options.family_size_maximum) input.max = options.family_size_maximum;
    else input.removeAttribute("max");
  }
}

function captureCriteria() {
  const strength = document.querySelector('input[name="match_strength"]:checked');
  const criteria = {
    match_strength: strength?.value || targetingOptions?.default_match_strength || "",
    family_member_count_min: optionalInteger("#planner-targeting-family-min"),
    family_member_count_max: optionalInteger("#planner-targeting-family-max"),
    top_matching_percent: optionalInteger("#planner-targeting-top-percent"),
    selection_mode: document.querySelector("#planner-targeting-selection-mode").value,
    target_count: optionalInteger("#planner-targeting-target-count"),
  };
  for (const [field, { selector }] of Object.entries(MULTI_FIELDS)) {
    criteria[field] = selectedValues(selector);
  }
  updateTargetingCriteria(criteria);
  renderActiveCriteria(getCampaignPlannerState().targetingCriteria);
  updateSelectionMode();
}

function applyCriteria(criteria) {
  for (const radio of document.querySelectorAll('input[name="match_strength"]')) {
    radio.checked = radio.value === criteria.match_strength;
  }
  for (const [field, { selector }] of Object.entries(MULTI_FIELDS)) {
    const selected = new Set(criteria[field] || []);
    for (const option of document.querySelector(selector).options) {
      option.selected = selected.has(option.value);
    }
  }
  const scalarFields = {
    "#planner-targeting-family-min": criteria.family_member_count_min,
    "#planner-targeting-family-max": criteria.family_member_count_max,
    "#planner-targeting-top-percent": criteria.top_matching_percent,
    "#planner-targeting-target-count": criteria.target_count,
  };
  for (const [selector, value] of Object.entries(scalarFields)) {
    document.querySelector(selector).value = value ?? "";
  }
  document.querySelector("#planner-targeting-selection-mode").value =
    criteria.selection_mode || "ALL_MATCHING";
  updateSelectionMode();
  renderActiveCriteria(criteria);
}

function updateSelectionMode() {
  const topN = document.querySelector("#planner-targeting-selection-mode").value === "TOP_N";
  const field = document.querySelector("#planner-targeting-target-count-field");
  const input = document.querySelector("#planner-targeting-target-count");
  field.hidden = !topN;
  input.required = topN;
  if (!topN) input.value = "";
}

function strengthLabel(value) {
  return targetingOptions?.match_strengths.find((item) => item.value === value)?.label || value;
}

function addChip(container, { field, value, text, removable = true }) {
  const chip = document.createElement("span");
  chip.className = "planner-targeting-chip";
  chip.setAttribute("role", "listitem");
  const copy = document.createElement("span");
  copy.textContent = text;
  chip.append(copy);
  if (removable) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "×";
    button.setAttribute("aria-label", `Remove ${text}`);
    button.dataset.targetingField = field;
    if (value !== null) button.dataset.targetingValue = value;
    chip.append(button);
  }
  container.append(chip);
}

function renderActiveCriteria(criteria) {
  const container = document.querySelector("#planner-targeting-chips");
  container.replaceChildren();
  addChip(container, {
    field: "match_strength",
    value: criteria.match_strength,
    text: `Strength: ${strengthLabel(criteria.match_strength)}`,
    removable: false,
  });
  let optionalCount = 0;
  for (const [field, { label }] of Object.entries(MULTI_FIELDS)) {
    for (const value of criteria[field] || []) {
      addChip(container, { field, value, text: `${label}: ${value}` });
      optionalCount += 1;
    }
  }
  const scalarChips = [
    ["family_member_count_min", criteria.family_member_count_min, "Minimum family size"],
    ["family_member_count_max", criteria.family_member_count_max, "Maximum family size"],
    ["top_matching_percent", criteria.top_matching_percent, "Top matching percentage"],
  ];
  for (const [field, value, label] of scalarChips) {
    if (value !== null) {
      addChip(container, { field, value: null, text: `${label}: ${value}${field === "top_matching_percent" ? "%" : ""}` });
      optionalCount += 1;
    }
  }
  const selectionText = criteria.selection_mode === "TOP_N"
    ? `Selection: Top ${criteria.target_count || "—"} people`
    : "Selection: All matching people";
  addChip(container, {
    field: "selection_mode",
    value: null,
    text: selectionText,
    removable: criteria.selection_mode === "TOP_N",
  });
  if (criteria.selection_mode === "TOP_N") optionalCount += 1;

  for (const [field, { selector }] of Object.entries(MULTI_FIELDS)) {
    const count = (criteria[field] || []).length;
    document.querySelector(`${selector}-count`).textContent =
      `${count} selected`;
  }
  document.querySelector("#planner-targeting-active-summary").textContent = optionalCount
    ? `${optionalCount} optional targeting choice${optionalCount === 1 ? "" : "s"} selected.`
    : "No optional preferences selected. Recommended match strength and all matching people remain visible.";
  document.querySelector("#planner-targeting-active").hidden = false;
}

function removeCriterion(button) {
  const field = button.dataset.targetingField;
  const state = getCampaignPlannerState();
  const criteria = state.targetingCriteria;
  if (field in MULTI_FIELDS) {
    updateTargetingCriteria({
      [field]: criteria[field].filter((value) => value !== button.dataset.targetingValue),
    });
  } else if (field === "selection_mode") {
    updateTargetingCriteria({ selection_mode: "ALL_MATCHING", target_count: null });
  } else {
    updateTargetingCriteria({ [field]: null });
  }
  applyCriteria(getCampaignPlannerState().targetingCriteria);
  announce("Targeting choice removed.");
  const scalarFocusSelectors = {
    family_member_count_min: "#planner-targeting-family-min",
    family_member_count_max: "#planner-targeting-family-max",
    top_matching_percent: "#planner-targeting-top-percent",
    selection_mode: "#planner-targeting-selection-mode",
  };
  const focusSelector = field in MULTI_FIELDS
    ? MULTI_FIELDS[field].selector
    : scalarFocusSelectors[field];
  document.querySelector(focusSelector)?.focus();
}

function clearAllCriteria() {
  const cleared = {
    match_strength: targetingOptions.default_match_strength,
    family_member_count_min: null,
    family_member_count_max: null,
    top_matching_percent: null,
    selection_mode: "ALL_MATCHING",
    target_count: null,
  };
  for (const field of Object.keys(MULTI_FIELDS)) cleared[field] = [];
  updateTargetingCriteria(cleared);
  applyCriteria(getCampaignPlannerState().targetingCriteria);
  announce("All optional targeting choices cleared. Recommended defaults remain visible.");
}

function setLoading(loading) {
  document.querySelector("#planner-targeting-loading").hidden = !loading;
  document.querySelector("#planner-targeting-form").hidden = loading;
  document.querySelector("#planner-targeting-save").disabled = loading;
}

function showLoadError(error) {
  setLoading(false);
  document.querySelector("#planner-targeting-form").hidden = true;
  document.querySelector("#planner-targeting-save").disabled = true;
  const errorBox = document.querySelector("#planner-targeting-error");
  errorBox.querySelector("p").textContent = error.message;
  errorBox.hidden = false;
  errorBox.focus();
}

function showSaveError(error) {
  const errorBox = document.querySelector("#planner-targeting-error");
  errorBox.querySelector("p").textContent = error.message;
  errorBox.hidden = false;
  errorBox.focus();
}

async function loadOptionsAndCriteria({ force = false } = {}) {
  setLoading(true);
  document.querySelector("#planner-targeting-error").hidden = true;
  try {
    targetingOptions = await getCachedJSON(OPTIONS_URL, { force });
    populateOptions(targetingOptions);
    const state = getCampaignPlannerState();
    let criteria = state.targetingCriteria;
    if (state.targetingContextId) {
      const saved = await getJSON(
        `/api/campaign-planner/contexts/${state.targetingContextId}/targeting-criteria`,
      );
      criteria = saved.criteria;
    }
    if (!criteria.match_strength) {
      criteria = { ...criteria, match_strength: targetingOptions.default_match_strength };
    }
    updateTargetingCriteria(criteria);
    applyCriteria(getCampaignPlannerState().targetingCriteria);
    setLoading(false);
  } catch (error) {
    showLoadError(error);
    throw error;
  }
}

function validateForm() {
  const form = document.querySelector("#planner-targeting-form");
  const minimum = optionalInteger("#planner-targeting-family-min");
  const maximum = optionalInteger("#planner-targeting-family-max");
  const maximumInput = document.querySelector("#planner-targeting-family-max");
  maximumInput.setCustomValidity(
    minimum !== null && maximum !== null && minimum > maximum
      ? "Maximum family size must be at least the minimum family size."
      : "",
  );
  const topN = document.querySelector("#planner-targeting-selection-mode").value === "TOP_N";
  const targetCount = optionalInteger("#planner-targeting-target-count");
  document.querySelector("#planner-targeting-target-count").setCustomValidity(
    topN && (targetCount === null || targetCount < 1)
      ? "Enter a whole number greater than zero."
      : "",
  );
  if (!form.reportValidity()) {
    announce("Review the highlighted targeting preference values.");
    return false;
  }
  return true;
}

export async function validateAndSaveBusinessTargeting() {
  if (loadPromise) {
    try {
      await loadPromise;
    } catch {
      return false;
    }
  }
  captureCriteria();
  if (!validateForm()) return false;
  const state = getCampaignPlannerState();
  if (!state.targetingContextId) {
    announce("Save Campaign Context before saving targeting preferences.");
    return false;
  }
  const saveButton = document.querySelector("#planner-targeting-save");
  saveButton.disabled = true;
  try {
    const response = await getJSON(
      `/api/campaign-planner/contexts/${state.targetingContextId}/targeting-criteria`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ criteria: state.targetingCriteria }),
      },
    );
    updateTargetingCriteria(response.criteria);
    applyCriteria(getCampaignPlannerState().targetingCriteria);
    const summary = document.querySelector("#planner-targeting-save-summary");
    const branchCount = response.audience_filter_branches.length;
    summary.textContent = `Targeting preferences saved as ${branchCount} valid filter ${branchCount === 1 ? "rule" : "branches"}.`;
    summary.hidden = false;
    announce("Targeting preferences saved and validated.");
    return true;
  } catch (error) {
    showSaveError(error);
    announce(error.message);
    return false;
  } finally {
    saveButton.disabled = false;
  }
}

export function initializeBusinessTargeting(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  document.querySelector("#planner-targeting-form").addEventListener("change", () => {
    document.querySelector("#planner-targeting-error").hidden = true;
    captureCriteria();
  });
  document.querySelector("#planner-targeting-form").addEventListener("input", () => {
    document.querySelector("#planner-targeting-error").hidden = true;
    captureCriteria();
  });
  document.querySelector("#planner-targeting-chips").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-targeting-field]");
    if (button) removeCriterion(button);
  });
  document.querySelector("#planner-targeting-clear-all").addEventListener("click", clearAllCriteria);
  document.querySelector("#planner-targeting-save").addEventListener("click", () => {
    validateAndSaveBusinessTargeting();
  });
  document.querySelector("#planner-targeting-retry").addEventListener("click", () => {
    loadPromise = loadOptionsAndCriteria({ force: true });
    loadPromise.catch(() => {});
  });
  loadPromise = loadOptionsAndCriteria();
  loadPromise.catch(() => {});
}

export function loadBusinessTargeting() {
  if (!loadPromise) loadPromise = loadOptionsAndCriteria();
  return loadPromise;
}
