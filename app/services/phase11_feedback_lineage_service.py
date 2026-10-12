"""Read-only lineage audit for future closed-loop feedback integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.services.feedback_grouping import (
    FEEDBACK_GROUPING_CONTRACT_VERSION, build_feedback_grouping,
)


class Phase11FeedbackLineageError(RuntimeError):
    """A completed search does not have a complete, auditable lineage chain."""


def get_completed_search_lineage(
    database_path: str | Path, search_run_id: int
) -> dict[str, Any]:
    """Project existing immutable references; never ingest outcomes or retrain."""

    if (
        isinstance(search_run_id, bool)
        or not isinstance(search_run_id, int)
        or search_run_id <= 0
    ):
        raise ValueError("search_run_id must be a positive integer.")

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                run.*,
                context.campaign_context_json,
                context.campaign_context_sha256,
                snapshot.result_membership_contract_version,
                snapshot.result_cache_key_sha256,
                snapshot.resolved_count,
                snapshot.storage_format,
                snapshot.storage_uri,
                snapshot.snapshot_sha256,
                snapshot.created_at AS snapshot_created_at,
                generation.intelligence_key_sha256,
                generation.customer_import_id,
                generation.customer_source_checksum,
                generation.campaign_sales_import_id,
                generation.campaign_sales_source_checksum,
                generation.demographic_import_id,
                generation.demographic_source_checksum,
                generation.artifact_sha256 AS generation_artifact_sha256,
                model.artifact_sha256 AS model_artifact_sha256,
                future.search_run_id AS future_search_run_id,
                future.activation_id,
                future.provider_campaign_id,
                future.feedback_batch_id,
                future.outcome_dataset_id
            FROM campaign_search_runs AS run
            JOIN campaign_targeting_contexts AS context
              ON context.targeting_context_id = run.targeting_context_id
            LEFT JOIN campaign_result_snapshots AS snapshot
              ON snapshot.result_snapshot_id = run.result_snapshot_id
            LEFT JOIN phase10_intelligence_generations AS generation
              ON generation.generation_id = run.generation_id
            LEFT JOIN model_runs AS model
              ON model.model_run_id = run.model_run_id
            LEFT JOIN campaign_search_future_lineage AS future
              ON future.search_run_id = run.search_run_id
            WHERE run.search_run_id = ?
            """,
            (search_run_id,),
        ).fetchone()
        export_rows = connection.execute(
            """
            SELECT export_event_id
            FROM campaign_result_export_events
            WHERE search_run_id = ?
            ORDER BY started_at, export_event_id
            """,
            (search_run_id,),
        ).fetchall()

    if row is None:
        raise Phase11FeedbackLineageError("The search run does not exist.")
    payload = dict(row)
    if payload["status"] != "COMPLETED":
        raise Phase11FeedbackLineageError(
            "Future outcome lineage is available only for completed searches."
        )
    if str(payload.get("selection_contract_version") or "1") == "3":
        with get_connection(database_path) as connection:
            snapshot = connection.execute(
                "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
                (payload["similarity_result_snapshot_id"],),
            ).fetchone()
            generation = connection.execute(
                "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
                (payload["similarity_generation_id"],),
            ).fetchone()
            profile = connection.execute(
                "SELECT * FROM buyer_similarity_profiles WHERE profile_id=?",
                (generation["profile_id"],),
            ).fetchone() if generation is not None else None
            similarity_exports = connection.execute(
                "SELECT export_event_id FROM buyer_similarity_export_events WHERE search_run_id=? ORDER BY export_event_id",
                (search_run_id,),
            ).fetchall()
            feedback_batches = connection.execute(
                "SELECT feedback_batch_id FROM campaign_feedback_batches WHERE search_run_id=? ORDER BY feedback_batch_id",
                (search_run_id,),
            ).fetchall()
            related_feedback = connection.execute(
                """SELECT b.search_run_id,o.person_id
                   FROM campaign_feedback_batches b
                   JOIN campaign_feedback_outcomes o ON o.feedback_batch_id=b.feedback_batch_id
                   WHERE b.selection_contract_version='3'
                     AND b.similarity_profile_set_sha256=? AND b.status='ACCEPTED'
                   ORDER BY b.search_run_id,o.person_id,b.feedback_batch_id""",
                (snapshot["profile_set_sha256"],),
            ).fetchall() if snapshot is not None else []
        if snapshot is None or generation is None or profile is None or any(payload.get(field) is None for field in (
            "campaign_context_json", "campaign_context_sha256",
            "targeting_criteria_sha256", "filter_branches_sha256",
            "similarity_profile_set_sha256", "completed_at",
        )):
            raise Phase11FeedbackLineageError("The completed similarity lineage is incomplete.")
        if (
            snapshot["result_membership_contract_version"] != "3"
            or snapshot["profile_set_sha256"] != payload["similarity_profile_set_sha256"]
            or snapshot["similarity_generation_id"] != payload["similarity_generation_id"]
            or snapshot["resolved_count"] != payload["selected_count"]
        ):
            raise Phase11FeedbackLineageError("The similarity result identity is inconsistent.")
        grouping = build_feedback_grouping([dict(row) for row in related_feedback])
        return {
            "selection_contract_version": "3",
            "search": {"search_run_id": search_run_id, "campaign_name": payload["campaign_name"],
                       "created_at": payload["created_at"], "completed_at": payload["completed_at"]},
            "business_context": {"targeting_context_id": int(payload["targeting_context_id"]),
                                 "campaign_context_sha256": payload["campaign_context_sha256"],
                                 "modeling_context_sha256": payload["modeling_context_sha256"]},
            "targeting": {"criteria_sha256": payload["targeting_criteria_sha256"],
                          "filter_branches_sha256": payload["filter_branches_sha256"],
                          "selection_mode": payload["selection_mode"],
                          "selected_count": int(payload["selected_count"])},
            "delivery": {"channel": payload["delivery_channel"],
                         "export_profile": payload["export_profile"],
                         "export_event_ids": [int(row["export_event_id"]) for row in similarity_exports]},
            "result": {"similarity_result_snapshot_id": int(snapshot["similarity_result_snapshot_id"]),
                       "membership_contract_version": "3",
                       "result_cache_key_sha256": snapshot["result_cache_key_sha256"],
                       "snapshot_sha256": snapshot["snapshot_sha256"],
                       "storage_uri": snapshot["storage_uri"]},
            "intelligence": {"similarity_generation_id": int(generation["similarity_generation_id"]),
                             "profile_set_sha256": snapshot["profile_set_sha256"],
                             "composite_context_sha256": snapshot["composite_context_sha256"],
                             "score_method_version": snapshot["score_method_version"],
                             "score_semantics": snapshot["score_semantics"],
                             "source_identity": {
                                 "customers": (profile["customer_import_id"], profile["customer_source_checksum"]),
                                 "campaign_sales": (profile["campaign_sales_import_id"], profile["campaign_sales_source_checksum"]),
                                 "demographics": (generation["demographic_import_id"], generation["demographic_source_checksum"]),
                             }},
            "feedback_batch_ids": [int(row["feedback_batch_id"]) for row in feedback_batches],
            "feedback_grouping": {
                "contract_version": FEEDBACK_GROUPING_CONTRACT_VERSION,
                "observation_count": len(related_feedback),
                "independent_group_count": len(grouping.independent_group_ids),
                "grouping_sha256": grouping.grouping_sha256,
                "status": "DESCRIPTIVE_LINEAGE_ONLY",
            },
            "learning_status": "NOT_AVAILABLE_WITHOUT_INDEPENDENT_PROBABILITY_LINEAGE",
        }
    required = (
        "generation_id",
        "analysis_run_id",
        "model_run_id",
        "scoring_run_id",
        "result_snapshot_id",
        "result_source",
        "selected_count",
        "completed_at",
        "campaign_context_json",
        "campaign_context_sha256",
        "targeting_criteria_json",
        "targeting_criteria_sha256",
        "filter_branches_json",
        "filter_branches_sha256",
        "result_cache_key_sha256",
        "snapshot_sha256",
        "generation_artifact_sha256",
        "model_artifact_sha256",
        "customer_source_checksum",
        "campaign_sales_source_checksum",
        "demographic_source_checksum",
        "future_search_run_id",
    )
    if any(payload.get(field) is None for field in required):
        raise Phase11FeedbackLineageError(
            "The completed search lineage is incomplete."
        )
    if payload["generation_artifact_sha256"] != payload["model_artifact_sha256"]:
        raise Phase11FeedbackLineageError(
            "The generation and model artifact lineage do not agree."
        )

    return {
        "search": {
            "search_run_id": search_run_id,
            "campaign_name": payload["campaign_name"],
            "description": payload["description"],
            "planned_launch_date": payload["planned_launch_date"],
            "created_by_user_id": payload["created_by_user_id"],
            "created_at": payload["created_at"],
            "started_at": payload["started_at"],
            "completed_at": payload["completed_at"],
        },
        "business_context": {
            "targeting_context_id": int(payload["targeting_context_id"]),
            "campaign_context": json.loads(payload["campaign_context_json"]),
            "campaign_context_sha256": payload["campaign_context_sha256"],
            "modeling_context_sha256": payload["modeling_context_sha256"],
        },
        "targeting": {
            "criteria": json.loads(payload["targeting_criteria_json"]),
            "criteria_sha256": payload["targeting_criteria_sha256"],
            "filter_branches": json.loads(payload["filter_branches_json"]),
            "filter_branches_sha256": payload["filter_branches_sha256"],
            "selection_mode": payload["selection_mode"],
            "target_count": payload["target_count"],
            "selected_count": int(payload["selected_count"]),
        },
        "delivery": {
            "channel": payload["delivery_channel"],
            "export_profile": payload["export_profile"],
            "export_event_ids": [
                int(export_row["export_event_id"])
                for export_row in export_rows
            ],
        },
        "result": {
            "result_source": payload["result_source"],
            "result_snapshot_id": int(payload["result_snapshot_id"]),
            "membership_contract_version": payload[
                "result_membership_contract_version"
            ],
            "result_cache_key_sha256": payload["result_cache_key_sha256"],
            "snapshot_sha256": payload["snapshot_sha256"],
            "snapshot_created_at": payload["snapshot_created_at"],
            "storage_format": payload["storage_format"],
            "storage_uri": payload["storage_uri"],
        },
        "intelligence": {
            "generation_id": int(payload["generation_id"]),
            "analysis_run_id": int(payload["analysis_run_id"]),
            "model_run_id": int(payload["model_run_id"]),
            "scoring_run_id": int(payload["scoring_run_id"]),
            "intelligence_key_sha256": payload["intelligence_key_sha256"],
            "model_artifact_sha256": payload["model_artifact_sha256"],
            "customer_import_id": int(payload["customer_import_id"]),
            "customer_source_checksum": payload["customer_source_checksum"],
            "campaign_sales_import_id": int(payload["campaign_sales_import_id"]),
            "campaign_sales_source_checksum": payload[
                "campaign_sales_source_checksum"
            ],
            "demographic_import_id": int(payload["demographic_import_id"]),
            "demographic_source_checksum": payload[
                "demographic_source_checksum"
            ],
        },
        "future_links": {
            "activation_id": payload["activation_id"],
            "provider_campaign_id": payload["provider_campaign_id"],
            "feedback_batch_id": payload["feedback_batch_id"],
            "outcome_dataset_id": payload["outcome_dataset_id"],
        },
    }


__all__ = ("Phase11FeedbackLineageError", "get_completed_search_lineage")
