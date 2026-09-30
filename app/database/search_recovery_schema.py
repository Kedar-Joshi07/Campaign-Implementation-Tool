"""Additive search recovery, calibration, catalog, and feedback schema."""

from __future__ import annotations


SEARCH_RECOVERY_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS campaign_search_attempts (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_id INTEGER NOT NULL REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
        attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
        attempt_contract_version TEXT NOT NULL CHECK (attempt_contract_version = '1'),
        selection_contract_version TEXT NOT NULL CHECK (selection_contract_version IN ('1','2')),
        propensity_bucket TEXT CHECK (propensity_bucket IN ('0.90','0.80','0.70','0.60','0.50')),
        bucket_minimum REAL CHECK (bucket_minimum IS NULL OR bucket_minimum BETWEEN 0 AND 1),
        bucket_maximum REAL CHECK (bucket_maximum IS NULL OR bucket_maximum BETWEEN 0 AND 1),
        bucket_maximum_inclusive INTEGER CHECK (bucket_maximum_inclusive IS NULL OR bucket_maximum_inclusive IN (0,1)),
        calibration_artifact_id INTEGER,
        generation_id INTEGER,
        scoring_run_id INTEGER,
        status TEXT NOT NULL CHECK (status IN ('QUEUED','PROCESSING','COMPLETED','BLOCKED','FAILED')),
        idempotency_key TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        failure_code TEXT,
        failure_stage_code TEXT,
        failure_summary TEXT,
        retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0,1)),
        UNIQUE(search_run_id, attempt_number),
        UNIQUE(search_run_id, idempotency_key),
        CHECK ((selection_contract_version='1' AND propensity_bucket IS NULL)
            OR (selection_contract_version='2' AND propensity_bucket IS NOT NULL
                AND bucket_minimum IS NOT NULL AND bucket_maximum IS NOT NULL
                AND bucket_maximum_inclusive IS NOT NULL)),
        CHECK ((status IN ('QUEUED','PROCESSING') AND completed_at IS NULL)
            OR (status IN ('COMPLETED','BLOCKED','FAILED') AND completed_at IS NOT NULL))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_search_progress_events (
        progress_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_id INTEGER NOT NULL REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
        attempt_number INTEGER NOT NULL,
        stage_code TEXT NOT NULL,
        stage_label TEXT NOT NULL,
        progress_percent INTEGER NOT NULL CHECK (progress_percent BETWEEN 0 AND 100),
        processed_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
        total_count INTEGER CHECK (total_count IS NULL OR total_count >= processed_count),
        status_message TEXT NOT NULL,
        workload_class TEXT NOT NULL DEFAULT 'SEARCH',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY(search_run_id, attempt_number)
            REFERENCES campaign_search_attempts(search_run_id, attempt_number) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS targeting_option_catalogs (
        catalog_version TEXT PRIMARY KEY,
        customer_source_checksum TEXT,
        campaign_sales_source_checksum TEXT,
        demographic_source_checksum TEXT,
        context_options_json TEXT NOT NULL CHECK (json_valid(context_options_json)),
        targeting_options_json TEXT NOT NULL CHECK (json_valid(targeting_options_json)),
        created_at TEXT NOT NULL,
        is_current INTEGER NOT NULL CHECK (is_current IN (0,1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS targeting_product_catalog (
        catalog_version TEXT NOT NULL REFERENCES targeting_option_catalogs(catalog_version) ON DELETE RESTRICT,
        product_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        product_category TEXT NOT NULL,
        PRIMARY KEY(catalog_version, product_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS score_calibration_artifacts (
        calibration_artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        calibration_contract_version TEXT NOT NULL CHECK (calibration_contract_version IN ('1','2')),
        scoring_run_id INTEGER NOT NULL REFERENCES scoring_runs(scoring_run_id) ON DELETE RESTRICT,
        model_run_id INTEGER NOT NULL REFERENCES model_runs(model_run_id) ON DELETE RESTRICT,
        outcome_definition TEXT NOT NULL CHECK (outcome_definition = 'ATTRIBUTED_PURCHASE'),
        method TEXT NOT NULL CHECK (method IN ('SIGMOID','ISOTONIC')),
        split_seed INTEGER NOT NULL,
        split_lineage_json TEXT NOT NULL CHECK (json_valid(split_lineage_json)),
        artifact_json TEXT NOT NULL CHECK (json_valid(artifact_json)),
        metrics_json TEXT NOT NULL CHECK (json_valid(metrics_json)),
        artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256)=64),
        source_checksum TEXT NOT NULL CHECK (length(source_checksum)=64),
        status TEXT NOT NULL CHECK (status IN ('CANDIDATE','PROMOTED','REJECTED','STALE')),
        created_at TEXT NOT NULL,
        promoted_at TEXT,
        UNIQUE(scoring_run_id, artifact_sha256)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS calibrated_propensity_scores (
        calibration_artifact_id INTEGER NOT NULL REFERENCES score_calibration_artifacts(calibration_artifact_id) ON DELETE RESTRICT,
        scoring_run_id INTEGER NOT NULL REFERENCES scoring_runs(scoring_run_id) ON DELETE RESTRICT,
        person_id TEXT NOT NULL,
        raw_score REAL NOT NULL CHECK (raw_score BETWEEN 0 AND 1),
        calibrated_probability REAL NOT NULL CHECK (calibrated_probability BETWEEN 0 AND 1),
        propensity_bucket TEXT CHECK (propensity_bucket IN ('0.90','0.80','0.70','0.60','0.50')),
        rank_position INTEGER NOT NULL CHECK (rank_position > 0),
        total_population INTEGER NOT NULL CHECK (total_population > 0),
        percentile_bucket INTEGER NOT NULL CHECK (percentile_bucket BETWEEN 1 AND 100),
        decile INTEGER NOT NULL CHECK (decile BETWEEN 1 AND 10),
        rank_band TEXT NOT NULL,
        PRIMARY KEY(calibration_artifact_id, person_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS calibration_score_stage (
        calibration_artifact_id INTEGER NOT NULL REFERENCES score_calibration_artifacts(calibration_artifact_id) ON DELETE RESTRICT,
        person_id TEXT NOT NULL,
        raw_score REAL NOT NULL CHECK (raw_score BETWEEN 0 AND 1),
        calibrated_probability REAL NOT NULL CHECK (calibrated_probability BETWEEN 0 AND 1),
        PRIMARY KEY(calibration_artifact_id, person_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS calibration_distribution_bins (
        calibration_artifact_id INTEGER NOT NULL REFERENCES score_calibration_artifacts(calibration_artifact_id) ON DELETE RESTRICT,
        bin_number INTEGER NOT NULL CHECK (bin_number BETWEEN 0 AND 9),
        population_count INTEGER NOT NULL CHECK (population_count >= 0),
        PRIMARY KEY(calibration_artifact_id, bin_number)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS intelligence_verification_attestations (
        attestation_key_sha256 TEXT PRIMARY KEY CHECK (length(attestation_key_sha256)=64),
        verification_contract_version TEXT,
        integrity_contract_version TEXT,
        generation_id INTEGER NOT NULL REFERENCES phase10_intelligence_generations(generation_id) ON DELETE RESTRICT,
        scoring_run_id INTEGER NOT NULL REFERENCES scoring_runs(scoring_run_id) ON DELETE RESTRICT,
        model_run_id INTEGER REFERENCES model_runs(model_run_id) ON DELETE RESTRICT,
        source_checksums_json TEXT NOT NULL CHECK (json_valid(source_checksums_json)),
        artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256)=64),
        feature_contract_version TEXT,
        feature_contract_sha256 TEXT,
        score_semantics_sha256 TEXT,
        customer_import_id INTEGER,
        customer_source_checksum TEXT,
        campaign_sales_import_id INTEGER,
        campaign_sales_source_checksum TEXT,
        demographic_import_id INTEGER,
        demographic_source_checksum TEXT,
        rank_contract_version TEXT,
        analytics_contract_version TEXT,
        schema_version TEXT NOT NULL,
        verified_facts_json TEXT CHECK (verified_facts_json IS NULL OR json_valid(verified_facts_json)),
        verified_facts_sha256 TEXT CHECK (verified_facts_sha256 IS NULL OR length(verified_facts_sha256)=64),
        failure_codes_json TEXT CHECK (failure_codes_json IS NULL OR json_valid(failure_codes_json)),
        verified_at TEXT NOT NULL,
        expires_at TEXT,
        verification_status TEXT NOT NULL CHECK (verification_status IN ('VERIFIED','FAILED','STALE')),
        verified_row_count INTEGER NOT NULL CHECK (verified_row_count >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_preflight_cache (
        cache_key_sha256 TEXT PRIMARY KEY CHECK (length(cache_key_sha256)=64),
        criteria_sha256 TEXT NOT NULL CHECK (length(criteria_sha256)=64),
        generation_id INTEGER NOT NULL,
        calibration_artifact_id INTEGER,
        demographic_count INTEGER NOT NULL CHECK (demographic_count >= 0),
        bucket_count INTEGER NOT NULL CHECK (bucket_count >= 0),
        intersection_count INTEGER NOT NULL CHECK (intersection_count >= 0),
        currentness_state TEXT NOT NULL CHECK (currentness_state IN ('CURRENT','STALE','UNVERIFIED')),
        created_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_feedback_batches (
        feedback_batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_id INTEGER NOT NULL REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
        attempt_number INTEGER NOT NULL,
        outcome_definition TEXT NOT NULL CHECK (outcome_definition='ATTRIBUTED_PURCHASE'),
        source_name TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
        selection_basis_sha256 TEXT CHECK (selection_basis_sha256 IS NULL OR length(selection_basis_sha256)=64),
        row_count INTEGER NOT NULL CHECK (row_count > 0),
        positive_count INTEGER NOT NULL CHECK (positive_count >= 0),
        negative_count INTEGER NOT NULL CHECK (negative_count >= 0),
        status TEXT NOT NULL CHECK (status IN ('ACCEPTED','REJECTED')),
        created_at TEXT NOT NULL,
        UNIQUE(search_run_id, idempotency_key),
        FOREIGN KEY(search_run_id, attempt_number)
            REFERENCES campaign_search_attempts(search_run_id, attempt_number) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_feedback_outcomes (
        feedback_batch_id INTEGER NOT NULL REFERENCES campaign_feedback_batches(feedback_batch_id) ON DELETE RESTRICT,
        person_id TEXT NOT NULL,
        outcome INTEGER NOT NULL CHECK (outcome IN (0,1)),
        outcome_at TEXT NOT NULL,
        outcome_value REAL,
        PRIMARY KEY(feedback_batch_id, person_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_retraining_decisions (
        retraining_decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_contract_version TEXT NOT NULL CHECK (decision_contract_version='1'),
        scoring_run_id INTEGER NOT NULL REFERENCES scoring_runs(scoring_run_id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK (status IN ('WAITING_FOR_DATA','QUEUED','TRAINING','PROMOTED','REJECTED','FAILED')),
        label_count INTEGER NOT NULL CHECK (label_count >= 0),
        positive_count INTEGER NOT NULL CHECK (positive_count >= 0),
        negative_count INTEGER NOT NULL CHECK (negative_count >= 0),
        distinct_run_count INTEGER NOT NULL CHECK (distinct_run_count >= 0),
        new_label_ratio REAL NOT NULL CHECK (new_label_ratio >= 0),
        population_stability_index REAL,
        decision_kind TEXT NOT NULL DEFAULT 'RECALIBRATION' CHECK (decision_kind='RECALIBRATION'),
        latest_feedback_batch_id INTEGER REFERENCES campaign_feedback_batches(feedback_batch_id) ON DELETE RESTRICT,
        reference_decision_id INTEGER REFERENCES feedback_retraining_decisions(retraining_decision_id) ON DELETE RESTRICT,
        drift_lineage_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(drift_lineage_json)),
        trigger_reason TEXT NOT NULL,
        incumbent_calibration_artifact_id INTEGER,
        candidate_calibration_artifact_id INTEGER,
        metrics_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metrics_json)),
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
)


SEARCH_RECOVERY_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_search_attempts_status ON campaign_search_attempts(status, created_at, search_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_search_progress_stage ON campaign_search_progress_events(stage_code, recorded_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_calibrated_rank ON calibrated_propensity_scores(calibration_artifact_id, rank_position)",
    "CREATE INDEX IF NOT EXISTS idx_calibrated_bucket ON calibrated_propensity_scores(calibration_artifact_id, propensity_bucket, calibrated_probability DESC, person_id)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_run ON campaign_feedback_batches(search_run_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_person ON campaign_feedback_outcomes(person_id, outcome_at)",
    "CREATE INDEX IF NOT EXISTS idx_targeting_product_lookup ON targeting_product_catalog(product_id, catalog_version)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_targeting_option_catalog_current ON targeting_option_catalogs(is_current) WHERE is_current=1",
)


__all__ = ("SEARCH_RECOVERY_INDEX_STATEMENTS", "SEARCH_RECOVERY_TABLE_STATEMENTS")
