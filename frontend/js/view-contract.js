// Presentation metadata only: not authentication, authorization, or RBAC.
// Future role-aware navigation can consume these groups; APIs require independent enforcement.
export const VIEW_GROUPS = Object.freeze({
  BUSINESS_USER_VISIBLE: "BUSINESS_USER_VISIBLE",
  ANALYST_HIDDEN: "ANALYST_HIDDEN",
  ADMIN_HIDDEN: "ADMIN_HIDDEN",
});

export const BUSINESS_VIEW_STATES = Object.freeze({
  HOME: "HOME",
  FIND_POTENTIAL_CUSTOMERS: "FIND_POTENTIAL_CUSTOMERS",
  RESULTS: "RESULTS",
  RESULT_DETAIL: "RESULT_DETAIL",
});

const business = (state, hash, domView, title, extra = {}) => Object.freeze({
  state, group: VIEW_GROUPS.BUSINESS_USER_VISIBLE, hash, domView, title,
  showInNavigation: true, ...extra,
});
const retained = (group, domView, title) => Object.freeze({
  group, domView, title, showInNavigation: false,
});

export const VIEW_DEFINITIONS = Object.freeze({
  home: business(BUSINESS_VIEW_STATES.HOME, "#home", "overview", "Home"),
  "find-potential-customers": business(BUSINESS_VIEW_STATES.FIND_POTENTIAL_CUSTOMERS,
    "#find-potential-customers", "campaign-planner", "Find Potential Customers"),
  results: business(BUSINESS_VIEW_STATES.RESULTS, "#results", "results", "Results"),
  "result-detail": business(BUSINESS_VIEW_STATES.RESULT_DETAIL, null, "result-detail", "Result Details", {
    hashPattern: "#results/<run-id>", showInNavigation: false, parentNavigation: "results",
  }),
  "saved-target-groups": retained(VIEW_GROUPS.ANALYST_HIDDEN, "saved-target-groups", "Saved Target Groups"),
  campaigns: retained(VIEW_GROUPS.ANALYST_HIDDEN, "campaigns", "Campaigns"),
  insights: retained(VIEW_GROUPS.ANALYST_HIDDEN, "insights", "Insights"),
  "historical-analysis": retained(VIEW_GROUPS.ANALYST_HIDDEN, "historical-analysis", "Historical Analysis"),
  "audience-explorer": retained(VIEW_GROUPS.ANALYST_HIDDEN, "audience-explorer", "Audience Explorer"),
  "data-status": retained(VIEW_GROUPS.ADMIN_HIDDEN, "data-status", "Data Status"),
  "model-training": retained(VIEW_GROUPS.ADMIN_HIDDEN, "model-training", "Model Training & Prospect Scoring"),
});

export const BUSINESS_NAVIGATION = Object.freeze(Object.keys(VIEW_DEFINITIONS)
  .filter((key) => VIEW_DEFINITIONS[key].showInNavigation));
export const LEGACY_ALIASES = Object.freeze({
  overview: "home", "campaign-planner": "find-potential-customers",
});

export function resolveBusinessRoute(fragment = "") {
  const key = fragment.replace(/^#/, "");
  const alias = Object.hasOwn(LEGACY_ALIASES, key) ? LEGACY_ALIASES[key] : key;
  const definition = Object.hasOwn(VIEW_DEFINITIONS, alias) ? VIEW_DEFINITIONS[alias] : null;
  if (definition?.showInNavigation) {
    return Object.freeze({ key: alias, definition, hash: definition.hash, runId: null });
  }
  // Step 5 assigns positive integer IDs. Treat the path-safe representation as opaque.
  const detail = /^results\/([1-9][0-9]*)$/.exec(key);
  if (detail) {
    return Object.freeze({ key: "result-detail", definition: VIEW_DEFINITIONS["result-detail"],
      hash: `#results/${detail[1]}`, runId: detail[1] });
  }
  return Object.freeze({ key: "home", definition: VIEW_DEFINITIONS.home, hash: "#home", runId: null });
}

export function applyViewContract(root = document) {
  for (const view of root.querySelectorAll("[data-view]")) {
    const definition = Object.values(VIEW_DEFINITIONS).find((item) => item.domView === view.dataset.view);
    view.dataset.viewGroup = definition?.group || VIEW_GROUPS.ADMIN_HIDDEN;
    if (definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE) view.hidden = true;
  }
  for (const control of root.querySelectorAll("[data-view-target]")) {
    const key = control.dataset.viewTarget;
    const alias = Object.hasOwn(LEGACY_ALIASES, key) ? LEGACY_ALIASES[key] : key;
    const definition = Object.hasOwn(VIEW_DEFINITIONS, alias) ? VIEW_DEFINITIONS[alias] : null;
    const inNavigation = control.closest("#business-navigation") !== null;
    control.hidden = definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE
      || (inNavigation && !definition.showInNavigation);
  }
  const navigation = root.querySelector("#business-navigation");
  if (navigation) {
    for (const key of BUSINESS_NAVIGATION) {
      const control = navigation.querySelector(`[data-view-target="${key}"]`);
      if (!control) continue;
      control.querySelector("span:last-child").textContent = VIEW_DEFINITIONS[key].title;
      navigation.append(control);
    }
  }
}
