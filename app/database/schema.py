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


logger = logging.getLogger(__name__)
PHASE_ONE_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 12
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
        religion TEXT
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

REQUIRED_INDEX_STATEMENTS = {
    **PHASE_ONE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_TWO_REQUIRED_INDEX_STATEMENTS,
    **PHASE_THREE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_FOUR_REQUIRED_INDEX_STATEMENTS,
    **PHASE_FIVE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_SIX_REQUIRED_INDEX_STATEMENTS,
    **PHASE_SEVEN_REQUIRED_INDEX_STATEMENTS,
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
