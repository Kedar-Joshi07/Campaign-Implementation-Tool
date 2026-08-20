"""Central environment-based application configuration."""

from __future__ import annotations

import os
from pathlib import Path


APP_NAME = os.getenv("APP_NAME", "Campaign Implementation Intelligence")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/campaign_poc.db"))
DATABASE_BUSY_TIMEOUT_MS = int(os.getenv("DATABASE_BUSY_TIMEOUT_MS", "5000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
