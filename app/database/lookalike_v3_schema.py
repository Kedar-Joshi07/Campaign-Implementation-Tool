"""Additive product-buyer-similarity registry for selection contract v3.

The v3 registry deliberately does not reuse probability calibration tables.
Every published profile and score generation is bound to immutable source and
method identities, while staging remains fenced and independently recoverable.
"""

from __future__ import annotations


LOOKALIKE_V3_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_profiles (
        profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
        immutable_identity_sha256 TEXT NOT NULL CHECK (
            length(immutable_identity_sha256)=64
            AND immutable_identity_sha256 NOT GLOB '*[^0-9a-f]*'),
        product_id TEXT NOT NULL CHECK (length(trim(product_id)) BETWEEN 1 AND 80),
        historical_context_sha256 TEXT NOT NULL CHECK (length(historical_context_sha256)=64),
        resolved_window_start TEXT NOT NULL,
        resolved_window_end TEXT NOT NULL,
        buyer_conversion_definition TEXT NOT NULL,
        customer_import_id INTEGER NOT NULL REFERENCES data_import_runs(import_id) ON DELETE RESTRICT,
        customer_source_checksum TEXT NOT NULL CHECK (length(customer_source_checksum)=64),
        campaign_sales_import_id INTEGER NOT NULL REFERENCES data_import_runs(import_id) ON DELETE RESTRICT,
        campaign_sales_source_checksum TEXT NOT NULL CHECK (length(campaign_sales_source_checksum)=64),
        feature_contract_sha256 TEXT NOT NULL CHECK (length(feature_contract_sha256)=64),
        score_method_version TEXT NOT NULL CHECK (score_method_version='BUYER_PROFILE_DISTANCE_V1'),
        preprocessor_contract_sha256 TEXT NOT NULL CHECK (length(preprocessor_contract_sha256)=64),
        fit_identity_sha256 TEXT NOT NULL CHECK (length(fit_identity_sha256)=64),
        holdout_identity_sha256 TEXT NOT NULL CHECK (length(holdout_identity_sha256)=64),
        split_seed INTEGER NOT NULL,
        prototype_support INTEGER NOT NULL CHECK (prototype_support > 0),
        realized_k INTEGER NOT NULL CHECK (realized_k > 0 AND realized_k <= prototype_support),
        publication_state TEXT NOT NULL CHECK (
            publication_state IN ('STAGING','BUILDING','PUBLISHED','FAILED','STALE')),
        execution_owner TEXT CHECK (execution_owner IS NULL OR length(execution_owner) BETWEEN 1 AND 128),
        execution_token TEXT CHECK (execution_token IS NULL OR (
            length(execution_token)=64 AND execution_token NOT GLOB '*[^0-9a-f]*')),
        lease_heartbeat_at TEXT,
        created_at TEXT NOT NULL,
        published_at TEXT,
        safe_error_code TEXT CHECK (safe_error_code IS NULL OR length(safe_error_code) <= 80),
        CHECK (resolved_window_start <= resolved_window_end),
        CHECK ((publication_state='PUBLISHED' AND published_at IS NOT NULL
                AND execution_owner IS NULL AND execution_token IS NULL)
            OR publication_state<>'PUBLISHED')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_profile_artifacts (
        profile_artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL REFERENCES buyer_similarity_profiles(profile_id) ON DELETE RESTRICT,
        serialization_contract_version TEXT NOT NULL CHECK (serialization_contract_version='1'),
        storage_uri TEXT NOT NULL CHECK (length(storage_uri) BETWEEN 1 AND 256),
        artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256)=64),
        profile_payload_sha256 TEXT NOT NULL CHECK (length(profile_payload_sha256)=64),
        artifact_state TEXT NOT NULL CHECK (artifact_state IN ('STAGED','PUBLISHED','STALE')),
        created_at TEXT NOT NULL,
        published_at TEXT,
        UNIQUE(profile_id, artifact_sha256),
        CHECK ((artifact_state='PUBLISHED' AND published_at IS NOT NULL)
            OR artifact_state<>'PUBLISHED')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_score_generations (
        similarity_generation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL REFERENCES buyer_similarity_profiles(profile_id) ON DELETE RESTRICT,
        product_id TEXT NOT NULL CHECK (length(trim(product_id)) BETWEEN 1 AND 80),
        composite_context_sha256 TEXT NOT NULL CHECK (length(composite_context_sha256)=64),
        profile_set_sha256 TEXT NOT NULL CHECK (length(profile_set_sha256)=64),
        demographic_import_id INTEGER NOT NULL REFERENCES data_import_runs(import_id) ON DELETE RESTRICT,
        demographic_source_checksum TEXT NOT NULL CHECK (length(demographic_source_checksum)=64),
        reference_date TEXT NOT NULL,
        scorer_contract_version TEXT NOT NULL CHECK (scorer_contract_version='1'),
        score_method_version TEXT NOT NULL CHECK (score_method_version='BUYER_PROFILE_DISTANCE_V1'),
        publication_state TEXT NOT NULL CHECK (
            publication_state IN ('STAGING','BUILDING','PUBLISHED','FAILED','STALE')),
        expected_person_count INTEGER NOT NULL CHECK (expected_person_count >= 0),
        published_person_count INTEGER CHECK (published_person_count IS NULL OR published_person_count >= 0),
        execution_owner TEXT CHECK (execution_owner IS NULL OR length(execution_owner) BETWEEN 1 AND 128),
        execution_token TEXT CHECK (execution_token IS NULL OR (
            length(execution_token)=64 AND execution_token NOT GLOB '*[^0-9a-f]*')),
        lease_heartbeat_at TEXT,
        created_at TEXT NOT NULL,
        published_at TEXT,
        safe_error_code TEXT CHECK (safe_error_code IS NULL OR length(safe_error_code) <= 80),
        UNIQUE(profile_id, demographic_import_id, composite_context_sha256),
        CHECK ((publication_state='PUBLISHED'
                AND published_at IS NOT NULL
                AND published_person_count=expected_person_count
                AND execution_owner IS NULL AND execution_token IS NULL)
            OR publication_state<>'PUBLISHED')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_generation_stages (
        similarity_generation_id INTEGER NOT NULL REFERENCES buyer_similarity_score_generations(similarity_generation_id) ON DELETE RESTRICT,
        stage_sequence INTEGER NOT NULL CHECK (stage_sequence > 0),
        stage_code TEXT NOT NULL CHECK (length(stage_code) BETWEEN 1 AND 80),
        status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
        processed_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
        total_count INTEGER CHECK (total_count IS NULL OR total_count >= processed_count),
        checkpoint_person_id TEXT,
        execution_token TEXT NOT NULL CHECK (length(execution_token)=64),
        started_at TEXT,
        heartbeat_at TEXT,
        completed_at TEXT,
        safe_message TEXT NOT NULL CHECK (length(safe_message) BETWEEN 1 AND 500),
        PRIMARY KEY(similarity_generation_id, stage_sequence),
        UNIQUE(similarity_generation_id, stage_code)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_score_stage (
        similarity_generation_id INTEGER NOT NULL REFERENCES buyer_similarity_score_generations(similarity_generation_id) ON DELETE RESTRICT,
        person_id TEXT NOT NULL CHECK (length(trim(person_id)) BETWEEN 1 AND 128),
        is_valid INTEGER NOT NULL CHECK (is_valid IN (0,1)),
        buyer_similarity_score REAL,
        feature_coverage REAL NOT NULL CHECK (feature_coverage BETWEEN 0 AND 1),
        prototype_key TEXT CHECK (prototype_key IS NULL OR length(prototype_key) BETWEEN 1 AND 80),
        invalid_reason_code TEXT CHECK (invalid_reason_code IS NULL OR length(invalid_reason_code) BETWEEN 1 AND 80),
        execution_token TEXT NOT NULL CHECK (length(execution_token)=64),
        PRIMARY KEY(similarity_generation_id, person_id),
        CHECK ((is_valid=1 AND buyer_similarity_score IS NOT NULL
                    AND buyer_similarity_score BETWEEN 0 AND 1
                    AND feature_coverage>=0.80
                    AND invalid_reason_code IS NULL AND prototype_key IS NOT NULL)
            OR (is_valid=0 AND buyer_similarity_score IS NULL
                    AND invalid_reason_code IS NOT NULL AND prototype_key IS NULL))
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_scores (
        similarity_generation_id INTEGER NOT NULL REFERENCES buyer_similarity_score_generations(similarity_generation_id) ON DELETE RESTRICT,
        person_id TEXT NOT NULL CHECK (length(trim(person_id)) BETWEEN 1 AND 128),
        product_id TEXT NOT NULL CHECK (length(trim(product_id)) BETWEEN 1 AND 80),
        is_valid INTEGER NOT NULL CHECK (is_valid IN (0,1)),
        buyer_similarity_score REAL,
        similarity_tier TEXT CHECK (similarity_tier IN (
            'VERY_STRONG','STRONG','GOOD','BROAD','EXPLORATORY','BELOW_MINIMUM')),
        feature_coverage REAL NOT NULL CHECK (feature_coverage BETWEEN 0 AND 1),
        prototype_key TEXT CHECK (prototype_key IS NULL OR length(prototype_key) BETWEEN 1 AND 80),
        invalid_reason_code TEXT CHECK (invalid_reason_code IS NULL OR length(invalid_reason_code) BETWEEN 1 AND 80),
        score_method_version TEXT NOT NULL CHECK (score_method_version='BUYER_PROFILE_DISTANCE_V1'),
        execution_token TEXT NOT NULL CHECK (
            length(execution_token)=64 AND execution_token NOT GLOB '*[^0-9a-f]*'),
        published_at TEXT NOT NULL,
        PRIMARY KEY(similarity_generation_id, person_id),
        CHECK ((is_valid=1 AND buyer_similarity_score IS NOT NULL
                    AND buyer_similarity_score BETWEEN 0 AND 1
                    AND similarity_tier IS NOT NULL AND feature_coverage>=0.80
                    AND invalid_reason_code IS NULL AND prototype_key IS NOT NULL)
            OR (is_valid=0 AND buyer_similarity_score IS NULL
                    AND similarity_tier IS NULL
                    AND invalid_reason_code IS NOT NULL AND prototype_key IS NULL))
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_generation_attestations (
        attestation_key_sha256 TEXT PRIMARY KEY CHECK (length(attestation_key_sha256)=64),
        similarity_generation_id INTEGER NOT NULL UNIQUE
            REFERENCES buyer_similarity_score_generations(similarity_generation_id)
            ON DELETE RESTRICT,
        verification_contract_version TEXT NOT NULL CHECK (verification_contract_version='1'),
        integrity_contract_version TEXT NOT NULL CHECK (integrity_contract_version='1'),
        profile_artifact_sha256 TEXT NOT NULL CHECK (length(profile_artifact_sha256)=64),
        demographic_import_id INTEGER NOT NULL REFERENCES data_import_runs(import_id) ON DELETE RESTRICT,
        demographic_source_checksum TEXT NOT NULL CHECK (length(demographic_source_checksum)=64),
        expected_person_count INTEGER NOT NULL CHECK (expected_person_count >= 0),
        verified_row_count INTEGER NOT NULL CHECK (verified_row_count >= 0),
        valid_score_count INTEGER NOT NULL CHECK (valid_score_count >= 0),
        invalid_score_count INTEGER NOT NULL CHECK (invalid_score_count >= 0),
        verified_facts_json TEXT NOT NULL CHECK (json_valid(verified_facts_json)),
        verified_facts_sha256 TEXT NOT NULL CHECK (length(verified_facts_sha256)=64),
        failure_codes_json TEXT NOT NULL CHECK (
            json_valid(failure_codes_json) AND json_type(failure_codes_json)='array'),
        verification_status TEXT NOT NULL CHECK (verification_status IN ('VERIFIED','FAILED')),
        verified_at TEXT NOT NULL,
        CHECK (verified_row_count = valid_score_count + invalid_score_count),
        CHECK ((verification_status='VERIFIED' AND verified_row_count=expected_person_count)
            OR verification_status='FAILED')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_similarity_result_snapshots (
        similarity_result_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        result_membership_contract_version TEXT NOT NULL CHECK (result_membership_contract_version='3'),
        similarity_generation_id INTEGER NOT NULL REFERENCES buyer_similarity_score_generations(similarity_generation_id) ON DELETE RESTRICT,
        selection_contract_version TEXT NOT NULL CHECK (selection_contract_version='3'),
        score_semantics TEXT NOT NULL CHECK (score_semantics='PRODUCT_BUYER_SIMILARITY'),
        score_method_version TEXT NOT NULL CHECK (score_method_version='BUYER_PROFILE_DISTANCE_V1'),
        similarity_minimum REAL NOT NULL CHECK (similarity_minimum IN (0.50,0.60,0.70,0.80,0.90)),
        threshold_predicate TEXT NOT NULL CHECK (threshold_predicate='GREATER_THAN_OR_EQUAL'),
        product_match_policy TEXT NOT NULL CHECK (product_match_policy='ANY_SELECTED_PRODUCT_MAX_V1'),
        profile_set_sha256 TEXT NOT NULL CHECK (length(profile_set_sha256)=64),
        composite_context_sha256 TEXT NOT NULL CHECK (length(composite_context_sha256)=64),
        targeting_criteria_sha256 TEXT NOT NULL CHECK (length(targeting_criteria_sha256)=64),
        filter_branches_sha256 TEXT NOT NULL CHECK (length(filter_branches_sha256)=64),
        selection_mode TEXT NOT NULL CHECK (selection_mode IN ('ALL_MATCHING','TOP_N')),
        target_count INTEGER,
        result_cache_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(result_cache_key_sha256)=64),
        resolved_count INTEGER NOT NULL CHECK (resolved_count >= 0),
        storage_format TEXT NOT NULL CHECK (storage_format IN ('CSV_GZIP','JSONL_GZIP','PARQUET')),
        storage_uri TEXT NOT NULL CHECK (length(storage_uri) BETWEEN 1 AND 256),
        snapshot_sha256 TEXT NOT NULL CHECK (length(snapshot_sha256)=64),
        publication_cutoff TEXT NOT NULL,
        currentness_state TEXT NOT NULL CHECK (currentness_state IN ('CURRENT','STALE','UNVERIFIED')),
        created_at TEXT NOT NULL,
        last_verified_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        CHECK ((selection_mode='ALL_MATCHING' AND target_count IS NULL)
            OR (selection_mode='TOP_N' AND target_count > 0)),
        CHECK (target_count IS NULL OR resolved_count <= target_count)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS similarity_preflight_cache (
        cache_key_sha256 TEXT PRIMARY KEY CHECK (length(cache_key_sha256)=64),
        selection_contract_version TEXT NOT NULL CHECK (selection_contract_version='3'),
        score_semantics TEXT NOT NULL CHECK (score_semantics='PRODUCT_BUYER_SIMILARITY'),
        score_method_version TEXT NOT NULL CHECK (score_method_version='BUYER_PROFILE_DISTANCE_V1'),
        similarity_minimum REAL NOT NULL CHECK (similarity_minimum IN (0.50,0.60,0.70,0.80,0.90)),
        threshold_predicate TEXT NOT NULL CHECK (threshold_predicate='GREATER_THAN_OR_EQUAL'),
        product_match_policy TEXT NOT NULL CHECK (product_match_policy='ANY_SELECTED_PRODUCT_MAX_V1'),
        criteria_sha256 TEXT NOT NULL CHECK (length(criteria_sha256)=64),
        filter_branches_sha256 TEXT NOT NULL CHECK (length(filter_branches_sha256)=64),
        catalog_version TEXT NOT NULL CHECK (length(catalog_version)=64),
        source_identity_sha256 TEXT NOT NULL CHECK (length(source_identity_sha256)=64),
        profile_ids_json TEXT NOT NULL CHECK (json_valid(profile_ids_json) AND json_type(profile_ids_json)='array'),
        profile_set_sha256 TEXT CHECK (profile_set_sha256 IS NULL OR length(profile_set_sha256)=64),
        composite_context_sha256 TEXT NOT NULL CHECK (length(composite_context_sha256)=64),
        similarity_generation_id INTEGER REFERENCES buyer_similarity_score_generations(similarity_generation_id) ON DELETE RESTRICT,
        demographic_eligible_count INTEGER NOT NULL CHECK (demographic_eligible_count >= 0),
        valid_similarity_count INTEGER CHECK (valid_similarity_count IS NULL OR valid_similarity_count >= 0),
        invalid_similarity_count INTEGER CHECK (invalid_similarity_count IS NULL OR invalid_similarity_count >= 0),
        similarity_qualifying_count INTEGER CHECK (similarity_qualifying_count IS NULL OR similarity_qualifying_count >= 0),
        selected_count INTEGER CHECK (selected_count IS NULL OR selected_count >= 0),
        similarity_currentness TEXT NOT NULL CHECK (similarity_currentness IN ('CURRENT','STALE','UNVERIFIED','NOT_AVAILABLE','BUILDING')),
        similarity_eligibility TEXT NOT NULL CHECK (similarity_eligibility IN ('ELIGIBLE','NOT_ELIGIBLE')),
        reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 80),
        build_available INTEGER NOT NULL CHECK (build_available IN (0,1)),
        source_snapshot_version TEXT NOT NULL,
        publication_cutoff TEXT,
        currentness_state TEXT NOT NULL CHECK (currentness_state IN ('CURRENT','STALE','UNVERIFIED')),
        created_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        CHECK ((similarity_generation_id IS NULL
                    AND valid_similarity_count IS NULL
                    AND invalid_similarity_count IS NULL
                    AND similarity_qualifying_count IS NULL
                    AND selected_count IS NULL)
            OR similarity_generation_id IS NOT NULL)
    )
    """,
)


LOOKALIKE_V3_INDEX_STATEMENTS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_buyer_similarity_one_published_profile ON buyer_similarity_profiles(immutable_identity_sha256) WHERE publication_state='PUBLISHED'",
    "CREATE INDEX IF NOT EXISTS idx_buyer_similarity_profile_product ON buyer_similarity_profiles(product_id,publication_state,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_buyer_similarity_generation_profile ON buyer_similarity_score_generations(profile_id,publication_state,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_buyer_similarity_score_lookup ON buyer_similarity_scores(similarity_generation_id,is_valid,buyer_similarity_score DESC,person_id)",
    "CREATE INDEX IF NOT EXISTS idx_buyer_similarity_attestation_generation ON buyer_similarity_generation_attestations(similarity_generation_id,verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_similarity_preflight_generation ON similarity_preflight_cache(similarity_generation_id,currentness_state)",
)


LOOKALIKE_V3_TRIGGER_STATEMENTS = (
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_score_stage_fenced_insert
       BEFORE INSERT ON buyer_similarity_score_stage
       WHEN NOT EXISTS (
           SELECT 1 FROM buyer_similarity_score_generations g
           WHERE g.similarity_generation_id=NEW.similarity_generation_id
             AND g.publication_state='BUILDING'
             AND g.execution_token=NEW.execution_token)
       BEGIN SELECT RAISE(ABORT,'similarity stage write has a stale fence'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_score_stage_fenced_update
       BEFORE UPDATE ON buyer_similarity_score_stage
       WHEN NEW.execution_token<>OLD.execution_token OR NOT EXISTS (
           SELECT 1 FROM buyer_similarity_score_generations g
           WHERE g.similarity_generation_id=OLD.similarity_generation_id
             AND g.publication_state='BUILDING'
             AND g.execution_token=OLD.execution_token)
       BEGIN SELECT RAISE(ABORT,'similarity stage write has a stale fence'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_score_stage_fenced_delete
       BEFORE DELETE ON buyer_similarity_score_stage
       WHEN NOT EXISTS (
           SELECT 1 FROM buyer_similarity_score_generations g
           WHERE g.similarity_generation_id=OLD.similarity_generation_id
             AND g.publication_state='BUILDING'
             AND g.execution_token=OLD.execution_token)
       BEGIN SELECT RAISE(ABORT,'similarity stage write has a stale fence'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_scores_published_insert
       BEFORE INSERT ON buyer_similarity_scores
       WHEN NOT EXISTS (
           SELECT 1 FROM buyer_similarity_score_generations g
           WHERE g.similarity_generation_id=NEW.similarity_generation_id
             AND g.publication_state='BUILDING'
             AND g.execution_token=NEW.execution_token)
       BEGIN SELECT RAISE(ABORT,'similarity generation is not fenced for publication'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_scores_no_update
       BEFORE UPDATE ON buyer_similarity_scores
       BEGIN SELECT RAISE(ABORT,'published similarity scores are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_scores_no_delete
       BEFORE DELETE ON buyer_similarity_scores
       BEGIN SELECT RAISE(ABORT,'published similarity scores are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS buyer_similarity_profile_published_immutable
       BEFORE UPDATE ON buyer_similarity_profiles
       WHEN OLD.publication_state='PUBLISHED' AND (
           NEW.immutable_identity_sha256<>OLD.immutable_identity_sha256
           OR NEW.product_id<>OLD.product_id
           OR NEW.historical_context_sha256<>OLD.historical_context_sha256
           OR NEW.resolved_window_start<>OLD.resolved_window_start
           OR NEW.resolved_window_end<>OLD.resolved_window_end
           OR NEW.buyer_conversion_definition<>OLD.buyer_conversion_definition
           OR NEW.customer_import_id<>OLD.customer_import_id
           OR NEW.customer_source_checksum<>OLD.customer_source_checksum
           OR NEW.campaign_sales_import_id<>OLD.campaign_sales_import_id
           OR NEW.campaign_sales_source_checksum<>OLD.campaign_sales_source_checksum
           OR NEW.feature_contract_sha256<>OLD.feature_contract_sha256
           OR NEW.score_method_version<>OLD.score_method_version
           OR NEW.preprocessor_contract_sha256<>OLD.preprocessor_contract_sha256
           OR NEW.fit_identity_sha256<>OLD.fit_identity_sha256
           OR NEW.holdout_identity_sha256<>OLD.holdout_identity_sha256
           OR NEW.split_seed<>OLD.split_seed
           OR NEW.prototype_support<>OLD.prototype_support
           OR NEW.realized_k<>OLD.realized_k)
       BEGIN SELECT RAISE(ABORT,'published similarity profile identity is immutable'); END""",
)


__all__ = (
    "LOOKALIKE_V3_INDEX_STATEMENTS",
    "LOOKALIKE_V3_TABLE_STATEMENTS",
    "LOOKALIKE_V3_TRIGGER_STATEMENTS",
)
