import { getJSON } from "./api.js";
import { enhanceMultiSelect, refreshMultiSelect, setMultiSelectState } from "./components/multi-select-dropdown.js";

const DRAFT_KEY = "phase11-business-search-draft-v1";
const CONTEXT_FIELDS = {
  product_ids: ["Products", "products"], campaign_types: ["Campaign Types", "campaign_types"],
  campaign_categories: ["Campaign Categories", "campaign_categories"], offer_types: ["Offer Types", "offer_types"],
  historical_campaign_channels: ["Historical Campaign Channels", "historical_campaign_channels"],
};
const TARGET_FIELDS = {
  genders: ["Gender", "genders"], age_groups: ["Age Groups", "age_groups"], states: ["State", "states"],
  regions: ["Region shortcut", "regions"], income_groups: ["Income Groups", "income_groups"],
  marital_statuses: ["Marital Status", "marital_statuses", true], education_levels: ["Education", "education_levels", true],
  employment_statuses: ["Employment Status", "employment_statuses", true], resident_statuses: ["Resident Status", "resident_statuses", true],
  resident_types: ["Resident Type", "resident_types", true], employment_types: ["Type of Employment", "employment_types", true],
};
const fields = new Map();
let initialized = false, loadPromise = null, options = null, submitting = false;
let draft = null;
const find = (id) => document.querySelector(`#${id}`);
const number = (id) => find(id).value === "" ? null : Number(find(id).value);
const selections = (field) => [...fields.get(field).selectedOptions].map((option) => option.value);

function make(tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
}

function createFields(definitions, context) {
  for (const [field, [label, , advanced]] of Object.entries(definitions)) {
    const container = make("div"); container.className = "form-field";
    const select = make("select"); select.id = `business-${field}`; select.name = field; select.multiple = true;
    select.required = field === "product_ids";
    const associated = make("label", label); associated.htmlFor = select.id;
    container.append(associated, select);
    find(context ? "business-context-fields" : advanced ? "business-more-fields" : "business-targeting-fields").append(container);
    fields.set(field, select);
    enhanceMultiSelect(select, { label });
  }
}

function capture() {
  const profile = options?.profiles.find((item) => item.export_profile === find("business-export-profile").value);
  const context = { campaign_channel: profile?.channel_code || "" };
  for (const field of Object.keys(CONTEXT_FIELDS)) context[field] = selections(field);
  const criteria = {
    match_strength: document.querySelector('input[name="business_match_strength"]:checked')?.value || "",
    family_member_count_min: number("business-family-min"), family_member_count_max: number("business-family-max"),
    top_matching_percent: number("business-top-percent"), selection_mode: find("business-selection-mode").value,
    target_count: find("business-selection-mode").value === "TOP_N" ? number("business-target-count") : null,
  };
  for (const field of Object.keys(TARGET_FIELDS)) if (field !== "regions") criteria[field] = selections(field);
  return { campaign_name: find("business-campaign-name").value.trim(), description: find("business-description").value.trim() || null,
    planned_launch_date: find("business-launch-date").value || null, context, criteria,
    export_profile: find("business-export-profile").value };
}

function saveDraft() {
  if (!options) return;
  draft = { contractVersion: "1", request: capture(), regions: selections("regions") };
  try { window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch { /* Session storage is optional. */ }
}

function selectionMode() {
  const top = find("business-selection-mode").value === "TOP_N";
  find("business-target-count-field").hidden = !top;
  find("business-target-count").disabled = !top;
  find("business-target-count").required = top;
  if (!top) find("business-target-count").value = "";
}

function addRegions() {
  const selected = new Set(selections("regions"));
  const states = new Set(options.targeting.regions.filter((region) => selected.has(region.value)).flatMap((region) => region.states));
  for (const option of fields.get("states").options) if (states.has(option.value)) option.selected = true;
  refreshMultiSelect(fields.get("states"));
}

function populate(payload) {
  const request = draft?.request || {};
  for (const [field, select] of fields) {
    const context = Object.hasOwn(CONTEXT_FIELDS, field);
    const [, key] = (context ? CONTEXT_FIELDS : TARGET_FIELDS)[field];
    const raw = (context ? payload.context : payload.targeting)[key] || [];
    const values = raw.map((item) => field === "product_ids"
      ? { value: item.product_id, label: `${item.product_name} (${item.product_id})` }
      : typeof item === "string" ? { value: item, label: item } : { value: item.value, label: item.label });
    const selected = field === "regions" ? draft?.regions || [] : (context ? request.context : request.criteria)?.[field] || [];
    // Previously backend-supplied draft values remain visibly unavailable, never silently erased.
    for (const value of selected) if (!values.some((item) => item.value === value)) values.push({ value, label: `${value} (No longer available)`, disabled: true });
    const component = enhanceMultiSelect(select);
    component.setOptions(values); component.setValues(selected);
  }
  const strengths = find("business-match-strength"); strengths.replaceChildren();
  for (const strength of payload.targeting.match_strengths) {
    const label = make("label"); label.className = "planner-strength-choice";
    const radio = make("input"); radio.type = "radio"; radio.name = "business_match_strength"; radio.value = strength.value; radio.required = true;
    radio.checked = strength.value === (request.criteria?.match_strength || payload.targeting.default_match_strength);
    label.append(radio, make("span", `${strength.label}${strength.recommended ? " — Recommended" : ""}`)); strengths.append(label);
  }
  const profiles = find("business-export-profile"); profiles.replaceChildren();
  const placeholder = make("option", "Choose a delivery/download profile"); placeholder.value = ""; profiles.append(placeholder);
  for (const profile of payload.profiles) {
    if (profile.availability !== "AVAILABLE" && profile.export_profile !== request.export_profile) continue;
    const option = make("option", profile.availability === "AVAILABLE" ? profile.label : `${profile.label} — ${profile.unavailable_reason}`);
    option.value = profile.export_profile; option.disabled = profile.availability !== "AVAILABLE"; profiles.append(option);
  }
  if (request.export_profile && !payload.profiles.some((item) => item.export_profile === request.export_profile)) {
    const unavailable = make("option", "Previous profile no longer available; choose a current profile");
    unavailable.value = request.export_profile; unavailable.disabled = true; profiles.append(unavailable);
  }
  profiles.value = request.export_profile || "";
  for (const [id, value] of Object.entries({
    "business-campaign-name": request.campaign_name, "business-description": request.description,
    "business-launch-date": request.planned_launch_date, "business-family-min": request.criteria?.family_member_count_min,
    "business-family-max": request.criteria?.family_member_count_max, "business-top-percent": request.criteria?.top_matching_percent,
    "business-target-count": request.criteria?.target_count,
  })) find(id).value = value ?? "";
  find("business-selection-mode").value = request.criteria?.selection_mode || "ALL_MATCHING";
  for (const id of ["business-family-min", "business-family-max"]) {
    find(id).min = payload.targeting.family_size_minimum || 1;
    if (payload.targeting.family_size_maximum) find(id).max = payload.targeting.family_size_maximum;
    else find(id).removeAttribute("max");
  }
  selectionMode();
  find("business-search-workflow-note").hidden = payload.workflow_available;
}

async function loadOptions() {
  saveDraft();
  find("business-search-loading").hidden = false; find("business-search-error").hidden = true;
  find("business-search-form").hidden = true;
  for (const select of fields.values()) setMultiSelectState(select, { loading: true, error: "" });
  try {
    const payload = await getJSON("/api/potential-customer-search/options");
    populate(payload); options = payload;
    for (const select of fields.values()) setMultiSelectState(select, { loading: false, error: "" });
    find("business-search-form").hidden = false;
    find("business-search-submit").disabled = submitting || payload.context.products.length === 0;
    if (!payload.context.products.length) showError("No products are currently available. Reload choices after product data is available.");
  } catch (error) {
    for (const select of fields.values()) setMultiSelectState(select, { loading: false, error: "Choices could not be loaded. Try again." });
    showError("Campaign choices could not be loaded. Please try again.");
  } finally { find("business-search-loading").hidden = true; }
}

function showError(message) {
  find("business-search-error-message").textContent = message;
  find("business-search-error").hidden = false; find("business-search-error").focus();
}

function valid() {
  // The form uses novalidate so every attempt reaches these refreshed custom
  // rules before reportValidity. An earlier error must not trap a corrected draft.
  find("business-campaign-name").setCustomValidity(find("business-campaign-name").value.trim() ? "" : "Enter a campaign name.");
  const profile = options.profiles.find((item) => item.export_profile === find("business-export-profile").value);
  find("business-export-profile").setCustomValidity(profile?.availability === "AVAILABLE" ? "" : "Choose an available download profile.");
  for (const select of fields.values()) select.setCustomValidity([...select.selectedOptions].some((option) => option.disabled) ? "Remove unavailable previous choices before continuing." : "");
  const minimum = number("business-family-min"), maximum = number("business-family-max");
  find("business-family-max").setCustomValidity(minimum !== null && maximum !== null && minimum > maximum ? "Maximum family size must be at least the minimum." : "");
  return find("business-search-form").reportValidity();
}

async function submit(event) {
  event.preventDefault();
  if (submitting || !options || !valid()) return;
  submitting = true; find("business-search-submit").disabled = true;
  saveDraft(); find("business-search-error").hidden = true;
  find("business-search-status").textContent = "Saving your search request…";
  const payload = capture();
  // Do not permit field edits changing this intentional submission while it is in flight.
  for (const fieldset of find("business-search-form").querySelectorAll(":scope > fieldset")) fieldset.disabled = true;
  for (const select of fields.values()) setMultiSelectState(select, { disabled: true });
  try {
    const result = await getJSON("/api/potential-customer-search/runs", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    find("business-search-status").textContent = result.safe_message;
    // Leaving the form does not cancel the persisted request or lose its acknowledgement.
    if (window.location.hash === "#find-potential-customers") window.location.hash = `results/${result.search_run_id}`;
  } catch (error) { showError("Your search could not be acknowledged. Review your choices and check Results before trying again."); find("business-search-status").textContent = "The request could not be acknowledged. Check Results before intentionally submitting again."; }
  finally {
    submitting = false;
    for (const fieldset of find("business-search-form").querySelectorAll(":scope > fieldset")) fieldset.disabled = false;
    selectionMode();
    for (const select of fields.values()) setMultiSelectState(select, { disabled: false });
    find("business-search-submit").disabled = options.context.products.length === 0;
  }
}

export function initializeBusinessSearchForm() {
  if (initialized) return; initialized = true;
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(DRAFT_KEY));
    if (saved?.contractVersion === "1" && saved.request && typeof saved.request === "object"
        && saved.request.context && saved.request.criteria
        && [...Object.keys(CONTEXT_FIELDS), ...Object.keys(TARGET_FIELDS)].every((field) => {
          const value = field === "regions" ? saved.regions : (Object.hasOwn(CONTEXT_FIELDS, field) ? saved.request.context : saved.request.criteria)[field];
          return value === undefined || (Array.isArray(value) && value.length <= 100 && value.every((item) => typeof item === "string" && item.length <= 200));
        })) draft = saved;
  } catch { /* Ignore unreadable drafts. */ }
  createFields(CONTEXT_FIELDS, true); createFields(TARGET_FIELDS, false);
  const form = find("business-search-form"); form.addEventListener("submit", submit);
  form.addEventListener("change", (event) => {
    if (event.target === fields.get("regions")) addRegions();
    selectionMode(); saveDraft();
  });
  form.addEventListener("input", saveDraft);
  find("business-search-retry").addEventListener("click", () => { loadPromise = loadOptions(); });
  loadPromise = loadOptions();
}
export function loadBusinessSearchForm() { return loadPromise; }
