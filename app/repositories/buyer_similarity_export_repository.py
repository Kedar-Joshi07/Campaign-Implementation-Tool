"""Aggregate-only audit registry for governed similarity downloads."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from app.database.connection import get_connection
from app.services.omnichannel_profile_contracts import OmnichannelExportProfile


class SimilarityExportAuditError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sources_current(connection, expected: Mapping[str, tuple[int, str]]) -> bool:
    for name in ("customers", "campaign_sales", "demographics"):
        latest = connection.execute(
            "SELECT import_id,source_checksum FROM data_import_runs "
            "WHERE dataset_name=? AND status='COMPLETED' ORDER BY import_id DESC LIMIT 1",
            (name,),
        ).fetchone()
        if latest is None or (latest["import_id"], latest["source_checksum"]) != expected.get(name):
            return False
    return True


def create_similarity_export_event(
    database_path: Path, *, run_id: int, snapshot_id: int,
    profile: OmnichannelExportProfile, selected: int, deliverable: int,
    source_identity: Mapping[str, tuple[int, str]],
) -> int:
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status,similarity_result_snapshot_id FROM campaign_search_runs WHERE search_run_id=?",
            (run_id,),
        ).fetchone()
        snapshot = connection.execute(
            "SELECT currentness_state FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        if (row is None or row["status"] != "COMPLETED"
            or row["similarity_result_snapshot_id"] != snapshot_id or snapshot is None
            or snapshot["currentness_state"] != "CURRENT"
            or not _sources_current(connection, source_identity)):
            raise SimilarityExportAuditError("The similarity result is not current for download.")
        return int(connection.execute(
            """INSERT INTO buyer_similarity_export_events (
                search_run_id,similarity_result_snapshot_id,export_profile,profile_version,
                status,selected_count,deliverable_count,undeliverable_count,
                started_at,currentness_state
            ) VALUES (?,?,?,'2','RUNNING',?,?,?,?, 'UNVERIFIED')""",
            (run_id, snapshot_id, profile.export_profile, selected, deliverable,
             selected - deliverable, _now()),
        ).lastrowid)


def finish_similarity_export_event(
    database_path: Path, event_id: int, *, status: str,
    row_count: int, digest: str | None = None,
    source_identity: Mapping[str, tuple[int, str]] | None = None,
) -> None:
    if status not in {"COMPLETED", "FAILED", "ABORTED"}:
        raise ValueError("Invalid export completion state.")
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        event = connection.execute(
            "SELECT * FROM buyer_similarity_export_events WHERE export_event_id=?", (event_id,),
        ).fetchone()
        if event is None or event["status"] != "RUNNING":
            raise SimilarityExportAuditError("Export audit is unavailable.")
        if status == "COMPLETED":
            snapshot = connection.execute(
                "SELECT currentness_state FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
                (event["similarity_result_snapshot_id"],),
            ).fetchone()
            if (snapshot is None or snapshot["currentness_state"] != "CURRENT"
                or row_count != event["deliverable_count"] or digest is None
                or source_identity is None or not _sources_current(connection, source_identity)):
                raise SimilarityExportAuditError("The similarity export could not be certified.")
        connection.execute(
            """UPDATE buyer_similarity_export_events SET status=?,row_count=?,csv_sha256=?,
               completed_at=?,currentness_state=?,safe_error_message=?
               WHERE export_event_id=? AND status='RUNNING'""",
            (status, row_count, digest, _now(),
             "CURRENT" if status == "COMPLETED" else "UNVERIFIED",
             None if status == "COMPLETED" else "The download did not complete. Please try again.",
             event_id),
        )


def reconcile_similarity_export_events(database_path: Path, *, cutoff: str, limit: int = 100) -> int:
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT export_event_id FROM buyer_similarity_export_events "
            "WHERE status='RUNNING' AND started_at<=? ORDER BY started_at LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        for row in rows:
            connection.execute(
                """UPDATE buyer_similarity_export_events SET status='ABORTED',
                   completed_at=?,currentness_state='UNVERIFIED',
                   safe_error_message='The download was interrupted. Please try again.'
                   WHERE export_event_id=? AND status='RUNNING'""",
                (_now(), row["export_event_id"]),
            )
    return len(rows)
