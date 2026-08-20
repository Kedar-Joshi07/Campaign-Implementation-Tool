"""Central environment-based application configuration."""

from __future__ import annotations

import math
import os
from pathlib import Path


def _percentage_from_env(name: str, default: str) -> float:
    """Read a finite percentage constrained to the inclusive 0–100 range."""
    raw_value = os.getenv(name, default)
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number from 0 through 100") from exc
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f"{name} must be a finite number from 0 through 100")
    return value


APP_NAME = os.getenv("APP_NAME", "Campaign Implementation Intelligence")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/campaign_poc.db"))
DATABASE_BUSY_TIMEOUT_MS = int(os.getenv("DATABASE_BUSY_TIMEOUT_MS", "5000"))
EXPECTED_CUSTOMER_ROWS = int(os.getenv("EXPECTED_CUSTOMER_ROWS", "125000"))
EXPECTED_CAMPAIGN_SALES_ROWS = int(os.getenv("EXPECTED_CAMPAIGN_SALES_ROWS", "570000"))
EXPECTED_DEMOGRAPHIC_ROWS = int(os.getenv("EXPECTED_DEMOGRAPHIC_ROWS", "5000000"))
CUSTOMER_COUNT_EXACT_REQUIRED = os.getenv(
    "CUSTOMER_COUNT_EXACT_REQUIRED", "false"
).lower() in {"1", "true", "yes", "on"}
CUSTOMER_COUNT_TOLERANCE_PERCENT = _percentage_from_env(
    "CUSTOMER_COUNT_TOLERANCE_PERCENT", "5.0"
)
CAMPAIGN_SALES_COUNT_EXACT_REQUIRED = os.getenv(
    "CAMPAIGN_SALES_COUNT_EXACT_REQUIRED", "true"
).lower() in {"1", "true", "yes", "on"}
DEMOGRAPHIC_COUNT_EXACT_REQUIRED = os.getenv(
    "DEMOGRAPHIC_COUNT_EXACT_REQUIRED", "true"
).lower() in {"1", "true", "yes", "on"}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
