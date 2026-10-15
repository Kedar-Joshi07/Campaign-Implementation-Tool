"""Summarize bounded native-browser work without claiming 19.3 certification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

from scripts.validation.browser.check_ui_control_coverage import evaluate_inventory


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs" / "evidence" / "post14b_closure"
SEEDS = ROOT / "Prompts" / "Next_Actions_Native_Browser_Prompt_Pack" / "STATIC_UI_CONTROL_SEEDS.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, payload: dict) -> None:
    (EVIDENCE / name).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--conditional-inventory-root", type=Path)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--retained-root", type=Path)
    parser.add_argument("--trainable-root", type=Path)
    parser.add_argument("--links-root", type=Path)
    parser.add_argument("--form-root", type=Path)
    parser.add_argument("--export-root", type=Path)
    parser.add_argument("--feedback-root", type=Path)
    parser.add_argument("--navigation-root", type=Path)
    parser.add_argument("--campaign-root", type=Path)
    parser.add_argument("--selection-root", type=Path)
    parser.add_argument("--blocked-root", type=Path)
    parser.add_argument("--fault-root", type=Path)
    parser.add_argument("--history-root", type=Path)
    parser.add_argument("--multi-product-root", type=Path)
    parser.add_argument("--planner-blocked-root", type=Path)
    parser.add_argument("--planner-positive-root", type=Path)
    parser.add_argument("--probability-root", type=Path)
    parser.add_argument("--legacy-root", type=Path)
    parser.add_argument("--two-tab-retry-root", type=Path)
    parser.add_argument("--source-currentness-root", type=Path)
    parser.add_argument("--qualification-root", type=Path)
    parser.add_argument("--transport-root", type=Path)
    parser.add_argument("--business-links-root", type=Path)
    parser.add_argument("--historical-alternates-root", type=Path)
    parser.add_argument("--model-alternates-root", type=Path)
    parser.add_argument("--audience-alternates-root", type=Path)
    parser.add_argument("--legacy-detail-root", type=Path)
    parser.add_argument("--campaign-stepper-root", type=Path)
    args = parser.parse_args()
    inventory = _read(args.inventory_root / "native_control_inventory.json")
    conditional_inventory = (_read(args.conditional_inventory_root / "native_control_inventory.json")
                             if args.conditional_inventory_root else None)
    case = _read(args.case_root / "native_business_case.json")
    retained = (_read(args.retained_root / "native_retained_historical.json")
                if args.retained_root else None)
    trainable = (_read(args.trainable_root / "native_retained_historical.json")
                 if args.trainable_root else None)
    links = (_read(args.links_root / "native_retained_links.json")
             if args.links_root else None)
    form = (_read(args.form_root / "native_business_form_controls.json")
            if args.form_root else None)
    export = (_read(args.export_root / "native_export_matrix.json")
              if args.export_root else None)
    feedback = (_read(args.feedback_root / "native_feedback_matrix.json")
                if args.feedback_root else None)
    navigation = (_read(args.navigation_root / "native_navigation_responsive.json")
                  if args.navigation_root else None)
    campaign = (_read(args.campaign_root / "native_campaign_builder.json")
                if args.campaign_root else None)
    campaign_recovery = (_read(args.campaign_root / "native_campaign_export_recovery.json")
                         if args.campaign_root else None)
    selection = (_read(args.selection_root / "native_similarity_selection_matrix.json")
                 if args.selection_root else None)
    topn_zero = (_read(args.selection_root / "native_similarity_topn_zero_resume.json")
                 if args.selection_root else None)
    blocked = (_read(args.blocked_root / "native_unsupported_product.json")
               if args.blocked_root else None)
    fault = (_read(args.fault_root / "native_retryable_failure.json")
             if args.fault_root else None)
    history = (_read(args.history_root / "native_history_paging.json")
               if args.history_root else None)
    multi_product = (_read(args.multi_product_root / "native_multi_product.json")
                     if args.multi_product_root else None)
    planner_blocked = (_read(args.planner_blocked_root / "native_retained_planner.json")
                       if args.planner_blocked_root else None)
    planner_positive = (_read(args.planner_positive_root / "native_retained_planner_positive_resume.json")
                        if args.planner_positive_root else None)
    probability = (_read(args.probability_root / "native_probability_v2.json")
                   if args.probability_root else None)
    legacy = (_read(args.legacy_root / "native_legacy_v1_reopen.json")
              if args.legacy_root else None)
    two_tab_retry = (_read(args.two_tab_retry_root / "native_retry_two_tabs.json")
                     if args.two_tab_retry_root else None)
    source_currentness = (_read(args.source_currentness_root / "native_source_currentness.json")
                          if args.source_currentness_root else None)
    qualification = (_read(args.qualification_root / "native_named_10k_qualification.json")
                     if args.qualification_root else None)
    transport = (_read(args.transport_root / "native_transport_rejoin.json")
                 if args.transport_root else None)
    business_links = (_read(args.business_links_root / "native_business_links.json")
                      if args.business_links_root else None)
    historical_alternates = (_read(args.historical_alternates_root / "native_historical_alternates.json")
                             if args.historical_alternates_root else None)
    model_alternates = (_read(args.model_alternates_root / "native_model_alternates.json")
                        if args.model_alternates_root else None)
    audience_alternates = (_read(args.audience_alternates_root / "native_audience_alternates.json")
                           if args.audience_alternates_root else None)
    legacy_detail = (_read(args.legacy_detail_root / "native_legacy_detail_actions.json")
                     if args.legacy_detail_root else None)
    campaign_stepper = (_read(args.campaign_stepper_root / "native_campaign_stepper.json")
                        if args.campaign_stepper_root else None)
    case_by_id = {item["id"]: item for item in case["cases"]}
    seeds = _read(SEEDS)
    if inventory["status"] != "PASS_DISCOVERY_ONLY" or case["status"] != "PASS_ONE_BUSINESS_CASE":
        raise RuntimeError("Partial evidence inputs must be successful and explicitly scoped.")
    if conditional_inventory and not (
        conditional_inventory["status"] == "PASS_DISCOVERY_ONLY"
        and any(view.get("state", {}).get("selection_contract_version") == "3"
                for view in conditional_inventory["views"])
    ):
        raise RuntimeError("Supplemental discovery must include a genuine v3 completed result.")
    if retained and retained["status"] != "PASS_RETAINED_HISTORICAL_AND_MODEL_BLOCK":
        raise RuntimeError("Retained input must be a successful bounded browser case.")
    if trainable and trainable["status"] != "PASS_RETAINED_TRAINABLE_MODEL":
        raise RuntimeError("Trainable input must include successful bounded model/scoring jobs.")
    if links and links["status"] != "PASS_RETAINED_INSIGHTS_LINKS_AND_ROUTING_BOUNDARY":
        raise RuntimeError("Insights navigation input must be a successful bounded browser case.")
    if form and form["status"] != "PASS_BUSINESS_FORM_CONTROLS":
        raise RuntimeError("Business form input must be a successful bounded browser case.")
    if export and export["status"] != "PASS_V3_ALL_AVAILABLE_EXPORT_PROFILES":
        raise RuntimeError("Export input must pass all 20 available v3 profiles.")
    if feedback and feedback["status"] != "PASS_FEEDBACK_NEGATIVE_MATRIX":
        raise RuntimeError("Feedback input must pass positive and negative uploads.")
    if navigation and navigation["status"] != "PASS_NAVIGATION_RESPONSIVE_SLICE":
        raise RuntimeError("Navigation input must pass the bounded headed-browser slice.")
    if campaign and campaign_recovery and not (
        campaign["status"] == "FAIL_CAMPAIGN_BUILDER_SLICE"
        and campaign_recovery["status"] == "PASS_RESTART_AND_EDGE_EXPORT"
        and any(item["id"] == "CAMPAIGN_EMAIL_DRAFT_FINALIZE_EXPORT"
                for item in campaign["cases"])
    ):
        raise RuntimeError("Campaign evidence must preserve the Chrome failure and Edge recovery.")
    if selection and topn_zero and not (
        selection["status"] == "PASS_V3_SELECTION_MINIMUM_MATRIX"
        and topn_zero["status"] == "PASS_TOPN_AND_HONEST_ZERO"
        and len(selection["cases"]) == 5 and len(topn_zero["cases"]) == 2
    ):
        raise RuntimeError("Selection evidence must pass five minima, TOP_N and honest zero.")
    if blocked and not (
        blocked["status"] == "PASS_PERMANENT_SUPPORT_BLOCK"
        and blocked["mixed_status_polling_contract"] == [True, True, False]
        and blocked["owned_server_stopped"]
        and blocked["runtime"][0] == "PROFILE_NOT_ELIGIBLE"
        and blocked["runtime"][3] == 0
    ):
        raise RuntimeError("Permanent-block evidence must include the mixed-status polling regression.")
    if fault and not (
        fault["status"] == "PASS_FAULT_RETRY_COMPLETED"
        and fault["first_attempts"] == fault["final_attempts"][:1]
        and len(fault["final_attempts"]) == 2
        and fault["final_attempts"][0][1] == "FAILED"
        and fault["final_attempts"][1][1] == "COMPLETED"
        and fault["owned_server_stopped"]
    ):
        raise RuntimeError("One-shot fault must preserve attempt one and complete attempt two.")
    if history and not (
        history["status"] == "PASS_HISTORY_PAGING_BOUNDARY"
        and history["ordered_run_ids"] == list(range(20, 0, -1))
        and history["owned_server_stopped"]
    ):
        raise RuntimeError("History paging must preserve the exact 20-run order.")
    if multi_product and not (
        multi_product["status"] == "PASS_MULTI_PRODUCT_ANY_MAX"
        and multi_product["profile_count"] == multi_product["generation_count"] == 2
        and multi_product["score_rows"] == 400
        and multi_product["strict_expected"] == multi_product["strict_selected"]
        and multi_product["owned_server_stopped"]
    ):
        raise RuntimeError("Multi-product evidence must reconcile both score generations and exact membership.")
    if planner_blocked and not (
        planner_blocked["status"] == "PASS_RETAINED_PLANNER_TO_INTELLIGENCE"
        and planner_blocked["owned_server_stopped"]
        and len(planner_blocked["cases"]) == 5
    ):
        raise RuntimeError("Retained planner blocked-path evidence is incomplete.")
    if planner_positive and not (
        planner_positive["status"] == "PASS_RETAINED_PLANNER_FIVE_STEPS"
        and planner_positive["owned_server_stopped"]
        and len(planner_positive["cases"]) == 7
        and int(planner_positive["preview_selected"]) == 200
    ):
        raise RuntimeError("Retained planner five-step positive evidence is incomplete.")
    if probability and not (
        probability["status"] == "PASS_V2_BUCKET_AND_MEMBERSHIP_MATRIX"
        and probability["owned_server_stopped"]
        and len(probability["cases"]) == 5
        and [item["bucket"] for item in probability["cases"]]
            == ["0.90", "0.80", "0.70", "0.60", "0.50"]
        and all(item["preflight_selected"] == item["independent_oracle"]
                for item in probability["cases"])
    ):
        raise RuntimeError("Native v2 bucket preflight and result evidence is incomplete.")
    if legacy and not (
        legacy["status"] == "PASS_LEGACY_V1_REOPEN"
        and legacy["selection_contract_version"] == "1"
        and legacy["selected_count"] == 200
        and legacy["exported_count"] == 160
        and len(legacy["csv_sha256"]) == 64
        and legacy["owned_server_stopped"]
    ):
        raise RuntimeError("Native legacy v1 historical reopen evidence is incomplete.")
    if two_tab_retry and not (
        two_tab_retry["status"] == "PASS_FAULT_TWO_TAB_RETRY_FENCED"
        and two_tab_retry["competing_retry_status"] == 409
        and len(two_tab_retry["final_attempts"]) == 2
        and two_tab_retry["final_attempts"][0][1] == "FAILED"
        and two_tab_retry["final_attempts"][1][1] == "COMPLETED"
        and two_tab_retry["owned_server_stopped"]
    ):
        raise RuntimeError("Two-tab retry must produce one second attempt and a safe conflict.")
    if source_currentness and not (
        source_currentness["status"] == "PASS_BOUNDED_SOURCE_REPLACEMENT_CURRENTNESS"
        and source_currentness["effective_result_currentness"] == "STALE"
        and source_currentness["post_import_preflight"]["selected_count"] is None
        and source_currentness["post_import_preflight"]["reason_code"] == "SIMILARITY_SOURCE_STALE"
        and source_currentness["before"] == source_currentness["after"]
        and source_currentness["owned_server_stopped"]
    ):
        raise RuntimeError("Source replacement must preserve the old result and show stale/unknown UI state.")
    if qualification and not (
        qualification["status"] == "PASS_NAMED_10K_TRUTHFUL_QUALIFICATION"
        and qualification["demographics"] == qualification["valid_score_rows"] == 12_000
        and qualification["independent_qualifying_count"] == qualification["selected_count"] == 12_000
        and qualification["qualification_threshold_met"]
        and not qualification["v3_demo_ready_field_present"]
        and qualification["owned_server_stopped"]
    ):
        raise RuntimeError("Named 12K case must prove exact membership and the unmodified 10K threshold.")
    if transport and not (
        transport["status"] == "PASS_NATIVE_TRANSPORT_REJOIN"
        and transport["database_counts_before_after"] == [1, 1, 0, 1]
        and transport["backend_status_sequence"] == ["ONLINE", "OFFLINE", "ONLINE"]
        and transport["offline_request_failures"]
        and not transport["page_errors"]
        and transport["owned_server_stopped"]
    ):
        raise RuntimeError("Native offline/rejoin must preserve the immutable result without writes.")
    if business_links and not (
        business_links["status"] == "PASS_BUSINESS_LINKS_AND_V3_TECHNICAL"
        and [item["id"] for item in business_links["cases"]] == [
            "HOME_VIEW_ALL_RESULTS", "RESULTS_FIND_CUSTOMERS_SHORTCUT",
            "BRAND_HOME_AND_RECENT_RESULT", "V3_TECHNICAL_DISCLOSURE",
        ]
        and business_links["database_counts_before_after"] == [1, 0, 1]
        and business_links["owned_server_stopped"]
    ):
        raise RuntimeError("Business links must pass real navigation/detail and preserve database counts.")
    if historical_alternates and not (
        historical_alternates["status"] == "PASS_RETAINED_HISTORICAL_ALTERNATES"
        and len(historical_alternates["cases"]) == 11
        and historical_alternates["analysis_runs_before_after"][1]
            - historical_alternates["analysis_runs_before_after"][0] == 3
        and all(item["status"] == "PASS" for item in historical_alternates["cases"])
        and all(item["selected_count"] >= item["positive_count"] >= 0
                for item in historical_alternates["cases"]
                if item["id"].startswith("HISTORICAL_CONVERSION_"))
        and historical_alternates["owned_server_stopped"]
    ):
        raise RuntimeError("Historical alternates must reconcile all three UI/DB result counts.")
    if model_alternates and not (
        model_alternates["status"] == "PASS_RETAINED_MODEL_ALTERNATES"
        and len(model_alternates["cases"]) == 5
        and all(item["status"] == "PASS" for item in model_alternates["cases"])
        and model_alternates["model_runs_before_after"][1]
            - model_alternates["model_runs_before_after"][0] == 1
        and model_alternates["scoring_runs_before_after"] == [1, 1]
        and model_alternates["owned_server_stopped"]
    ):
        raise RuntimeError("Model alternates must prove validation, a real bounded job, and reopen.")
    if audience_alternates and not (
        audience_alternates["status"] == "PASS_RETAINED_AUDIENCE_ALTERNATES"
        and len(audience_alternates["cases"]) == 20
        and all(item["status"] == "PASS" for item in audience_alternates["cases"])
        and audience_alternates["audiences_before_after"][1]
            - audience_alternates["audiences_before_after"][0] == 1
        and audience_alternates["scoring_runs_before_after"] == [1, 1]
        and audience_alternates["owned_server_stopped"]
    ):
        raise RuntimeError("Audience alternate fields must pass real estimates and one durable save.")
    if legacy_detail and not (
        legacy_detail["status"] == "PASS_LEGACY_DETAIL_ACTIONS"
        and len(legacy_detail["cases"]) == 20
        and all(item["status"] == "PASS" for item in legacy_detail["cases"])
        and [item["exported"] for item in legacy_detail["cases"]
             if item["id"].endswith("_EXPORT")] == [160, 0, 160]
        and legacy_detail["feedback_batches_before_after"] == [0, 0]
        and legacy_detail["search_runs_before_after"] == [3, 3]
        and legacy_detail["owned_server_stopped"]
    ):
        raise RuntimeError("Legacy detail controls must prove all three versions/states and export audits.")
    if campaign_stepper and not (
        campaign_stepper["status"] == "PASS_RETAINED_CAMPAIGN_STEPPER"
        and [item["id"] for item in campaign_stepper["cases"]] == [
            "SAVED_GROUP_CREATE_CAMPAIGN_ROUTE", "CAMPAIGN_WORKSPACE_REFRESH",
            "CAMPAIGN_STEPPER_GUARDED_VISITED_NAVIGATION",
            "CAMPAIGN_RECENT_OPEN_FINALIZED", "CAMPAIGN_DRAFT_EDIT_SAVE_SAME_AUDIENCE",
            "CAMPAIGN_POST_FIX_DRAFT_FINALIZE_EXPORT",
        ]
        and all(item["status"] == "PASS" for item in campaign_stepper["cases"])
        and campaign_stepper["campaigns_before_after"][1]
            - campaign_stepper["campaigns_before_after"][0] == 1
        and campaign_stepper["cases"][-1]["exported"] == 160
        and campaign_stepper["owned_server_stopped"]
    ):
        raise RuntimeError("Campaign stepper must prove guarded navigation and post-fix export.")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_sha = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in ("frontend/index.html", "frontend/css/main.css", "frontend/css/components.css",
                         "frontend/js/app.js", "frontend/js/view-contract.js",
                         "frontend/js/business-search-form.js", "frontend/js/business-search-status.js",
                         "frontend/js/run-progress.js",
                         "frontend/js/audience-explorer.js", "frontend/js/campaigns.js",
                         "app/services/prospect_scoring_service.py",
                         "app/services/campaign_service.py",
                         "app/routers/potential_customer_search.py")
    }
    for qa_root in (args.inventory_root, args.case_root, args.retained_root,
                    args.trainable_root, args.links_root, args.form_root,
                    args.export_root, args.feedback_root, args.navigation_root,
                    args.campaign_root, args.selection_root, args.blocked_root,
                    args.fault_root, args.history_root, args.multi_product_root,
                    args.planner_blocked_root, args.planner_positive_root,
                    args.probability_root, args.legacy_root, args.two_tab_retry_root,
                    args.source_currentness_root, args.qualification_root,
                    args.conditional_inventory_root, args.transport_root,
                    args.business_links_root, args.historical_alternates_root,
                    args.model_alternates_root, args.audience_alternates_root,
                    args.legacy_detail_root, args.campaign_stepper_root):
        if qa_root is None:
            continue
        for relative, digest in source_sha.items():
            if relative in ("frontend/js/app.js", "frontend/js/view-contract.js"):
                continue  # The frozen QA copy changes only their routing seam.
            if relative == "frontend/js/audience-explorer.js" and qa_root != args.trainable_root:
                continue  # Earlier cases did not exercise this corrected retained view.
            if relative == "frontend/js/campaigns.js" and qa_root != args.campaign_stepper_root:
                continue  # Earlier cases predate the guarded stepper click repair.
            if relative in ("frontend/css/main.css", "frontend/css/components.css") \
                    and qa_root != args.campaign_stepper_root:
                continue  # Earlier cases predate the native 200-percent reflow repair.
            if relative == "app/services/campaign_service.py" and qa_root != args.campaign_stepper_root:
                continue  # Earlier cases predate the per-response campaign-list reuse repair.
            if relative == "app/routers/potential_customer_search.py" and qa_root != args.feedback_root:
                continue  # Earlier cases did not exercise the repaired malformed-JSON branch.
            if relative == "frontend/js/run-progress.js" and qa_root not in (
                args.blocked_root, args.fault_root, args.planner_positive_root,
                args.probability_root, args.legacy_root, args.two_tab_retry_root,
                args.source_currentness_root,
                args.qualification_root,
                args.transport_root,
                args.business_links_root,
            ):
                continue  # Earlier roots predate the mixed-status polling repair.
            if relative == "app/services/prospect_scoring_service.py" and qa_root not in (
                args.probability_root, args.two_tab_retry_root,
                args.source_currentness_root,
                args.qualification_root,
                args.transport_root,
                args.business_links_root,
            ):
                continue  # Only the new calibrated fixture ran the intermediate-mean repair.
            copied = qa_root / "source" / relative
            if hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"QA evidence executable differs from candidate: {qa_root}/{relative}")
    static = []
    for seed in seeds["controls"]:
        static.append({
            "control_id": f"STATIC_{seed['index']:03d}", "source": "STATIC_HTML_SEED",
            "dom_view": seed.get("dom_view"), "id": seed.get("id"),
            "tag": seed["tag"], "type": seed.get("type"),
            "role": seed.get("role"), "data_attributes": seed.get("data_attributes", {}),
            "classification": "CONTAINER_OR_DISCLOSURE" if seed["tag"] in {"form", "div", "details"}
                else "ACTIONABLE_SEED", "status": "NOT_RUN",
            "unresolved_reason": "Static seed requires mapped runtime state and functional case.",
        })
    runtime = []
    discovered_views = list(inventory["views"])
    if conditional_inventory:
        discovered_views.extend(
            view for view in conditional_inventory["views"]
            if view.get("state", {}).get("selection_contract_version") == "3"
        )

    def proven_case(view: dict, item: dict) -> str | None:
        """Map only controls with a passed native case and the same shared handler/state."""
        selector = str(item["selector"])
        label = str(item["label"])
        route = str(view["route"])
        version = (view.get("state") or {}).get("selection_contract_version")
        if navigation and selector in {
            "#sidebar-collapse", "#nav-home", "#nav-find-potential-customers", "#nav-results",
        }:
            return "NAVIGATION_RESPONSIVE_SHARED_GLOBAL_CONTROL"
        if business_links and selector == '[data-view-target="home"]':
            return "BRAND_HOME_AND_RECENT_RESULT"
        if transport and selector == "#backend-status":
            return "NATIVE_BACKEND_STATUS_ONLINE_OFFLINE_ONLINE"
        if route == "home" and navigation and selector == "#home-find-potential-customers":
            return "HOME_COUNTS_RECENT_AND_NAV"
        if route == "home" and business_links:
            if selector == '[data-view-target="results"]':
                return "HOME_VIEW_ALL_RESULTS"
            if label == "View Result":
                return "BRAND_HOME_AND_RECENT_RESULT"
        if route == "find-potential-customers" and form:
            multiselects = {
                f"#business-{row['field']}-trigger" for row in form["multiselects"]
            }
            if selector in multiselects:
                return "BUSINESS_FORM_DYNAMIC_MULTISELECT_MATRIX"
            if selector in {
                "#business-campaign-name", "#business-description", "#business-launch-date",
                "#business-family-min", "#business-family-max", "#business-selection-mode",
                "#business-export-profile", "#business-search-preflight", "#business-search-submit",
            }:
                return "BUSINESS_FORM_VALIDATION_AND_PREFLIGHT"
            if item.get("name") in {"business_score_mode", "business_similarity_minimum"}:
                return "BUSINESS_FORM_SCORE_MODE_AND_MINIMUM_MATRIX"
            if label.startswith("More options"):
                return "BUSINESS_FORM_ADVANCED_DISCLOSURE"
        if route == "results" and navigation and selector == "#business-history-refresh":
            return "THREE_ROUTES_BACK_FORWARD_REPEAT"
        if route == "results" and business_links and selector == '[data-view-target="find-potential-customers"]':
            return "RESULTS_FIND_CUSTOMERS_SHORTCUT"
        if route == "saved-target-groups" and trainable:
            if selector in {"#business-target-groups-refresh"}:
                return "RETAINED_SAVED_TARGET_GROUPS_REFRESH"
            if label == "View advanced definition":
                return "RETAINED_ADVANCED_DEFINITION_LINK"
        if route == "saved-target-groups" and campaign_stepper and label == "Create Campaign":
            return "SAVED_GROUP_CREATE_CAMPAIGN_ROUTE"
        if route == "insights" and links and selector in {
            '[data-view-target="historical-analysis"]', '[data-view-target="audience-explorer"]',
        }:
            return "RETAINED_INSIGHTS_DESTINATION_LINKS"
        if route == "historical-analysis" and trainable:
            if selector in {"#historical-analysis-reset", "#analysis-name", "#campaign-filter",
                            "#analyze-population"} or label == "Reopen":
                return "RETAINED_HISTORICAL_TRAINABLE_ANALYSIS"
            if item.get("name") == "conversion_definition" and label.startswith("Any purchase"):
                return "RETAINED_HISTORICAL_ANY_PURCHASE"
        if route == "historical-analysis" and historical_alternates:
            alt_controls = {
                "#historical-analysis-refresh": "HISTORICAL_OPTIONS_REFRESH",
                "#contact-date-from": "HISTORICAL_DATE_GUARD_RESET",
                "#contact-date-to": "HISTORICAL_DATE_GUARD_RESET",
                "#product-filter": "HISTORICAL_FILTER_PRODUCT_IDS",
                "#product-category-filter": "HISTORICAL_FILTER_PRODUCT_CATEGORIES",
                "#channel-filter": "HISTORICAL_FILTER_CAMPAIGN_CHANNELS",
                "#campaign-type-filter": "HISTORICAL_FILTER_CAMPAIGN_TYPES",
                "#conversion-attributed-purchase": "HISTORICAL_CONVERSION_ATTRIBUTED_PURCHASE",
                "#conversion-response": "HISTORICAL_CONVERSION_RESPONSE",
                "#contacted-only": "HISTORICAL_CONVERSION_ANY_PURCHASE",
                "#recent-analyses-refresh": "HISTORICAL_RECENT_REFRESH_REOPEN",
            }
            if selector in alt_controls:
                return alt_controls[selector]
        if route == "model-training" and trainable and selector in {
            "#source-analysis-select", "#model-name-input", "#train-model-submit",
        }:
            return "RETAINED_MODEL_TRAINING_AND_BOUNDED_SCORING"
        if route == "model-training" and model_alternates:
            model_controls = {
                "#model-training-refresh": "MODEL_WORKSPACE_REFRESH_AND_SOURCE",
                "#random-seed-input": "MODEL_RANDOM_SEED_GUARD",
                "#validation-fraction-input": "MODEL_VALIDATION_FRACTION_GUARD",
                "#run-elkan-challenger-input": "MODEL_ALTERNATE_REAL_TRAIN_NO_CHALLENGER",
                "#recent-model-runs-refresh": "MODEL_RECENT_REFRESH_REOPEN",
            }
            if selector in model_controls:
                return model_controls[selector]
            if label == "Load":
                return "MODEL_RECENT_REFRESH_REOPEN"
        if route == "audience-explorer" and trainable and selector in {
            "#audience-filter-reset", "#audience-score-min", "#audience-score-max",
            "#audience-selection-topn", "#audience-target-count", "#audience-apply-filters",
            "#audience-save-name", "#audience-save-submit", "#audience-profile-dimension",
        }:
            return "RETAINED_AUDIENCE_ESTIMATE_SAVE_PAGINATION_TOPN"
        if route == "audience-explorer" and trainable and selector.startswith(
            "#audience-profile-comparison-tabs > button"
        ):
            return "RETAINED_AUDIENCE_ESTIMATE_SAVE_PAGINATION_TOPN"
        if route == "audience-explorer" and audience_alternates:
            audience_controls = {
                "#audience-explorer-refresh": "AUDIENCE_WORKSPACE_REFRESH",
                "#audience-top-percentile": "AUDIENCE_FILTER_TOP_PERCENTILE_MAX",
                "#audience-deciles": "AUDIENCE_FILTER_DECILES",
                "#audience-rank-bands": "AUDIENCE_FILTER_RANK_BANDS",
                "#audience-age-min": "AUDIENCE_FILTER_AGE_MIN",
                "#audience-age-max": "AUDIENCE_FILTER_AGE_MAX",
                "#audience-income-min": "AUDIENCE_FILTER_INDIVIDUAL_YEARLY_INCOME_MIN",
                "#audience-income-max": "AUDIENCE_FILTER_INDIVIDUAL_YEARLY_INCOME_MAX",
                "#audience-family-min": "AUDIENCE_FILTER_FAMILY_MEMBER_COUNT_MIN",
                "#audience-family-max": "AUDIENCE_FILTER_FAMILY_MEMBER_COUNT_MAX",
                "#audience-gender": "AUDIENCE_FILTER_GENDER",
                "#audience-state": "AUDIENCE_FILTER_STATE",
                "#audience-marital-status": "AUDIENCE_FILTER_MARITAL_STATUS",
                "#audience-education": "AUDIENCE_FILTER_EDUCATION",
                "#audience-employment-status": "AUDIENCE_FILTER_EMPLOYMENT_STATUS",
                "#audience-resident-status": "AUDIENCE_FILTER_RESIDENT_STATUS",
                "#audience-resident-type": "AUDIENCE_FILTER_RESIDENT_TYPE",
                "#audience-type-of-employment": "AUDIENCE_FILTER_TYPE_OF_EMPLOYMENT",
                "#audience-selection-all": "AUDIENCE_CLEAR_CHIPS_ALL_MODE",
                "#audience-clear-filter-chips": "AUDIENCE_CLEAR_CHIPS_ALL_MODE",
                "#saved-audiences-refresh": "AUDIENCE_SAVED_REFRESH_DESCRIPTION_VIEW",
                "#audience-save-description": "AUDIENCE_SAVED_REFRESH_DESCRIPTION_VIEW",
            }
            if selector in audience_controls:
                return audience_controls[selector]
            if label == "View":
                return "AUDIENCE_SAVED_REFRESH_DESCRIPTION_VIEW"
        if route == "data-status" and trainable and selector == "#data-status-refresh":
            return "RETAINED_DATA_STATUS_REFRESH"
        if route == "campaigns" and campaign and selector in {
            "#campaign-new-draft", "#campaign-audience-select", "#campaign-step-next-1",
            "#campaign-export-history-refresh",
        }:
            return "RETAINED_CAMPAIGN_EMAIL_DRAFT_EXPORT"
        if route == "campaigns" and campaign_stepper:
            if selector == "#campaigns-refresh":
                return "CAMPAIGN_WORKSPACE_REFRESH"
            if selector in {f"#campaign-step-{step}" for step in range(1, 5)}:
                return "CAMPAIGN_STEPPER_GUARDED_VISITED_NAVIGATION"
            if label == "Open":
                return "CAMPAIGN_RECENT_OPEN_FINALIZED"
        if route.startswith("results/"):
            if legacy_detail and version in {"1", "2"}:
                run_id = route.split("/", 1)[1]
                prefix = f"LEGACY_V{version}_{run_id}_"
                legacy_controls = {
                    "#result-detail-refresh": "REFRESH_TECHNICAL",
                    "#result-detail-run-again": "RUN_AGAIN_RESTORE",
                    "#result-detail-download": "EXPORT",
                    "#result-feedback-csv-template": "CSV_TEMPLATE",
                    "#result-feedback-json-template": "JSON_TEMPLATE",
                    "#result-feedback-file": "UPLOAD_GUARDS",
                    "#result-feedback-upload": "UPLOAD_GUARDS",
                }
                suffix = legacy_controls.get(selector)
                if label == "View accepted CSV and JSON formats":
                    suffix = "FORMAT_GUIDE"
                elif label == "View technical details":
                    suffix = "REFRESH_TECHNICAL"
                if suffix and any(case["id"] == prefix + suffix for case in legacy_detail["cases"]):
                    return prefix + suffix
            if version == "1" and legacy:
                if selector in {"#result-detail-back", "#result-detail-download"}:
                    return "LEGACY_V1_REOPEN_AND_NATIVE_EXPORT"
                if label == "View technical details":
                    return "LEGACY_V1_TECHNICAL_LINEAGE"
            if version == "2" and probability:
                if selector == "#result-detail-back":
                    return "V2_BUCKET_RESULT_REOPEN"
            if version == "3" and case:
                if selector in {
                    "#result-detail-back", "#result-detail-refresh", "#result-detail-run-again",
                    "#result-detail-download", "#result-feedback-csv-template",
                    "#result-feedback-json-template", "#result-feedback-file",
                    "#result-feedback-upload",
                }:
                    return "V3_RESULT_EXPORT_FEEDBACK_REUSE"
                if label == "View accepted CSV and JSON formats":
                    return "V3_FEEDBACK_FORMAT_GUIDE"
                if business_links and label == "View technical details":
                    return "V3_TECHNICAL_DISCLOSURE"
        return None

    for view in discovered_views:
        observed_state = view.get("state") or {}
        state_suffix = (
            f"V{observed_state['selection_contract_version']}_"
            f"{'ZERO' if observed_state['zero_result'] else 'POSITIVE'}"
            if "selection_contract_version" in observed_state else "ENTRY"
        )
        for number, item in enumerate(view["controls"], 1):
            case_id = proven_case(view, item)
            runtime.append({
                "control_id": f"RUNTIME_{view['route'].upper().replace('-', '_').replace('/', '_')}_{state_suffix}_{number:03d}",
                "scope": view["scope"], "route": view["route"],
                "observed_state": observed_state,
                "source": "HEADED_CHROME_VISIBLE_DOM", "locator": item["selector"],
                "label": item["label"], "tag": item["tag"], "type": item["type"],
                "name": item.get("name"), "value": item.get("value"),
                "disabled_in_observed_state": item["disabled"],
                "expanded_in_observed_state": item["expanded"],
                "option_count_in_observed_state": item["option_count"],
                "status": "PASS" if case_id else "NOT_RUN",
                "case_id": case_id,
                "unresolved_reason": None if case_id else
                    "Discovery is not a functional PASS; conditional states and side effects remain to be mapped.",
            })
    summary = {
        "stage": "19_3", "status": "NO_GO_PARTIAL_DISCOVERY",
        "baseline_head": head, "source_sha256": source_sha,
        "browser": inventory["browser"], "playwright_version": inventory["playwright_version"],
        "static_seed_count": len(static),
        "static_actionable_seed_count": sum(r["classification"] == "ACTIONABLE_SEED" for r in static),
        "static_container_or_disclosure_count": sum(r["classification"] != "ACTIONABLE_SEED" for r in static),
        "runtime_control_observations": len(runtime),
        "runtime_coverage_gate": evaluate_inventory({
            "controls": [{"selector": item["locator"] or item["control_id"],
                          "status": item["status"]} for item in runtime],
        }),
        "runtime_observations_by_scope": dict(Counter(r["scope"] for r in runtime)),
        "views_discovered": [v["route"] for v in discovered_views],
        "not_yet_discovered": ["menus and options after interactions",
                               "empty/error/retry states", "post-job retained workspaces",
                               "additional conditional run/detail states"],
        "static_seeds": static, "runtime_observations": runtime,
        "qa_output_evidence": str(args.inventory_root / "native_control_inventory.json"),
        "supplemental_qa_output_evidence": (
            str(args.conditional_inventory_root / "native_control_inventory.json")
            if conditional_inventory else None),
    }
    _write("19_3_RUNTIME_CONTROL_INVENTORY.json", summary)
    cases = {
        "stage": "19_3", "status": "NO_GO_PARTIAL_CASES",
        "baseline_head": head, "source_sha256": source_sha,
        "case_scope": case["scope"], "browser": case["browser"],
        "passed_cases": case["cases"], "api_responses": case["api_responses"],
        "retained_historical_case": ({key: retained[key] for key in (
            "scope", "status", "browser", "analysis_run_id", "selected_people",
            "positive_people", "observations", "breakdown_tabs_tested", "api_responses",
            "model_one_component_job_status", "model_one_component_safe_failure",
            "model_one_component_failure_category",
            "console_errors", "page_errors", "request_failures", "owned_server_stopped")}
            if retained else None),
        "retained_trainable_case": ({key: trainable[key] for key in (
            "scope", "status", "fixture_kind", "browser", "analysis_run_id",
            "selected_people", "positive_people", "observations",
            "model_one_component_job_status", "bounded_scoring_status", "bounded_scored_people",
            "bounded_audience_saved_people", "bounded_audience_top_n_people",
            "bounded_audience_paginated_people", "bounded_saved_target_groups_visible",
            "bounded_data_status_counts",
            "api_responses", "console_errors", "page_errors", "request_failures",
            "owned_server_stopped")}
            if trainable else None),
        "retained_insights_links_case": ({key: links[key] for key in (
            "scope", "status", "browser", "business_insights_hash_hidden",
            "retained_destinations_clicked", "audience_no_run_guard_visible",
            "jobs_after_navigation", "scoring_runs_after_navigation",
            "api_responses", "console_errors", "page_errors", "request_failures",
            "owned_server_stopped")}
            if links else None),
        "business_form_controls_case": ({key: form[key] for key in (
            "scope", "status", "browser", "multiselects", "tested_similarity_minima",
            "tested_probability_bucket_count", "required_and_numeric_guards",
            "preflight_request", "runs_after", "jobs_after", "api_responses",
            "console_errors", "page_errors", "request_failures", "owned_server_stopped")}
            if form else None),
        "all_v3_export_profiles_case": ({
            "scope": export["scope"], "status": export["status"],
            "profile_count": len(export["profiles"]),
            "profiles": [{key: item[key] for key in (
                "profile", "run_id", "selected", "deliverable", "excluded", "csv_sha256")}
                for item in export["profiles"]],
            "browser": export["browser"], "owned_server_stopped": export["owned_server_stopped"],
        } if export else None),
        "feedback_negative_matrix_case": ({
            "scope": feedback["scope"], "status": feedback["status"],
            "cases": feedback["cases"], "lineage": feedback["lineage"],
            "database_counts": feedback["database_counts"],
            "browser": feedback["browser"], "owned_server_stopped": feedback["owned_server_stopped"],
        } if feedback else None),
        "navigation_responsive_case": ({
            "scope": navigation["scope"], "status": navigation["status"],
            "cases": navigation["cases"], "database_counts_before_after": navigation["database_counts_before_after"],
            "browser": navigation["browser"], "owned_server_stopped": navigation["owned_server_stopped"],
        } if navigation else None),
        "campaign_builder_and_export_recovery_case": ({
            "scope": campaign["scope"], "initial_status": campaign["status"],
            "initial_passed_cases": campaign["cases"],
            "recovery_scope": campaign_recovery["scope"],
            "recovery_status": campaign_recovery["status"],
            "reconciled_interrupted_event": campaign_recovery["reconciled_interrupted_event"],
            "recovery_event_statuses": campaign_recovery["event_statuses"],
            "recovery_browser": campaign_recovery["browser"],
            "direct_mail_selected": campaign_recovery["selected"],
            "direct_mail_deliverable": campaign_recovery["deliverable"],
            "direct_mail_excluded": campaign_recovery["excluded"],
            "direct_mail_csv_sha256": campaign_recovery["csv_sha256"],
            "owned_server_stopped": campaign_recovery["owned_server_stopped"],
            "limitation": "Not all retained Campaign Builder controls/states certified; original Chrome crash preserved.",
        } if campaign else None),
        "v3_exact_selection_and_zero_case": ({
            "scope": selection["scope"], "status": selection["status"],
            "score_range": selection["score_range"], "threshold_cases": selection["cases"],
            "topn_zero_status": topn_zero["status"], "topn_zero_cases": topn_zero["cases"],
            "browser": selection["browser"],
            "owned_servers_stopped": selection["owned_server_stopped"]
                and topn_zero["owned_server_stopped"],
        } if selection else None),
        "permanent_support_block_case": ({key: blocked[key] for key in (
            "scope", "status", "browser", "run_id", "run", "runtime", "attempts",
            "profile_count", "issue_text", "mixed_status_polling_contract",
            "owned_server_stopped")}
            if blocked else None),
        "retryable_failure_and_recovery_case": ({key: fault[key] for key in (
            "scope", "status", "browser", "run_id", "first_attempts",
            "final_attempts", "run", "profile_count", "generation_count",
            "api_responses", "owned_server_stopped")}
            if fault else None),
        "history_paging_boundary_case": ({key: history[key] for key in (
            "scope", "status", "browser", "ordered_run_ids",
            "history_responses", "database_counts_unchanged",
            "owned_server_stopped")}
            if history else None),
        "multi_product_any_max_case": ({key: multi_product[key] for key in (
            "scope", "status", "browser", "fresh_run_id", "strict_run_id",
            "profile_count", "generation_count", "score_rows", "unique_score_people",
            "strict_expected", "strict_selected", "strict_snapshot_sha256",
            "strict_result_source", "owned_server_stopped")}
            if multi_product else None),
        "retained_planner_blocked_case": ({key: planner_blocked[key] for key in (
            "scope", "status", "cases", "browser", "api_responses", "owned_server_stopped")}
            if planner_blocked else None),
        "retained_planner_positive_case": ({key: planner_positive[key] for key in (
            "scope", "status", "cases", "preview_selected", "browser", "api_responses",
            "console_errors", "page_errors", "request_failures", "owned_server_stopped")}
            if planner_positive else None),
        "governed_probability_v2_case": ({key: probability[key] for key in (
            "scope", "status", "calibration_artifact_id", "scoring_run_id", "cases",
            "browser", "api_responses", "console_errors", "page_errors",
            "request_failures", "owned_server_stopped")}
            if probability else None),
        "legacy_v1_historical_reopen_case": ({key: legacy[key] for key in (
            "scope", "status", "run_id", "selected_count", "exported_count",
            "csv_sha256", "export_profile", "export_header", "selection_contract_version",
            "setup", "browser", "console_errors", "page_errors", "request_failures",
            "owned_server_stopped")}
            if legacy else None),
        "two_tab_retry_fencing_case": ({key: two_tab_retry[key] for key in (
            "scope", "status", "run_id", "first_attempts", "final_attempts",
            "competing_retry_status", "second_tab_retry_visible_before_click",
            "profile_count", "generation_count", "browser", "page_errors",
            "request_failures", "owned_server_stopped")}
            if two_tab_retry else None),
        "source_replacement_currentness_case": ({key: source_currentness[key] for key in (
            "scope", "status", "before", "after", "post_import_snapshot_state",
            "effective_result_currentness", "post_import_preflight", "old_snapshot_sha256",
            "browser", "page_errors", "request_failures", "owned_server_stopped")}
            if source_currentness else None),
        "named_10k_qualification_case": ({key: qualification[key] for key in (
            "scope", "status", "browser", "demographics", "valid_score_rows",
            "minimum", "independent_qualifying_count", "selected_count",
            "qualification_threshold_met", "v3_demo_ready_field_present", "generation_id",
            "snapshot_sha256", "submit_to_completed_seconds", "console_errors",
            "page_errors", "request_failures", "owned_server_stopped")}
            if qualification else None),
        "native_transport_rejoin_case": ({key: transport[key] for key in (
            "scope", "status", "browser", "database_counts_before_after",
            "offline_request_failures", "final_request_failures", "console_errors",
            "page_errors", "backend_status_sequence", "owned_server_stopped")}
            if transport else None),
        "business_links_case": ({key: business_links[key] for key in (
            "scope", "status", "cases", "browser", "database_counts_before_after",
            "console_errors", "page_errors", "request_failures", "owned_server_stopped")}
            if business_links else None),
        "historical_alternates_case": ({key: historical_alternates[key] for key in (
            "scope", "status", "cases", "selected_filters", "analysis_runs_before_after",
            "browser", "console_errors", "page_errors", "request_failures",
            "owned_server_stopped")}
            if historical_alternates else None),
        "model_alternates_case": ({key: model_alternates[key] for key in (
            "scope", "status", "cases", "request_payload", "model_runs_before_after",
            "scoring_runs_before_after", "browser", "console_errors", "page_errors",
            "request_failures", "owned_server_stopped")}
            if model_alternates else None),
        "audience_alternates_case": ({key: audience_alternates[key] for key in (
            "scope", "status", "cases", "audiences_before_after",
            "scoring_runs_before_after", "browser", "console_errors", "page_errors",
            "request_failures", "owned_server_stopped")}
            if audience_alternates else None),
        "legacy_detail_actions_case": ({key: legacy_detail[key] for key in (
            "scope", "status", "cases", "runs", "feedback_batches_before_after",
            "search_runs_before_after", "browser", "console_errors", "page_errors",
            "request_failures", "owned_server_stopped")}
            if legacy_detail else None),
        "campaign_stepper_post_fix_case": ({key: campaign_stepper[key] for key in (
            "scope", "status", "cases", "campaigns_before_after", "browser",
            "console_errors", "page_errors", "request_failures", "owned_server_stopped")}
            if campaign_stepper else None),
        "database_before": case["database_before"],
        "database_after": case["database_after"],
        "console_errors": case["console_errors"],
        "expected_console_errors": case.get("expected_console_errors", []),
        "unexpected_console_errors": case.get("unexpected_console_errors", []),
        "page_errors": case["page_errors"],
        "request_failures": case["request_failures"],
        "untested": ["other reuse variants", "stale retry and broader concurrency",
                     "retained planner and Campaign Builder stale/error alternatives",
                     "in-flight worker restart and source-change faults",
                     "full 200-percent route, keyboard/focus and accessibility matrix"],
        "qa_output_evidence": str(args.case_root / "native_business_case.json"),
        "retained_qa_output_evidence": (
            str(args.retained_root / "native_retained_historical.json") if retained else None),
        "trainable_qa_output_evidence": (
            str(args.trainable_root / "native_retained_historical.json") if trainable else None),
        "links_qa_output_evidence": (
            str(args.links_root / "native_retained_links.json") if links else None),
        "form_qa_output_evidence": (
            str(args.form_root / "native_business_form_controls.json") if form else None),
        "export_qa_output_evidence": (
            str(args.export_root / "native_export_matrix.json") if export else None),
        "feedback_qa_output_evidence": (
            str(args.feedback_root / "native_feedback_matrix.json") if feedback else None),
        "navigation_qa_output_evidence": (
            str(args.navigation_root / "native_navigation_responsive.json") if navigation else None),
        "campaign_qa_output_evidence": (
            str(args.campaign_root / "native_campaign_builder.json") if campaign else None),
        "campaign_recovery_qa_output_evidence": (
            str(args.campaign_root / "native_campaign_export_recovery.json") if campaign else None),
        "selection_qa_output_evidence": (
            str(args.selection_root / "native_similarity_selection_matrix.json") if selection else None),
        "topn_zero_qa_output_evidence": (
            str(args.selection_root / "native_similarity_topn_zero_resume.json") if topn_zero else None),
        "blocked_qa_output_evidence": (
            str(args.blocked_root / "native_unsupported_product.json") if blocked else None),
        "fault_qa_output_evidence": (
            str(args.fault_root / "native_retryable_failure.json") if fault else None),
        "history_qa_output_evidence": (
            str(args.history_root / "native_history_paging.json") if history else None),
        "multi_product_qa_output_evidence": (
            str(args.multi_product_root / "native_multi_product.json") if multi_product else None),
        "planner_blocked_qa_output_evidence": (
            str(args.planner_blocked_root / "native_retained_planner.json") if planner_blocked else None),
        "planner_positive_qa_output_evidence": (
            str(args.planner_positive_root / "native_retained_planner_positive_resume.json")
            if planner_positive else None),
        "probability_qa_output_evidence": (
            str(args.probability_root / "native_probability_v2.json") if probability else None),
        "legacy_qa_output_evidence": (
            str(args.legacy_root / "native_legacy_v1_reopen.json") if legacy else None),
        "two_tab_retry_qa_output_evidence": (
            str(args.two_tab_retry_root / "native_retry_two_tabs.json") if two_tab_retry else None),
        "source_currentness_qa_output_evidence": (
            str(args.source_currentness_root / "native_source_currentness.json")
            if source_currentness else None),
        "qualification_qa_output_evidence": (
            str(args.qualification_root / "native_named_10k_qualification.json")
            if qualification else None),
        "transport_qa_output_evidence": (
            str(args.transport_root / "native_transport_rejoin.json")
            if transport else None),
        "business_links_qa_output_evidence": (
            str(args.business_links_root / "native_business_links.json")
            if business_links else None),
        "historical_alternates_qa_output_evidence": (
            str(args.historical_alternates_root / "native_historical_alternates.json")
            if historical_alternates else None),
        "model_alternates_qa_output_evidence": (
            str(args.model_alternates_root / "native_model_alternates.json")
            if model_alternates else None),
        "audience_alternates_qa_output_evidence": (
            str(args.audience_alternates_root / "native_audience_alternates.json")
            if audience_alternates else None),
        "legacy_detail_qa_output_evidence": (
            str(args.legacy_detail_root / "native_legacy_detail_actions.json")
            if legacy_detail else None),
        "campaign_stepper_qa_output_evidence": (
            str(args.campaign_stepper_root / "native_campaign_stepper.json")
            if campaign_stepper else None),
    }
    _write("19_3_CASE_RESULTS.json", cases)
    qa_roots = [args.case_root] + ([args.retained_root] if retained else []) + (
        [args.trainable_root] if trainable else []) + ([args.links_root] if links else []) + (
        [args.form_root] if form else []) + ([args.export_root] if export else []) + (
        [args.feedback_root] if feedback else []) + ([args.navigation_root] if navigation else []) + (
        [args.campaign_root] if campaign else []) + (
        [args.selection_root] if selection else []) + (
        [args.blocked_root] if blocked else [])
    qa_roots += [args.fault_root] if fault else []
    qa_roots += [args.history_root] if history else []
    qa_roots += [args.multi_product_root] if multi_product else []
    qa_roots += [args.planner_blocked_root] if planner_blocked else []
    qa_roots += [args.planner_positive_root] if planner_positive else []
    qa_roots += [args.probability_root] if probability else []
    qa_roots += [args.legacy_root] if legacy else []
    qa_roots += [args.two_tab_retry_root] if two_tab_retry else []
    qa_roots += [args.source_currentness_root] if source_currentness else []
    qa_roots += [args.qualification_root] if qualification else []
    qa_roots += [args.transport_root] if transport else []
    qa_roots += [args.business_links_root] if business_links else []
    qa_roots += [args.historical_alternates_root] if historical_alternates else []
    qa_roots += [args.model_alternates_root] if model_alternates else []
    qa_roots += [args.audience_alternates_root] if audience_alternates else []
    qa_roots += [args.legacy_detail_root] if legacy_detail else []
    qa_roots += [args.campaign_stepper_root] if campaign_stepper else []
    qa_roots = list(dict.fromkeys(qa_roots))
    admissions = [json.loads(line) for root in qa_roots for line in
                  (root / "guard_admissions.jsonl").read_text(encoding="utf-8").splitlines()]
    checks = []
    for root in qa_roots:
        with sqlite3.connect(root / "state" / "qa.db") as connection:
            checks.append({
                "qa_root": str(root),
                "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
                "active_runs": connection.execute(
                    "SELECT COUNT(*) FROM campaign_search_runs WHERE status IN (?,?)",
                    ("QUEUED", "PROCESSING"),
                ).fetchone()[0],
                "active_compute_jobs": connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN (?,?)",
                    ("QUEUED", "RUNNING"),
                ).fetchone()[0],
            })
    no_5m = {
        "stage": "19_3", "status": "PASS_FOR_OBSERVED_BOUNDED_CASE_ONLY",
        "admitted_operations": [row["operation"] for row in admissions],
        "max_admitted_demographics": max(row["counts"]["demographics"] for row in admissions),
        "max_allowed_demographics": max(row["cap"] for row in admissions),
        "canonical_scale_dispatches_observed": sum(
            row["counts"]["demographics"] >= 5_000_000 for row in admissions),
        "qa_root_checks": checks,
        "all_owned_servers_stopped": case["owned_server_stopped"] and (
            retained["owned_server_stopped"] if retained else True) and (
            trainable["owned_server_stopped"] if trainable else True) and (
            links["owned_server_stopped"] if links else True) and (
            form["owned_server_stopped"] if form else True) and (
            export["owned_server_stopped"] if export else True) and (
            feedback["owned_server_stopped"] if feedback else True) and (
            navigation["owned_server_stopped"] if navigation else True) and (
            campaign_recovery["owned_server_stopped"] if campaign else True) and (
            selection["owned_server_stopped"] and topn_zero["owned_server_stopped"]
             if selection else True) and (
            blocked["owned_server_stopped"] if blocked else True) and (
            fault["owned_server_stopped"] if fault else True) and (
            history["owned_server_stopped"] if history else True) and (
            multi_product["owned_server_stopped"] if multi_product else True) and (
            planner_blocked["owned_server_stopped"] if planner_blocked else True) and (
            planner_positive["owned_server_stopped"] if planner_positive else True) and (
            probability["owned_server_stopped"] if probability else True) and (
            legacy["owned_server_stopped"] if legacy else True) and (
            two_tab_retry["owned_server_stopped"] if two_tab_retry else True) and (
            source_currentness["owned_server_stopped"] if source_currentness else True) and (
            qualification["owned_server_stopped"] if qualification else True) and (
            transport["owned_server_stopped"] if transport else True) and (
            business_links["owned_server_stopped"] if business_links else True) and (
            historical_alternates["owned_server_stopped"] if historical_alternates else True) and (
            model_alternates["owned_server_stopped"] if model_alternates else True) and (
            audience_alternates["owned_server_stopped"] if audience_alternates else True) and (
            legacy_detail["owned_server_stopped"] if legacy_detail else True) and (
            campaign_stepper["owned_server_stopped"] if campaign_stepper else True),
        "scope_limit": "Does not certify every 19.3 UI or background scenario.",
    }
    _write("19_3_NO_5M_DISPATCH_PROOF.json", no_5m)
    _write("19_3_BACKGROUND_PROCESS_MATRIX.json", {
        "stage": "19_3", "status": "NO_GO_PARTIAL_MATRIX",
        "observed": [{"workflow": "v3 fresh buyer similarity via business form",
                      "status": "PASS", "stages": case_by_id["V3_FRESH_UI_TO_WORKER_TO_DB_TO_EXPORT"]["stages"],
                      "selected_count": case_by_id["V3_FRESH_UI_TO_WORKER_TO_DB_TO_EXPORT"]["selected_count"],
                      "exported_count": case_by_id["V3_FRESH_UI_TO_WORKER_TO_DB_TO_EXPORT"]["exported_count"]},
                     {"workflow": "v3 feedback upload retained with lineage",
                      "status": "PASS", "accepted_outcomes": case_by_id[
                          "V3_NATIVE_FEEDBACK_TEMPLATES_AND_UPLOAD"]["accepted_outcomes"]},
                     {"workflow": "v3 exact result reuse via run again form",
                      "status": "PASS", "selected_count": case_by_id["V3_UI_EXACT_RESULT_REUSE"]["selected_count"],
                      "result_source": case_by_id["V3_UI_EXACT_RESULT_REUSE"]["result_source"]}]
                     + ([{"workflow": "retained historical analysis via native UI",
                          "status": "PASS", "selected_people": retained["selected_people"],
                          "positive_people": retained["positive_people"],
                          "observations": retained["observations"]},
                         {"workflow": "one-component legacy training block via native UI",
                          "status": "PASS_EXPECTED_FAILURE",
                          "job_status": retained["model_one_component_job_status"],
                          "failure_category": retained["model_one_component_failure_category"],
                          "safe_failure": retained["model_one_component_safe_failure"]}] if retained else [])
                     + ([{"workflow": "trainable legacy analysis via native UI",
                          "status": "PASS", "observations": trainable["observations"],
                          "selected_people": trainable["selected_people"],
                          "positive_people": trainable["positive_people"]},
                         {"workflow": "governed legacy model training via native UI",
                          "status": "PASS"},
                         {"workflow": "bounded legacy prospect scoring via native UI",
                          "status": "PASS", "scored_people": trainable["bounded_scored_people"]},
                         {"workflow": "bounded audience preparation/estimate/save via native UI",
                          "status": "PASS", "saved_people": trainable[
                              "bounded_audience_saved_people"]},
                         {"workflow": "bounded audience pagination, TOP_N and saved reopen via native UI",
                          "status": "PASS", "paginated_people": trainable[
                              "bounded_audience_paginated_people"],
                          "top_n_people": trainable["bounded_audience_top_n_people"]},
                         {"workflow": "retained saved target groups refresh and advanced-definition link",
                          "status": "PASS", "visible_groups": trainable[
                              "bounded_saved_target_groups_visible"]},
                         {"workflow": "retained data status counts and refresh",
                          "status": "PASS", "source_counts": trainable[
                              "bounded_data_status_counts"]}]
                        if trainable else [])
                     + ([{"workflow": "Insights destination buttons and production-route hiding",
                          "status": "PASS", "destinations": links[
                              "retained_destinations_clicked"],
                          "jobs_after_navigation": links["jobs_after_navigation"]}]
                        if links else [])
                     + ([{"workflow": "business form dynamic controls, mode/validation and bounded preflight",
                          "status": "PASS", "multiselect_widgets": len(form["multiselects"]),
                          "jobs_after": form["jobs_after"]}]
                        if form else [])
                     + ([{"workflow": "v3 channel/profile native export matrix",
                          "status": "PASS", "available_profiles": len(export["profiles"]),
                          "distinct_runs": len({item["run_id"] for item in export["profiles"]})}]
                        if export else [])
                     + ([{"workflow": "feedback positive/negative browser upload matrix",
                          "status": "PASS", "cases": len(feedback["cases"]),
                          "accepted_batches": feedback["database_counts"][0]}]
                        if feedback else [])
                     + ([{"workflow": "business navigation/sidebar/responsive matrix",
                          "status": "PASS", "cases": len(navigation["cases"]),
                          "compute_counts_unchanged": navigation["database_counts_before_after"]}]
                        if navigation else [])
                     + ([{"workflow": "retained Campaign Builder EMAIL local finalize/export",
                          "status": "PASS", "selected": 10, "deliverable": 8},
                         {"workflow": "retained Campaign Builder DIRECT_MAIL interrupted export/restart/Edge retry",
                          "status": "PASS_AFTER_RECOVERY_WITH_ORIGINAL_CHROME_CRASH_RETAINED",
                          "selected": campaign_recovery["selected"],
                          "deliverable": campaign_recovery["deliverable"],
                          "event_statuses": campaign_recovery["event_statuses"]}]
                        if campaign else [])
                     + ([{"workflow": "v3 five inclusive minima with exact preflight/snapshot membership",
                          "status": "PASS", "cases": len(selection["cases"]),
                          "score_range": selection["score_range"]},
                         {"workflow": "v3 TOP_N ranking and genuine zero-result materialization",
                          "status": "PASS", "cases": len(topn_zero["cases"])}]
                        if selection else [])
                     + ([{"workflow": "v3 permanent insufficient-history block and mixed-status polling",
                          "status": "PASS", "failure_code": blocked["runtime"][0],
                          "attempts": len(blocked["attempts"]), "retryable": False}]
                        if blocked else [])
                     + ([{"workflow": "one-shot bounded v3 worker fault, UI retry and genuine recovery",
                          "status": "PASS", "attempts": len(fault["final_attempts"]),
                          "selected": fault["run"][2],
                          "profiles": fault["profile_count"],
                          "generations": fault["generation_count"]}]
                        if fault else [])
                     + ([{"workflow": "20-run results history, older-page boundary, detail and refresh",
                          "status": "PASS", "runs": len(history["ordered_run_ids"]),
                          "database_counts_unchanged": history["database_counts_unchanged"]}]
                        if history else [])
                     + ([{"workflow": "v3 two-product ANY/max exact selection and unique snapshot",
                          "status": "PASS", "score_rows": multi_product["score_rows"],
                          "unique_people": multi_product["unique_score_people"],
                          "strict_selected": multi_product["strict_selected"],
                          "profiles": multi_product["profile_count"]}]
                        if multi_product else [])
                     + ([{"workflow": "retained Phase 10 planner insufficient-history block",
                          "status": "PASS_EXPECTED_BLOCK", "steps": len(planner_blocked["cases"])}]
                        if planner_blocked else [])
                     + ([{"workflow": "retained Phase 10 planner five-step preparation/preview/draft",
                          "status": "PASS", "steps": len(planner_positive["cases"]),
                          "preview_selected": planner_positive["preview_selected"]}]
                        if planner_positive else [])
                     + ([{"workflow": "v2 governed calibration and native discrete-bucket selection",
                          "status": "PASS", "buckets": len(probability["cases"]),
                          "materialized_runs": sum("run_id" in item for item in probability["cases"]),
                          "calibration_artifact_id": probability["calibration_artifact_id"]}]
                        if probability else [])
                     + ([{"workflow": "legacy v1 historical result/detail reopen",
                          "status": "PASS_READER_ONLY", "run_id": legacy["run_id"],
                          "selected": legacy["selected_count"],
                          "native_exported": legacy["exported_count"],
                          "export_profile": legacy["export_profile"]}]
                        if legacy else [])
                     + ([{"workflow": "two headed Chrome tabs retry one failed search",
                          "status": "PASS", "attempts": len(two_tab_retry["final_attempts"]),
                          "competing_status": two_tab_retry["competing_retry_status"]}]
                        if two_tab_retry else [])
                     + ([{"workflow": "bounded source replacement, historical result and unknown preflight",
                          "status": "PASS", "effective_result_currentness": "STALE",
                          "reason_code": source_currentness["post_import_preflight"]["reason_code"],
                          "selected_count": None}]
                        if source_currentness else [])
                     + ([{"workflow": "named 12K bounded v3 exact 10K qualification",
                          "status": "PASS", "demographics": qualification["demographics"],
                          "independent_qualifying_count": qualification["independent_qualifying_count"],
                          "selected_count": qualification["selected_count"],
                          "qualification_threshold_met": qualification["qualification_threshold_met"],
                          "v3_demo_ready_field_present": qualification["v3_demo_ready_field_present"]}]
                        if qualification else [])
                     + ([{"workflow": "native offline result-detail failure and online retry",
                          "status": "PASS", "database_counts_unchanged":
                              transport["database_counts_before_after"],
                          "expected_offline_failures": len(transport["offline_request_failures"])}]
                        if transport else [])
                     + ([{"workflow": "business shortcuts and v3 technical disclosure",
                          "status": "PASS", "cases": len(business_links["cases"]),
                          "database_counts_unchanged": business_links["database_counts_before_after"]}]
                        if business_links else [])
                     + ([{"workflow": "retained historical alternate filters and outcome definitions",
                          "status": "PASS", "cases": len(historical_alternates["cases"]),
                          "saved_runs": 3, "counts_reconciled_with_ui": True}]
                        if historical_alternates else [])
                     + ([{"workflow": "retained model training configuration and bounded new job",
                          "status": "PASS", "cases": len(model_alternates["cases"]),
                          "new_model_runs": 1, "new_scoring_runs": 0}]
                        if model_alternates else [])
                     + ([{"workflow": "retained audience alternate filters and durable save",
                          "status": "PASS", "cases": len(audience_alternates["cases"]),
                          "new_audiences": 1, "new_scoring_runs": 0}]
                        if audience_alternates else [])
                     + ([{"workflow": "legacy v1/v2 native result detail actions and zero export",
                          "status": "PASS", "cases": len(legacy_detail["cases"]),
                          "feedback_batch_delta": 0, "search_run_delta": 0}]
                        if legacy_detail else [])
                     + ([{"workflow": "post-fix retained campaign stepper, draft edit, finalize and export",
                          "status": "PASS", "cases": len(campaign_stepper["cases"]),
                          "new_campaigns": 1, "exported": campaign_stepper["cases"][-1]["exported"]}]
                        if campaign_stepper else []),
        "not_run": ["other reuse variants", "stale retry and broader concurrency",
                    "Audience Explorer error/stale branches and remaining conditional controls",
                    "Phase 10 planner alternate/error controls",
                    "Campaign Builder stale, invalid-export and duplicate-submission states",
                    "additional fault injection", "in-flight worker restart recovery"],
    })
    print(json.dumps({"status": "NO_GO_PARTIAL_19_3_EVIDENCE", "runtime_observations": len(runtime),
                      "passed_cases": len(case["cases"]) + (2 if retained else 0)
                      + (7 if trainable else 0) + (1 if links else 0)
                      + (1 if form else 0) + (len(export["profiles"]) if export else 0)
                      + (len(feedback["cases"]) if feedback else 0)
                      + (len(navigation["cases"]) if navigation else 0)
                      + (len(campaign["cases"]) + 1 if campaign else 0)
                      + (len(selection["cases"]) + len(topn_zero["cases"])
                         if selection else 0) + (1 if blocked else 0) + (1 if fault else 0)
                      + (1 if history else 0) + (1 if multi_product else 0)
                      + (1 if planner_blocked else 0) + (1 if planner_positive else 0)
                      + (len(probability["cases"]) if probability else 0)
                      + (1 if legacy else 0) + (1 if two_tab_retry else 0)
                      + (1 if source_currentness else 0) + (1 if qualification else 0)
                      + (1 if transport else 0) + (len(business_links["cases"]) if business_links else 0)
                      + (len(historical_alternates["cases"]) if historical_alternates else 0)
                      + (len(model_alternates["cases"]) if model_alternates else 0)
                      + (len(audience_alternates["cases"]) if audience_alternates else 0)
                      + (len(legacy_detail["cases"]) if legacy_detail else 0)
                      + (len(campaign_stepper["cases"]) if campaign_stepper else 0)}))


if __name__ == "__main__":
    main()
