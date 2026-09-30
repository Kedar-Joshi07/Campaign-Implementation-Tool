"""Idempotent SQLite schema creation and inspection."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import APP_VERSION, DATABASE_PATH
from app.database.connection import get_connection
from app.database.phase11_schema import (
    CAMPAIGN_SEARCH_RUN_COLUMNS,
    CAMPAIGN_RESULT_SNAPSHOT_COLUMNS as CAMPAIGN_RESULT_SNAPSHOT_COLUMNS,
    CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS as CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS,
    PHASE_ELEVEN_CREATE_TABLE_STATEMENTS,
    PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS,
    CAMPAIGN_SEARCH_RUN_RUNTIME_COLUMNS as CAMPAIGN_SEARCH_RUN_RUNTIME_COLUMNS,
    PHASE_ELEVEN_RUNTIME_CREATE_TABLE_STATEMENT,
    PHASE_ELEVEN_RUNTIME_INDEX_STATEMENTS,
    PHASE_ELEVEN_RUNTIME_TRIGGER_STATEMENTS,
    PHASE_ELEVEN_TRIGGER_STATEMENTS,
)
from app.database.phase11_feedback_schema import (
    CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS as CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS,
    PHASE_ELEVEN_FEEDBACK_CREATE_TABLE_STATEMENT,
    PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS,
    PHASE_ELEVEN_FEEDBACK_TRIGGER_STATEMENTS,
)
from app.database.search_recovery_schema import (
    SEARCH_RECOVERY_INDEX_STATEMENTS,
    SEARCH_RECOVERY_TABLE_STATEMENTS,
)


logger = logging.getLogger(__name__)
PHASE_ONE_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 30
SCHEMA_VERSION = str(CURRENT_SCHEMA_VERSION)

EXPECTED_TABLES = (
    "app_metadata",
    "data_import_runs",
    "customers",
    "campaign_sales",
    "demographics",
    "historical_analysis_runs",
    "model_runs",
    "jobs",
    "scoring_runs",
    "propensity_scores",
    "audience_rank_boundaries",
    "saved_audiences",
    "audience_analytics_snapshots",
    "campaigns",
    "campaign_export_events",
    "campaign_targeting_contexts",
    "phase9_saved_target_groups",
    "phase10_intelligence_generations",
    "phase10_orchestration_runs",
    "phase10_context_bindings",
    "campaign_search_runs",
    "campaign_result_snapshots",
    "campaign_result_export_events",
    "campaign_search_future_lineage",
    "campaign_search_run_runtime",
    "campaign_search_attempts",
    "campaign_search_progress_events",
    "targeting_option_catalogs",
    "targeting_product_catalog",
    "score_calibration_artifacts",
    "calibrated_propensity_scores",
    "calibration_score_stage",
    "calibration_distribution_bins",
    "intelligence_verification_attestations",
    "search_preflight_cache",
    "campaign_feedback_batches",
    "campaign_feedback_outcomes",
    "feedback_retraining_decisions",
)

HISTORICAL_ANALYSIS_RUN_COLUMNS = (
    "analysis_run_id",
    "analysis_name",
    "created_at",
    "completed_at",
    "status",
    "conversion_definition",
    "filters_json",
    "results_json",
    "customer_import_id",
    "customer_source_checksum",
    "campaign_sales_import_id",
    "campaign_sales_source_checksum",
    "observation_count",
    "selected_customer_count",
    "positive_customer_count",
    "unlabeled_customer_count",
    "positive_customer_rate",
    "error_message",
)

MODEL_RUN_COLUMNS = (
    "model_run_id",
    "analysis_run_id",
    "model_name",
    "created_at",
    "completed_at",
    "status",
    "algorithm",
    "selected_candidate",
    "random_seed",
    "validation_fraction",
    "reconstructed_observation_count",
    "selected_customer_count",
    "positive_customer_count",
    "unlabeled_customer_count",
    "train_customer_count",
    "validation_customer_count",
    "train_positive_count",
    "validation_positive_count",
    "feature_contract_json",
    "preprocessing_json",
    "hyperparameters_json",
    "metrics_json",
    "library_versions_json",
    "artifact_path",
    "artifact_sha256",
    "error_message",
    "split_lineage_json",
)

JOB_COLUMNS = (
    "job_id",
    "job_type",
    "status",
    "progress_percent",
    "stage",
    "message",
    "analysis_run_id",
    "model_run_id",
    "created_at",
    "started_at",
    "finished_at",
    "request_json",
    "result_json",
    "error_message",
)

SCORING_RUN_COLUMNS = (
    "scoring_run_id",
    "job_id",
    "model_run_id",
    "created_at",
    "completed_at",
    "status",
    "demographic_snapshot_count",
    "demographic_min_person_id",
    "demographic_max_person_id",
    "scored_person_count",
    "chunk_size",
    "last_person_id",
    "selected_candidate",
    "model_role_policy_version",
    "feature_contract_version",
    "feature_contract_sha256",
    "artifact_sha256",
    "score_min",
    "score_max",
    "score_mean",
    "score_summary_json",
    "error_message",
)

PROPENSITY_SCORE_COLUMNS = (
    "scoring_run_id",
    "model_run_id",
    "person_id",
    "propensity_score",
)

AUDIENCE_RANK_BOUNDARY_COLUMNS = (
    "scoring_run_id",
    "percentile_bucket",
    "boundary_rank",
    "boundary_score",
    "boundary_person_id",
    "total_population",
    "rank_contract_version",
    "created_at",
)

SAVED_AUDIENCE_COLUMNS = (
    "audience_id",
    "audience_name",
    "description",
    "created_at",
    "scoring_run_id",
    "model_run_id",
    "analysis_run_id",
    "selection_mode",
    "target_count",
    "resolved_count",
    "filter_contract_version",
    "rank_contract_version",
    "selection_contract_version",
    "filters_json",
    "selection_json",
    "profile_summary_json",
    "customer_import_id",
    "customer_source_checksum",
    "campaign_sales_import_id",
    "campaign_sales_source_checksum",
    "demographic_import_id",
    "demographic_source_checksum",
    "feature_contract_version",
    "feature_contract_sha256",
    "artifact_sha256",
)

AUDIENCE_ANALYTICS_SNAPSHOT_COLUMNS = (
    "scoring_run_id",
    "analytics_contract_version",
    "model_run_id",
    "analysis_run_id",
    "customer_import_id",
    "customer_source_checksum",
    "campaign_sales_import_id",
    "campaign_sales_source_checksum",
    "demographic_import_id",
    "demographic_source_checksum",
    "feature_contract_version",
    "feature_contract_sha256",
    "artifact_sha256",
    "filter_contract_version",
    "rank_contract_version",
    "selection_contract_version",
    "population_count",
    "options_json",
    "universe_profile_json",
    "historical_positive_profile_json",
    "score_bucket_stats_json",
    "created_at",
)

CAMPAIGN_COLUMNS = (
    "campaign_id",
    "campaign_contract_version",
    "campaign_name",
    "description",
    "channel",
    "planned_launch_date",
    "saved_audience_id",
    "scoring_run_id",
    "model_run_id",
    "analysis_run_id",
    "saved_audience_filter_hash",
    "saved_audience_selection_json",
    "saved_audience_resolved_count",
    "filter_contract_version",
    "rank_contract_version",
    "selection_contract_version",
    "analytics_contract_version",
    "member_resolution_contract_version",
    "export_contract_version",
    "status",
    "created_at",
    "updated_at",
    "finalized_at",
)

CAMPAIGN_EXPORT_EVENT_COLUMNS = (
    "export_event_id",
    "campaign_id",
    "export_contract_version",
    "export_profile",
    "status",
    "selected_count",
    "deliverable_count",
    "undeliverable_count",
    "row_count",
    "csv_sha256",
    "started_at",
    "completed_at",
    "safe_error_message",
    "export_snapshot_contract_version",
    "start_provenance_sha256",
    "source_changed_during_export",
    "completion_currentness_state",
)

CAMPAIGN_TARGETING_CONTEXT_COLUMNS = (
    "targeting_context_id",
    "campaign_id",
    "campaign_targeting_context_contract_version",
    "targeting_segment_contract_version",
    "business_match_strength_contract_version",
    "campaign_context_json",
    "campaign_context_sha256",
    "targeting_criteria_json",
    "targeting_criteria_sha256",
    "source_scoring_run_id",
    "created_at",
    "updated_at",
)

PHASE9_SAVED_TARGET_GROUP_COLUMNS = (
    "audience_id",
    "targeting_context_id",
    "target_group_contract_version",
    "filter_branches_json",
    "filter_branches_sha256",
    "campaign_context_contract_version",
    "campaign_context_json",
    "campaign_context_sha256",
    "targeting_segment_contract_version",
    "business_match_strength_contract_version",
    "targeting_criteria_json",
    "targeting_criteria_sha256",
    "source_scoring_run_id",
    "source_status",
    "resolved_count",
    "created_at",
)

PHASE10_INTELLIGENCE_GENERATION_COLUMNS = (
    "generation_id",
    "intelligence_generation_contract_version",
    "compatibility_contract_version",
    "intelligence_key_sha256",
    "modeling_context_json",
    "modeling_context_sha256",
    "historical_filters_json",
    "historical_filters_sha256",
    "historical_window_policy_version",
    "multi_product_positive_policy_version",
    "training_eligibility_policy_version",
    "customer_import_id",
    "customer_source_checksum",
    "campaign_sales_import_id",
    "campaign_sales_source_checksum",
    "demographic_import_id",
    "demographic_source_checksum",
    "feature_contract_version",
    "feature_contract_sha256",
    "model_role_policy_version",
    "evaluation_contract_version",
    "automated_training_policy_version",
    "analysis_run_id",
    "model_run_id",
    "scoring_run_id",
    "artifact_sha256",
    "score_semantics_json",
    "score_semantics_sha256",
    "rank_contract_version",
    "analytics_contract_version",
    "lifecycle_policy_version",
    "generation_status",
    "lifecycle_state",
    "created_at",
    "last_verified_at",
    "last_used_at",
)

PHASE10_ORCHESTRATION_RUN_COLUMNS = (
    "orchestration_id",
    "orchestration_contract_version",
    "targeting_context_id",
    "modeling_context_sha256",
    "intelligence_key_sha256",
    "status",
    "stage",
    "progress_percent",
    "business_message",
    "technical_message",
    "reuse_plan_json",
    "analysis_run_id",
    "model_run_id",
    "scoring_run_id",
    "generation_id",
    "training_job_id",
    "scoring_job_id",
    "created_at",
    "started_at",
    "updated_at",
    "completed_at",
    "safe_error_message",
    "failure_code",
    "failure_category",
    "retryable",
)

PHASE10_CONTEXT_BINDING_COLUMNS = (
    "targeting_context_id",
    "modeling_context_sha256",
    "orchestration_id",
    "generation_id",
    "binding_status",
    "created_at",
    "updated_at",
    "last_used_at",
)

CUSTOMER_COLUMNS = (
    "customer_id",
    "first_name",
    "last_name",
    "gender",
    "date_of_birth",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "state",
    "country",
    "phone_number",
    "email",
    "individual_yearly_income",
    "family_member_count",
    "resident_status",
    "resident_type",
    "education",
    "employment_status",
    "type_of_employment",
    "marital_status",
)

CAMPAIGN_SALES_COLUMNS = (
    "campaign_sales_id",
    "customer_id",
    "campaign_id",
    "product_id",
    "order_id",
    "campaign_name",
    "campaign_type",
    "campaign_channel",
    "campaign_start_date",
    "campaign_end_date",
    "campaign_category",
    "offer_type",
    "offer_value",
    "creative_id",
    "target_segment",
    "product_name",
    "product_category",
    "product_subcategory",
    "product_price",
    "product_cost",
    "product_tier",
    "product_launch_date",
    "contact_date",
    "contacted_flag",
    "delivery_status",
    "engagement_flag",
    "engagement_type",
    "response_flag",
    "purchase_flag",
    "purchase_date",
    "quantity",
    "gross_sales_amount",
    "discount_amount",
    "net_sales_amount",
    "gross_margin_amount",
    "days_to_purchase",
    "campaign_attributed_sale_flag",
    "pu_label",
)

DEMOGRAPHIC_COLUMNS = (
    "person_id",
    "first_name",
    "last_name",
    "gender",
    "age",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "state",
    "country",
    "phone_number",
    "email",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "ethnicity",
    "type_of_employment",
    "occupation_industry",
    "family_yearly_income",
    "religion",
    "email_contactable",
    "direct_mail_contactable",
    "sms_opt_in",
    "whatsapp_opt_in",
    "telemarketing_contactable",
    "do_not_call",
    "push_token",
    "push_opt_in",
    "advertising_id",
    "advertising_targetable",
    "web_visitor_id",
    "onsite_targetable",
)

CREATE_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_metadata (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_import_runs (
        import_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
        rows_read INTEGER NOT NULL DEFAULT 0 CHECK (rows_read >= 0),
        rows_inserted INTEGER NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
        rows_rejected INTEGER NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
        error_message TEXT,
        source_checksum TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT NOT NULL PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        date_of_birth TEXT NOT NULL,
        address_line_1 TEXT,
        address_line_2 TEXT,
        street TEXT,
        postal_code TEXT,
        city TEXT,
        state TEXT NOT NULL,
        country TEXT,
        phone_number TEXT,
        email TEXT,
        individual_yearly_income REAL NOT NULL CHECK (individual_yearly_income >= 0),
        family_member_count INTEGER NOT NULL CHECK (family_member_count >= 1),
        resident_status TEXT,
        resident_type TEXT,
        education TEXT,
        employment_status TEXT,
        type_of_employment TEXT,
        marital_status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_sales (
        campaign_sales_id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        campaign_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        order_id TEXT,
        campaign_name TEXT,
        campaign_type TEXT,
        campaign_channel TEXT,
        campaign_start_date TEXT NOT NULL,
        campaign_end_date TEXT NOT NULL,
        campaign_category TEXT,
        offer_type TEXT,
        offer_value REAL,
        creative_id TEXT,
        target_segment TEXT,
        product_name TEXT,
        product_category TEXT,
        product_subcategory TEXT,
        product_price REAL,
        product_cost REAL,
        product_tier TEXT,
        product_launch_date TEXT,
        contact_date TEXT NOT NULL,
        contacted_flag INTEGER NOT NULL CHECK (contacted_flag IN (0, 1)),
        delivery_status TEXT,
        engagement_flag INTEGER NOT NULL CHECK (engagement_flag IN (0, 1)),
        engagement_type TEXT,
        response_flag INTEGER NOT NULL CHECK (response_flag IN (0, 1)),
        purchase_flag INTEGER NOT NULL CHECK (purchase_flag IN (0, 1)),
        purchase_date TEXT,
        quantity INTEGER CHECK (quantity IS NULL OR quantity >= 0),
        gross_sales_amount REAL,
        discount_amount REAL,
        net_sales_amount REAL,
        gross_margin_amount REAL,
        days_to_purchase INTEGER CHECK (days_to_purchase IS NULL OR days_to_purchase >= 0),
        campaign_attributed_sale_flag INTEGER NOT NULL
            CHECK (campaign_attributed_sale_flag IN (0, 1)),
        pu_label INTEGER NOT NULL CHECK (pu_label IN (0, 1)),
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demographics (
        person_id TEXT NOT NULL PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
        address_line_1 TEXT,
        address_line_2 TEXT,
        street TEXT,
        postal_code TEXT,
        city TEXT,
        state TEXT NOT NULL,
        country TEXT,
        phone_number TEXT,
        email TEXT,
        individual_yearly_income REAL NOT NULL CHECK (individual_yearly_income >= 0),
        marital_status TEXT,
        education TEXT,
        employment_status TEXT,
        resident_status TEXT,
        resident_type TEXT,
        family_member_count INTEGER NOT NULL CHECK (family_member_count >= 1),
        number_of_children_in_family INTEGER NOT NULL
            CHECK (number_of_children_in_family >= 0),
        number_of_adults_in_family INTEGER NOT NULL
            CHECK (number_of_adults_in_family >= 0),
        ethnicity TEXT,
        type_of_employment TEXT,
        occupation_industry TEXT,
        family_yearly_income REAL NOT NULL CHECK (family_yearly_income >= 0),
        religion TEXT,
        email_contactable INTEGER NOT NULL DEFAULT 0
            CHECK (email_contactable IN (0, 1)),
        direct_mail_contactable INTEGER NOT NULL DEFAULT 0
            CHECK (direct_mail_contactable IN (0, 1)),
        sms_opt_in INTEGER NOT NULL DEFAULT 0 CHECK (sms_opt_in IN (0, 1)),
        whatsapp_opt_in INTEGER NOT NULL DEFAULT 0
            CHECK (whatsapp_opt_in IN (0, 1)),
        telemarketing_contactable INTEGER NOT NULL DEFAULT 0
            CHECK (telemarketing_contactable IN (0, 1)),
        do_not_call INTEGER NOT NULL DEFAULT 0 CHECK (do_not_call IN (0, 1)),
        push_token TEXT,
        push_opt_in INTEGER NOT NULL DEFAULT 0 CHECK (push_opt_in IN (0, 1)),
        advertising_id TEXT,
        advertising_targetable INTEGER NOT NULL DEFAULT 0
            CHECK (advertising_targetable IN (0, 1)),
        web_visitor_id TEXT,
        onsite_targetable INTEGER NOT NULL DEFAULT 0
            CHECK (onsite_targetable IN (0, 1))
    )
    """,
)

PHASE_ONE_REQUIRED_INDEX_STATEMENTS = {
    "idx_customers_state": "CREATE INDEX IF NOT EXISTS idx_customers_state ON customers (state)",
    "idx_customers_date_of_birth": (
        "CREATE INDEX IF NOT EXISTS idx_customers_date_of_birth ON customers (date_of_birth)"
    ),
    "idx_customers_individual_yearly_income": (
        "CREATE INDEX IF NOT EXISTS idx_customers_individual_yearly_income "
        "ON customers (individual_yearly_income)"
    ),
    "idx_campaign_sales_customer_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_customer_id ON campaign_sales (customer_id)"
    ),
    "idx_campaign_sales_campaign_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_id ON campaign_sales (campaign_id)"
    ),
    "idx_campaign_sales_product_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_product_id ON campaign_sales (product_id)"
    ),
    "idx_campaign_sales_contact_date": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_contact_date ON campaign_sales (contact_date)"
    ),
    "idx_campaign_sales_purchase_flag": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_purchase_flag ON campaign_sales (purchase_flag)"
    ),
    "idx_campaign_sales_pu_label": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_pu_label ON campaign_sales (pu_label)"
    ),
    "idx_campaign_sales_campaign_product_pu": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_product_pu "
        "ON campaign_sales (campaign_id, product_id, pu_label)"
    ),
    "idx_demographics_state": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_state ON demographics (state)"
    ),
    "idx_demographics_age": "CREATE INDEX IF NOT EXISTS idx_demographics_age ON demographics (age)",
    "idx_demographics_individual_yearly_income": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_individual_yearly_income "
        "ON demographics (individual_yearly_income)"
    ),
    "idx_demographics_education": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_education ON demographics (education)"
    ),
    "idx_demographics_employment_status": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_employment_status "
        "ON demographics (employment_status)"
    ),
    "idx_demographics_resident_status": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_resident_status "
        "ON demographics (resident_status)"
    ),
    "idx_demographics_type_of_employment": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_type_of_employment "
        "ON demographics (type_of_employment)"
    ),
}

PHASE_TWO_REQUIRED_INDEX_STATEMENTS = {
    "idx_historical_analysis_runs_newest": (
        "CREATE INDEX IF NOT EXISTS idx_historical_analysis_runs_newest "
        "ON historical_analysis_runs (created_at DESC, analysis_run_id DESC)"
    ),
    "idx_campaign_sales_campaign_channel": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_channel "
        "ON campaign_sales (campaign_channel)"
    ),
    "idx_campaign_sales_product_category": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_product_category "
        "ON campaign_sales (product_category)"
    ),
    "idx_campaign_sales_campaign_type": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_type "
        "ON campaign_sales (campaign_type)"
    ),
}

PHASE_THREE_REQUIRED_INDEX_STATEMENTS = {
    "idx_model_runs_newest": (
        "CREATE INDEX IF NOT EXISTS idx_model_runs_newest "
        "ON model_runs (created_at DESC, model_run_id DESC)"
    ),
    "idx_model_runs_analysis_run_id": (
        "CREATE INDEX IF NOT EXISTS idx_model_runs_analysis_run_id "
        "ON model_runs (analysis_run_id)"
    ),
}

PHASE_FOUR_REQUIRED_INDEX_STATEMENTS = {
    "idx_jobs_newest": (
        "CREATE INDEX IF NOT EXISTS idx_jobs_newest "
        "ON jobs (created_at DESC, job_id DESC)"
    ),
    "idx_jobs_status": (
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)"
    ),
    "idx_jobs_analysis_run_id": (
        "CREATE INDEX IF NOT EXISTS idx_jobs_analysis_run_id ON jobs (analysis_run_id)"
    ),
    "idx_jobs_model_run_id": (
        "CREATE INDEX IF NOT EXISTS idx_jobs_model_run_id ON jobs (model_run_id)"
    ),
}

PHASE_FIVE_REQUIRED_INDEX_STATEMENTS = {
    "idx_scoring_runs_newest": (
        "CREATE INDEX IF NOT EXISTS idx_scoring_runs_newest "
        "ON scoring_runs (created_at DESC, scoring_run_id DESC)"
    ),
    "idx_scoring_runs_model_newest": (
        "CREATE INDEX IF NOT EXISTS idx_scoring_runs_model_newest "
        "ON scoring_runs (model_run_id, created_at DESC, scoring_run_id DESC)"
    ),
    "idx_scoring_runs_status": (
        "CREATE INDEX IF NOT EXISTS idx_scoring_runs_status "
        "ON scoring_runs (status, created_at DESC, scoring_run_id DESC)"
    ),
    "idx_scoring_runs_completed_model_newest": (
        "CREATE INDEX IF NOT EXISTS idx_scoring_runs_completed_model_newest "
        "ON scoring_runs (model_run_id, completed_at DESC, scoring_run_id DESC) "
        "WHERE status = 'COMPLETED'"
    ),
    "idx_propensity_scores_run_score_person": (
        "CREATE INDEX IF NOT EXISTS idx_propensity_scores_run_score_person "
        "ON propensity_scores (scoring_run_id, propensity_score DESC, person_id ASC)"
    ),
}

PHASE_SIX_REQUIRED_INDEX_STATEMENTS = {
    "idx_audience_rank_boundaries_scoring_bucket": (
        "CREATE INDEX IF NOT EXISTS idx_audience_rank_boundaries_scoring_bucket "
        "ON audience_rank_boundaries (scoring_run_id, percentile_bucket)"
    ),
    "idx_saved_audiences_newest": (
        "CREATE INDEX IF NOT EXISTS idx_saved_audiences_newest "
        "ON saved_audiences (created_at DESC, audience_id DESC)"
    ),
    "idx_saved_audiences_scoring_run_id": (
        "CREATE INDEX IF NOT EXISTS idx_saved_audiences_scoring_run_id "
        "ON saved_audiences (scoring_run_id, created_at DESC, audience_id DESC)"
    ),
    "idx_saved_audiences_model_run_id": (
        "CREATE INDEX IF NOT EXISTS idx_saved_audiences_model_run_id "
        "ON saved_audiences (model_run_id, created_at DESC, audience_id DESC)"
    ),
}

PHASE_SEVEN_REQUIRED_INDEX_STATEMENTS = {
    "idx_campaigns_newest": (
        "CREATE INDEX IF NOT EXISTS idx_campaigns_newest "
        "ON campaigns (created_at DESC, campaign_id DESC)"
    ),
    "idx_campaigns_status_newest": (
        "CREATE INDEX IF NOT EXISTS idx_campaigns_status_newest "
        "ON campaigns (status, created_at DESC, campaign_id DESC)"
    ),
    "idx_campaigns_saved_audience": (
        "CREATE INDEX IF NOT EXISTS idx_campaigns_saved_audience "
        "ON campaigns (saved_audience_id, created_at DESC, campaign_id DESC)"
    ),
    "idx_campaign_export_events_campaign_started": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_export_events_campaign_started "
        "ON campaign_export_events (campaign_id, started_at DESC, export_event_id DESC)"
    ),
    "idx_campaign_export_events_status_started": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_export_events_status_started "
        "ON campaign_export_events (status, started_at DESC, export_event_id DESC)"
    ),
}

PHASE_NINE_CONTEXT_REQUIRED_INDEX_STATEMENTS = {
    "idx_campaign_targeting_contexts_updated": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_targeting_contexts_updated "
        "ON campaign_targeting_contexts (updated_at DESC, targeting_context_id DESC)"
    ),
    "idx_campaign_targeting_contexts_source_scoring": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_targeting_contexts_source_scoring "
        "ON campaign_targeting_contexts (source_scoring_run_id, updated_at DESC) "
        "WHERE source_scoring_run_id IS NOT NULL"
    ),
}

PHASE_NINE_REQUIRED_INDEX_STATEMENTS = {
    **PHASE_NINE_CONTEXT_REQUIRED_INDEX_STATEMENTS,
    "idx_phase9_saved_target_groups_context": (
        "CREATE INDEX IF NOT EXISTS idx_phase9_saved_target_groups_context "
        "ON phase9_saved_target_groups (targeting_context_id, created_at DESC, audience_id DESC)"
    ),
}

PHASE_TEN_REQUIRED_INDEX_STATEMENTS = {
    "idx_phase10_generations_modeling_context": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_modeling_context "
        "ON phase10_intelligence_generations "
        "(modeling_context_sha256, created_at DESC, generation_id DESC)"
    ),
    "idx_phase10_generations_intelligence_key": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_intelligence_key "
        "ON phase10_intelligence_generations (intelligence_key_sha256)"
    ),
    "idx_phase10_generations_lifecycle": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_lifecycle "
        "ON phase10_intelligence_generations "
        "(lifecycle_state, last_used_at DESC, generation_id DESC)"
    ),
    "idx_phase10_generations_analysis": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_analysis "
        "ON phase10_intelligence_generations (analysis_run_id, generation_id DESC)"
    ),
    "idx_phase10_generations_model": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_model "
        "ON phase10_intelligence_generations (model_run_id, generation_id DESC)"
    ),
    "idx_phase10_generations_scoring": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_generations_scoring "
        "ON phase10_intelligence_generations (scoring_run_id, generation_id DESC)"
    ),
    "idx_phase10_orchestrations_modeling_context": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_orchestrations_modeling_context "
        "ON phase10_orchestration_runs "
        "(modeling_context_sha256, updated_at DESC, orchestration_id DESC)"
    ),
    "idx_phase10_orchestrations_intelligence_key": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_orchestrations_intelligence_key "
        "ON phase10_orchestration_runs "
        "(intelligence_key_sha256, updated_at DESC, orchestration_id DESC)"
    ),
    "idx_phase10_orchestrations_active_key": (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_phase10_orchestrations_active_key "
        "ON phase10_orchestration_runs (intelligence_key_sha256) "
        "WHERE status IN ('QUEUED', 'RUNNING')"
    ),
    "idx_phase10_orchestrations_targeting_context": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_orchestrations_targeting_context "
        "ON phase10_orchestration_runs "
        "(targeting_context_id, updated_at DESC, orchestration_id DESC)"
    ),
    "idx_phase10_bindings_generation": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_bindings_generation "
        "ON phase10_context_bindings (generation_id, updated_at DESC) "
        "WHERE generation_id IS NOT NULL"
    ),
    "idx_phase10_bindings_orchestration": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_bindings_orchestration "
        "ON phase10_context_bindings (orchestration_id, updated_at DESC)"
    ),
    "idx_phase10_bindings_modeling_context": (
        "CREATE INDEX IF NOT EXISTS idx_phase10_bindings_modeling_context "
        "ON phase10_context_bindings (modeling_context_sha256, updated_at DESC)"
    ),
}

REQUIRED_INDEX_STATEMENTS = {
    **PHASE_ONE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_TWO_REQUIRED_INDEX_STATEMENTS,
    **PHASE_THREE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_FOUR_REQUIRED_INDEX_STATEMENTS,
    **PHASE_FIVE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_SIX_REQUIRED_INDEX_STATEMENTS,
    **PHASE_SEVEN_REQUIRED_INDEX_STATEMENTS,
    **PHASE_NINE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_TEN_REQUIRED_INDEX_STATEMENTS,
    **PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS,
    **PHASE_ELEVEN_RUNTIME_INDEX_STATEMENTS,
}


class UnsupportedSchemaVersionError(RuntimeError):
    """Raised when a database version cannot be safely handled by this application."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _user_table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    )


def _stored_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = ?",
        ("schema_version",),
    ).fetchone()
    if row is None:
        raise UnsupportedSchemaVersionError(
            "Database metadata does not contain a schema_version value."
        )
    try:
        return int(row["value"])
    except (TypeError, ValueError) as exc:
        raise UnsupportedSchemaVersionError(
            f"Database schema_version is invalid: {row['value']!r}."
        ) from exc


def _initialize_phase_one_schema(path: Path, timestamp: str) -> None:
    """Create the accepted Phase 1 base only when the database is empty."""
    with get_connection(path) as connection:
        if _table_exists(connection, "app_metadata"):
            return

    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if _table_exists(connection, "app_metadata"):
            return

        existing_tables = _user_table_names(connection)
        if existing_tables:
            raise UnsupportedSchemaVersionError(
                "Database has tables but no app_metadata schema version; "
                "automatic migration was not attempted."
            )

        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)

        for key, value in (
            ("schema_version", str(PHASE_ONE_SCHEMA_VERSION)),
            ("application_version", APP_VERSION),
            ("database_initialized_at", timestamp),
        ):
            connection.execute(
                """
                INSERT INTO app_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, timestamp),
            )


def _migrate_to_version_2(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE historical_analysis_runs (
            analysis_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            conversion_definition TEXT NOT NULL
                CHECK (conversion_definition IN (
                    'ATTRIBUTED_PURCHASE', 'ANY_PURCHASE', 'RESPONSE'
                )),
            filters_json TEXT NOT NULL,
            results_json TEXT,
            customer_import_id INTEGER,
            customer_source_checksum TEXT,
            campaign_sales_import_id INTEGER,
            campaign_sales_source_checksum TEXT,
            observation_count INTEGER NOT NULL DEFAULT 0
                CHECK (observation_count >= 0),
            selected_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (selected_customer_count >= 0),
            positive_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (positive_customer_count >= 0),
            unlabeled_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (unlabeled_customer_count >= 0),
            positive_customer_rate REAL,
            error_message TEXT,
            CHECK (
                positive_customer_rate IS NULL
                OR positive_customer_rate BETWEEN 0 AND 1
            ),
            CHECK (
                customer_import_id IS NULL OR customer_import_id > 0
            ),
            CHECK (
                campaign_sales_import_id IS NULL OR campaign_sales_import_id > 0
            ),
            CHECK (
                customer_source_checksum IS NULL OR length(customer_source_checksum) = 64
            ),
            CHECK (
                campaign_sales_source_checksum IS NULL
                OR length(campaign_sales_source_checksum) = 64
            )
        )
        """
    )
    for statement in PHASE_TWO_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_3(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE model_runs (
            model_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_run_id INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            algorithm TEXT,
            selected_candidate TEXT,
            random_seed INTEGER NOT NULL,
            validation_fraction REAL NOT NULL
                CHECK (validation_fraction > 0 AND validation_fraction < 1),
            reconstructed_observation_count INTEGER NOT NULL DEFAULT 0
                CHECK (reconstructed_observation_count >= 0),
            selected_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (selected_customer_count >= 0),
            positive_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (positive_customer_count >= 0),
            unlabeled_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (unlabeled_customer_count >= 0),
            train_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (train_customer_count >= 0),
            validation_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (validation_customer_count >= 0),
            train_positive_count INTEGER NOT NULL DEFAULT 0
                CHECK (train_positive_count >= 0),
            validation_positive_count INTEGER NOT NULL DEFAULT 0
                CHECK (validation_positive_count >= 0),
            feature_contract_json TEXT,
            preprocessing_json TEXT,
            hyperparameters_json TEXT,
            metrics_json TEXT,
            library_versions_json TEXT,
            artifact_path TEXT,
            artifact_sha256 TEXT,
            error_message TEXT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (positive_customer_count <= selected_customer_count),
            CHECK (unlabeled_customer_count <= selected_customer_count),
            CHECK (
                positive_customer_count + unlabeled_customer_count
                <= selected_customer_count
            ),
            CHECK (train_customer_count <= selected_customer_count),
            CHECK (validation_customer_count <= selected_customer_count),
            CHECK (
                train_customer_count + validation_customer_count
                <= selected_customer_count
            ),
            CHECK (train_positive_count <= train_customer_count),
            CHECK (validation_positive_count <= validation_customer_count),
            CHECK (
                train_positive_count + validation_positive_count
                <= positive_customer_count
            ),
            CHECK (
                status != 'COMPLETED'
                OR positive_customer_count + unlabeled_customer_count
                    = selected_customer_count
            ),
            CHECK (
                status != 'COMPLETED'
                OR train_customer_count + validation_customer_count
                    = selected_customer_count
            ),
            CHECK (
                status != 'COMPLETED'
                OR train_positive_count + validation_positive_count
                    = positive_customer_count
            ),
            CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64)
        )
        """
    )
    for statement in PHASE_THREE_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_4(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE jobs (
            job_id INTEGER PRIMARY KEY,
            job_type TEXT NOT NULL
                CHECK (job_type IN ('MODEL_TRAINING')),
            status TEXT NOT NULL
                CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
            progress_percent INTEGER NOT NULL DEFAULT 0
                CHECK (progress_percent BETWEEN 0 AND 100),
            stage TEXT NOT NULL
                CHECK (stage IN (
                    'QUEUED',
                    'STARTING',
                    'RECONSTRUCTING_COHORT',
                    'SPLITTING_DATA',
                    'PREPROCESSING',
                    'TRAINING_PRIMARY',
                    'TRAINING_CHALLENGER',
                    'TRAINING_DIAGNOSTIC',
                    'EVALUATING',
                    'PERSISTING_ARTIFACT',
                    'VERIFYING_ARTIFACT',
                    'COMPLETED',
                    'FAILED'
                )),
            message TEXT,
            analysis_run_id INTEGER,
            model_run_id INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            request_json TEXT NOT NULL,
            result_json TEXT,
            error_message TEXT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (analysis_run_id IS NULL OR analysis_run_id > 0),
            CHECK (model_run_id IS NULL OR model_run_id > 0),
            CHECK (
                status != 'QUEUED'
                OR (
                    progress_percent = 0
                    AND started_at IS NULL
                    AND finished_at IS NULL
                )
            ),
            CHECK (
                status != 'RUNNING'
                OR progress_percent BETWEEN 1 AND 99
            ),
            CHECK (
                status != 'COMPLETED'
                OR (
                    progress_percent = 100
                    AND finished_at IS NOT NULL
                    AND result_json IS NOT NULL
                )
            ),
            CHECK (
                status != 'FAILED'
                OR (
                    progress_percent <= 99
                    AND finished_at IS NOT NULL
                    AND error_message IS NOT NULL
                )
            )
        )
        """
    )
    for statement in PHASE_FOUR_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_5(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE jobs_v5 (
            job_id INTEGER PRIMARY KEY,
            job_type TEXT NOT NULL
                CHECK (job_type IN ('MODEL_TRAINING', 'PROSPECT_SCORING')),
            status TEXT NOT NULL
                CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
            progress_percent INTEGER NOT NULL DEFAULT 0
                CHECK (progress_percent BETWEEN 0 AND 100),
            stage TEXT NOT NULL
                CHECK (stage IN (
                    'QUEUED',
                    'STARTING',
                    'RECONSTRUCTING_COHORT',
                    'SPLITTING_DATA',
                    'PREPROCESSING',
                    'TRAINING_PRIMARY',
                    'TRAINING_CHALLENGER',
                    'TRAINING_DIAGNOSTIC',
                    'EVALUATING',
                    'PERSISTING_ARTIFACT',
                    'VERIFYING_ARTIFACT',
                    'VALIDATING_MODEL',
                    'PREPARING_SCORING_RUN',
                    'SCORING_PROSPECTS',
                    'FINALIZING_SCORES',
                    'VERIFYING_COMPLETENESS',
                    'COMPLETED',
                    'FAILED'
                )),
            message TEXT,
            analysis_run_id INTEGER,
            model_run_id INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            request_json TEXT NOT NULL,
            result_json TEXT,
            error_message TEXT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (analysis_run_id IS NULL OR analysis_run_id > 0),
            CHECK (model_run_id IS NULL OR model_run_id > 0),
            CHECK (
                job_type != 'MODEL_TRAINING'
                OR analysis_run_id IS NOT NULL
            ),
            CHECK (
                job_type != 'PROSPECT_SCORING'
                OR (
                    analysis_run_id IS NULL
                    AND model_run_id IS NOT NULL
                )
            ),
            CHECK (
                job_type != 'MODEL_TRAINING'
                OR stage IN (
                    'QUEUED',
                    'STARTING',
                    'RECONSTRUCTING_COHORT',
                    'SPLITTING_DATA',
                    'PREPROCESSING',
                    'TRAINING_PRIMARY',
                    'TRAINING_CHALLENGER',
                    'TRAINING_DIAGNOSTIC',
                    'EVALUATING',
                    'PERSISTING_ARTIFACT',
                    'VERIFYING_ARTIFACT',
                    'COMPLETED',
                    'FAILED'
                )
            ),
            CHECK (
                job_type != 'PROSPECT_SCORING'
                OR stage IN (
                    'QUEUED',
                    'STARTING',
                    'VALIDATING_MODEL',
                    'PREPARING_SCORING_RUN',
                    'SCORING_PROSPECTS',
                    'FINALIZING_SCORES',
                    'VERIFYING_COMPLETENESS',
                    'COMPLETED',
                    'FAILED'
                )
            ),
            CHECK (
                status != 'QUEUED'
                OR (
                    progress_percent = 0
                    AND started_at IS NULL
                    AND finished_at IS NULL
                    AND stage = 'QUEUED'
                )
            ),
            CHECK (
                status != 'RUNNING'
                OR (
                    progress_percent BETWEEN 1 AND 99
                    AND started_at IS NOT NULL
                    AND finished_at IS NULL
                    AND stage NOT IN ('QUEUED', 'COMPLETED', 'FAILED')
                )
            ),
            CHECK (
                status != 'COMPLETED'
                OR (
                    progress_percent = 100
                    AND finished_at IS NOT NULL
                    AND result_json IS NOT NULL
                    AND error_message IS NULL
                    AND stage = 'COMPLETED'
                )
            ),
            CHECK (
                status != 'FAILED'
                OR (
                    progress_percent <= 99
                    AND finished_at IS NOT NULL
                    AND error_message IS NOT NULL
                    AND stage = 'FAILED'
                )
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO jobs_v5 (
            job_id,
            job_type,
            status,
            progress_percent,
            stage,
            message,
            analysis_run_id,
            model_run_id,
            created_at,
            started_at,
            finished_at,
            request_json,
            result_json,
            error_message
        )
        SELECT
            job_id,
            job_type,
            status,
            progress_percent,
            stage,
            message,
            analysis_run_id,
            model_run_id,
            created_at,
            started_at,
            finished_at,
            request_json,
            result_json,
            error_message
        FROM jobs
        ORDER BY job_id
        """
    )
    old_job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    new_job_count = connection.execute("SELECT COUNT(*) FROM jobs_v5").fetchone()[0]
    if old_job_count != new_job_count:
        raise RuntimeError("Job migration lost rows while upgrading to schema version 5.")

    connection.execute("DROP TABLE jobs")
    connection.execute("ALTER TABLE jobs_v5 RENAME TO jobs")
    for statement in PHASE_FOUR_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)

    connection.execute(
        """
        CREATE TABLE scoring_runs (
            scoring_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            model_run_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            demographic_snapshot_count INTEGER NOT NULL
                CHECK (demographic_snapshot_count >= 0),
            demographic_min_person_id TEXT,
            demographic_max_person_id TEXT,
            scored_person_count INTEGER NOT NULL DEFAULT 0
                CHECK (scored_person_count >= 0),
            chunk_size INTEGER NOT NULL
                CHECK (chunk_size BETWEEN 1000 AND 100000),
            last_person_id TEXT,
            selected_candidate TEXT NOT NULL,
            model_role_policy_version TEXT NOT NULL,
            feature_contract_version TEXT NOT NULL,
            feature_contract_sha256 TEXT NOT NULL
                CHECK (length(feature_contract_sha256) = 64),
            artifact_sha256 TEXT NOT NULL
                CHECK (length(artifact_sha256) = 64),
            score_min REAL,
            score_max REAL,
            score_mean REAL,
            score_summary_json TEXT,
            error_message TEXT,
            FOREIGN KEY (job_id)
                REFERENCES jobs (job_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            UNIQUE (scoring_run_id, model_run_id),
            CHECK (scored_person_count <= demographic_snapshot_count),
            CHECK (
                status != 'RUNNING'
                OR (
                    completed_at IS NULL
                    AND error_message IS NULL
                )
            ),
            CHECK (
                status != 'COMPLETED'
                OR (
                    completed_at IS NOT NULL
                    AND error_message IS NULL
                    AND scored_person_count = demographic_snapshot_count
                    AND score_min IS NOT NULL
                    AND score_max IS NOT NULL
                    AND score_mean IS NOT NULL
                )
            ),
            CHECK (
                status != 'FAILED'
                OR (
                    completed_at IS NOT NULL
                    AND error_message IS NOT NULL
                )
            ),
            CHECK (score_min IS NULL OR (score_min = score_min AND score_min BETWEEN 0 AND 1)),
            CHECK (score_max IS NULL OR (score_max = score_max AND score_max BETWEEN 0 AND 1)),
            CHECK (score_mean IS NULL OR (score_mean = score_mean AND score_mean BETWEEN 0 AND 1)),
            CHECK (score_min IS NULL OR score_max IS NULL OR score_min <= score_max),
            CHECK (score_mean IS NULL OR score_min IS NULL OR score_mean >= score_min),
            CHECK (score_mean IS NULL OR score_max IS NULL OR score_mean <= score_max)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE propensity_scores (
            scoring_run_id INTEGER NOT NULL,
            model_run_id INTEGER NOT NULL,
            person_id TEXT NOT NULL,
            propensity_score REAL NOT NULL
                CHECK (
                    propensity_score = propensity_score
                    AND propensity_score BETWEEN 0 AND 1
                ),
            PRIMARY KEY (scoring_run_id, person_id),
            FOREIGN KEY (scoring_run_id, model_run_id)
                REFERENCES scoring_runs (scoring_run_id, model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (person_id)
                REFERENCES demographics (person_id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    for statement in PHASE_FIVE_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_6(connection: sqlite3.Connection) -> None:
    # Replace legacy one-completed-run-per-model uniqueness with lookup indexing.
    connection.execute("DROP INDEX IF EXISTS idx_scoring_runs_completed_model_unique")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scoring_runs_completed_model_unique
        ON scoring_runs (model_run_id, completed_at DESC, scoring_run_id DESC)
        WHERE status = 'COMPLETED'
        """
    )


def _migrate_to_version_7(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(historical_analysis_runs)").fetchall()
    }
    if "customer_import_id" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE historical_analysis_runs
            ADD COLUMN customer_import_id INTEGER
            """
        )
    if "customer_source_checksum" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE historical_analysis_runs
            ADD COLUMN customer_source_checksum TEXT
            """
        )
    if "campaign_sales_import_id" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE historical_analysis_runs
            ADD COLUMN campaign_sales_import_id INTEGER
            """
        )
    if "campaign_sales_source_checksum" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE historical_analysis_runs
            ADD COLUMN campaign_sales_source_checksum TEXT
            """
        )


def _migrate_to_version_8(connection: sqlite3.Connection) -> None:
    connection.execute("DROP INDEX IF EXISTS idx_scoring_runs_completed_model_unique")
    connection.execute(
        PHASE_FIVE_REQUIRED_INDEX_STATEMENTS[
            "idx_scoring_runs_completed_model_newest"
        ]
    )


def _migrate_to_version_9(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE jobs_v9 (
            job_id INTEGER PRIMARY KEY,
            job_type TEXT NOT NULL
                CHECK (job_type IN ('MODEL_TRAINING', 'PROSPECT_SCORING', 'AUDIENCE_PREPARATION')),
            status TEXT NOT NULL
                CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
            progress_percent INTEGER NOT NULL DEFAULT 0
                CHECK (progress_percent BETWEEN 0 AND 100),
            stage TEXT NOT NULL
                CHECK (stage IN (
                    'QUEUED',
                    'STARTING',
                    'RECONSTRUCTING_COHORT',
                    'SPLITTING_DATA',
                    'PREPROCESSING',
                    'TRAINING_PRIMARY',
                    'TRAINING_CHALLENGER',
                    'TRAINING_DIAGNOSTIC',
                    'EVALUATING',
                    'PERSISTING_ARTIFACT',
                    'VERIFYING_ARTIFACT',
                    'VALIDATING_MODEL',
                    'PREPARING_SCORING_RUN',
                    'SCORING_PROSPECTS',
                    'FINALIZING_SCORES',
                    'VERIFYING_COMPLETENESS',
                    'VALIDATING_SCORING_RUN',
                    'PREPARING_RANK_BOUNDARIES',
                    'VERIFYING_RANK_BOUNDARIES',
                    'COMPLETED',
                    'FAILED'
                )),
            message TEXT,
            analysis_run_id INTEGER,
            model_run_id INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            request_json TEXT NOT NULL,
            result_json TEXT,
            error_message TEXT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (analysis_run_id IS NULL OR analysis_run_id > 0),
            CHECK (model_run_id IS NULL OR model_run_id > 0),
            CHECK (
                job_type != 'MODEL_TRAINING'
                OR analysis_run_id IS NOT NULL
            ),
            CHECK (
                job_type != 'PROSPECT_SCORING'
                OR (
                    analysis_run_id IS NULL
                    AND model_run_id IS NOT NULL
                )
            ),
            CHECK (
                job_type != 'AUDIENCE_PREPARATION'
                OR (
                    analysis_run_id IS NULL
                    AND model_run_id IS NULL
                )
            ),
            CHECK (
                job_type != 'MODEL_TRAINING'
                OR stage IN (
                    'QUEUED',
                    'STARTING',
                    'RECONSTRUCTING_COHORT',
                    'SPLITTING_DATA',
                    'PREPROCESSING',
                    'TRAINING_PRIMARY',
                    'TRAINING_CHALLENGER',
                    'TRAINING_DIAGNOSTIC',
                    'EVALUATING',
                    'PERSISTING_ARTIFACT',
                    'VERIFYING_ARTIFACT',
                    'COMPLETED',
                    'FAILED'
                )
            ),
            CHECK (
                job_type != 'PROSPECT_SCORING'
                OR stage IN (
                    'QUEUED',
                    'STARTING',
                    'VALIDATING_MODEL',
                    'PREPARING_SCORING_RUN',
                    'SCORING_PROSPECTS',
                    'FINALIZING_SCORES',
                    'VERIFYING_COMPLETENESS',
                    'COMPLETED',
                    'FAILED'
                )
            ),
            CHECK (
                job_type != 'AUDIENCE_PREPARATION'
                OR stage IN (
                    'QUEUED',
                    'STARTING',
                    'VALIDATING_SCORING_RUN',
                    'PREPARING_RANK_BOUNDARIES',
                    'VERIFYING_RANK_BOUNDARIES',
                    'COMPLETED',
                    'FAILED'
                )
            ),
            CHECK (
                status != 'QUEUED'
                OR (
                    progress_percent = 0
                    AND started_at IS NULL
                    AND finished_at IS NULL
                    AND stage = 'QUEUED'
                )
            ),
            CHECK (
                status != 'RUNNING'
                OR (
                    progress_percent BETWEEN 1 AND 99
                    AND started_at IS NOT NULL
                    AND finished_at IS NULL
                    AND stage NOT IN ('QUEUED', 'COMPLETED', 'FAILED')
                )
            ),
            CHECK (
                status != 'COMPLETED'
                OR (
                    progress_percent = 100
                    AND finished_at IS NOT NULL
                    AND result_json IS NOT NULL
                    AND error_message IS NULL
                    AND stage = 'COMPLETED'
                )
            ),
            CHECK (
                status != 'FAILED'
                OR (
                    progress_percent <= 99
                    AND finished_at IS NOT NULL
                    AND error_message IS NOT NULL
                    AND stage = 'FAILED'
                )
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO jobs_v9 (
            job_id,
            job_type,
            status,
            progress_percent,
            stage,
            message,
            analysis_run_id,
            model_run_id,
            created_at,
            started_at,
            finished_at,
            request_json,
            result_json,
            error_message
        )
        SELECT
            job_id,
            job_type,
            status,
            progress_percent,
            stage,
            message,
            analysis_run_id,
            model_run_id,
            created_at,
            started_at,
            finished_at,
            request_json,
            result_json,
            error_message
        FROM jobs
        ORDER BY job_id
        """
    )
    old_job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    new_job_count = connection.execute("SELECT COUNT(*) FROM jobs_v9").fetchone()[0]
    if old_job_count != new_job_count:
        raise RuntimeError("Job migration lost rows while upgrading to schema version 9.")

    connection.execute(
        """
        CREATE TABLE scoring_runs_v9 (
            scoring_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            model_run_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            demographic_snapshot_count INTEGER NOT NULL
                CHECK (demographic_snapshot_count >= 0),
            demographic_min_person_id TEXT,
            demographic_max_person_id TEXT,
            scored_person_count INTEGER NOT NULL DEFAULT 0
                CHECK (scored_person_count >= 0),
            chunk_size INTEGER NOT NULL
                CHECK (chunk_size BETWEEN 1000 AND 100000),
            last_person_id TEXT,
            selected_candidate TEXT NOT NULL,
            model_role_policy_version TEXT NOT NULL,
            feature_contract_version TEXT NOT NULL,
            feature_contract_sha256 TEXT NOT NULL
                CHECK (length(feature_contract_sha256) = 64),
            artifact_sha256 TEXT NOT NULL
                CHECK (length(artifact_sha256) = 64),
            score_min REAL,
            score_max REAL,
            score_mean REAL,
            score_summary_json TEXT,
            error_message TEXT,
            FOREIGN KEY (job_id)
                REFERENCES jobs_v9 (job_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            UNIQUE (scoring_run_id, model_run_id),
            CHECK (scored_person_count <= demographic_snapshot_count),
            CHECK (
                status != 'RUNNING'
                OR (
                    completed_at IS NULL
                    AND error_message IS NULL
                )
            ),
            CHECK (
                status != 'COMPLETED'
                OR (
                    completed_at IS NOT NULL
                    AND error_message IS NULL
                    AND scored_person_count = demographic_snapshot_count
                    AND score_min IS NOT NULL
                    AND score_max IS NOT NULL
                    AND score_mean IS NOT NULL
                )
            ),
            CHECK (
                status != 'FAILED'
                OR (
                    completed_at IS NOT NULL
                    AND error_message IS NOT NULL
                )
            ),
            CHECK (score_min IS NULL OR (score_min = score_min AND score_min BETWEEN 0 AND 1)),
            CHECK (score_max IS NULL OR (score_max = score_max AND score_max BETWEEN 0 AND 1)),
            CHECK (score_mean IS NULL OR (score_mean = score_mean AND score_mean BETWEEN 0 AND 1)),
            CHECK (score_min IS NULL OR score_max IS NULL OR score_min <= score_max),
            CHECK (score_mean IS NULL OR score_min IS NULL OR score_mean >= score_min),
            CHECK (score_mean IS NULL OR score_max IS NULL OR score_mean <= score_max)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO scoring_runs_v9 (
            scoring_run_id,
            job_id,
            model_run_id,
            created_at,
            completed_at,
            status,
            demographic_snapshot_count,
            demographic_min_person_id,
            demographic_max_person_id,
            scored_person_count,
            chunk_size,
            last_person_id,
            selected_candidate,
            model_role_policy_version,
            feature_contract_version,
            feature_contract_sha256,
            artifact_sha256,
            score_min,
            score_max,
            score_mean,
            score_summary_json,
            error_message
        )
        SELECT
            scoring_run_id,
            job_id,
            model_run_id,
            created_at,
            completed_at,
            status,
            demographic_snapshot_count,
            demographic_min_person_id,
            demographic_max_person_id,
            scored_person_count,
            chunk_size,
            last_person_id,
            selected_candidate,
            model_role_policy_version,
            feature_contract_version,
            feature_contract_sha256,
            artifact_sha256,
            score_min,
            score_max,
            score_mean,
            score_summary_json,
            error_message
        FROM scoring_runs
        ORDER BY scoring_run_id
        """
    )
    old_scoring_count = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
    new_scoring_count = connection.execute("SELECT COUNT(*) FROM scoring_runs_v9").fetchone()[0]
    if old_scoring_count != new_scoring_count:
        raise RuntimeError("Scoring run migration lost rows while upgrading to schema version 9.")

    connection.execute(
        """
        CREATE TABLE propensity_scores_v9 (
            scoring_run_id INTEGER NOT NULL,
            model_run_id INTEGER NOT NULL,
            person_id TEXT NOT NULL,
            propensity_score REAL NOT NULL
                CHECK (
                    propensity_score = propensity_score
                    AND propensity_score BETWEEN 0 AND 1
                ),
            PRIMARY KEY (scoring_run_id, person_id),
            FOREIGN KEY (scoring_run_id, model_run_id)
                REFERENCES scoring_runs_v9 (scoring_run_id, model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (person_id)
                REFERENCES demographics (person_id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO propensity_scores_v9 (
            scoring_run_id,
            model_run_id,
            person_id,
            propensity_score
        )
        SELECT
            scoring_run_id,
            model_run_id,
            person_id,
            propensity_score
        FROM propensity_scores
        ORDER BY scoring_run_id, person_id
        """
    )
    old_scores_count = connection.execute("SELECT COUNT(*) FROM propensity_scores").fetchone()[0]
    new_scores_count = connection.execute("SELECT COUNT(*) FROM propensity_scores_v9").fetchone()[0]
    if old_scores_count != new_scores_count:
        raise RuntimeError("Propensity score migration lost rows while upgrading to schema version 9.")

    connection.execute("DROP TABLE propensity_scores")
    connection.execute("DROP TABLE scoring_runs")
    connection.execute("DROP TABLE jobs")
    connection.execute("ALTER TABLE jobs_v9 RENAME TO jobs")
    connection.execute("ALTER TABLE scoring_runs_v9 RENAME TO scoring_runs")
    connection.execute("ALTER TABLE propensity_scores_v9 RENAME TO propensity_scores")
    for statement in PHASE_FOUR_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)
    for statement in PHASE_FIVE_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)

    connection.execute(
        """
        CREATE TABLE audience_rank_boundaries (
            scoring_run_id INTEGER NOT NULL,
            percentile_bucket INTEGER NOT NULL
                CHECK (percentile_bucket BETWEEN 1 AND 100),
            boundary_rank INTEGER NOT NULL
                CHECK (boundary_rank > 0),
            boundary_score REAL NOT NULL
                CHECK (boundary_score = boundary_score AND boundary_score BETWEEN 0 AND 1),
            boundary_person_id TEXT NOT NULL
                CHECK (length(trim(boundary_person_id)) > 0),
            total_population INTEGER NOT NULL
                CHECK (total_population > 0),
            rank_contract_version TEXT NOT NULL
                CHECK (length(trim(rank_contract_version)) > 0),
            created_at TEXT NOT NULL,
            PRIMARY KEY (scoring_run_id, percentile_bucket),
            FOREIGN KEY (scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (boundary_rank <= total_population),
            CHECK (percentile_bucket != 100 OR boundary_rank = total_population)
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE saved_audiences (
            audience_id INTEGER PRIMARY KEY AUTOINCREMENT,
            audience_name TEXT NOT NULL
                CHECK (length(trim(audience_name)) BETWEEN 1 AND 120),
            description TEXT
                CHECK (description IS NULL OR length(trim(description)) <= 500),
            created_at TEXT NOT NULL,
            scoring_run_id INTEGER NOT NULL,
            model_run_id INTEGER NOT NULL,
            analysis_run_id INTEGER NOT NULL,
            selection_mode TEXT NOT NULL
                CHECK (selection_mode IN ('ALL_MATCHING', 'TOP_N')),
            target_count INTEGER,
            resolved_count INTEGER NOT NULL
                CHECK (resolved_count >= 1),
            filter_contract_version TEXT NOT NULL
                CHECK (length(trim(filter_contract_version)) > 0),
            rank_contract_version TEXT NOT NULL
                CHECK (length(trim(rank_contract_version)) > 0),
            selection_contract_version TEXT NOT NULL
                CHECK (length(trim(selection_contract_version)) > 0),
            filters_json TEXT NOT NULL
                CHECK (length(trim(filters_json)) > 0),
            selection_json TEXT NOT NULL
                CHECK (length(trim(selection_json)) > 0),
            profile_summary_json TEXT,
            customer_import_id INTEGER NOT NULL,
            customer_source_checksum TEXT NOT NULL
                CHECK (length(trim(customer_source_checksum)) = 64),
            campaign_sales_import_id INTEGER NOT NULL,
            campaign_sales_source_checksum TEXT NOT NULL
                CHECK (length(trim(campaign_sales_source_checksum)) = 64),
            demographic_import_id INTEGER NOT NULL,
            demographic_source_checksum TEXT NOT NULL
                CHECK (length(trim(demographic_source_checksum)) = 64),
            feature_contract_version TEXT NOT NULL
                CHECK (length(trim(feature_contract_version)) > 0),
            feature_contract_sha256 TEXT NOT NULL
                CHECK (length(trim(feature_contract_sha256)) = 64),
            artifact_sha256 TEXT NOT NULL
                CHECK (length(trim(artifact_sha256)) = 64),
            FOREIGN KEY (scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (customer_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (campaign_sales_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (demographic_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (scoring_run_id > 0),
            CHECK (model_run_id > 0),
            CHECK (analysis_run_id > 0),
            CHECK (customer_import_id > 0),
            CHECK (campaign_sales_import_id > 0),
            CHECK (demographic_import_id > 0),
            CHECK (target_count IS NULL OR target_count >= 1),
            CHECK (selection_mode != 'TOP_N' OR target_count IS NOT NULL),
            CHECK (selection_mode != 'ALL_MATCHING' OR target_count IS NULL)
        )
        """
    )

    for statement in PHASE_SIX_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_10(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE audience_analytics_snapshots (
            scoring_run_id INTEGER NOT NULL,
            analytics_contract_version TEXT NOT NULL
                CHECK (length(trim(analytics_contract_version)) BETWEEN 1 AND 24),
            model_run_id INTEGER NOT NULL,
            analysis_run_id INTEGER NOT NULL,
            customer_import_id INTEGER NOT NULL,
            customer_source_checksum TEXT NOT NULL
                CHECK (length(trim(customer_source_checksum)) = 64),
            campaign_sales_import_id INTEGER NOT NULL,
            campaign_sales_source_checksum TEXT NOT NULL
                CHECK (length(trim(campaign_sales_source_checksum)) = 64),
            demographic_import_id INTEGER NOT NULL,
            demographic_source_checksum TEXT NOT NULL
                CHECK (length(trim(demographic_source_checksum)) = 64),
            feature_contract_version TEXT NOT NULL
                CHECK (length(trim(feature_contract_version)) BETWEEN 1 AND 24),
            feature_contract_sha256 TEXT NOT NULL
                CHECK (length(trim(feature_contract_sha256)) = 64),
            artifact_sha256 TEXT NOT NULL
                CHECK (length(trim(artifact_sha256)) = 64),
            filter_contract_version TEXT NOT NULL
                CHECK (length(trim(filter_contract_version)) BETWEEN 1 AND 24),
            rank_contract_version TEXT NOT NULL
                CHECK (length(trim(rank_contract_version)) BETWEEN 1 AND 24),
            selection_contract_version TEXT NOT NULL
                CHECK (length(trim(selection_contract_version)) BETWEEN 1 AND 24),
            population_count INTEGER NOT NULL
                CHECK (population_count > 0),
            options_json TEXT NOT NULL
                CHECK (length(trim(options_json)) BETWEEN 2 AND 1048576),
            universe_profile_json TEXT NOT NULL
                CHECK (length(trim(universe_profile_json)) BETWEEN 2 AND 1048576),
            historical_positive_profile_json TEXT NOT NULL
                CHECK (length(trim(historical_positive_profile_json)) BETWEEN 2 AND 1048576),
            score_bucket_stats_json TEXT NOT NULL
                CHECK (length(trim(score_bucket_stats_json)) BETWEEN 2 AND 1048576),
            created_at TEXT NOT NULL,
            PRIMARY KEY (scoring_run_id, analytics_contract_version),
            FOREIGN KEY (scoring_run_id, model_run_id)
                REFERENCES scoring_runs (scoring_run_id, model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (customer_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (campaign_sales_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (demographic_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (scoring_run_id > 0),
            CHECK (model_run_id > 0),
            CHECK (analysis_run_id > 0),
            CHECK (customer_import_id > 0),
            CHECK (campaign_sales_import_id > 0),
            CHECK (demographic_import_id > 0)
        )
        """
    )


def _migrate_to_version_11(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_contract_version TEXT NOT NULL
                CHECK (length(trim(campaign_contract_version)) BETWEEN 1 AND 24),
            campaign_name TEXT NOT NULL
                CHECK (length(trim(campaign_name)) BETWEEN 1 AND 120),
            description TEXT
                CHECK (description IS NULL OR length(trim(description)) <= 500),
            channel TEXT NOT NULL
                CHECK (channel IN ('EMAIL', 'DIRECT_MAIL')),
            planned_launch_date TEXT,
            saved_audience_id INTEGER NOT NULL,
            scoring_run_id INTEGER NOT NULL,
            model_run_id INTEGER NOT NULL,
            analysis_run_id INTEGER NOT NULL,
            saved_audience_filter_hash TEXT NOT NULL
                CHECK (length(trim(saved_audience_filter_hash)) = 64),
            saved_audience_selection_json TEXT NOT NULL
                CHECK (length(trim(saved_audience_selection_json)) BETWEEN 2 AND 65536),
            saved_audience_resolved_count INTEGER NOT NULL
                CHECK (saved_audience_resolved_count >= 1),
            filter_contract_version TEXT NOT NULL
                CHECK (length(trim(filter_contract_version)) BETWEEN 1 AND 24),
            rank_contract_version TEXT NOT NULL
                CHECK (length(trim(rank_contract_version)) BETWEEN 1 AND 24),
            selection_contract_version TEXT NOT NULL
                CHECK (length(trim(selection_contract_version)) BETWEEN 1 AND 24),
            analytics_contract_version TEXT NOT NULL
                CHECK (length(trim(analytics_contract_version)) BETWEEN 1 AND 24),
            member_resolution_contract_version TEXT NOT NULL
                CHECK (length(trim(member_resolution_contract_version)) BETWEEN 1 AND 24),
            export_contract_version TEXT NOT NULL
                CHECK (length(trim(export_contract_version)) BETWEEN 1 AND 24),
            status TEXT NOT NULL
                CHECK (status IN ('DRAFT', 'FINALIZED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finalized_at TEXT,
            FOREIGN KEY (saved_audience_id)
                REFERENCES saved_audiences (audience_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (scoring_run_id, model_run_id)
                REFERENCES scoring_runs (scoring_run_id, model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (scoring_run_id > 0),
            CHECK (model_run_id > 0),
            CHECK (analysis_run_id > 0),
            CHECK (
                (status = 'DRAFT' AND finalized_at IS NULL)
                OR (status = 'FINALIZED' AND finalized_at IS NOT NULL)
            )
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_export_events (
            export_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            export_contract_version TEXT NOT NULL
                CHECK (length(trim(export_contract_version)) BETWEEN 1 AND 24),
            export_profile TEXT NOT NULL
                CHECK (export_profile IN ('EMAIL_CONTACT_V1', 'DIRECT_MAIL_CONTACT_V1')),
            status TEXT NOT NULL
                CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED', 'ABORTED')),
            selected_count INTEGER NOT NULL
                CHECK (selected_count >= 0),
            deliverable_count INTEGER NOT NULL
                CHECK (deliverable_count >= 0),
            undeliverable_count INTEGER NOT NULL
                CHECK (undeliverable_count >= 0),
            row_count INTEGER NOT NULL
                CHECK (row_count >= 0),
            csv_sha256 TEXT
                CHECK (csv_sha256 IS NULL OR length(trim(csv_sha256)) = 64),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            safe_error_message TEXT
                CHECK (safe_error_message IS NULL OR length(trim(safe_error_message)) <= 512),
            FOREIGN KEY (campaign_id)
                REFERENCES campaigns (campaign_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (deliverable_count + undeliverable_count = selected_count),
            CHECK (row_count = deliverable_count),
            CHECK (
                (status = 'STARTED' AND completed_at IS NULL)
                OR (status != 'STARTED' AND completed_at IS NOT NULL)
            )
        )
        """
    )

    for statement in PHASE_SEVEN_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_12(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "campaign_export_events"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 12 because campaign_export_events does not exist."
        )

    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(campaign_export_events)").fetchall()
    }

    if "export_snapshot_contract_version" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE campaign_export_events
            ADD COLUMN export_snapshot_contract_version TEXT NOT NULL DEFAULT '1'
                CHECK (length(trim(export_snapshot_contract_version)) BETWEEN 1 AND 24)
            """
        )
    if "start_provenance_sha256" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE campaign_export_events
            ADD COLUMN start_provenance_sha256 TEXT
                CHECK (
                    start_provenance_sha256 IS NULL
                    OR length(trim(start_provenance_sha256)) = 64
                )
            """
        )
    if "source_changed_during_export" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE campaign_export_events
            ADD COLUMN source_changed_during_export INTEGER NOT NULL DEFAULT 0
                CHECK (source_changed_during_export IN (0, 1))
            """
        )
    if "completion_currentness_state" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE campaign_export_events
            ADD COLUMN completion_currentness_state TEXT
                CHECK (
                    completion_currentness_state IS NULL
                    OR completion_currentness_state IN ('CURRENT', 'STALE', 'UNKNOWN')
                )
            """
        )

    connection.execute(
        """
        UPDATE campaign_export_events
        SET
            export_snapshot_contract_version = COALESCE(NULLIF(trim(export_snapshot_contract_version), ''), '1'),
            start_provenance_sha256 = CASE
                WHEN start_provenance_sha256 IS NULL OR trim(start_provenance_sha256) = '' THEN NULL
                ELSE lower(trim(start_provenance_sha256))
            END,
            source_changed_during_export = CASE
                WHEN source_changed_during_export IN (0, 1) THEN source_changed_during_export
                ELSE 0
            END,
            completion_currentness_state = CASE
                WHEN completion_currentness_state IN ('CURRENT', 'STALE', 'UNKNOWN')
                    THEN completion_currentness_state
                WHEN status = 'COMPLETED' THEN 'CURRENT'
                ELSE 'UNKNOWN'
            END
        """
    )


def _migrate_to_version_13(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_targeting_contexts (
            targeting_context_id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER UNIQUE,
            campaign_targeting_context_contract_version TEXT NOT NULL
                CHECK (
                    length(trim(campaign_targeting_context_contract_version))
                    BETWEEN 1 AND 24
                ),
            targeting_segment_contract_version TEXT NOT NULL
                CHECK (length(trim(targeting_segment_contract_version)) BETWEEN 1 AND 24),
            business_match_strength_contract_version TEXT NOT NULL
                CHECK (
                    length(trim(business_match_strength_contract_version))
                    BETWEEN 1 AND 24
                ),
            campaign_context_json TEXT NOT NULL
                CHECK (
                    length(trim(campaign_context_json)) BETWEEN 2 AND 65536
                    AND json_valid(campaign_context_json)
                ),
            campaign_context_sha256 TEXT NOT NULL
                CHECK (length(trim(campaign_context_sha256)) = 64),
            targeting_criteria_json TEXT NOT NULL
                CHECK (
                    length(trim(targeting_criteria_json)) BETWEEN 2 AND 65536
                    AND json_valid(targeting_criteria_json)
                ),
            targeting_criteria_sha256 TEXT NOT NULL
                CHECK (length(trim(targeting_criteria_sha256)) = 64),
            source_scoring_run_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (campaign_id)
                REFERENCES campaigns (campaign_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (source_scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (campaign_id IS NULL OR campaign_id > 0),
            CHECK (source_scoring_run_id IS NULL OR source_scoring_run_id > 0)
        )
        """
    )

    for statement in PHASE_NINE_CONTEXT_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_14(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS phase9_saved_target_groups (
            audience_id INTEGER PRIMARY KEY,
            targeting_context_id INTEGER NOT NULL,
            target_group_contract_version TEXT NOT NULL
                CHECK (length(trim(target_group_contract_version)) BETWEEN 1 AND 24),
            filter_branches_json TEXT NOT NULL
                CHECK (
                    length(trim(filter_branches_json)) BETWEEN 2 AND 262144
                    AND json_valid(filter_branches_json)
                ),
            filter_branches_sha256 TEXT NOT NULL
                CHECK (length(trim(filter_branches_sha256)) = 64),
            campaign_context_contract_version TEXT NOT NULL
                CHECK (length(trim(campaign_context_contract_version)) BETWEEN 1 AND 24),
            campaign_context_json TEXT NOT NULL
                CHECK (
                    length(trim(campaign_context_json)) BETWEEN 2 AND 65536
                    AND json_valid(campaign_context_json)
                ),
            campaign_context_sha256 TEXT NOT NULL
                CHECK (length(trim(campaign_context_sha256)) = 64),
            targeting_segment_contract_version TEXT NOT NULL
                CHECK (length(trim(targeting_segment_contract_version)) BETWEEN 1 AND 24),
            business_match_strength_contract_version TEXT NOT NULL
                CHECK (
                    length(trim(business_match_strength_contract_version))
                    BETWEEN 1 AND 24
                ),
            targeting_criteria_json TEXT NOT NULL
                CHECK (
                    length(trim(targeting_criteria_json)) BETWEEN 2 AND 65536
                    AND json_valid(targeting_criteria_json)
                ),
            targeting_criteria_sha256 TEXT NOT NULL
                CHECK (length(trim(targeting_criteria_sha256)) = 64),
            source_scoring_run_id INTEGER NOT NULL,
            source_status TEXT NOT NULL CHECK (source_status = 'READY'),
            resolved_count INTEGER NOT NULL CHECK (resolved_count >= 1),
            created_at TEXT NOT NULL,
            FOREIGN KEY (audience_id)
                REFERENCES saved_audiences (audience_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (targeting_context_id)
                REFERENCES campaign_targeting_contexts (targeting_context_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (source_scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    for statement in PHASE_NINE_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_15(connection: sqlite3.Connection) -> None:
    """Add the Phase 10 registry without rewriting immutable analytical rows."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS phase10_intelligence_generations (
            generation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            intelligence_generation_contract_version TEXT NOT NULL
                CHECK (length(trim(intelligence_generation_contract_version)) BETWEEN 1 AND 24),
            compatibility_contract_version TEXT NOT NULL
                CHECK (length(trim(compatibility_contract_version)) BETWEEN 1 AND 24),
            intelligence_key_sha256 TEXT NOT NULL
                CHECK (length(trim(intelligence_key_sha256)) = 64),
            modeling_context_json TEXT NOT NULL
                CHECK (
                    length(trim(modeling_context_json)) BETWEEN 2 AND 65536
                    AND json_valid(modeling_context_json)
                ),
            modeling_context_sha256 TEXT NOT NULL
                CHECK (length(trim(modeling_context_sha256)) = 64),
            historical_filters_json TEXT NOT NULL
                CHECK (
                    length(trim(historical_filters_json)) BETWEEN 2 AND 65536
                    AND json_valid(historical_filters_json)
                ),
            historical_filters_sha256 TEXT NOT NULL
                CHECK (length(trim(historical_filters_sha256)) = 64),
            historical_window_policy_version TEXT NOT NULL
                CHECK (length(trim(historical_window_policy_version)) BETWEEN 1 AND 24),
            multi_product_positive_policy_version TEXT NOT NULL
                CHECK (length(trim(multi_product_positive_policy_version)) BETWEEN 1 AND 24),
            training_eligibility_policy_version TEXT NOT NULL
                CHECK (length(trim(training_eligibility_policy_version)) BETWEEN 1 AND 24),
            customer_import_id INTEGER NOT NULL CHECK (customer_import_id > 0),
            customer_source_checksum TEXT NOT NULL
                CHECK (length(trim(customer_source_checksum)) = 64),
            campaign_sales_import_id INTEGER NOT NULL CHECK (campaign_sales_import_id > 0),
            campaign_sales_source_checksum TEXT NOT NULL
                CHECK (length(trim(campaign_sales_source_checksum)) = 64),
            demographic_import_id INTEGER NOT NULL CHECK (demographic_import_id > 0),
            demographic_source_checksum TEXT NOT NULL
                CHECK (length(trim(demographic_source_checksum)) = 64),
            feature_contract_version TEXT NOT NULL
                CHECK (length(trim(feature_contract_version)) BETWEEN 1 AND 24),
            feature_contract_sha256 TEXT NOT NULL
                CHECK (length(trim(feature_contract_sha256)) = 64),
            model_role_policy_version TEXT NOT NULL
                CHECK (length(trim(model_role_policy_version)) BETWEEN 1 AND 24),
            evaluation_contract_version TEXT NOT NULL
                CHECK (length(trim(evaluation_contract_version)) BETWEEN 1 AND 24),
            automated_training_policy_version TEXT NOT NULL
                CHECK (length(trim(automated_training_policy_version)) BETWEEN 1 AND 24),
            analysis_run_id INTEGER NOT NULL CHECK (analysis_run_id > 0),
            model_run_id INTEGER NOT NULL CHECK (model_run_id > 0),
            scoring_run_id INTEGER NOT NULL CHECK (scoring_run_id > 0),
            artifact_sha256 TEXT NOT NULL
                CHECK (length(trim(artifact_sha256)) = 64),
            score_semantics_json TEXT NOT NULL
                CHECK (
                    length(trim(score_semantics_json)) BETWEEN 2 AND 65536
                    AND json_valid(score_semantics_json)
                ),
            score_semantics_sha256 TEXT NOT NULL
                CHECK (length(trim(score_semantics_sha256)) = 64),
            rank_contract_version TEXT NOT NULL
                CHECK (length(trim(rank_contract_version)) BETWEEN 1 AND 24),
            analytics_contract_version TEXT NOT NULL
                CHECK (length(trim(analytics_contract_version)) BETWEEN 1 AND 24),
            lifecycle_policy_version TEXT NOT NULL
                CHECK (length(trim(lifecycle_policy_version)) BETWEEN 1 AND 24),
            generation_status TEXT NOT NULL CHECK (generation_status = 'READY'),
            lifecycle_state TEXT NOT NULL CHECK (
                lifecycle_state IN (
                    'CURRENT', 'REUSABLE', 'SUPERSEDED', 'STALE',
                    'RETIREMENT_ELIGIBLE', 'PROTECTED'
                )
            ),
            created_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            FOREIGN KEY (customer_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (campaign_sales_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (demographic_import_id)
                REFERENCES data_import_runs (import_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS phase10_orchestration_runs (
            orchestration_id INTEGER PRIMARY KEY AUTOINCREMENT,
            orchestration_contract_version TEXT NOT NULL
                CHECK (length(trim(orchestration_contract_version)) BETWEEN 1 AND 24),
            targeting_context_id INTEGER NOT NULL CHECK (targeting_context_id > 0),
            modeling_context_sha256 TEXT NOT NULL
                CHECK (length(trim(modeling_context_sha256)) = 64),
            intelligence_key_sha256 TEXT NOT NULL
                CHECK (length(trim(intelligence_key_sha256)) = 64),
            status TEXT NOT NULL
                CHECK (status IN ('QUEUED', 'RUNNING', 'READY', 'BLOCKED', 'FAILED')),
            stage TEXT NOT NULL CHECK (length(trim(stage)) BETWEEN 1 AND 80),
            progress_percent INTEGER NOT NULL CHECK (progress_percent BETWEEN 0 AND 100),
            business_message TEXT NOT NULL
                CHECK (length(trim(business_message)) BETWEEN 1 AND 1000),
            technical_message TEXT
                CHECK (
                    technical_message IS NULL
                    OR length(trim(technical_message)) BETWEEN 1 AND 8192
                ),
            reuse_plan_json TEXT NOT NULL
                CHECK (
                    length(trim(reuse_plan_json)) BETWEEN 2 AND 65536
                    AND json_valid(reuse_plan_json)
                ),
            analysis_run_id INTEGER CHECK (analysis_run_id IS NULL OR analysis_run_id > 0),
            model_run_id INTEGER CHECK (model_run_id IS NULL OR model_run_id > 0),
            scoring_run_id INTEGER CHECK (scoring_run_id IS NULL OR scoring_run_id > 0),
            generation_id INTEGER CHECK (generation_id IS NULL OR generation_id > 0),
            training_job_id INTEGER CHECK (training_job_id IS NULL OR training_job_id > 0),
            scoring_job_id INTEGER CHECK (scoring_job_id IS NULL OR scoring_job_id > 0),
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            safe_error_message TEXT
                CHECK (
                    safe_error_message IS NULL
                    OR length(trim(safe_error_message)) BETWEEN 1 AND 1000
                ),
            FOREIGN KEY (targeting_context_id)
                REFERENCES campaign_targeting_contexts (targeting_context_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (analysis_run_id)
                REFERENCES historical_analysis_runs (analysis_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (model_run_id)
                REFERENCES model_runs (model_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (scoring_run_id)
                REFERENCES scoring_runs (scoring_run_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (generation_id)
                REFERENCES phase10_intelligence_generations (generation_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (training_job_id)
                REFERENCES jobs (job_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (scoring_job_id)
                REFERENCES jobs (job_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (
                (status = 'QUEUED' AND progress_percent = 0
                    AND started_at IS NULL AND completed_at IS NULL)
                OR (status = 'RUNNING' AND progress_percent BETWEEN 1 AND 99
                    AND started_at IS NOT NULL AND completed_at IS NULL)
                OR (status = 'READY' AND progress_percent = 100
                    AND started_at IS NOT NULL AND completed_at IS NOT NULL
                    AND analysis_run_id IS NOT NULL AND model_run_id IS NOT NULL
                    AND scoring_run_id IS NOT NULL AND generation_id IS NOT NULL)
                OR (status IN ('BLOCKED', 'FAILED') AND progress_percent BETWEEN 0 AND 99
                    AND completed_at IS NOT NULL)
            ),
            CHECK (status != 'FAILED' OR safe_error_message IS NOT NULL)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS phase10_context_bindings (
            targeting_context_id INTEGER PRIMARY KEY CHECK (targeting_context_id > 0),
            modeling_context_sha256 TEXT NOT NULL
                CHECK (length(trim(modeling_context_sha256)) = 64),
            orchestration_id INTEGER NOT NULL CHECK (orchestration_id > 0),
            generation_id INTEGER CHECK (generation_id IS NULL OR generation_id > 0),
            binding_status TEXT NOT NULL CHECK (
                binding_status IN ('PREPARING', 'READY', 'BLOCKED', 'FAILED', 'STALE')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            FOREIGN KEY (targeting_context_id)
                REFERENCES campaign_targeting_contexts (targeting_context_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (orchestration_id)
                REFERENCES phase10_orchestration_runs (orchestration_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (generation_id)
                REFERENCES phase10_intelligence_generations (generation_id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            CHECK (binding_status != 'READY' OR generation_id IS NOT NULL)
        )
        """
    )
    # A generation key can have older SUPERSEDED/STALE rows; uniqueness belongs
    # only to active orchestration, not immutable generation history.
    connection.execute("DROP INDEX IF EXISTS idx_phase10_generations_intelligence_key")
    for statement in PHASE_TEN_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


def _migrate_to_version_16(connection: sqlite3.Connection) -> None:
    """Append governed Phase 11 contactability and activation source fields."""

    if not _table_exists(connection, "demographics"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 16 because demographics does not exist."
        )

    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(demographics)").fetchall()
    }
    additions = (
        (
            "email_contactable",
            "INTEGER NOT NULL DEFAULT 0 CHECK (email_contactable IN (0, 1))",
        ),
        (
            "direct_mail_contactable",
            "INTEGER NOT NULL DEFAULT 0 CHECK (direct_mail_contactable IN (0, 1))",
        ),
        ("sms_opt_in", "INTEGER NOT NULL DEFAULT 0 CHECK (sms_opt_in IN (0, 1))"),
        (
            "whatsapp_opt_in",
            "INTEGER NOT NULL DEFAULT 0 CHECK (whatsapp_opt_in IN (0, 1))",
        ),
        (
            "telemarketing_contactable",
            "INTEGER NOT NULL DEFAULT 0 CHECK (telemarketing_contactable IN (0, 1))",
        ),
        ("do_not_call", "INTEGER NOT NULL DEFAULT 0 CHECK (do_not_call IN (0, 1))"),
        ("push_token", "TEXT"),
        ("push_opt_in", "INTEGER NOT NULL DEFAULT 0 CHECK (push_opt_in IN (0, 1))"),
        ("advertising_id", "TEXT"),
        (
            "advertising_targetable",
            "INTEGER NOT NULL DEFAULT 0 CHECK (advertising_targetable IN (0, 1))",
        ),
        ("web_visitor_id", "TEXT"),
        (
            "onsite_targetable",
            "INTEGER NOT NULL DEFAULT 0 CHECK (onsite_targetable IN (0, 1))",
        ),
    )
    for column_name, definition in additions:
        if column_name not in existing_columns:
            connection.execute(
                f'ALTER TABLE demographics ADD COLUMN "{column_name}" {definition}'
            )


def _migrate_to_version_17(connection: sqlite3.Connection) -> None:
    """Create separate immutable business-search/result/export registries."""
    for statement in PHASE_ELEVEN_CREATE_TABLE_STATEMENTS:
        connection.execute(statement)
    for statement in PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)
    for statement in PHASE_ELEVEN_TRIGGER_STATEMENTS:
        connection.execute(statement)


def _migrate_to_version_18(connection: sqlite3.Connection) -> None:
    """Add a nullable, write-once seam for future delivery/outcome lineage."""

    if not _table_exists(connection, "campaign_search_runs"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 18 because campaign_search_runs does not exist."
        )
    connection.execute(PHASE_ELEVEN_FEEDBACK_CREATE_TABLE_STATEMENT)
    connection.execute(
        """
        INSERT OR IGNORE INTO campaign_search_future_lineage (
            search_run_id, created_at, updated_at
        )
        SELECT search_run_id, created_at, created_at
        FROM campaign_search_runs
        ORDER BY search_run_id
        """
    )
    for statement in PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS.values():
        connection.execute(statement)
    for statement in PHASE_ELEVEN_FEEDBACK_TRIGGER_STATEMENTS:
        connection.execute(statement)


def _migrate_to_version_19(connection: sqlite3.Connection) -> None:
    """Add durable Phase 11 lifecycle, progress, and safe issue state."""

    if not _table_exists(connection, "campaign_search_runs"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 19 because campaign_search_runs does not exist."
        )
    connection.execute(PHASE_ELEVEN_RUNTIME_CREATE_TABLE_STATEMENT)
    connection.execute(
        """
        INSERT OR IGNORE INTO campaign_search_run_runtime (
            search_run_id, lifecycle_contract_version, lifecycle_status,
            stage_code, stage_label, progress_percent, processed_count,
            total_count, progress_unit, status_message, failure_code,
            failure_category, failure_summary, resolution_steps_json,
            retryable, created_at, processing_started_at, updated_at,
            heartbeat_at, state_version
        )
        SELECT
            search_run_id, '1', status,
            CASE status
                WHEN 'QUEUED' THEN 'QUEUED'
                WHEN 'PROCESSING' THEN 'RECOVERING'
                WHEN 'COMPLETED' THEN 'COMPLETED'
                ELSE status
            END,
            CASE status
                WHEN 'QUEUED' THEN 'Waiting to start'
                WHEN 'PROCESSING' THEN 'Recovering saved work'
                WHEN 'COMPLETED' THEN 'Result ready'
                WHEN 'BLOCKED' THEN 'Search blocked'
                ELSE 'Search failed'
            END,
            CASE status WHEN 'COMPLETED' THEN 100 WHEN 'PROCESSING' THEN 2 ELSE 0 END,
            COALESCE(selected_count, 0),
            CASE WHEN selection_mode = 'TOP_N' THEN target_count ELSE selected_count END,
            'potential customers',
            CASE status
                WHEN 'QUEUED' THEN 'Saved and waiting to prepare targeting intelligence.'
                WHEN 'PROCESSING' THEN 'Recovering this search from durable state.'
                WHEN 'COMPLETED' THEN 'Potential-customer results are ready.'
                WHEN 'BLOCKED' THEN 'This search cannot proceed with the current targeting intelligence.'
                ELSE 'The search could not be completed. Please try again.'
            END,
            CASE WHEN status = 'BLOCKED' THEN 'LEGACY_BLOCKED'
                 WHEN status = 'FAILED' THEN 'LEGACY_FAILED' END,
            CASE WHEN status = 'BLOCKED' THEN 'TARGETING_INTELLIGENCE'
                 WHEN status = 'FAILED' THEN 'PROCESSING_FAILURE' END,
            CASE WHEN status IN ('BLOCKED','FAILED') THEN safe_error_message END,
            CASE WHEN status = 'BLOCKED'
                 THEN '["Review the saved targeting criteria and available campaign history.","Try a broader search after the source data is updated."]'
                 WHEN status = 'FAILED'
                 THEN '["Try the search again after the system is available.","Use the saved search details when requesting support if the problem continues."]'
                 ELSE '[]' END,
            CASE WHEN status IN ('BLOCKED','FAILED') THEN 1 ELSE 0 END,
            created_at,
            CASE WHEN status != 'QUEUED' THEN started_at END,
            COALESCE(completed_at, started_at, created_at),
            CASE WHEN status = 'PROCESSING' THEN COALESCE(started_at, created_at) END,
            1
        FROM campaign_search_runs
        """
    )
    for statement in PHASE_ELEVEN_RUNTIME_INDEX_STATEMENTS.values():
        connection.execute(statement)
    for statement in PHASE_ELEVEN_RUNTIME_TRIGGER_STATEMENTS:
        connection.execute(statement)


def _migrate_to_version_20(connection: sqlite3.Connection) -> None:
    """Add retry attempts, calibrated selection, fast catalogs, and feedback."""

    for statement in SEARCH_RECOVERY_TABLE_STATEMENTS:
        connection.execute(statement)
    for statement in SEARCH_RECOVERY_INDEX_STATEMENTS:
        connection.execute(statement)
    run_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(campaign_search_runs)")
    }
    additions = (
        ("current_attempt_number", "INTEGER NOT NULL DEFAULT 1 CHECK (current_attempt_number > 0)"),
        ("selection_contract_version", "TEXT NOT NULL DEFAULT '1' CHECK (selection_contract_version IN ('1','2'))"),
        ("propensity_bucket", "TEXT CHECK (propensity_bucket IN ('0.90','0.80','0.70','0.60','0.50'))"),
        ("catalog_version", "TEXT"),
        ("calibration_artifact_id", "INTEGER REFERENCES score_calibration_artifacts(calibration_artifact_id) ON DELETE RESTRICT"),
    )
    for name, definition in additions:
        if name not in run_columns:
            connection.execute(f'ALTER TABLE campaign_search_runs ADD COLUMN "{name}" {definition}')
    runtime_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(campaign_search_run_runtime)")
    }
    if "stage_started_at" not in runtime_columns:
        connection.execute("ALTER TABLE campaign_search_run_runtime ADD COLUMN stage_started_at TEXT")
        connection.execute(
            "UPDATE campaign_search_run_runtime SET stage_started_at=updated_at WHERE stage_started_at IS NULL"
        )
    if "failure_stage_code" not in runtime_columns:
        connection.execute("ALTER TABLE campaign_search_run_runtime ADD COLUMN failure_stage_code TEXT")
    snapshot_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(campaign_result_snapshots)")
    }
    snapshot_additions = (
        ("selection_contract_version", "TEXT NOT NULL DEFAULT '1' CHECK (selection_contract_version IN ('1','2'))"),
        ("propensity_bucket", "TEXT CHECK (propensity_bucket IN ('0.90','0.80','0.70','0.60','0.50'))"),
        ("calibration_artifact_id", "INTEGER REFERENCES score_calibration_artifacts(calibration_artifact_id) ON DELETE RESTRICT"),
    )
    for name, definition in snapshot_additions:
        if name not in snapshot_columns:
            connection.execute(f'ALTER TABLE campaign_result_snapshots ADD COLUMN "{name}" {definition}')
    connection.execute(
        """
        INSERT OR IGNORE INTO campaign_search_attempts (
            search_run_id, attempt_number, attempt_contract_version,
            selection_contract_version, status, generation_id, scoring_run_id,
            created_at, started_at, completed_at, failure_stage_code,
            failure_summary, retryable
        )
        SELECT search_run_id, 1, '1', '1', status, generation_id, scoring_run_id,
               created_at, started_at, completed_at,
               CASE WHEN status IN ('BLOCKED','FAILED') THEN status END,
               safe_error_message,
               CASE WHEN status IN ('BLOCKED','FAILED') THEN 1 ELSE 0 END
        FROM campaign_search_runs
        """
    )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_runs_terminal")
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_runs_immutable_identity")
    retry_mutable = {
        "generation_id", "analysis_run_id", "model_run_id", "scoring_run_id",
        "result_snapshot_id", "result_source", "status", "selected_count",
        "started_at", "completed_at", "processing_seconds", "safe_error_message",
        "current_attempt_number", "calibration_artifact_id",
    }
    immutable_condition = " OR ".join(
        f"NEW.{column} IS NOT OLD.{column}"
        for column in CAMPAIGN_SEARCH_RUN_COLUMNS
        if column not in retry_mutable
    )
    connection.execute(
        "CREATE TRIGGER campaign_search_runs_immutable_identity "
        "BEFORE UPDATE ON campaign_search_runs WHEN " + immutable_condition
        + " BEGIN SELECT RAISE(ABORT, 'immutable registry identity'); END"
    )
    connection.execute(
        """
        CREATE TRIGGER campaign_search_runs_terminal BEFORE UPDATE ON campaign_search_runs
        WHEN (OLD.status='COMPLETED')
          OR (OLD.status IN ('BLOCKED','FAILED') AND NEW.status != 'QUEUED')
          OR (OLD.status='PROCESSING' AND NEW.status='QUEUED')
        BEGIN SELECT RAISE(ABORT, 'invalid search transition or terminal mutation'); END
        """
    )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_run_runtime_transition")
    connection.execute(
        """
        CREATE TRIGGER campaign_search_run_runtime_transition
        BEFORE UPDATE ON campaign_search_run_runtime
        WHEN NEW.lifecycle_status != OLD.lifecycle_status AND NOT (
            (OLD.lifecycle_status='QUEUED' AND NEW.lifecycle_status IN
                ('PROCESSING','PAUSE_REQUESTED','STOP_REQUESTED','STOPPED','BLOCKED','FAILED')) OR
            (OLD.lifecycle_status='PROCESSING' AND NEW.lifecycle_status IN
                ('PAUSE_REQUESTED','STOP_REQUESTED','RESTART_REQUESTED','COMPLETED','BLOCKED','FAILED')) OR
            (OLD.lifecycle_status='PAUSE_REQUESTED' AND NEW.lifecycle_status IN
                ('PROCESSING','PAUSED','STOP_REQUESTED','STOPPED','FAILED')) OR
            (OLD.lifecycle_status='PAUSED' AND NEW.lifecycle_status IN
                ('PROCESSING','STOP_REQUESTED','RESTART_REQUESTED','STOPPED','FAILED')) OR
            (OLD.lifecycle_status='STOP_REQUESTED' AND NEW.lifecycle_status IN ('STOPPED','FAILED')) OR
            (OLD.lifecycle_status='RESTART_REQUESTED' AND NEW.lifecycle_status IN ('STOPPED','FAILED')) OR
            (OLD.lifecycle_status IN ('BLOCKED','FAILED') AND NEW.lifecycle_status='QUEUED')
        )
        BEGIN SELECT RAISE(ABORT, 'invalid search runtime transition'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS campaign_search_attempt_create
        AFTER INSERT ON campaign_search_runs
        BEGIN
            INSERT INTO campaign_search_attempts (
                search_run_id, attempt_number, attempt_contract_version,
                selection_contract_version, propensity_bucket,
                bucket_minimum, bucket_maximum, bucket_maximum_inclusive,
                status, created_at, started_at
            ) VALUES (
                NEW.search_run_id, NEW.current_attempt_number, '1',
                NEW.selection_contract_version, NEW.propensity_bucket,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 0.90 WHEN '0.80' THEN 0.80
                    WHEN '0.70' THEN 0.70 WHEN '0.60' THEN 0.60
                    WHEN '0.50' THEN 0.50 END,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 1.00 WHEN '0.80' THEN 0.90
                    WHEN '0.70' THEN 0.80 WHEN '0.60' THEN 0.70
                    WHEN '0.50' THEN 0.60 END,
                CASE WHEN NEW.propensity_bucket='0.90' THEN 1
                     WHEN NEW.propensity_bucket IS NOT NULL THEN 0 END,
                NEW.status, NEW.created_at, NEW.started_at
            );
        END
        """
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS campaign_search_attempts_terminal
           BEFORE UPDATE ON campaign_search_attempts
           WHEN OLD.status IN ('COMPLETED','BLOCKED','FAILED')
           BEGIN SELECT RAISE(ABORT, 'terminal search attempt is immutable'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS campaign_search_attempts_no_delete
           BEFORE DELETE ON campaign_search_attempts
           BEGIN SELECT RAISE(ABORT, 'search attempt history cannot be deleted'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS campaign_search_progress_events_no_update
           BEFORE UPDATE ON campaign_search_progress_events
           BEGIN SELECT RAISE(ABORT, 'search progress history is immutable'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS campaign_search_progress_events_no_delete
           BEFORE DELETE ON campaign_search_progress_events
           BEGIN SELECT RAISE(ABORT, 'search progress history cannot be deleted'); END"""
    )


def _migrate_to_version_21(connection: sqlite3.Connection) -> None:
    """Add the normalized compact product catalog used by business history."""

    for statement in SEARCH_RECOVERY_TABLE_STATEMENTS:
        connection.execute(statement)
    for statement in SEARCH_RECOVERY_INDEX_STATEMENTS:
        connection.execute(statement)


def _migrate_to_version_22(connection: sqlite3.Connection) -> None:
    """Add durable per-attempt execution fencing and lease metadata."""

    if not _table_exists(connection, "campaign_search_attempts"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 22 because campaign_search_attempts does not exist."
        )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(campaign_search_attempts)")
    }
    additions = (
        (
            "execution_lease_token",
            "TEXT CHECK (execution_lease_token IS NULL OR "
            "(length(execution_lease_token)=64 AND "
            "execution_lease_token NOT GLOB '*[^0-9a-f]*'))",
        ),
        (
            "lease_owner",
            "TEXT CHECK (lease_owner IS NULL OR length(lease_owner) BETWEEN 1 AND 128)",
        ),
        ("lease_claimed_at", "TEXT"),
        ("lease_heartbeat_at", "TEXT"),
    )
    for name, definition in additions:
        if name not in columns:
            connection.execute(
                f'ALTER TABLE campaign_search_attempts ADD COLUMN "{name}" {definition}'
            )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_attempts_terminal")
    connection.execute(
        """UPDATE campaign_search_attempts
           SET execution_lease_token=lower(hex(randomblob(32)))
           WHERE execution_lease_token IS NULL"""
    )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_search_attempt_execution_lease
           ON campaign_search_attempts(execution_lease_token)
           WHERE execution_lease_token IS NOT NULL"""
    )
    invalid = connection.execute(
        """SELECT COUNT(*) FROM campaign_search_attempts
           WHERE execution_lease_token IS NULL
              OR length(execution_lease_token) != 64
              OR execution_lease_token GLOB '*[^0-9a-f]*'"""
    ).fetchone()[0]
    if invalid:
        raise UnsupportedSchemaVersionError(
            "Attempt execution-fence backfill did not produce valid lease tokens."
        )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_attempt_create")
    connection.execute(
        """
        CREATE TRIGGER campaign_search_attempt_create
        AFTER INSERT ON campaign_search_runs
        BEGIN
            INSERT INTO campaign_search_attempts (
                search_run_id, attempt_number, attempt_contract_version,
                selection_contract_version, propensity_bucket,
                bucket_minimum, bucket_maximum, bucket_maximum_inclusive,
                status, execution_lease_token, created_at, started_at
            ) VALUES (
                NEW.search_run_id, NEW.current_attempt_number, '1',
                NEW.selection_contract_version, NEW.propensity_bucket,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 0.90 WHEN '0.80' THEN 0.80
                    WHEN '0.70' THEN 0.70 WHEN '0.60' THEN 0.60
                    WHEN '0.50' THEN 0.50 END,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 1.00 WHEN '0.80' THEN 0.90
                    WHEN '0.70' THEN 0.80 WHEN '0.60' THEN 0.70
                    WHEN '0.50' THEN 0.60 END,
                CASE WHEN NEW.propensity_bucket='0.90' THEN 1
                     WHEN NEW.propensity_bucket IS NOT NULL THEN 0 END,
                NEW.status, lower(hex(randomblob(32))), NEW.created_at, NEW.started_at
            );
        END
        """
    )
    connection.execute(
        """CREATE TRIGGER campaign_search_attempts_terminal
           BEFORE UPDATE ON campaign_search_attempts
           WHEN OLD.status IN ('COMPLETED','BLOCKED','FAILED')
           BEGIN SELECT RAISE(ABORT, 'terminal search attempt is immutable'); END"""
    )


def _migrate_to_version_23(connection: sqlite3.Connection) -> None:
    """Add Phase 10 failure ownership and Phase 11 dependency lineage."""

    required = (
        "phase10_orchestration_runs",
        "campaign_search_attempts",
        "campaign_search_run_runtime",
    )
    if any(not _table_exists(connection, table) for table in required):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 23 because dependency tables are missing."
        )
    phase10_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(phase10_orchestration_runs)")
    }
    phase10_additions = (
        (
            "failure_code",
            "TEXT CHECK (failure_code IS NULL OR length(failure_code) BETWEEN 1 AND 80)",
        ),
        (
            "failure_category",
            "TEXT CHECK (failure_category IS NULL OR length(failure_category) BETWEEN 1 AND 80)",
        ),
        ("retryable", "INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0,1))"),
    )
    for name, definition in phase10_additions:
        if name not in phase10_columns:
            connection.execute(
                f'ALTER TABLE phase10_orchestration_runs ADD COLUMN "{name}" {definition}'
            )
    connection.execute(
        """UPDATE phase10_orchestration_runs
           SET failure_code=CASE status
                   WHEN 'FAILED' THEN 'LEGACY_PHASE10_FAILED'
                   WHEN 'BLOCKED' THEN 'PHASE10_BUSINESS_BLOCKED'
                   ELSE failure_code END,
               failure_category=CASE status
                   WHEN 'FAILED' THEN 'TRANSIENT_DEPENDENCY'
                   WHEN 'BLOCKED' THEN 'BUSINESS_DATA_INSUFFICIENCY'
                   ELSE failure_category END,
               retryable=CASE WHEN status='FAILED' THEN 1 ELSE 0 END
           WHERE status IN ('FAILED','BLOCKED')
             AND (failure_code IS NULL OR failure_category IS NULL)"""
    )

    attempt_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(campaign_search_attempts)")
    }
    attempt_additions = (
        (
            "phase10_orchestration_id",
            "INTEGER REFERENCES phase10_orchestration_runs(orchestration_id) ON DELETE RESTRICT",
        ),
        (
            "phase10_dependency_status",
            "TEXT CHECK (phase10_dependency_status IS NULL OR "
            "phase10_dependency_status IN ('NOT_STARTED','QUEUED','RUNNING','READY','BLOCKED','FAILED','STALE'))",
        ),
        (
            "phase10_dependency_rejoined",
            "INTEGER NOT NULL DEFAULT 0 CHECK (phase10_dependency_rejoined IN (0,1))",
        ),
        ("phase10_dependency_updated_at", "TEXT"),
    )
    for name, definition in attempt_additions:
        if name not in attempt_columns:
            connection.execute(
                f'ALTER TABLE campaign_search_attempts ADD COLUMN "{name}" {definition}'
            )

    runtime_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(campaign_search_run_runtime)")
    }
    if "technical_reference" not in runtime_columns:
        connection.execute(
            """ALTER TABLE campaign_search_run_runtime
               ADD COLUMN technical_reference TEXT
               CHECK (technical_reference IS NULL OR length(technical_reference) BETWEEN 1 AND 80)"""
        )
        connection.execute(
            """UPDATE campaign_search_run_runtime
               SET technical_reference=failure_code
               WHERE failure_code IS NOT NULL"""
        )
    invalid = connection.execute(
        """SELECT COUNT(*) FROM phase10_orchestration_runs
           WHERE status IN ('FAILED','BLOCKED')
             AND (failure_code IS NULL OR failure_category IS NULL)
        """
    ).fetchone()[0]
    if invalid:
        raise UnsupportedSchemaVersionError(
            "Phase 10 failure ownership backfill did not complete."
        )


def _migrate_to_version_24(connection: sqlite3.Connection) -> None:
    """Version intelligence attestations as full lineage/integrity evidence."""

    table = "intelligence_verification_attestations"
    if not _table_exists(connection, table):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 24 because intelligence attestations are missing."
        )
    existing = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    additions = (
        ("verification_contract_version", "TEXT"),
        ("integrity_contract_version", "TEXT"),
        ("model_run_id", "INTEGER REFERENCES model_runs(model_run_id) ON DELETE RESTRICT"),
        ("feature_contract_version", "TEXT"),
        ("feature_contract_sha256", "TEXT"),
        ("score_semantics_sha256", "TEXT"),
        ("customer_import_id", "INTEGER"),
        ("customer_source_checksum", "TEXT"),
        ("campaign_sales_import_id", "INTEGER"),
        ("campaign_sales_source_checksum", "TEXT"),
        ("demographic_import_id", "INTEGER"),
        ("demographic_source_checksum", "TEXT"),
        ("rank_contract_version", "TEXT"),
        ("analytics_contract_version", "TEXT"),
        (
            "verified_facts_json",
            "TEXT CHECK (verified_facts_json IS NULL OR json_valid(verified_facts_json))",
        ),
        (
            "verified_facts_sha256",
            "TEXT CHECK (verified_facts_sha256 IS NULL OR length(verified_facts_sha256)=64)",
        ),
        (
            "failure_codes_json",
            "TEXT CHECK (failure_codes_json IS NULL OR json_valid(failure_codes_json))",
        ),
    )
    for name, definition in additions:
        if name not in existing:
            connection.execute(f'ALTER TABLE {table} ADD COLUMN "{name}" {definition}')
    # A row-count-only verification cannot satisfy contract v2. Retain the
    # historical record, but make it ineligible for direct reuse.
    connection.execute(
        f"""UPDATE {table}
            SET verification_status='STALE'
            WHERE verification_status='VERIFIED'
              AND (verification_contract_version IS NULL
                   OR integrity_contract_version IS NULL
                   OR verified_facts_sha256 IS NULL)"""
    )


def _migrate_to_version_25(connection: sqlite3.Connection) -> None:
    """Make attempt start timestamps represent actual worker processing."""

    if not _table_exists(connection, "campaign_search_attempts"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 25 because search attempts are missing."
        )
    # Active queued attempts have not started and are safe to correct. Terminal
    # attempts remain immutable historical evidence.
    connection.execute(
        """UPDATE campaign_search_attempts
           SET started_at=NULL
           WHERE status='QUEUED' AND completed_at IS NULL"""
    )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_attempt_create")
    connection.execute(
        """
        CREATE TRIGGER campaign_search_attempt_create
        AFTER INSERT ON campaign_search_runs
        BEGIN
            INSERT INTO campaign_search_attempts (
                search_run_id, attempt_number, attempt_contract_version,
                selection_contract_version, propensity_bucket,
                bucket_minimum, bucket_maximum, bucket_maximum_inclusive,
                status, execution_lease_token, created_at, started_at
            ) VALUES (
                NEW.search_run_id, NEW.current_attempt_number, '1',
                NEW.selection_contract_version, NEW.propensity_bucket,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 0.90 WHEN '0.80' THEN 0.80
                    WHEN '0.70' THEN 0.70 WHEN '0.60' THEN 0.60
                    WHEN '0.50' THEN 0.50 END,
                CASE NEW.propensity_bucket
                    WHEN '0.90' THEN 1.00 WHEN '0.80' THEN 0.90
                    WHEN '0.70' THEN 0.80 WHEN '0.60' THEN 0.70
                    WHEN '0.50' THEN 0.60 END,
                CASE WHEN NEW.propensity_bucket='0.90' THEN 1
                     WHEN NEW.propensity_bucket IS NOT NULL THEN 0 END,
                NEW.status, lower(hex(randomblob(32))), NEW.created_at,
                CASE WHEN NEW.status='QUEUED' THEN NULL ELSE NEW.started_at END
            );
        END
        """
    )


def _migrate_to_version_26(connection: sqlite3.Connection) -> None:
    """Add workload-qualified progress and transactional initial events."""

    required = (
        "campaign_search_runs",
        "campaign_search_run_runtime",
        "campaign_search_attempts",
        "campaign_search_progress_events",
    )
    if any(not _table_exists(connection, table) for table in required):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 26 because search progress tables are missing."
        )
    runtime_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(campaign_search_run_runtime)"
        )
    }
    if "workload_class" not in runtime_columns:
        connection.execute(
            """ALTER TABLE campaign_search_run_runtime
               ADD COLUMN workload_class TEXT NOT NULL
               DEFAULT 'PENDING_CLASSIFICATION'
               CHECK (length(workload_class) BETWEEN 1 AND 80)"""
        )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_search_progress_workload_stage
           ON campaign_search_progress_events(
               workload_class,stage_code,recorded_at,search_run_id
           )"""
    )
    connection.execute("DROP TRIGGER IF EXISTS campaign_search_initial_progress_event")
    connection.execute(
        """
        CREATE TRIGGER campaign_search_initial_progress_event
        AFTER INSERT ON campaign_search_attempts
        WHEN NEW.status='QUEUED'
        BEGIN
            INSERT INTO campaign_search_progress_events (
                search_run_id,attempt_number,stage_code,stage_label,
                progress_percent,processed_count,total_count,status_message,
                workload_class,recorded_at
            ) VALUES (
                NEW.search_run_id,NEW.attempt_number,'QUEUED','Waiting to start',
                0,0,NULL,'Saved and waiting for processing capacity.',
                'PENDING_CLASSIFICATION',NEW.created_at
            );
        END
        """
    )


def _migrate_to_version_27(connection: sqlite3.Connection) -> None:
    """Permit explicit v2 membership while preserving every v1 snapshot row."""

    required = (
        "campaign_result_snapshots",
        "campaign_search_runs",
        "campaign_result_export_events",
    )
    if any(not _table_exists(connection, table) for table in required):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 27 because result registry tables are missing."
        )
    definition_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_result_snapshots'"
    ).fetchone()
    definition = str(definition_row["sql"] or "")
    normalized = "".join(definition.split()).lower()
    if "check(result_membership_contract_versionin('1','2'))" not in normalized:
        legacy = "CHECK (result_membership_contract_version = '1')"
        replacement = (
            "CHECK (result_membership_contract_version IN ('1','2'))"
        )
        if definition.count(legacy) != 1:
            raise UnsupportedSchemaVersionError(
                "Result snapshot membership constraint is not the supported v26 definition."
            )
        # This is a guarded constraint broadening, not a table rebuild. It keeps
        # snapshot rows, AUTOINCREMENT identity, triggers, indexes, and every
        # child foreign-key reference byte-for-byte unchanged. SQLite has no
        # ALTER CHECK syntax, so update only the verified schema definition and
        # advance the schema cookie to force an immediate reparse.
        revised = definition.replace(legacy, replacement, 1)
        try:
            connection.execute("PRAGMA writable_schema=ON")
            cursor = connection.execute(
                """UPDATE sqlite_master SET sql=?
                   WHERE type='table' AND name='campaign_result_snapshots'
                     AND sql=?""",
                (revised, definition),
            )
        finally:
            connection.execute("PRAGMA writable_schema=OFF")
        if cursor.rowcount != 1:
            raise UnsupportedSchemaVersionError(
                "Result snapshot membership constraint could not be updated safely."
            )
        schema_version = int(
            connection.execute("PRAGMA schema_version").fetchone()[0]
        )
        connection.execute(f"PRAGMA schema_version={schema_version + 1}")
    for statement in PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)
    for statement in PHASE_ELEVEN_TRIGGER_STATEMENTS:
        connection.execute(statement)
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise UnsupportedSchemaVersionError(
            "Result snapshot migration failed foreign-key verification."
        )
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise UnsupportedSchemaVersionError(
            "Result snapshot migration failed database integrity verification."
        )


def _migrate_to_version_28(connection: sqlite3.Connection) -> None:
    """Enforce one current targeting catalog at the persistence boundary."""

    if not _table_exists(connection, "targeting_option_catalogs"):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 28 because targeting catalogs are missing."
        )
    current = connection.execute(
        """SELECT catalog_version FROM targeting_option_catalogs
           WHERE is_current=1
           ORDER BY created_at DESC,catalog_version DESC"""
    ).fetchall()
    if len(current) > 1:
        winner = str(current[0]["catalog_version"])
        connection.execute(
            """UPDATE targeting_option_catalogs SET is_current=0
               WHERE is_current=1 AND catalog_version<>?""",
            (winner,),
        )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_targeting_option_catalog_current
           ON targeting_option_catalogs(is_current) WHERE is_current=1"""
    )


def _migrate_to_version_29(connection: sqlite3.Connection) -> None:
    """Persist grouped model lineage and permit isolated calibration v2 artifacts."""

    if not _table_exists(connection, "model_runs") or not _table_exists(
        connection, "score_calibration_artifacts"
    ):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 29 because model/calibration tables are missing."
        )
    model_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(model_runs)")
    }
    if "split_lineage_json" not in model_columns:
        connection.execute(
            """ALTER TABLE model_runs ADD COLUMN split_lineage_json TEXT
               CHECK (split_lineage_json IS NULL OR json_valid(split_lineage_json))"""
        )

    definition_row = connection.execute(
        """SELECT sql FROM sqlite_master
           WHERE type='table' AND name='score_calibration_artifacts'"""
    ).fetchone()
    definition = str(definition_row["sql"] or "")
    normalized = "".join(definition.split()).lower()
    if "check(calibration_contract_versionin('1','2'))" not in normalized:
        legacy = "CHECK (calibration_contract_version = '1')"
        replacement = "CHECK (calibration_contract_version IN ('1','2'))"
        if definition.count(legacy) != 1:
            raise UnsupportedSchemaVersionError(
                "Calibration contract constraint is not the supported v1 definition."
            )
        revised = definition.replace(legacy, replacement, 1)
        try:
            connection.execute("PRAGMA writable_schema=ON")
            cursor = connection.execute(
                """UPDATE sqlite_master SET sql=?
                   WHERE type='table' AND name='score_calibration_artifacts'
                     AND sql=?""",
                (revised, definition),
            )
        finally:
            connection.execute("PRAGMA writable_schema=OFF")
        if cursor.rowcount != 1:
            raise UnsupportedSchemaVersionError(
                "Calibration contract constraint could not be updated safely."
            )
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        connection.execute(f"PRAGMA schema_version={schema_version + 1}")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise UnsupportedSchemaVersionError(
            "Calibration isolation migration failed foreign-key verification."
        )


def _migrate_to_version_30(connection: sqlite3.Connection) -> None:
    """Add truthful, bounded feedback-recalibration decision lineage."""

    required = ("campaign_feedback_batches", "feedback_retraining_decisions")
    if any(not _table_exists(connection, table) for table in required):
        raise UnsupportedSchemaVersionError(
            "Cannot migrate to version 30 because feedback tables are missing."
        )
    batch_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(campaign_feedback_batches)")
    }
    if "selection_basis_sha256" not in batch_columns:
        connection.execute(
            """ALTER TABLE campaign_feedback_batches
               ADD COLUMN selection_basis_sha256 TEXT
               CHECK (selection_basis_sha256 IS NULL OR length(selection_basis_sha256)=64)"""
        )
    decision_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(feedback_retraining_decisions)")
    }
    additions = (
        (
            "decision_kind",
            "TEXT NOT NULL DEFAULT 'RECALIBRATION' CHECK (decision_kind='RECALIBRATION')",
        ),
        (
            "latest_feedback_batch_id",
            "INTEGER REFERENCES campaign_feedback_batches(feedback_batch_id) ON DELETE RESTRICT",
        ),
        (
            "reference_decision_id",
            "INTEGER REFERENCES feedback_retraining_decisions(retraining_decision_id) ON DELETE RESTRICT",
        ),
        (
            "drift_lineage_json",
            "TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(drift_lineage_json))",
        ),
    )
    for name, definition in additions:
        if name not in decision_columns:
            connection.execute(
                f'ALTER TABLE feedback_retraining_decisions ADD COLUMN "{name}" {definition}'
            )
    duplicate_waiting = connection.execute(
        """SELECT scoring_run_id,MAX(retraining_decision_id) AS keeper
           FROM feedback_retraining_decisions
           WHERE status='WAITING_FOR_DATA'
           GROUP BY scoring_run_id HAVING COUNT(*)>1"""
    ).fetchall()
    for row in duplicate_waiting:
        connection.execute(
            """UPDATE feedback_retraining_decisions
               SET status='REJECTED',
                   trigger_reason='Superseded during bounded recalibration-state migration.',
                   completed_at=COALESCE(completed_at,created_at)
               WHERE scoring_run_id=? AND status='WAITING_FOR_DATA'
                 AND retraining_decision_id<>?""",
            (int(row["scoring_run_id"]), int(row["keeper"])),
        )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_recalibration_waiting
           ON feedback_retraining_decisions(scoring_run_id)
           WHERE status='WAITING_FOR_DATA'"""
    )
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise UnsupportedSchemaVersionError(
            "Feedback recalibration migration failed foreign-key verification."
        )
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_version_2,
    3: _migrate_to_version_3,
    4: _migrate_to_version_4,
    5: _migrate_to_version_5,
    6: _migrate_to_version_6,
    7: _migrate_to_version_7,
    8: _migrate_to_version_8,
    9: _migrate_to_version_9,
    10: _migrate_to_version_10,
    11: _migrate_to_version_11,
    12: _migrate_to_version_12,
    13: _migrate_to_version_13,
    14: _migrate_to_version_14,
    15: _migrate_to_version_15,
    16: _migrate_to_version_16,
    17: _migrate_to_version_17,
    18: _migrate_to_version_18,
    19: _migrate_to_version_19,
    20: _migrate_to_version_20,
    21: _migrate_to_version_21,
    22: _migrate_to_version_22,
    23: _migrate_to_version_23,
    24: _migrate_to_version_24,
    25: _migrate_to_version_25,
    26: _migrate_to_version_26,
    27: _migrate_to_version_27,
    28: _migrate_to_version_28,
    29: _migrate_to_version_29,
    30: _migrate_to_version_30,
}


def initialize_database(database_path: str | Path | None = None) -> Path:
    """Create the Phase 1 base and apply each missing schema migration in order."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    timestamp = _utc_timestamp()

    _initialize_phase_one_schema(path, timestamp)

    with get_connection(path) as connection:
        stored_version = _stored_schema_version(connection)

    if stored_version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            "Database schema version "
            f"{stored_version} is newer than supported version {CURRENT_SCHEMA_VERSION}."
        )
    if stored_version < PHASE_ONE_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Database schema version {stored_version} is older than the supported base "
            f"version {PHASE_ONE_SCHEMA_VERSION}."
        )

    for target_version in range(stored_version + 1, CURRENT_SCHEMA_VERSION + 1):
        migration = MIGRATIONS.get(target_version)
        if migration is None:
            raise UnsupportedSchemaVersionError(
                f"No migration is registered for schema version {target_version}."
            )

        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_version = _stored_schema_version(connection)
            if current_version >= target_version:
                continue
            if current_version != target_version - 1:
                raise UnsupportedSchemaVersionError(
                    "Database schema changed during migration; expected version "
                    f"{target_version - 1}, found {current_version}."
                )
            migration(connection)
            connection.execute(
                """
                UPDATE app_metadata
                SET value = ?, updated_at = ?
                WHERE key = 'schema_version'
                """,
                (str(target_version), timestamp),
            )

    with get_connection(path) as connection:
        application_version_row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'application_version'"
        ).fetchone()

    if application_version_row is None or application_version_row["value"] != APP_VERSION:
        with get_connection(path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO app_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                ("application_version", APP_VERSION, timestamp),
            )

    logger.info("SQLite schema initialized or verified | path=%s version=%s", path, SCHEMA_VERSION)
    return path


def initialize_required_indexes(database_path: str | Path | None = None) -> dict[str, float]:
    """Create all required query indexes idempotently and return per-index timings."""
    path = initialize_database(database_path)
    timings: dict[str, float] = {}

    with get_connection(path, write=True) as connection:
        for index_name, statement in REQUIRED_INDEX_STATEMENTS.items():
            started = time.perf_counter()
            connection.execute(statement)
            connection.commit()
            elapsed = time.perf_counter() - started
            timings[index_name] = elapsed
            logger.info("SQLite index verified | index=%s seconds=%.3f", index_name, elapsed)

    return timings


def verify_required_indexes(database_path: str | Path | None = None) -> dict[str, bool]:
    """Report whether each required index exists in the SQLite catalog."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    with get_connection(path) as connection:
        existing = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    return {name: name in existing for name in REQUIRED_INDEX_STATEMENTS}


def _quote_identifier(identifier: str) -> str:
    """Quote an identifier obtained from SQLite's own schema catalog."""
    return '"' + identifier.replace('"', '""') + '"'


def inspect_database(database_path: str | Path | None = None) -> dict[str, Any]:
    """Return tables, columns, indexes, and row counts for development inspection."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    report: dict[str, Any] = {"database_path": str(path), "tables": []}

    with get_connection(path) as connection:
        table_names = [
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        for table_name in table_names:
            quoted_name = _quote_identifier(table_name)
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "not_null": bool(row["notnull"]),
                    "primary_key_position": row["pk"],
                }
                for row in connection.execute(f"PRAGMA table_info({quoted_name})").fetchall()
            ]
            indexes = [
                {
                    "name": row["name"],
                    "unique": bool(row["unique"]),
                    "origin": row["origin"],
                }
                for row in connection.execute(f"PRAGMA index_list({quoted_name})").fetchall()
            ]
            row_count = connection.execute(
                f"SELECT COUNT(*) AS row_count FROM {quoted_name}"
            ).fetchone()["row_count"]
            report["tables"].append(
                {
                    "name": table_name,
                    "row_count": row_count,
                    "columns": columns,
                    "indexes": indexes,
                }
            )

    return report


def format_inspection_report(report: dict[str, Any]) -> str:
    """Format an inspection result for the initialization CLI."""
    lines = [f"Database: {report['database_path']}"]
    for table in report["tables"]:
        lines.append(f"\nTable: {table['name']} | rows: {table['row_count']}")
        lines.append("  Columns:")
        for column in table["columns"]:
            markers = []
            if column["not_null"]:
                markers.append("NOT NULL")
            if column["primary_key_position"]:
                markers.append("PRIMARY KEY")
            suffix = f" [{' | '.join(markers)}]" if markers else ""
            lines.append(f"    - {column['name']}: {column['type']}{suffix}")
        lines.append("  Indexes:")
        if table["indexes"]:
            for index in table["indexes"]:
                lines.append(
                    f"    - {index['name']} | unique={index['unique']} | origin={index['origin']}"
                )
        else:
            lines.append("    - none")
    return "\n".join(lines)
