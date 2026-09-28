"""Dependency-neutral application filesystem paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

__all__ = ("PROJECT_ROOT",)
