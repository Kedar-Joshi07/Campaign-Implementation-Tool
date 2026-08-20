"""Configured, per-operation SQLite connections."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import DATABASE_BUSY_TIMEOUT_MS, DATABASE_PATH


logger = logging.getLogger(__name__)


def _prepare_database_path(database_path: str | Path | None) -> Path:
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def open_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open and configure one SQLite connection."""
    path = _prepare_database_path(database_path)
    connection = sqlite3.connect(
        str(path),
        timeout=DATABASE_BUSY_TIMEOUT_MS / 1000,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DATABASE_BUSY_TIMEOUT_MS}")

    try:
        connection.execute("PRAGMA journal_mode = WAL").fetchone()
    except sqlite3.OperationalError as exc:
        logger.warning("Unable to enable SQLite WAL mode | path=%s error=%s", path, exc)

    return connection


@contextmanager
def get_connection(
    database_path: str | Path | None = None,
    *,
    write: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection and manage commit, rollback, and close."""
    connection = open_connection(database_path)
    try:
        yield connection
        if write:
            connection.commit()
    except Exception:
        if write:
            connection.rollback()
        raise
    finally:
        connection.close()
