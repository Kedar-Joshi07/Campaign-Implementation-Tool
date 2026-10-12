import { getJSON } from "./api.js";
import { enhanceMultiSelect, refreshMultiSelect, setMultiSelectState } from "./components/multi-select-dropdown.js";

const DRAFT_KEY = "phase11-business-search-draft-v2";
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
let preflightRevision = 0;
let preflightRequest = 0;
const find = (id) => document.querySelector(`#${id}`);
const number = (id) => find(id).value === "" ? null : Number(find(id).value);
const selections = (field) => [...fields.get(field).selectedOptions].map((option) => option.value);
const scoreMode = () => document.querySelector('input[name="business_score_mode"]:checked')?.value || "similarity";

function invalidatePreflight() {
  preflightRevision += 1;
  preflightRequest += 1;
  find("business-search-preflight-result").textContent = "Choices changed. Check the exact count again.";
}

function renderScoreMode() {
  const similarity = scoreMode() === "similarity";
  const profileSelect = find("business-export-profile");
  const chosen = options?.profiles.find((item) => item.export_profile === profileSelect.value);
  for (const option of profileSelect.options) {
    if (!option.value) continue;
    const candidate = options?.profiles.find((item) => item.export_profile === option.value);
    // Historical v3 forms supplied a v1 channel choice. It remains an explicit
    // alias here, but capture resolves it to the new v3 analytical export.
    option.hidden = !!candidate && !similarity && candidate.profile_version === "2";
    option.disabled = option.hidden || candidate?.availability !== "AVAILABLE";
  }
  if (chosen && (chosen.profile_version === "2") !== similarity) {
    profileSelect.value = options?.profiles.find((candidate) => candidate.channel_code === chosen.channel_code
      && (candidate.profile_version === "2") === similarity
      && (!similarity || candidate.analytical_fields))?.export_profile || "";
  }
  find("business-similarity-fieldset").hidden = !similarity;
  find("business-probability-fieldset").hidden = similarity;
  find("business-top-percent-field").hidden = similarity;
  find("business-top-percent").disabled = similarity;
  for (const input of find("business-similarity-minimums").querySelectorAll("input")) input.disabled = !similarity;
  for (const input of find("business-match-strength").querySelectorAll("input")) input.disabled = similarity;
  if (similarity) find("business-top-percent").value = "";
  const readiness = similarity ? options?.mode_readiness?.buyer_similarity : options?.mode_readiness?.purchase_probability;
  find("business-search-submit").textContent = similarity
    ? readiness?.source_status === "AVAILABLE" ? "Prepare & Start Search" : "Save Search (Imports Required)"
    : "Find Potential Customers";
  const message = similarity
    ? readiness?.source_status === "AVAILABLE"
      ? "Buyer similarity is available to check or prepare for the exact selected products and historical context. Purchase-probability calibration is not required."
      : "Buyer similarity needs governed customer, sales, and demographic imports before it can be prepared."
    : readiness?.calibration_status === "CHECK_EXACT_PREFLIGHT"
      ? "Check the exact selection for current governed purchase-probability calibration."
      : "Purchase Probability is not currently calibrated. This does not block the separate Buyer Similarity mode.";
  find("business-mode-readiness").textContent = readiness?.workflow_available === false
    ? `${message} Search processing is temporarily unavailable.` : message;
}

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
  const propensityBucket = document.querySelector('input[name="business_propensity_bucket"]:checked')?.value || "";
  const legacyStrength = options?.targeting.propensity_buckets
    .find((item) => item.value === propensityBucket)?.legacy_match_strength || "GOOD";
  const similarity = scoreMode() === "similarity";
  const criteria = {
    family_member_count_min: number("business-family-min"), family_member_count_max: number("business-family-max"),
  };
  if (!similarity) Object.assign(criteria, {
    match_strength: legacyStrength,
    top_matching_percent: number("business-top-percent"), selection_mode: find("business-selection-mode").value,
    target_count: find("business-selection-mode").value === "TOP_N" ? number("business-target-count") : null,
  });
  for (const field of Object.keys(TARGET_FIELDS)) if (field !== "regions") criteria[field] = selections(field);
  const shared = { campaign_name: find("business-campaign-name").value.trim(), description: find("business-description").value.trim() || null,
    planned_launch_date: find("business-launch-date").value || null, context, criteria,
    export_profile: similarity && profile?.profile_version === "1"
      ? options?.profiles.find((item) => item.channel_code === profile.channel_code
        && item.profile_version === "2" && item.analytical_fields)?.export_profile || ""
      : find("business-export-profile").value,
    catalog_version: options?.catalog_version };
  return similarity ? { ...shared, selection_contract_version: "3", score_semantics: "PRODUCT_BUYER_SIMILARITY",
    similarity_minimum: Number(document.querySelector('input[name="business_similarity_minimum"]:checked')?.value),
    selection_mode: find("business-selection-mode").value,
    top_n: find("business-selection-mode").value === "TOP_N" ? number("business-target-count") : null,
  } : { ...shared, propensity_bucket: propensityBucket };
}

function saveDraft() {
  if (!options) return;
  draft = { contractVersion: scoreMode() === "similarity" ? "3" : "2", request: capture(), regions: selections("regions") };
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
  const selectedMode = draft?.contractVersion === "2" ? "probability" : "similarity";
  document.querySelector(`input[name="business_score_mode"][value="${selectedMode}"]`).checked = true;
  for (const [field, select] of fields) {
    const context = Object.hasOwn(CONTEXT_FIELDS, field);
    const [, key] = (context ? CONTEXT_FIELDS : TARGET_FIELDS)[field];
    const raw = (context ? payload.context : payload.targeting)[key] || [];
    const values = raw.map((item) => field === "product_ids"
      ? { value: item.product_id, label: `${item.product_name} (${item.product_id})${
          item.buyer_support?.status === "INSUFFICIENT_HISTORY"
            ? ` — unsupported for buyer similarity (${item.buyer_support.distinct_attributed_buyers} attributed buyers across all history)`
            : item.buyer_support?.status === "POTENTIALLY_SUPPORTED"
              ? ` — ${item.buyer_support.distinct_attributed_buyers} attributed buyers across all history; exact context checked before use`
              : " — buyer support not verified yet"
        }` }
      : typeof item === "string" ? { value: item, label: item } : { value: item.value, label: item.label });
    const selected = field === "regions" ? draft?.regions || [] : (context ? request.context : request.criteria)?.[field] || [];
    // Previously backend-supplied draft values remain visibly unavailable, never silently erased.
    for (const value of selected) if (!values.some((item) => item.value === value)) values.push({ value, label: `${value} (No longer available)`, disabled: true });
    const component = enhanceMultiSelect(select);
    component.setOptions(values); component.setValues(selected);
  }
  const strengths = find("business-match-strength"); strengths.replaceChildren();
  for (const strength of payload.targeting.propensity_buckets) {
    const label = make("label"); label.className = "planner-strength-choice";
    const radio = make("input"); radio.type = "radio"; radio.name = "business_propensity_bucket"; radio.value = strength.value; radio.required = true;
    radio.checked = strength.value === (request.propensity_bucket || payload.targeting.default_propensity_bucket);
    label.append(radio, make("span", `${strength.label}${strength.recommended ? " — Recommended" : ""}`)); strengths.append(label);
  }
  const minimums = find("business-similarity-minimums"); minimums.replaceChildren();
  for (const minimum of payload.targeting.buyer_similarity.minimums) {
    const label = make("label"); label.className = "planner-strength-choice";
    const radio = make("input"); radio.type = "radio"; radio.name = "business_similarity_minimum";
    radio.value = String(minimum.value); radio.required = true;
    radio.checked = minimum.value === (request.similarity_minimum ?? payload.targeting.buyer_similarity.default_minimum);
    label.append(radio, make("span", `${Math.round(Number(minimum.value) * 100)} and above${minimum.recommended ? " — Recommended" : ""}`));
    minimums.append(label);
  }
  const profiles = find("business-export-profile"); profiles.replaceChildren();
  const placeholder = make("option", "Choose a delivery/download profile"); placeholder.value = ""; profiles.append(placeholder);
  for (const profile of payload.profiles) {
    if (profile.availability !== "AVAILABLE" && profile.export_profile !== request.export_profile) continue;
    const option = make("option", profile.availability === "AVAILABLE"
      ? profile.profile_version === "1"
        ? `${profile.label} — legacy choice maps to Buyer Similarity export in this mode`
        : profile.label
      : `${profile.label} — ${profile.unavailable_reason}`);
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
    "business-target-count": request.criteria?.target_count ?? request.top_n,
  })) find(id).value = value ?? "";
  find("business-selection-mode").value = request.criteria?.selection_mode || request.selection_mode || "ALL_MATCHING";
  for (const id of ["business-family-min", "business-family-max"]) {
    find(id).min = payload.targeting.family_size_minimum || 1;
    if (payload.targeting.family_size_maximum) find(id).max = payload.targeting.family_size_maximum;
    else find(id).removeAttribute("max");
  }
  selectionMode();
  renderScoreMode();
  find("business-search-workflow-note").hidden = payload.workflow_available;
}

async function loadOptions() {
  saveDraft();
  find("business-search-loading").hidden = false; find("business-search-error").hidden = true;
  find("business-search-form").hidden = true;
  for (const select of fields.values()) setMultiSelectState(select, { loading: true, error: "" });
  try {
    const payload = await getJSON("/api/potential-customer-search/options?include_similarity=true");
    options = payload; populate(payload);
    for (const select of fields.values()) setMultiSelectState(select, { loading: false, error: "" });
    find("business-search-form").hidden = false;
    find("business-search-submit").disabled = submitting || payload.context.products.length === 0;
    find("business-search-preflight").disabled = payload.context.products.length === 0;
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

function renderSimilarityPreflight(output, result) {
  const ready = result.similarity_eligibility === "ELIGIBLE";
  const state = ready ? result.selected_count === 0 ? "No exact matches" : "Current buyer similarity"
    : result.reason_code === "PROFILE_NOT_ELIGIBLE" ? "Unsupported product or historical context"
    : result.reason_code === "SPLIT_SOLVER_UNRESOLVED" ? "Buyer split needs another preparation attempt"
    : result.similarity_currentness === "STALE" ? "Stale intelligence"
    : result.similarity_currentness === "BUILDING" ? "Building intelligence"
    : "Not prepared";
  const heading = make("h3", state);
  const metrics = make("dl"); metrics.className = "business-preflight-metrics";
  const entries = [
    ["Eligible prospects", result.demographic_eligible_count],
    ["Validly scored pool", ready ? result.valid_similarity_count : null],
    ["Feature coverage gaps", ready ? result.invalid_similarity_count : null],
    ["Similarity-qualified", ready ? result.similarity_qualifying_count : null],
    ["Selected", ready ? result.selected_count : null],
    ["Eventual exportable", null],
  ];
  for (const [term, count] of entries) {
    const metric = make("div");
    metric.append(make("dt", term), make("dd", count === null || count === undefined
      ? "Not available" : Number(count).toLocaleString()));
    metrics.append(metric);
  }
  const message = make("p", ready && result.selected_count === 0
    ? "No prospects meet this exact similarity minimum and eligibility filter. Filters were not widened."
    : result.safe_message);
  const guidance = make("p", ready
    ? "Exportable count is determined later by governed contactability checks."
    : result.build_available
      ? "Use Prepare & Start Search to build this exact context. Selected and exportable counts are not available yet."
      : "Review the selected products or historical context before starting. Selected and exportable counts are not available.");
  output.replaceChildren(heading, metrics, message, guidance);
}

function valid() {
  // The form uses novalidate so every attempt reaches these refreshed custom
  // rules before reportValidity. An earlier error must not trap a corrected draft.
  find("business-campaign-name").setCustomValidity(find("business-campaign-name").value.trim() ? "" : "Enter a campaign name.");
  const profile = options.profiles.find((item) => item.export_profile === find("business-export-profile").value);
  find("business-export-profile").setCustomValidity(profile?.availability === "AVAILABLE"
    && (scoreMode() === "similarity" || profile.profile_version !== "2")
    ? "" : "Choose a download profile for the selected score mode.");
  for (const select of fields.values()) select.setCustomValidity([...select.selectedOptions].some((option) => option.disabled) ? "Remove unavailable previous choices before continuing." : "");
  const minimum = number("business-family-min"), maximum = number("business-family-max");
  find("business-family-max").setCustomValidity(minimum !== null && maximum !== null && minimum > maximum ? "Maximum family size must be at least the minimum." : "");
  if (scoreMode() === "similarity" && !document.querySelector('input[name="business_similarity_minimum"]:checked')) {
    showError("Choose a buyer similarity minimum."); return false;
  }
  if (scoreMode() === "probability" && !document.querySelector('input[name="business_propensity_bucket"]:checked')) {
    showError("Choose a purchase probability band."); return false;
  }
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
    find("business-search-preflight").disabled = options.context.products.length === 0;
  }
}

async function preflight() {
  if (!options || !valid()) return;
  const button = find("business-search-preflight");
  const output = find("business-search-preflight-result");
  const request = capture();
  const revision = preflightRevision;
  const requestId = ++preflightRequest;
  const similarity = request.selection_contract_version === "3";
  button.disabled = true;
  output.textContent = similarity ? "Checking current buyer similarity for the exact products and filters..." : "Checking the exact calibrated audience...";
  try {
    const result = await getJSON("/api/potential-customer-search/preflight", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(similarity ? {
        selection_contract_version: "3", score_semantics: request.score_semantics,
        similarity_minimum: request.similarity_minimum, context: request.context,
        criteria: request.criteria, selection_mode: request.selection_mode,
        top_n: request.top_n, catalog_version: request.catalog_version,
      } : { context: request.context, criteria: request.criteria,
        propensity_bucket: request.propensity_bucket, catalog_version: request.catalog_version }),
    });
    if (revision !== preflightRevision || requestId !== preflightRequest) return;
    if (similarity) {
      renderSimilarityPreflight(output, result);
    } else {
      const countSummary = result.selection_mode === "TOP_N"
        ? `${result.qualifying_count.toLocaleString()} qualify; ${result.selected_count.toLocaleString()} would be selected.`
        : `${result.selected_count.toLocaleString()} exact potential customers.`;
      output.textContent = `${countSummary} ${result.safe_message} Demographic pool: ${result.demographic_count.toLocaleString()}; propensity bucket: ${result.bucket_count.toLocaleString()}; calibration: ${result.calibration_currentness}.`;
    }
  } catch (error) {
    if (revision === preflightRevision && requestId === preflightRequest)
      output.textContent = `Exact count temporarily unavailable: ${error.message || "Try again."}`;
  } finally {
    button.disabled = false;
  }
}

export function initializeBusinessSearchForm() {
  if (initialized) return; initialized = true;
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(DRAFT_KEY));
    if (["2", "3"].includes(saved?.contractVersion) && saved.request && typeof saved.request === "object"
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
    if (event.target.name === "business_score_mode") {
      renderScoreMode();
    }
    selectionMode(); invalidatePreflight(); saveDraft();
  });
  form.addEventListener("input", () => { invalidatePreflight(); saveDraft(); });
  find("business-search-preflight").addEventListener("click", preflight);
  find("business-search-retry").addEventListener("click", () => { loadPromise = loadOptions(); });
  loadPromise = null;
}
export function loadBusinessSearchForm() {
  if (!loadPromise) loadPromise = loadOptions();
  return loadPromise;
}

export async function restoreBusinessSearchFromResult(run) {
  if (!["2", "3"].includes(run.selection_contract_version)) return false;
  const version = run.selection_contract_version;
  draft = {
    contractVersion: version,
    regions: [],
    request: {
      campaign_name: `${run.campaign_name} — new search`.slice(0, 120),
      description: run.description || null,
      planned_launch_date: run.planned_launch_date || null,
      context: run.campaign_context,
      criteria: {
        ...run.targeting_criteria,
        selection_mode: run.selection?.mode || "ALL_MATCHING",
        target_count: run.selection?.target_count ?? null,
      },
      export_profile: run.export_profile,
      propensity_bucket: version === "2" ? run.propensity_bucket : undefined,
      similarity_minimum: version === "3" ? run.similarity_minimum : undefined,
    },
  };
  try { window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch { /* Optional session storage. */ }
  await loadBusinessSearchForm();
  if (options) populate(options);
  invalidatePreflight();
  return true;
}
