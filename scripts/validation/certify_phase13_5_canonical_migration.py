#!/usr/bin/env python3
"""Certify the production schema migration on a byte-for-byte database copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database


TABLES = (
    "data_import_runs",
    "historical_analysis_runs",
    "model_runs",
    "scoring_runs",
    "phase10_intelligence_generations",
    "phase10_orchestration_runs",
    "intelligence_verification_attestations",
    "score_calibration_artifacts",
    "campaign_search_runs",
    "campaign_search_attempts",
    "campaign_search_run_runtime",
    "campaign_search_progress_events",
    "campaign_result_snapshots",
    "campaign_result_export_events",
    "search_preflight_cache",
    "targeting_option_catalogs",
    "campaign_feedback_batches",
    "feedback_retraining_decisions",
)

IDENTITY_COLUMNS = {
    "data_import_runs": ("import_id",),
    "historical_analysis_runs": ("analysis_run_id",),
    "model_runs": ("model_run_id",),
    "scoring_runs": ("scoring_run_id",),
    "phase10_intelligence_generations": ("generation_id",),
    "phase10_orchestration_runs": ("orchestration_id",),
    "intelligence_verification_attestations": ("attestation_key_sha256",),
    "score_calibration_artifacts": ("calibration_artifact_id",),
    "campaign_search_runs": ("search_run_id",),
    "campaign_search_attempts": ("search_run_id", "attempt_number"),
    "campaign_search_run_runtime": ("search_run_id",),
    "campaign_search_progress_events": ("progress_event_id",),
    "campaign_result_snapshots": ("result_snapshot_id",),
    "campaign_result_export_events": ("export_event_id",),
    "search_preflight_cache": ("cache_key_sha256",),
    "targeting_option_catalogs": ("catalog_version",),
    "campaign_feedback_batches": ("feedback_batch_id",),
    "feedback_retraining_decisions": ("retraining_decision_id",),
}

STATUS_COLUMNS = (
    "status",
    "generation_status",
    "lifecycle_state",
    "lifecycle_status",
    "verification_status",
    "currentness_state",
    "is_current",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=60000")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        raise RuntimeError("Database does not record a schema version.")
    return int(row["value"])


def _identity_digest(
    connection: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
) -> dict[str, Any]:
    identity_columns = tuple(columns)
    selection = ",".join(f'"{column}"' for column in identity_columns)
    ordering = ",".join(f'"{column}"' for column in identity_columns)
    digest = hashlib.sha256()
    first: list[Any] | None = None
    last: list[Any] | None = None
    count = 0
    for row in connection.execute(
        f'SELECT {selection} FROM "{table}" ORDER BY {ordering}'
    ):
        values = [row[column] for column in identity_columns]
        if first is None:
            first = values
        last = values
        digest.update(
            json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        digest.update(b"\n")
        count += 1
    return {
        "columns": list(identity_columns),
        "count": count,
        "first": first,
        "last": last,
        "ordered_sha256": digest.hexdigest(),
    }


def _table_metrics(connection: sqlite3.Connection) -> dict[str, Any]:
    available = _tables(connection)
    metrics: dict[str, Any] = {}
    for table in TABLES:
        if table not in available:
            metrics[table] = {"present": False}
            continue
        columns = {
            str(row["name"])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        item: dict[str, Any] = {
            "present": True,
            "row_count": int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            ),
            "identity": _identity_digest(
                connection, table, IDENTITY_COLUMNS[table]
            ),
            "status_counts": {},
        }
        for column in STATUS_COLUMNS:
            if column not in columns:
                continue
            item["status_counts"][column] = {
                str(row["value"]): int(row["count"])
                for row in connection.execute(
                    f'SELECT "{column}" AS value,COUNT(*) AS count '
                    f'FROM "{table}" GROUP BY "{column}" ORDER BY "{column}"'
                )
            }
        metrics[table] = item
    return metrics


def _source_lineage(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    if "data_import_runs" not in _tables(connection):
        return []
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(data_import_runs)")
    }
    wanted = tuple(
        column
        for column in (
            "import_id",
            "dataset_name",
            "source_checksum",
            "status",
            "rows_read",
            "rows_inserted",
            "rows_rejected",
        )
        if column in columns
    )
    selection = ",".join(f'"{column}"' for column in wanted)
    return [
        {column: row[column] for column in wanted}
        for row in connection.execute(
            f"SELECT {selection} FROM data_import_runs ORDER BY import_id"
        )
    ]


def _snapshot(path: Path, *, include_health: bool) -> dict[str, Any]:
    with _connect(path) as connection:
        report: dict[str, Any] = {
            "schema_version": _schema_version(connection),
            "table_metrics": _table_metrics(connection),
            "source_lineage": _source_lineage(connection),
        }
        if include_health:
            report["integrity_check"] = str(
                connection.execute("PRAGMA integrity_check").fetchone()[0]
            )
            report["foreign_key_violations"] = [
                list(row) for row in connection.execute("PRAGMA foreign_key_check")
            ]
        return report


def _semantic_signature(snapshot: dict[str, Any]) -> str:
    payload = {
        "schema_version": snapshot["schema_version"],
        "table_metrics": snapshot["table_metrics"],
        "source_lineage": snapshot["source_lineage"],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--copy", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--final-health-only",
        action="store_true",
        help=(
            "Run the expensive full integrity/FK checks once on the final "
            "twice-initialized copy; semantic snapshots still run at every stage."
        ),
    )
    args = parser.parse_args()
    source = args.source.resolve()
    working_copy = args.copy.resolve()
    report_path = args.report.resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise SystemExit("Canonical source database is missing or empty.")
    if working_copy == source:
        raise SystemExit("Working copy must not be the canonical source.")
    if working_copy.exists():
        raise SystemExit("Working copy already exists; refusing to overwrite it.")

    source_before = {
        "path": str(source),
        "size_bytes": source.stat().st_size,
        "modified_time_ns": source.stat().st_mtime_ns,
        "sha256": _sha256(source),
    }
    print("[migration-cert] copying canonical database", flush=True)
    working_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, working_copy)
    copy_before = {
        "path": str(working_copy),
        "size_bytes": working_copy.stat().st_size,
        "sha256": _sha256(working_copy),
    }
    if copy_before["size_bytes"] != source_before["size_bytes"] or (
        copy_before["sha256"] != source_before["sha256"]
    ):
        raise RuntimeError("Byte-for-byte copy verification failed.")

    print("[migration-cert] inspecting schema-26 copy", flush=True)
    before = _snapshot(working_copy, include_health=not args.final_health_only)
    print("[migration-cert] running production initialization", flush=True)
    initialize_database(working_copy)
    after_first = _snapshot(working_copy, include_health=not args.final_health_only)
    first_signature = _semantic_signature(after_first)

    print("[migration-cert] checking initialization idempotency", flush=True)
    initialize_database(working_copy)
    after_second = _snapshot(working_copy, include_health=True)
    second_signature = _semantic_signature(after_second)

    source_after_stat = source.stat()
    source_after = {
        "path": str(source),
        "size_bytes": source_after_stat.st_size,
        "modified_time_ns": source_after_stat.st_mtime_ns,
        "sha256": _sha256(source),
    }
    report = {
        "certification_contract": (
            "PHASE13_6_CANONICAL_COPY_MIGRATION_V1"
            if args.final_health_only
            else "PHASE13_5_CANONICAL_COPY_MIGRATION_V1"
        ),
        "full_health_check_stage": (
            "AFTER_SECOND_INITIALIZATION"
            if args.final_health_only
            else "EVERY_SNAPSHOT"
        ),
        "recorded_at": _utc_now(),
        "current_schema_version": CURRENT_SCHEMA_VERSION,
        "source_before": source_before,
        "source_after": source_after,
        "authoritative_source_unchanged": source_before == source_after,
        "copy_before": copy_before,
        "before_migration": before,
        "after_first_initialization": after_first,
        "after_second_initialization": after_second,
        "first_semantic_signature": first_signature,
        "second_semantic_signature": second_signature,
        "second_initialization_semantically_idempotent": (
            first_signature == second_signature
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    passed = all(
        (
            (
                args.final_health_only
                or before["integrity_check"] == "ok"
            ),
            (
                args.final_health_only
                or not before["foreign_key_violations"]
            ),
            before["schema_version"] == 26,
            after_second["schema_version"] == CURRENT_SCHEMA_VERSION,
            after_second["integrity_check"] == "ok",
            not after_second["foreign_key_violations"],
            report["authoritative_source_unchanged"],
            report["second_initialization_semantically_idempotent"],
        )
    )
    print(
        f"[migration-cert:{'pass' if passed else 'fail'}] report={report_path}",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
