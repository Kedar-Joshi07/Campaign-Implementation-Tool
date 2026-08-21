"""FastAPI dependencies shared by application routers."""

from __future__ import annotations

from pathlib import Path

from app import config
from app.database.schema import initialize_database


def get_database_path() -> Path:
    """Initialize/migrate and return the configured database path."""
    return initialize_database(config.DATABASE_PATH)
