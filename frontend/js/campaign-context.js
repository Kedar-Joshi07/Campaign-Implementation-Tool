import { getCachedJSON, getJSON } from "./api.js";
import { enhanceMultiSelect, refreshMultiSelect, setMultiSelectState } from "./components/multi-select-dropdown.js";
import {
  getCampaignPlannerState,
  setTargetingContextId,
  updateCampaignContext,
} from "./campaign-planner-state.js";

const OPTIONS_URL = "/api/campaign-planner/context-options";
const FIELD_IDS = {
  product_ids: "#planner-context-products",
  campaign_types: "#planner-context-types",
  campaign_categories: "#planner-context-categories",
  offer_types: "#planner-context-offers",
  campaign_channel: "#planner-context-delivery-channel",
  historical_campaign_channels: "#planner-context-historical-channels",
};

let initialized = false;
let loadPromise = null;
let announce = () => {};
let campaignOptionsAvailable = true;

function selectedValues(selector) {
  return [...document.querySelector(selector).selectedOptions].map((option) => option.value);
}

function captureContext() {
  updateCampaignContext({
    product_ids: selectedValues(FIELD_IDS.product_ids),
    campaign_types: selectedValues(FIELD_IDS.campaign_types),
    campaign_categories: selectedValues(FIELD_IDS.campaign_categories),
    offer_types: selectedValues(FIELD_IDS.offer_types),
    campaign_channel: document.querySelector(FIELD_IDS.campaign_channel).value,
    historical_campaign_channels: selectedValues(FIELD_IDS.historical_campaign_channels),
  });
}

function appendOption(select, value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function fillMultiSelect(selector, values, labelForValue = (value) => value) {
  const select = document.querySelector(selector);
  select.replaceChildren();
  for (const value of values) appendOption(select, value, labelForValue(value));
}

function populateOptions(options) {
  const productSelect = document.querySelector(FIELD_IDS.product_ids);
  productSelect.replaceChildren();
  for (const product of options.products) {
    const category = product.product_category ? ` · ${product.product_category}` : "";
    appendOption(
      productSelect,
      product.product_id,
      `${product.product_name} (${product.product_id})${category}`,
    );
  }
  fillMultiSelect(FIELD_IDS.campaign_types, options.campaign_types);
  fillMultiSelect(FIELD_IDS.campaign_categories, options.campaign_categories);
  fillMultiSelect(FIELD_IDS.offer_types, options.offer_types);
  fillMultiSelect(
    FIELD_IDS.historical_campaign_channels,
    options.historical_campaign_channels,
  );

  const delivery = document.querySelector(FIELD_IDS.campaign_channel);
  delivery.replaceChildren();
  appendOption(delivery, "", "Choose a delivery channel");
  for (const channel of options.delivery_channels) {
    appendOption(delivery, channel.value, channel.label);
  }
  campaignOptionsAvailable = options.products.length > 0;
  for (const selector of Object.values(FIELD_IDS)) refreshMultiSelect(document.querySelector(selector));
  document.querySelector("#planner-context-empty").hidden = campaignOptionsAvailable;
  document.querySelector("#planner-next-2").disabled = !campaignOptionsAvailable;
}

function applyContext(context) {
  for (const [field, selector] of Object.entries(FIELD_IDS)) {
    const select = document.querySelector(selector);
    const selected = field === "campaign_channel"
      ? new Set([context[field]])
      : new Set(context[field] || []);
    for (const option of select.options) option.selected = selected.has(option.value);
    refreshMultiSelect(select);
  }
}

function setLoading(loading) {
  for (const selector of Object.values(FIELD_IDS)) {
    setMultiSelectState(document.querySelector(selector), { loading, error: "" });
  }
  document.querySelector("#planner-context-loading").hidden = !loading;
  document.querySelector("#planner-context-form").hidden =
    loading || !campaignOptionsAvailable;
  document.querySelector("#planner-context-save").disabled =
    loading || !campaignOptionsAvailable;
}

function showLoadError(error) {
  setLoading(false);
  for (const selector of Object.values(FIELD_IDS)) {
    setMultiSelectState(document.querySelector(selector), { error: "Choices could not be loaded. Try again." });
  }
  document.querySelector("#planner-context-form").hidden = true;
  document.querySelector("#planner-context-save").disabled = true;
  document.querySelector("#planner-context-empty").hidden = true;
  const errorBox = document.querySelector("#planner-context-error");
  errorBox.querySelector("p").textContent = error.message;
  errorBox.hidden = false;
  errorBox.focus();
}

function showSaveError(error) {
  const errorBox = document.querySelector("#planner-context-error");
  errorBox.querySelector("p").textContent = error.message;
  errorBox.hidden = false;
  errorBox.focus();
}

function showSaved(response) {
  const summary = document.querySelector("#planner-context-summary");
  summary.textContent = `Campaign context saved and verified (reference ${response.targeting_context_id}).`;
  summary.hidden = false;
}

async function loadOptionsAndReopen({ force = false } = {}) {
  setLoading(true);
  document.querySelector("#planner-context-error").hidden = true;
  try {
    const options = await getCachedJSON(OPTIONS_URL, { force });
    populateOptions(options);
    const state = getCampaignPlannerState();
    if (state.targetingContextId) {
      const saved = await getJSON(
        `/api/campaign-planner/contexts/${state.targetingContextId}`,
      );
      updateCampaignContext(saved.context);
      applyContext(saved.context);
      showSaved(saved);
    } else {
      applyContext(state.campaignContext);
    }
    setLoading(false);
  } catch (error) {
    showLoadError(error);
    throw error;
  }
}

export async function validateAndSaveCampaignContext() {
  if (loadPromise) {
    try {
      await loadPromise;
    } catch {
      return false;
    }
  }
  captureContext();
  const form = document.querySelector("#planner-context-form");
  const state = getCampaignPlannerState();
  if (!state.campaignContext.product_ids.length) {
    document.querySelector(FIELD_IDS.product_ids).setCustomValidity(
      "Choose at least one product.",
    );
  } else {
    document.querySelector(FIELD_IDS.product_ids).setCustomValidity("");
  }
  if (!form.reportValidity()) {
    announce("Choose at least one product and a delivery channel before continuing.");
    return false;
  }

  const contextId = state.targetingContextId;
  const url = contextId
    ? `/api/campaign-planner/contexts/${contextId}`
    : "/api/campaign-planner/contexts";
  const saveButton = document.querySelector("#planner-context-save");
  saveButton.disabled = true;
  try {
    const response = await getJSON(url, {
      method: contextId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context: state.campaignContext }),
    });
    setTargetingContextId(response.targeting_context_id);
    updateCampaignContext(response.context);
    applyContext(response.context);
    showSaved(response);
    announce("Campaign context saved. You can reopen it in this browser session.");
    return true;
  } catch (error) {
    showSaveError(error);
    announce(error.message);
    return false;
  } finally {
    saveButton.disabled = false;
  }
}

export function initializeCampaignContext(onStatus) {
  if (initialized) return;
  initialized = true;
  announce = onStatus;
  for (const selector of Object.values(FIELD_IDS)) {
    const select = document.querySelector(selector);
    if (select.multiple) enhanceMultiSelect(select);
    select.addEventListener("change", () => {
      document.querySelector("#planner-context-error").hidden = true;
      captureContext();
    });
  }
  document.querySelector("#planner-context-save").addEventListener("click", () => {
    validateAndSaveCampaignContext();
  });
  document.querySelector("#planner-context-retry").addEventListener("click", () => {
    loadPromise = loadOptionsAndReopen({ force: true });
    loadPromise.catch(() => {});
  });
  loadPromise = loadOptionsAndReopen();
  loadPromise.catch(() => {});
}

export function loadCampaignContext() {
  if (!loadPromise) loadPromise = loadOptionsAndReopen();
  return loadPromise;
}
