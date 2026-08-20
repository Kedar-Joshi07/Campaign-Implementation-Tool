"""Streaming, batched CSV import orchestration for the three Phase 1 datasets."""

from __future__ import annotations

import csv
import gzip
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from app.config import DATABASE_PATH
from app.database.connection import get_connection
from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    initialize_database,
)
from app.services.data_validation_service import (
    DataValidationError,
    validate_campaign_sales_row,
    validate_customer_row,
    validate_demographic_row,
)


logger = logging.getLogger(__name__)
RowValidator = Callable[[Mapping[str, str]], tuple[object, ...]]


class DataImportError(RuntimeError):
    """Raised when an import cannot complete safely."""


@dataclass(frozen=True)
class DatasetSpec:
    dataset_name: str
    table_name: str
    columns: tuple[str, ...]
    validator: RowValidator


@dataclass
class ImportProgress:
    rows_read: int = 0
    rows_inserted: int = 0
    rows_rejected: int = 0


@dataclass(frozen=True)
class ImportResult:
    import_id: int
    dataset_name: str
    status: str
    rows_read: int
    rows_inserted: int
    rows_rejected: int
    duration_seconds: float
    source_paths: tuple[str, ...]


CUSTOMER_SPEC = DatasetSpec(
    dataset_name="customers",
    table_name="customers",
    columns=CUSTOMER_COLUMNS,
    validator=validate_customer_row,
)
CAMPAIGN_SALES_SPEC = DatasetSpec(
    dataset_name="campaign_sales",
    table_name="campaign_sales",
    columns=CAMPAIGN_SALES_COLUMNS,
    validator=validate_campaign_sales_row,
)
DEMOGRAPHIC_SPEC = DatasetSpec(
    dataset_name="demographics",
    table_name="demographics",
    columns=DEMOGRAPHIC_COLUMNS,
    validator=validate_demographic_row,
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_source_paths(source_paths: Sequence[Path]) -> tuple[Path, ...]:
    if not source_paths:
        raise DataImportError("At least one source file is required")

    validated: list[Path] = []
    for source_path in source_paths:
        path = Path(source_path)
        if not path.is_file():
            raise DataImportError(f"Source file does not exist: {path}")
        lower_name = path.name.lower()
        if not (lower_name.endswith(".csv") or lower_name.endswith(".csv.gz")):
            raise DataImportError(f"Unsupported source format for {path}; use .csv or .csv.gz")
        validated.append(path.resolve())
    return tuple(validated)


def resolve_demographic_sources(
    *,
    files: Sequence[str | Path] | None = None,
    input_dir: str | Path | None = None,
    pattern: str = "*.csv.gz",
) -> tuple[Path, ...]:
    """Resolve repeated files or one directory/pattern into a stable ordered list."""
    if files and input_dir is not None:
        raise DataImportError("Use repeated --file values or --input-dir, not both")
    if files:
        return _validate_source_paths(tuple(Path(path) for path in files))
    if input_dir is None:
        raise DataImportError("Provide at least one --file or an --input-dir")

    directory = Path(input_dir)
    if not directory.is_dir():
        raise DataImportError(f"Demographic input directory does not exist: {directory}")
    matches = tuple(sorted(path for path in directory.glob(pattern) if path.is_file()))
    if not matches:
        raise DataImportError(
            f"No demographic files matched pattern {pattern!r} in {directory}"
        )
    return _validate_source_paths(matches)


def _open_source(path: Path) -> TextIO:
    if path.name.lower().endswith(".csv.gz"):
        return gzip.open(path, mode="rt", encoding="utf-8-sig", newline="")
    return path.open(mode="r", encoding="utf-8-sig", newline="")


def _validate_source_header(
    reader: Iterator[list[str]],
    source_path: Path,
    spec: DatasetSpec,
) -> None:
    try:
        header = next(reader)
    except StopIteration as exc:
        raise DataImportError(f"Source file is empty: {source_path}") from exc
    if tuple(header) != spec.columns:
        raise DataImportError(
            f"Schema mismatch in {source_path}; expected {list(spec.columns)!r}, "
            f"received {header!r}"
        )


def _preflight_sources(
    spec: DatasetSpec,
    source_paths: tuple[Path, ...],
    *,
    full_read: bool,
) -> None:
    """Prove source structure/readability before a replacement can clear data."""
    for source_path in source_paths:
        logger.info(
            "Source preflight started | dataset=%s path=%s full_read=%s",
            spec.dataset_name,
            source_path,
            full_read,
        )
        try:
            with _open_source(source_path) as source:
                reader = csv.reader(source, strict=True)
                _validate_source_header(reader, source_path, spec)
                if full_read:
                    for raw_row in reader:
                        if len(raw_row) != len(spec.columns):
                            raise DataImportError(
                                f"{source_path}: CSV line {reader.line_num} has "
                                f"{len(raw_row)} fields; expected {len(spec.columns)}"
                            )
        except DataImportError:
            logger.error(
                "Source preflight failed | dataset=%s path=%s",
                spec.dataset_name,
                source_path,
            )
            raise
        except (OSError, EOFError, UnicodeError, csv.Error) as exc:
            logger.error(
                "Source preflight failed | dataset=%s path=%s error=%s",
                spec.dataset_name,
                source_path,
                exc,
            )
            raise DataImportError(f"Unable to read {source_path}: {exc}") from exc
        logger.info(
            "Source preflight completed | dataset=%s path=%s",
            spec.dataset_name,
            source_path,
        )


def _start_import_run(
    database_path: Path,
    dataset_name: str,
    source_description: str,
) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,
                source_path,
                started_at,
                status,
                rows_read,
                rows_inserted,
                rows_rejected
            ) VALUES (?, ?, ?, 'RUNNING', 0, 0, 0)
            """,
            (dataset_name, source_description, _utc_timestamp()),
        )
        return int(cursor.lastrowid)


def _finish_import_run(
    database_path: Path,
    import_id: int,
    status: str,
    progress: ImportProgress,
    error_message: str | None = None,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE data_import_runs
            SET completed_at = ?,
                status = ?,
                rows_read = ?,
                rows_inserted = ?,
                rows_rejected = ?,
                error_message = ?
            WHERE import_id = ?
            """,
            (
                _utc_timestamp(),
                status,
                progress.rows_read,
                progress.rows_inserted,
                progress.rows_rejected,
                error_message,
                import_id,
            ),
        )


def _table_count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _prepare_target(
    database_path: Path,
    spec: DatasetSpec,
    *,
    replace: bool,
) -> None:
    with get_connection(database_path, write=True) as connection:
        target_count = _table_count(connection, spec.table_name)

        if spec is CAMPAIGN_SALES_SPEC and _table_count(connection, "customers") == 0:
            raise DataImportError("Import customers before campaign_sales")
        if spec is DEMOGRAPHIC_SPEC:
            if _table_count(connection, "customers") == 0:
                raise DataImportError("Import customers before demographics")
            if _table_count(connection, "campaign_sales") == 0:
                raise DataImportError("Import campaign_sales before demographics")

        if not replace and target_count > 0:
            raise DataImportError(
                f"Target table {spec.table_name} already contains {target_count:,} rows; "
                "rerun with --replace only if an explicit reload is intended"
            )

        if replace:
            if spec is CUSTOMER_SPEC and _table_count(connection, "campaign_sales") > 0:
                raise DataImportError(
                    "Cannot replace customers while campaign_sales contains rows; "
                    "replace/clear campaign_sales first"
                )
            connection.execute(f'DELETE FROM "{spec.table_name}"')
            logger.warning("Explicit replace cleared target table | table=%s", spec.table_name)


def _insert_batch(
    connection: sqlite3.Connection,
    spec: DatasetSpec,
    batch: list[tuple[object, ...]],
) -> None:
    placeholders = ", ".join("?" for _ in spec.columns)
    columns = ", ".join(f'"{column}"' for column in spec.columns)
    connection.executemany(
        f'INSERT INTO "{spec.table_name}" ({columns}) VALUES ({placeholders})',
        batch,
    )
    connection.commit()


def _stream_sources(
    database_path: Path,
    spec: DatasetSpec,
    source_paths: tuple[Path, ...],
    progress: ImportProgress,
    *,
    batch_size: int,
    progress_every: int,
) -> None:
    batch: list[tuple[object, ...]] = []

    with get_connection(database_path, write=True) as connection:
        connection.execute("PRAGMA synchronous = NORMAL")
        for source_path in source_paths:
            logger.info("Reading import source | dataset=%s path=%s", spec.dataset_name, source_path)
            try:
                with _open_source(source_path) as source:
                    reader = csv.reader(source, strict=True)
                    _validate_source_header(reader, source_path, spec)

                    for raw_row in reader:
                        progress.rows_read += 1
                        if len(raw_row) != len(spec.columns):
                            progress.rows_rejected += 1
                            raise DataImportError(
                                f"{source_path}: CSV line {reader.line_num} has {len(raw_row)} "
                                f"fields; expected {len(spec.columns)}"
                            )

                        row = dict(zip(spec.columns, raw_row, strict=True))
                        try:
                            batch.append(spec.validator(row))
                        except DataValidationError as exc:
                            progress.rows_rejected += 1
                            raise DataImportError(
                                f"{source_path}: CSV line {reader.line_num}: {exc}"
                            ) from exc

                        if len(batch) >= batch_size:
                            try:
                                _insert_batch(connection, spec, batch)
                            except sqlite3.IntegrityError as exc:
                                progress.rows_rejected += 1
                                raise DataImportError(
                                    f"{source_path}: database rejected batch ending at CSV line "
                                    f"{reader.line_num}: {exc}"
                                ) from exc
                            progress.rows_inserted += len(batch)
                            batch.clear()

                        if progress_every and progress.rows_read % progress_every == 0:
                            logger.info(
                                "Import progress | dataset=%s rows_read=%s rows_inserted=%s",
                                spec.dataset_name,
                                f"{progress.rows_read:,}",
                                f"{progress.rows_inserted:,}",
                            )
            except (OSError, EOFError, UnicodeError, csv.Error) as exc:
                progress.rows_rejected += 1
                raise DataImportError(f"Unable to read {source_path}: {exc}") from exc

        if batch:
            try:
                _insert_batch(connection, spec, batch)
            except sqlite3.IntegrityError as exc:
                progress.rows_rejected += 1
                raise DataImportError(
                    f"Database rejected final {spec.dataset_name} batch: {exc}"
                ) from exc
            progress.rows_inserted += len(batch)
            batch.clear()


def _import_dataset(
    spec: DatasetSpec,
    source_paths: Sequence[str | Path],
    *,
    database_path: str | Path | None,
    replace: bool,
    batch_size: int,
    progress_every: int,
) -> ImportResult:
    if batch_size <= 0:
        raise DataImportError("batch_size must be positive")
    if progress_every < 0:
        raise DataImportError("progress_every must be zero or positive")

    path = Path(database_path) if database_path is not None else DATABASE_PATH
    try:
        initialize_database(path)
    except (OSError, sqlite3.Error) as exc:
        message = f"Unable to prepare SQLite database {path}: {exc}"
        logger.error(
            "Import database preparation failed | dataset=%s database=%s error=%s",
            spec.dataset_name,
            path,
            exc,
        )
        raise DataImportError(message) from exc

    raw_sources = tuple(Path(source_path) for source_path in source_paths)
    source_description = " | ".join(str(source_path) for source_path in raw_sources)
    try:
        import_id = _start_import_run(path, spec.dataset_name, source_description)
    except sqlite3.Error as exc:
        message = f"Unable to start import metadata for SQLite database {path}: {exc}"
        logger.error(
            "Import metadata start failed | dataset=%s database=%s error=%s",
            spec.dataset_name,
            path,
            exc,
        )
        raise DataImportError(message) from exc
    progress = ImportProgress()
    started = time.perf_counter()

    logger.info(
        "Import started | import_id=%s dataset=%s replace=%s",
        import_id,
        spec.dataset_name,
        replace,
    )
    try:
        validated_sources = _validate_source_paths(raw_sources)
        _preflight_sources(spec, validated_sources, full_read=replace)
        _prepare_target(path, spec, replace=replace)
        _stream_sources(
            path,
            spec,
            validated_sources,
            progress,
            batch_size=batch_size,
            progress_every=progress_every,
        )
    except Exception as exc:
        message = str(exc)
        _finish_import_run(path, import_id, "FAILED", progress, message)
        logger.error(
            "Import failed | import_id=%s dataset=%s rows_read=%s rows_inserted=%s error=%s",
            import_id,
            spec.dataset_name,
            progress.rows_read,
            progress.rows_inserted,
            message,
        )
        if isinstance(exc, DataImportError):
            raise
        raise DataImportError(message) from exc

    _finish_import_run(path, import_id, "COMPLETED", progress)
    duration = time.perf_counter() - started
    logger.info(
        "Import completed | import_id=%s dataset=%s rows=%s duration_seconds=%.2f",
        import_id,
        spec.dataset_name,
        f"{progress.rows_inserted:,}",
        duration,
    )
    return ImportResult(
        import_id=import_id,
        dataset_name=spec.dataset_name,
        status="COMPLETED",
        rows_read=progress.rows_read,
        rows_inserted=progress.rows_inserted,
        rows_rejected=progress.rows_rejected,
        duration_seconds=duration,
        source_paths=tuple(str(path) for path in validated_sources),
    )


def import_customers(
    source_file: str | Path,
    *,
    database_path: str | Path | None = None,
    replace: bool = False,
    batch_size: int = 10_000,
    progress_every: int = 50_000,
) -> ImportResult:
    return _import_dataset(
        CUSTOMER_SPEC,
        (source_file,),
        database_path=database_path,
        replace=replace,
        batch_size=batch_size,
        progress_every=progress_every,
    )


def import_campaign_sales(
    source_file: str | Path,
    *,
    database_path: str | Path | None = None,
    replace: bool = False,
    batch_size: int = 10_000,
    progress_every: int = 50_000,
) -> ImportResult:
    return _import_dataset(
        CAMPAIGN_SALES_SPEC,
        (source_file,),
        database_path=database_path,
        replace=replace,
        batch_size=batch_size,
        progress_every=progress_every,
    )


def import_demographics(
    source_files: Sequence[str | Path],
    *,
    database_path: str | Path | None = None,
    replace: bool = False,
    batch_size: int = 10_000,
    progress_every: int = 50_000,
) -> ImportResult:
    return _import_dataset(
        DEMOGRAPHIC_SPEC,
        source_files,
        database_path=database_path,
        replace=replace,
        batch_size=batch_size,
        progress_every=progress_every,
    )
