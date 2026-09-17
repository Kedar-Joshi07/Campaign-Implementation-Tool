"""Transactional search/snapshot/export metadata, separate from legacy Campaigns.

No propensity-score scans, artifact writes, or analytical build/reuse decisions.
Callers must validate live Phase 10 currentness and artifact contents before
publishing a snapshot or completing an export (Steps 9, 11, and 13).
"""

from __future__ import annotations

import math
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.services.omnichannel_profile_contracts import get_omnichannel_profile_for_channel, get_omnichannel_profile
from app.services.phase11_result_contracts import (
    RESULT_CURRENTNESS_STATES, RESULT_EXPORT_STATUSES, RESULT_MEMBERSHIP_CONTRACT_VERSION,
    RESULT_EXPORT_CONTRACT_VERSION, RESULT_SOURCES, RESULT_STORAGE_FORMATS,
    SEARCH_RUN_CONTRACT_VERSION, Phase11RegistryStateError, Phase11RegistryValidationError,
    SEARCH_RUN_STATUSES, canonical_metadata_json,
)

_READY_LIFECYCLES = {"CURRENT", "REUSABLE", "PROTECTED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _integer(value: Any, *, zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if zero else 1):
        raise Phase11RegistryValidationError("Expected a valid nonnegative count or positive ID.")
    return value


def _text(value: Any, maximum: int, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise Phase11RegistryValidationError("Invalid bounded text metadata.")
    return value.strip()


def _sha(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Phase11RegistryValidationError("Expected a lowercase SHA-256 value.")
    return value


def _timestamp(value: str | None) -> str:
    value = _now() if value is None else value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError, AttributeError) as exc:
        raise Phase11RegistryValidationError("Expected a timezone-aware timestamp.") from exc


def _selection(mode: str, count: int | None) -> None:
    if mode == "ALL_MATCHING" and count is None:
        return
    if mode == "TOP_N" and count is not None:
        _integer(count)
        return
    raise Phase11RegistryValidationError("Invalid selection mode/target count.")


class CampaignResultRegistryRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    @staticmethod
    def _insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> int:
        columns = ", ".join(values)
        parameters = ", ".join("?" for _ in values)
        return int(connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({parameters})", tuple(values.values())
        ).lastrowid)

    def _fetch(self, table: str, key: str, identifier: int) -> dict[str, Any] | None:
        _integer(identifier)
        with get_connection(self.database_path) as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE {key} = ?", (identifier,)).fetchone()
        return dict(row) if row is not None else None

    def fetch_search_run(self, search_run_id: int) -> dict[str, Any] | None:
        return self._fetch("campaign_search_runs", "search_run_id", search_run_id)

    def fetch_snapshot(self, result_snapshot_id: int) -> dict[str, Any] | None:
        return self._fetch("campaign_result_snapshots", "result_snapshot_id", result_snapshot_id)

    def fetch_export_event(self, export_event_id: int) -> dict[str, Any] | None:
        return self._fetch("campaign_result_export_events", "export_event_id", export_event_id)

    def create_search_run(
        self, *, campaign_name: str, targeting_context_id: int, modeling_context_sha256: str,
        targeting_criteria: Any, filter_branches: Any, delivery_channel: str,
        selection_mode: str = "ALL_MATCHING", target_count: int | None = None,
        export_profile: str | None = None, description: str | None = None,
        planned_launch_date: str | None = None, created_by_user_id: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        _selection(selection_mode, target_count)
        try:
            profile = get_omnichannel_profile_for_channel(delivery_channel)
            if export_profile is not None and get_omnichannel_profile(export_profile) != profile:
                raise ValueError("mismatched profile")
        except ValueError as exc:
            raise Phase11RegistryValidationError("Delivery channel/profile mismatch.") from exc
        criteria_json, criteria_sha = canonical_metadata_json(targeting_criteria)
        branches_json, branches_sha = canonical_metadata_json(filter_branches, branches=True)
        criteria = json.loads(criteria_json)
        if criteria.get("selection_mode", selection_mode) != selection_mode or criteria.get("target_count", target_count) != target_count:
            raise Phase11RegistryValidationError("Criteria selection differs from stored selection.")
        if planned_launch_date is not None:
            try:
                planned_launch_date = date.fromisoformat(planned_launch_date).isoformat()
            except (TypeError, ValueError) as exc:
                raise Phase11RegistryValidationError("Invalid planned launch date.") from exc
        timestamp = _timestamp(timestamp)
        values = dict(
            search_run_contract_version=SEARCH_RUN_CONTRACT_VERSION,
            campaign_name=_text(campaign_name, 200), description=_text(description, 2000, optional=True),
            planned_launch_date=planned_launch_date, targeting_context_id=_integer(targeting_context_id),
            modeling_context_sha256=_sha(modeling_context_sha256), targeting_criteria_json=criteria_json,
            targeting_criteria_sha256=criteria_sha, filter_branches_json=branches_json,
            filter_branches_sha256=branches_sha, selection_mode=selection_mode, target_count=target_count,
            delivery_channel=profile.channel_code, export_profile=profile.export_profile,
            status="QUEUED", created_at=timestamp, started_at=timestamp,
            created_by_user_id=_text(created_by_user_id, 200, optional=True),
        )
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._insert(connection, "campaign_search_runs", values)

    def mark_processing(self, search_run_id: int) -> None:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                "UPDATE campaign_search_runs SET status = 'PROCESSING' WHERE search_run_id = ? AND status = 'QUEUED'",
                (_integer(search_run_id),),
            )
            if cursor.rowcount != 1:
                raise Phase11RegistryStateError("Search is missing or no longer queued.")

    def complete_search_run(
        self, search_run_id: int, *, result_snapshot_id: int, result_source: str,
        timestamp: str | None = None,
    ) -> None:
        if result_source not in RESULT_SOURCES:
            raise Phase11RegistryValidationError("Invalid result source.")
        timestamp = _timestamp(timestamp)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM campaign_search_runs WHERE search_run_id = ?", (_integer(search_run_id),)).fetchone()
            snapshot = connection.execute(
                "SELECT s.*, g.analysis_run_id, g.model_run_id, g.scoring_run_id, g.generation_status, g.lifecycle_state "
                "FROM campaign_result_snapshots s JOIN phase10_intelligence_generations g ON g.generation_id = s.generation_id "
                "WHERE result_snapshot_id = ?", (_integer(result_snapshot_id),),
            ).fetchone()
            if run is None or run["status"] != "PROCESSING" or snapshot is None or snapshot["currentness_state"] != "CURRENT" or snapshot["generation_status"] != "READY" or snapshot["lifecycle_state"] not in _READY_LIFECYCLES:
                raise Phase11RegistryStateError("Search/snapshot is not ready for completion.")
            seconds = self._elapsed(run["started_at"], timestamp)
            connection.execute(
                "UPDATE campaign_search_runs SET status='COMPLETED', generation_id=?, analysis_run_id=?, model_run_id=?, "
                "scoring_run_id=?, result_snapshot_id=?, result_source=?, selected_count=?, completed_at=?, processing_seconds=? "
                "WHERE search_run_id=?",
                (snapshot["generation_id"], snapshot["analysis_run_id"], snapshot["model_run_id"], snapshot["scoring_run_id"],
                 result_snapshot_id, result_source, snapshot["resolved_count"], timestamp, seconds, search_run_id),
            )
            connection.execute("UPDATE campaign_result_snapshots SET last_used_at=? WHERE result_snapshot_id=?", (timestamp, result_snapshot_id))

    @staticmethod
    def _elapsed(started: str, completed: str) -> float:
        elapsed = (datetime.fromisoformat(completed.replace("Z", "+00:00")) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        if not math.isfinite(elapsed) or elapsed < 0:
            raise Phase11RegistryValidationError("Completion precedes start.")
        return elapsed

    def fail_search_run(self, search_run_id: int, *, blocked: bool = False, timestamp: str | None = None) -> None:
        # Store a fixed safe message, never caller exceptions/paths/PII.
        timestamp = _timestamp(timestamp)
        status = "BLOCKED" if blocked else "FAILED"
        message = "This search cannot proceed with the current intelligence." if blocked else "The search could not be completed. Please try again."
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM campaign_search_runs WHERE search_run_id=?", (_integer(search_run_id),)).fetchone()
            if run is None or run["status"] not in {"QUEUED", "PROCESSING"}:
                raise Phase11RegistryStateError("Search is missing or terminal.")
            connection.execute(
                "UPDATE campaign_search_runs SET status=?, completed_at=?, processing_seconds=?, safe_error_message=? WHERE search_run_id=?",
                (status, timestamp, self._elapsed(run["started_at"], timestamp), message, search_run_id),
            )

    def register_snapshot(
        self, *, generation_id: int, targeting_criteria_sha256: str, filter_branches_sha256: str,
        result_cache_key_sha256: str, resolved_count: int, storage_format: str,
        storage_uri: str, snapshot_sha256: str, selection_mode: str = "ALL_MATCHING",
        target_count: int | None = None, timestamp: str | None = None,
    ) -> int:
        """Record an already validated artifact; does not certify its contents."""
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self.register_snapshot_in_transaction(
                connection,
                generation_id=generation_id,
                targeting_criteria_sha256=targeting_criteria_sha256,
                filter_branches_sha256=filter_branches_sha256,
                result_cache_key_sha256=result_cache_key_sha256,
                resolved_count=resolved_count,
                storage_format=storage_format,
                storage_uri=storage_uri,
                snapshot_sha256=snapshot_sha256,
                selection_mode=selection_mode,
                target_count=target_count,
                timestamp=timestamp,
            )

    def register_snapshot_in_transaction(
        self, connection: sqlite3.Connection, *, generation_id: int,
        targeting_criteria_sha256: str, filter_branches_sha256: str,
        result_cache_key_sha256: str, resolved_count: int, storage_format: str,
        storage_uri: str, snapshot_sha256: str,
        selection_mode: str = "ALL_MATCHING", target_count: int | None = None,
        timestamp: str | None = None, expected_snapshot_id: int | None = None,
    ) -> int:
        """Insert through a caller-owned write transaction after artifact publication.

        The Step 11 publisher uses this boundary while holding ``BEGIN IMMEDIATE``
        so the path's numeric snapshot identity and the AUTOINCREMENT identity
        cannot race.  The caller still owns commit/rollback and artifact cleanup.
        """
        if not isinstance(connection, sqlite3.Connection) or not connection.in_transaction:
            raise Phase11RegistryStateError("Snapshot registration requires an active transaction.")
        _selection(selection_mode, target_count)
        _integer(resolved_count, zero=True)
        if target_count is not None and resolved_count > target_count:
            raise Phase11RegistryValidationError("Resolved count exceeds target count.")
        extensions = {"CSV_GZIP": "csv.gz", "JSONL_GZIP": "jsonl.gz", "PARQUET": "parquet"}
        if storage_format not in RESULT_STORAGE_FORMATS or not isinstance(storage_uri, str) or re.fullmatch(
            r"artifacts/results/result_snapshot_[0-9]+/members\." + re.escape(extensions[storage_format]), storage_uri
        ) is None:
            raise Phase11RegistryValidationError("Expected a portable, non-PII result artifact URI.")
        timestamp = _timestamp(timestamp)
        values = dict(
            result_membership_contract_version=RESULT_MEMBERSHIP_CONTRACT_VERSION,
            generation_id=_integer(generation_id), targeting_criteria_sha256=_sha(targeting_criteria_sha256),
            filter_branches_sha256=_sha(filter_branches_sha256), selection_mode=selection_mode,
            target_count=target_count, result_cache_key_sha256=_sha(result_cache_key_sha256),
            resolved_count=resolved_count, storage_format=storage_format, storage_uri=storage_uri,
            snapshot_sha256=_sha(snapshot_sha256), created_at=timestamp, last_verified_at=timestamp,
            last_used_at=timestamp, currentness_state="CURRENT",
        )
        generation = connection.execute(
            "SELECT generation_status,lifecycle_state FROM phase10_intelligence_generations WHERE generation_id=?", (generation_id,)
        ).fetchone()
        if generation is None or generation["generation_status"] != "READY" or generation["lifecycle_state"] not in _READY_LIFECYCLES:
            raise Phase11RegistryStateError("A compatible READY generation is required.")
        snapshot_id = self._insert(connection, "campaign_result_snapshots", values)
        if expected_snapshot_id is not None and snapshot_id != _integer(expected_snapshot_id):
            raise Phase11RegistryStateError("Snapshot artifact and registry identities differ.")
        return snapshot_id

    def find_snapshot_by_cache_key(self, result_cache_key_sha256: str) -> dict[str, Any] | None:
        """Metadata lookup only; caller must verify currentness/artifact before reuse."""
        with get_connection(self.database_path) as connection:
            row = connection.execute("SELECT * FROM campaign_result_snapshots WHERE result_cache_key_sha256=?", (_sha(result_cache_key_sha256),)).fetchone()
        return dict(row) if row is not None else None

    def update_snapshot_currentness(self, result_snapshot_id: int, *, state: str, timestamp: str | None = None) -> None:
        if state not in RESULT_CURRENTNESS_STATES:
            raise Phase11RegistryValidationError("Invalid snapshot currentness state.")
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                "UPDATE campaign_result_snapshots SET currentness_state=?, last_verified_at=? WHERE result_snapshot_id=?",
                (state, _timestamp(timestamp), _integer(result_snapshot_id)),
            )
            if cursor.rowcount != 1:
                raise Phase11RegistryStateError("Snapshot is missing.")

    def list_search_runs(self, *, limit: int = 50, before_search_run_id: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
        if not 1 <= _integer(limit) <= 100 or status is not None and status not in SEARCH_RUN_STATUSES:
            raise Phase11RegistryValidationError("Invalid bounded history query.")
        clauses, parameters = [], []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        with get_connection(self.database_path) as connection:
            if before_search_run_id is not None:
                cursor = connection.execute(
                    "SELECT created_at FROM campaign_search_runs WHERE search_run_id=?",
                    (_integer(before_search_run_id),),
                ).fetchone()
                if cursor is None:
                    raise Phase11RegistryStateError("History cursor was not found.")
                clauses.append("(created_at < ? OR (created_at = ? AND search_run_id < ?))")
                parameters.extend((cursor["created_at"], cursor["created_at"], before_search_run_id))
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = connection.execute(
                "SELECT * FROM campaign_search_runs" + where
                + " ORDER BY created_at DESC, search_run_id DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_export_event(self, *, search_run_id: int, snapshot_id: int, export_profile: str, selected_count: int, deliverable_count: int, undeliverable_count: int, timestamp: str | None = None) -> int:
        try:
            profile = get_omnichannel_profile(export_profile)
        except ValueError as exc:
            raise Phase11RegistryValidationError("Invalid export profile.") from exc
        for count in (selected_count, deliverable_count, undeliverable_count):
            _integer(count, zero=True)
        if selected_count != deliverable_count + undeliverable_count:
            raise Phase11RegistryValidationError("Export counts do not reconcile.")
        values = dict(search_run_id=_integer(search_run_id), snapshot_id=_integer(snapshot_id), export_contract_version=RESULT_EXPORT_CONTRACT_VERSION,
            export_profile=profile.export_profile, profile_version=profile.profile_version, status="RUNNING", selected_count=selected_count,
            deliverable_count=deliverable_count, undeliverable_count=undeliverable_count, row_count=0, started_at=_timestamp(timestamp), currentness_state="UNVERIFIED")
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            snapshot = connection.execute("SELECT s.currentness_state,g.generation_status,g.lifecycle_state FROM campaign_result_snapshots s JOIN phase10_intelligence_generations g ON g.generation_id=s.generation_id WHERE result_snapshot_id=?", (snapshot_id,)).fetchone()
            if snapshot is None or snapshot["currentness_state"] != "CURRENT" or snapshot["generation_status"] != "READY" or snapshot["lifecycle_state"] not in _READY_LIFECYCLES:
                raise Phase11RegistryStateError("Export snapshot is not current.")
            return self._insert(connection, "campaign_result_export_events", values)

    def finish_export_event(self, export_event_id: int, *, status: str, row_count: int, csv_sha256: str | None = None, currentness_state: str = "UNVERIFIED", timestamp: str | None = None) -> None:
        if status not in RESULT_EXPORT_STATUSES - {"RUNNING"} or currentness_state not in RESULT_CURRENTNESS_STATES:
            raise Phase11RegistryValidationError("Invalid export completion state.")
        _integer(row_count, zero=True)
        if csv_sha256 is not None:
            _sha(csv_sha256)
        timestamp = _timestamp(timestamp)
        message = None if status == "COMPLETED" else "The download did not complete. Please try again."
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            event = connection.execute("SELECT * FROM campaign_result_export_events WHERE export_event_id=?", (_integer(export_event_id),)).fetchone()
            if event is None or event["status"] != "RUNNING":
                raise Phase11RegistryStateError("Export is missing or terminal.")
            self._elapsed(event["started_at"], timestamp)
            if row_count > event["deliverable_count"] or status == "COMPLETED" and (row_count != event["deliverable_count"] or csv_sha256 is None or currentness_state != "CURRENT"):
                raise Phase11RegistryValidationError("Completed export counts/checksum/currentness are invalid.")
            snapshot = connection.execute("SELECT s.currentness_state,g.generation_status,g.lifecycle_state FROM campaign_result_snapshots s JOIN phase10_intelligence_generations g ON g.generation_id=s.generation_id WHERE result_snapshot_id=?", (event["snapshot_id"],)).fetchone()
            if status == "COMPLETED" and (snapshot is None or snapshot["currentness_state"] != "CURRENT" or snapshot["generation_status"] != "READY" or snapshot["lifecycle_state"] not in _READY_LIFECYCLES):
                raise Phase11RegistryStateError("Snapshot became stale during export.")
            connection.execute("UPDATE campaign_result_export_events SET status=?, row_count=?, csv_sha256=?, completed_at=?, currentness_state=?, safe_error_message=? WHERE export_event_id=?",
                (status, row_count, csv_sha256, timestamp, currentness_state, message, export_event_id))

    def list_export_events(self, search_run_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= _integer(limit) <= 100:
            raise Phase11RegistryValidationError("Invalid audit history limit.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM campaign_result_export_events WHERE search_run_id=? ORDER BY started_at DESC, export_event_id DESC LIMIT ?", (_integer(search_run_id), limit)).fetchall()
        return [dict(row) for row in rows]

    def reconcile_stale_export_events(
        self, *, stale_started_at_max: str, timestamp: str | None = None,
        limit: int = 100,
    ) -> int:
        """Boundedly terminalize process-crash residue without contact data."""

        cutoff = _timestamp(stale_started_at_max)
        completed_at = _timestamp(timestamp)
        if not 1 <= _integer(limit) <= 1000:
            raise Phase11RegistryValidationError("Invalid export recovery limit.")
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT export_event_id
                FROM campaign_result_export_events
                WHERE status='RUNNING' AND started_at <= ?
                ORDER BY started_at ASC, export_event_id ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
            identifiers = [int(row["export_event_id"]) for row in rows]
            for export_event_id in identifiers:
                connection.execute(
                    """
                    UPDATE campaign_result_export_events
                    SET status='ABORTED', completed_at=?,
                        currentness_state='UNVERIFIED',
                        safe_error_message='The download was interrupted. Please try again.'
                    WHERE export_event_id=? AND status='RUNNING'
                    """,
                    (completed_at, export_event_id),
                )
        return len(identifiers)
