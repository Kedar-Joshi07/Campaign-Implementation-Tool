"""Additive future feedback lineage seam; no feedback processing behavior."""

from __future__ import annotations


CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS = (
    "search_run_id",
    "activation_id",
    "provider_campaign_id",
    "feedback_batch_id",
    "outcome_dataset_id",
    "created_at",
    "updated_at",
)

PHASE_ELEVEN_FEEDBACK_CREATE_TABLE_STATEMENT = """
CREATE TABLE IF NOT EXISTS campaign_search_future_lineage (
    search_run_id INTEGER PRIMARY KEY
        REFERENCES campaign_search_runs(search_run_id) ON DELETE RESTRICT,
    activation_id TEXT
        CHECK (activation_id IS NULL OR length(trim(activation_id)) BETWEEN 1 AND 200),
    provider_campaign_id TEXT
        CHECK (provider_campaign_id IS NULL OR length(trim(provider_campaign_id)) BETWEEN 1 AND 200),
    feedback_batch_id TEXT
        CHECK (feedback_batch_id IS NULL OR length(trim(feedback_batch_id)) BETWEEN 1 AND 200),
    outcome_dataset_id TEXT
        CHECK (outcome_dataset_id IS NULL OR length(trim(outcome_dataset_id)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS = {
    "idx_campaign_search_future_activation": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_future_activation "
        "ON campaign_search_future_lineage(activation_id, search_run_id) "
        "WHERE activation_id IS NOT NULL"
    ),
    "idx_campaign_search_future_provider": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_future_provider "
        "ON campaign_search_future_lineage(provider_campaign_id, search_run_id) "
        "WHERE provider_campaign_id IS NOT NULL"
    ),
    "idx_campaign_search_future_feedback": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_future_feedback "
        "ON campaign_search_future_lineage(feedback_batch_id, search_run_id) "
        "WHERE feedback_batch_id IS NOT NULL"
    ),
    "idx_campaign_search_future_outcome": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_search_future_outcome "
        "ON campaign_search_future_lineage(outcome_dataset_id, search_run_id) "
        "WHERE outcome_dataset_id IS NOT NULL"
    ),
}

PHASE_ELEVEN_FEEDBACK_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS campaign_search_future_lineage_create
    AFTER INSERT ON campaign_search_runs
    BEGIN
        INSERT INTO campaign_search_future_lineage (
            search_run_id, created_at, updated_at
        ) VALUES (NEW.search_run_id, NEW.created_at, NEW.created_at);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS campaign_search_future_lineage_write_once
    BEFORE UPDATE ON campaign_search_future_lineage
    WHEN NEW.search_run_id IS NOT OLD.search_run_id
      OR NEW.created_at IS NOT OLD.created_at
      OR (OLD.activation_id IS NOT NULL AND NEW.activation_id IS NOT OLD.activation_id)
      OR (OLD.provider_campaign_id IS NOT NULL
          AND NEW.provider_campaign_id IS NOT OLD.provider_campaign_id)
      OR (OLD.feedback_batch_id IS NOT NULL
          AND NEW.feedback_batch_id IS NOT OLD.feedback_batch_id)
      OR (OLD.outcome_dataset_id IS NOT NULL
          AND NEW.outcome_dataset_id IS NOT OLD.outcome_dataset_id)
    BEGIN
        SELECT RAISE(ABORT, 'future lineage references are write-once');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS campaign_search_future_lineage_completed_only
    BEFORE UPDATE ON campaign_search_future_lineage
    WHEN (
        NEW.activation_id IS NOT OLD.activation_id
        OR NEW.provider_campaign_id IS NOT OLD.provider_campaign_id
        OR NEW.feedback_batch_id IS NOT OLD.feedback_batch_id
        OR NEW.outcome_dataset_id IS NOT OLD.outcome_dataset_id
    ) AND NOT EXISTS (
        SELECT 1 FROM campaign_search_runs AS run
        WHERE run.search_run_id = NEW.search_run_id
          AND run.status = 'COMPLETED'
    )
    BEGIN
        SELECT RAISE(ABORT, 'future lineage requires a completed search');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS campaign_search_future_lineage_no_delete
    BEFORE DELETE ON campaign_search_future_lineage
    BEGIN
        SELECT RAISE(ABORT, 'future lineage history cannot be deleted');
    END
    """,
)


__all__ = (
    "CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS",
    "PHASE_ELEVEN_FEEDBACK_CREATE_TABLE_STATEMENT",
    "PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS",
    "PHASE_ELEVEN_FEEDBACK_TRIGGER_STATEMENTS",
)
