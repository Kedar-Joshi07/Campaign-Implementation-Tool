"""Application logging configuration."""

from __future__ import annotations

from logging.config import dictConfig

from app.config import LOG_LEVEL


def configure_logging() -> None:
    """Configure consistent console logging for the local POC."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": LOG_LEVEL,
                }
            },
            "root": {"handlers": ["console"], "level": LOG_LEVEL},
        }
    )

