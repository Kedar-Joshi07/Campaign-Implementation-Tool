"""FastAPI dependencies shared by application routers."""

from __future__ import annotations

from pathlib import Path

from app import config


def get_database_path() -> Path:
    """Return the configured database path with an override seam for tests."""
    return config.DATABASE_PATH
