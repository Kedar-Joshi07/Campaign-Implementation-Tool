"""Additive Phase 11 registry DDL; no analytical membership or contact PII."""

from __future__ import annotations


CAMPAIGN_SEARCH_RUN_COLUMNS = (
    "search_run_id", "search_run_contract_version", "campaign_name", "description",
    "planned_launch_date", "targeting_context_id", "modeling_context_sha256",
    "targeting_criteria_json", "targeting_criteria_sha256", "filter_branches_json",
    "filter_branches_sha256", "selection_mode", "target_count", "delivery_channel",
    "export_profile", "generation_id", "analysis_run_id", "model_run_id",
    "scoring_run_id", "result_snapshot_id", "result_source", "status",
    "selected_count", "created_at", "started_at", "completed_at",
    "processing_seconds", "created_by_user_id", "safe_error_message",
)
CAMPAIGN_RESULT_SNAPSHOT_COLUMNS = (
    "result_snapshot_id", "result_membership_contract_version", "generation_id",
    "targeting_criteria_sha256", "filter_branches_sha256", "selection_mode",
    "target_count", "result_cache_key_sha256", "resolved_count", "storage_format",
    "storage_uri", "snapshot_sha256", "created_at", "last_verified_at",
    "last_used_at", "currentness_state",
)
CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS = (
    "export_event_id", "search_run_id", "snapshot_id", "export_contract_version",
    "export_profile", "profile_version", "status", "selected_count",
    "deliverable_count", "undeliverable_count", "row_count", "csv_sha256",
    "started_at", "completed_at", "currentness_state", "safe_error_message",
)
CAMPAIGN_SEARCH_RUN_RUNTIME_COLUMNS = (
    "search_run_id", "lifecycle_contract_version", "lifecycle_status",
    "stage_code", "stage_label", "progress_percent", "processed_count",
    "total_count", "progress_unit", "status_message", "failure_code",
    "failure_category", "failure_summary", "resolution_steps_json",
    "retryable", "created_at", "processing_started_at", "updated_at",
    "heartbeat_at", "state_version",
)

SEARCH_RUN_LIFECYCLE_STATUSES = (
    "QUEUED", "PROCESSING", "PAUSE_REQUESTED", "PAUSED",
    "STOP_REQUESTED", "STOPPED", "RESTART_REQUESTED",
    "COMPLETED", "BLOCKED", "FAILED",
)


def _digest(name: str) -> str:
    return (
        f"{name} TEXT NOT NULL CHECK (length({name}) = 64 "
        f"AND {name} NOT GLOB '*[^0-9a-f]*')"
    )


_SELECTION_CHECK = """
    CHECK ((selection_mode = 'ALL_MATCHING' AND target_count IS NULL)
        OR (selection_mode = 'TOP_N' AND target_count > 0 AND target_count IS NOT NULL))
"""

PHASE_ELEVEN_CREATE_TABLE_STATEMENTS = (
    f"""
    CREATE TABLE IF NOT EXISTS campaign_result_snapshots (
        result_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        result_membership_contract_version TEXT NOT NULL CHECK (result_membership_contract_version = '1'),
        generation_id INTEGER NOT NULL REFERENCES phase10_intelligence_generations(generation_id) ON DELETE RESTRICT,
        {_digest('targeting_criteria_sha256')},
        {_digest('filter_branches_sha256')},
        selection_mode TEXT NOT NULL CHECK (selection_mode IN ('ALL_MATCHING', 'TOP_N')),
        target_count INTEGER,
        {_digest('result_cache_key_sha256')} UNIQUE,
        resolved_count INTEGER NOT NULL CHECK (resolved_count >= 0),
        storage_format TEXT NOT NULL CHECK (storage_format IN ('CSV_GZIP', 'JSONL_GZIP', 'PARQUET')),
        storage_uri TEXT NOT NULL CHECK (length(storage_uri) BETWEEN 1 AND 256),
        {_digest('snapshot_sha256')},
        created_at TEXT NOT NULL,
        last_verified_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        currentness_state TEXT NOT NULL CHECK (currentness_state IN ('CURRENT', 'STALE', 'UNVERIFIED')),
        {_SELECTION_CHECK},
        CHECK (target_count IS NULL OR resolved_count <= target_count)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS campaign_search_runs (
        search_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_contract_version TEXT NOT NULL CHECK (search_run_contract_version = '1'),
        campaign_name TEXT NOT NULL CHECK (length(trim(campaign_name)) BETWEEN 1 AND 200),
        description TEXT CHECK (description IS NULL OR length(description) <= 2000),
        planned_launch_date TEXT,
        targeting_context_id INTEGER NOT NULL REFERENCES campaign_targeting_contexts(targeting_context_id) ON DELETE RESTRICT,
        {_digest('modeling_context_sha256')},
        targeting_criteria_json TEXT NOT NULL CHECK (json_valid(targeting_criteria_json) AND json_type(targeting_criteria_json) = 'object'),
        {_digest('targeting_criteria_sha256')},
        filter_branches_json TEXT NOT NULL CHECK (json_valid(filter_branches_json) AND json_type(filter_branches_json) = 'array' AND json_array_length(filter_branches_json) BETWEEN 1 AND 49),
        {_digest('filter_branches_sha256')},
        selection_mode TEXT NOT NULL CHECK (selection_mode IN ('ALL_MATCHING', 'TOP_N')),
        target_count INTEGER,
        delivery_channel TEXT NOT NULL,
        export_profile TEXT NOT NULL,
        generation_id INTEGER REFERENCES phase10_intelligence_generations(generation_id) ON DELETE RESTRICT,
        analysis_run_id INTEGER REFERENCES historical_analysis_runs(analysis_run_id) ON DELETE RESTRICT,
        model_run_id INTEGER REFERENCES model_runs(model_run_id) ON DELETE RESTRICT,
        scoring_run_id INTEGER REFERENCES scoring_runs(scoring_run_id) ON DELETE RESTRICT,
        result_snapshot_id INTEGER REFERENCES campaign_result_snapshots(result_snapshot_id) ON DELETE RESTRICT,
        result_source TEXT CHECK (result_source IN ('EXACT_RESULT_REUSE', 'INTELLIGENCE_REUSE', 'NEW_INTELLIGENCE_BUILD')),
        status TEXT NOT NULL CHECK (status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'BLOCKED', 'FAILED')),
        selected_count INTEGER CHECK (selected_count >= 0),
        created_at TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        processing_seconds REAL CHECK (processing_seconds >= 0),
        created_by_user_id TEXT,
        safe_error_message TEXT CHECK (safe_error_message IS NULL OR length(safe_error_message) <= 500),
        {_SELECTION_CHECK},
        CHECK (target_count IS NULL OR selected_count IS NULL OR selected_count <= target_count),
        CHECK ((status IN ('QUEUED', 'PROCESSING') AND completed_at IS NULL AND processing_seconds IS NULL)
            OR (status IN ('COMPLETED', 'BLOCKED', 'FAILED') AND completed_at IS NOT NULL AND processing_seconds IS NOT NULL)),
        CHECK (status != 'COMPLETED' OR (generation_id IS NOT NULL AND analysis_run_id IS NOT NULL
            AND model_run_id IS NOT NULL AND scoring_run_id IS NOT NULL AND result_snapshot_id IS NOT NULL
            AND result_source IS NOT NULL AND selected_count IS NOT NULL AND safe_error_message IS NULL)),
        CHECK (status NOT IN ('BLOCKED', 'FAILED') OR safe_error_message IS NOT NULL)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_result_export_events (
        export_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_id INTEGER NOT NULL REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
        snapshot_id INTEGER NOT NULL REFERENCES campaign_result_snapshots(result_snapshot_id) ON DELETE RESTRICT,
        export_contract_version TEXT NOT NULL CHECK (export_contract_version = '1'),
        export_profile TEXT NOT NULL,
        profile_version TEXT NOT NULL CHECK (profile_version = '1'),
        status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'ABORTED')),
        selected_count INTEGER NOT NULL CHECK (selected_count >= 0),
        deliverable_count INTEGER NOT NULL CHECK (deliverable_count >= 0),
        undeliverable_count INTEGER NOT NULL CHECK (undeliverable_count >= 0),
        row_count INTEGER NOT NULL CHECK (row_count >= 0 AND row_count <= deliverable_count),
        csv_sha256 TEXT CHECK (csv_sha256 IS NULL OR (length(csv_sha256) = 64 AND csv_sha256 NOT GLOB '*[^0-9a-f]*')),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        currentness_state TEXT NOT NULL CHECK (currentness_state IN ('CURRENT', 'STALE', 'UNVERIFIED')),
        safe_error_message TEXT CHECK (safe_error_message IS NULL OR length(safe_error_message) <= 500),
        CHECK (selected_count = deliverable_count + undeliverable_count),
        CHECK ((status = 'RUNNING' AND completed_at IS NULL)
            OR (status != 'RUNNING' AND completed_at IS NOT NULL)),
        CHECK (status != 'COMPLETED' OR (row_count = deliverable_count AND csv_sha256 IS NOT NULL
            AND currentness_state = 'CURRENT' AND safe_error_message IS NULL)),
        CHECK (status NOT IN ('FAILED', 'ABORTED') OR safe_error_message IS NOT NULL)
    )
    """,
)

PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS = {
    "idx_campaign_search_runs_created": "CREATE INDEX IF NOT EXISTS idx_campaign_search_runs_created ON campaign_search_runs(created_at DESC, search_run_id DESC)",
    "idx_campaign_search_runs_status": "CREATE INDEX IF NOT EXISTS idx_campaign_search_runs_status ON campaign_search_runs(status, created_at DESC, search_run_id DESC)",
    "idx_campaign_search_runs_generation": "CREATE INDEX IF NOT EXISTS idx_campaign_search_runs_generation ON campaign_search_runs(generation_id, search_run_id DESC)",
    "idx_campaign_search_runs_snapshot": "CREATE INDEX IF NOT EXISTS idx_campaign_search_runs_snapshot ON campaign_search_runs(result_snapshot_id, search_run_id DESC)",
    "idx_campaign_search_runs_context": "CREATE INDEX IF NOT EXISTS idx_campaign_search_runs_context ON campaign_search_runs(targeting_context_id, search_run_id DESC)",
    # UNIQUE result_cache_key_sha256 also supplies the exact-key lookup index.
    "idx_campaign_result_snapshots_generation": "CREATE INDEX IF NOT EXISTS idx_campaign_result_snapshots_generation ON campaign_result_snapshots(generation_id, created_at DESC, result_snapshot_id DESC)",
    "idx_campaign_result_snapshots_created": "CREATE INDEX IF NOT EXISTS idx_campaign_result_snapshots_created ON campaign_result_snapshots(created_at DESC, result_snapshot_id DESC)",
    "idx_campaign_result_export_events_search": "CREATE INDEX IF NOT EXISTS idx_campaign_result_export_events_search ON campaign_result_export_events(search_run_id, started_at DESC, export_event_id DESC)",
    "idx_campaign_result_export_events_snapshot": "CREATE INDEX IF NOT EXISTS idx_campaign_result_export_events_snapshot ON campaign_result_export_events(snapshot_id, started_at DESC, export_event_id DESC)",
    "idx_campaign_result_export_events_status": "CREATE INDEX IF NOT EXISTS idx_campaign_result_export_events_status ON campaign_result_export_events(status, started_at DESC, export_event_id DESC)",
}


PHASE_ELEVEN_RUNTIME_CREATE_TABLE_STATEMENT = """
    CREATE TABLE IF NOT EXISTS campaign_search_run_runtime (
        search_run_id INTEGER PRIMARY KEY REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
        lifecycle_contract_version TEXT NOT NULL CHECK (lifecycle_contract_version = '1'),
        lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
            'QUEUED', 'PROCESSING', 'PAUSE_REQUESTED', 'PAUSED',
            'STOP_REQUESTED', 'STOPPED', 'RESTART_REQUESTED',
            'COMPLETED', 'BLOCKED', 'FAILED'
        )),
        stage_code TEXT NOT NULL CHECK (length(stage_code) BETWEEN 1 AND 80),
        stage_label TEXT NOT NULL CHECK (length(stage_label) BETWEEN 1 AND 200),
        progress_percent INTEGER NOT NULL CHECK (progress_percent BETWEEN 0 AND 100),
        processed_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
        total_count INTEGER CHECK (total_count IS NULL OR total_count >= 0),
        progress_unit TEXT NOT NULL CHECK (length(progress_unit) BETWEEN 1 AND 40),
        status_message TEXT NOT NULL CHECK (length(status_message) BETWEEN 1 AND 1000),
        failure_code TEXT CHECK (failure_code IS NULL OR length(failure_code) BETWEEN 1 AND 80),
        failure_category TEXT CHECK (failure_category IS NULL OR length(failure_category) BETWEEN 1 AND 80),
        failure_summary TEXT CHECK (failure_summary IS NULL OR length(failure_summary) BETWEEN 1 AND 1000),
        resolution_steps_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(resolution_steps_json) AND json_type(resolution_steps_json) = 'array'
                AND json_array_length(resolution_steps_json) <= 8),
        retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
        created_at TEXT NOT NULL,
        processing_started_at TEXT,
        updated_at TEXT NOT NULL,
        heartbeat_at TEXT,
        state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
        CHECK (total_count IS NULL OR processed_count <= total_count),
        CHECK (lifecycle_status != 'COMPLETED' OR progress_percent = 100),
        CHECK (lifecycle_status NOT IN ('BLOCKED', 'FAILED') OR
            (failure_code IS NOT NULL AND failure_category IS NOT NULL
             AND failure_summary IS NOT NULL AND json_array_length(resolution_steps_json) >= 1))
    )
"""

PHASE_ELEVEN_RUNTIME_INDEX_STATEMENTS = {
    "idx_campaign_search_run_runtime_status": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_run_runtime_status "
        "ON campaign_search_run_runtime(lifecycle_status, updated_at DESC, search_run_id DESC)"
    ),
    "idx_campaign_search_run_runtime_heartbeat": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_run_runtime_heartbeat "
        "ON campaign_search_run_runtime(heartbeat_at, search_run_id) "
        "WHERE heartbeat_at IS NOT NULL"
    ),
}

PHASE_ELEVEN_RUNTIME_TRIGGER_STATEMENTS = (
    """CREATE TRIGGER IF NOT EXISTS campaign_search_run_runtime_create
        AFTER INSERT ON campaign_search_runs
        BEGIN
            INSERT INTO campaign_search_run_runtime (
                search_run_id, lifecycle_contract_version, lifecycle_status,
                stage_code, stage_label, progress_percent, processed_count,
                total_count, progress_unit, status_message,
                failure_code, failure_category, failure_summary,
                resolution_steps_json, retryable, created_at,
                processing_started_at, updated_at,
                state_version
            ) VALUES (
                NEW.search_run_id, '1', NEW.status, NEW.status,
                CASE NEW.status
                    WHEN 'QUEUED' THEN 'Waiting to start'
                    WHEN 'PROCESSING' THEN 'Recovering saved work'
                    WHEN 'COMPLETED' THEN 'Result ready'
                    WHEN 'BLOCKED' THEN 'Search blocked'
                    ELSE 'Search failed'
                END,
                CASE NEW.status WHEN 'COMPLETED' THEN 100
                    WHEN 'PROCESSING' THEN 2 ELSE 0 END,
                COALESCE(NEW.selected_count, 0),
                CASE WHEN NEW.selection_mode='TOP_N' THEN NEW.target_count
                    ELSE NEW.selected_count END,
                'potential customers',
                CASE NEW.status
                    WHEN 'QUEUED' THEN 'Saved and waiting to prepare targeting intelligence.'
                    WHEN 'PROCESSING' THEN 'Recovering this search from durable state.'
                    WHEN 'COMPLETED' THEN 'Potential-customer results are ready.'
                    WHEN 'BLOCKED' THEN 'This search cannot proceed with the current targeting intelligence.'
                    ELSE 'The search could not be completed. Please try again.'
                END,
                CASE WHEN NEW.status='BLOCKED' THEN 'LEGACY_BLOCKED'
                    WHEN NEW.status='FAILED' THEN 'LEGACY_FAILED' END,
                CASE WHEN NEW.status='BLOCKED' THEN 'TARGETING_INTELLIGENCE'
                    WHEN NEW.status='FAILED' THEN 'PROCESSING_FAILURE' END,
                CASE WHEN NEW.status IN ('BLOCKED','FAILED')
                    THEN NEW.safe_error_message END,
                CASE WHEN NEW.status='BLOCKED'
                    THEN '["Review the saved targeting criteria and available campaign history."]'
                    WHEN NEW.status='FAILED'
                    THEN '["Try the search again after the system is available."]'
                    ELSE '[]' END,
                CASE WHEN NEW.status IN ('BLOCKED','FAILED') THEN 1 ELSE 0 END,
                NEW.created_at,
                CASE WHEN NEW.status != 'QUEUED' THEN NEW.started_at END,
                COALESCE(NEW.completed_at, NEW.started_at, NEW.created_at), 1
            );
        END""",
    """CREATE TRIGGER IF NOT EXISTS campaign_search_run_runtime_identity
        BEFORE UPDATE ON campaign_search_run_runtime
        WHEN NEW.search_run_id IS NOT OLD.search_run_id
          OR NEW.lifecycle_contract_version IS NOT OLD.lifecycle_contract_version
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN SELECT RAISE(ABORT, 'immutable search runtime identity'); END""",
    """CREATE TRIGGER IF NOT EXISTS campaign_search_run_runtime_transition
        BEFORE UPDATE ON campaign_search_run_runtime
        WHEN NEW.lifecycle_status != OLD.lifecycle_status AND NOT (
            (OLD.lifecycle_status = 'QUEUED' AND NEW.lifecycle_status IN
                ('PROCESSING','PAUSE_REQUESTED','STOP_REQUESTED','STOPPED','BLOCKED','FAILED')) OR
            (OLD.lifecycle_status = 'PROCESSING' AND NEW.lifecycle_status IN
                ('PAUSE_REQUESTED','STOP_REQUESTED','RESTART_REQUESTED','COMPLETED','BLOCKED','FAILED')) OR
            (OLD.lifecycle_status = 'PAUSE_REQUESTED' AND NEW.lifecycle_status IN
                ('PROCESSING','PAUSED','STOP_REQUESTED','STOPPED','FAILED')) OR
            (OLD.lifecycle_status = 'PAUSED' AND NEW.lifecycle_status IN
                ('PROCESSING','STOP_REQUESTED','RESTART_REQUESTED','STOPPED','FAILED')) OR
            (OLD.lifecycle_status = 'STOP_REQUESTED' AND NEW.lifecycle_status IN
                ('STOPPED','FAILED')) OR
            (OLD.lifecycle_status = 'RESTART_REQUESTED' AND NEW.lifecycle_status IN
                ('STOPPED','FAILED'))
        )
        BEGIN SELECT RAISE(ABORT, 'invalid search runtime transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS campaign_search_run_runtime_no_delete
        BEFORE DELETE ON campaign_search_run_runtime
        BEGIN SELECT RAISE(ABORT, 'search runtime history cannot be deleted'); END""",
)


def _immutable_trigger(table: str, columns: tuple[str, ...], mutable: set[str]) -> str:
    immutable = [column for column in columns if column not in mutable]
    condition = " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in immutable)
    return f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_identity BEFORE UPDATE ON {table}
        WHEN {condition} BEGIN SELECT RAISE(ABORT, 'immutable registry identity'); END"""


PHASE_ELEVEN_TRIGGER_STATEMENTS = (
    _immutable_trigger("campaign_search_runs", CAMPAIGN_SEARCH_RUN_COLUMNS, {
        "generation_id", "analysis_run_id", "model_run_id", "scoring_run_id",
        "result_snapshot_id", "result_source", "status", "selected_count",
        "completed_at", "processing_seconds", "safe_error_message",
    }),
    _immutable_trigger("campaign_result_snapshots", CAMPAIGN_RESULT_SNAPSHOT_COLUMNS, {
        "last_verified_at", "last_used_at", "currentness_state",
    }),
    _immutable_trigger("campaign_result_export_events", CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS, {
        "status", "row_count", "csv_sha256", "completed_at", "currentness_state", "safe_error_message",
    }),
    """CREATE TRIGGER IF NOT EXISTS campaign_search_runs_terminal BEFORE UPDATE ON campaign_search_runs
        WHEN OLD.status IN ('COMPLETED', 'BLOCKED', 'FAILED') OR (OLD.status = 'PROCESSING' AND NEW.status = 'QUEUED')
        BEGIN SELECT RAISE(ABORT, 'invalid search transition or terminal mutation'); END""",
    """CREATE TRIGGER IF NOT EXISTS campaign_result_export_events_terminal BEFORE UPDATE ON campaign_result_export_events
        WHEN OLD.status != 'RUNNING'
        BEGIN SELECT RAISE(ABORT, 'terminal export audit is immutable'); END""",
    *(
        f"""CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT, 'registry history cannot be deleted'); END"""
        for table in ("campaign_search_runs", "campaign_result_snapshots", "campaign_result_export_events")
    ),
    *(
        f"""CREATE TRIGGER IF NOT EXISTS campaign_search_runs_snapshot_{operation.lower()}
        BEFORE {operation} ON campaign_search_runs WHEN NEW.result_snapshot_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM campaign_result_snapshots s
            JOIN phase10_intelligence_generations g ON g.generation_id = s.generation_id
            WHERE s.result_snapshot_id = NEW.result_snapshot_id AND s.generation_id = NEW.generation_id
            AND s.targeting_criteria_sha256 = NEW.targeting_criteria_sha256
            AND s.filter_branches_sha256 = NEW.filter_branches_sha256
            AND s.selection_mode = NEW.selection_mode AND s.target_count IS NEW.target_count
            AND s.resolved_count = NEW.selected_count AND g.analysis_run_id = NEW.analysis_run_id
            AND g.model_run_id = NEW.model_run_id AND g.scoring_run_id = NEW.scoring_run_id
            AND g.modeling_context_sha256 = NEW.modeling_context_sha256)
        BEGIN SELECT RAISE(ABORT, 'search snapshot lineage mismatch'); END"""
        for operation in ("INSERT", "UPDATE")
    ),
    """CREATE TRIGGER IF NOT EXISTS campaign_result_export_events_lineage BEFORE INSERT ON campaign_result_export_events
        WHEN NOT EXISTS (SELECT 1 FROM campaign_search_runs r WHERE r.search_run_id = NEW.search_run_id
            AND r.status = 'COMPLETED' AND r.result_snapshot_id = NEW.snapshot_id AND r.selected_count = NEW.selected_count)
        BEGIN SELECT RAISE(ABORT, 'export search snapshot lineage mismatch'); END""",
)
