"""Business-safe durable lifecycle, progress, issue, and ETA projections."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


ACTIVE_LIFECYCLE_STATUSES = frozenset(
    {
        "QUEUED",
        "PROCESSING",
        "PAUSE_REQUESTED",
        "PAUSED",
        "STOP_REQUESTED",
        "RESTART_REQUESTED",
    }
)
TERMINAL_LIFECYCLE_STATUSES = frozenset(
    {"COMPLETED", "STOPPED", "BLOCKED", "FAILED"}
)
MAX_ESTIMATE_SECONDS = 24 * 60 * 60


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _bounded_eta(
    run: Mapping[str, Any],
    runtime: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    status = str(runtime["lifecycle_status"])
    progress = int(runtime["progress_percent"])
    if status == "COMPLETED":
        return {
            "estimated_seconds_remaining_low": 0,
            "estimated_seconds_remaining_high": 0,
            "estimated_completion_at": run.get("completed_at"),
            "estimate_confidence": "HIGH",
            "estimate_basis": "COMPLETED",
        }
    if status != "PROCESSING" or progress < 2 or progress >= 100:
        return {
            "estimated_seconds_remaining_low": None,
            "estimated_seconds_remaining_high": None,
            "estimated_completion_at": None,
            "estimate_confidence": "UNAVAILABLE",
            "estimate_basis": (
                "WAITING_FOR_CAPACITY" if status == "QUEUED" else "NOT_APPLICABLE"
            ),
        }

    started = _parse_timestamp(
        runtime.get("processing_started_at")
        or run.get("started_at")
        or run.get("created_at")
    )
    if started is None:
        return {
            "estimated_seconds_remaining_low": None,
            "estimated_seconds_remaining_high": None,
            "estimated_completion_at": None,
            "estimate_confidence": "UNAVAILABLE",
            "estimate_basis": "INSUFFICIENT_TIMING_DATA",
        }
    elapsed = max(1.0, (now - started).total_seconds())
    remaining = elapsed * (100 - progress) / max(progress, 1)
    if not math.isfinite(remaining) or remaining < 0:
        remaining = float(MAX_ESTIMATE_SECONDS)
    remaining = min(remaining, float(MAX_ESTIMATE_SECONDS))
    low = max(1, min(MAX_ESTIMATE_SECONDS, math.ceil(remaining * 0.65)))
    high = max(low, min(MAX_ESTIMATE_SECONDS, math.ceil(remaining * 1.75)))
    return {
        "estimated_seconds_remaining_low": low,
        "estimated_seconds_remaining_high": high,
        "estimated_completion_at": _timestamp(now + timedelta(seconds=high)),
        "estimate_confidence": "MEDIUM" if progress >= 25 else "LOW",
        "estimate_basis": "CURRENT_RUN_OBSERVED_RATE",
    }


def project_run_progress(
    run: Mapping[str, Any],
    runtime: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Project persisted facts plus a bounded, explicitly qualified ETA."""

    if runtime is None:
        status = str(run["status"])
        progress = 100 if status == "COMPLETED" else 0
        runtime = {
            "lifecycle_status": status,
            "stage_code": status,
            "stage_label": status.replace("_", " ").title(),
            "progress_percent": progress,
            "processed_count": int(run.get("selected_count") or 0),
            "total_count": run.get("selected_count"),
            "progress_unit": "potential customers",
            "status_message": "Progress details are unavailable for this saved search.",
            "updated_at": run.get("completed_at") or run.get("created_at"),
            "heartbeat_at": None,
            "state_version": 1,
        }
    current = now or datetime.now(timezone.utc)
    eta = _bounded_eta(run, runtime, now=current)
    return {
        "contract_version": "1",
        "lifecycle_status": str(runtime["lifecycle_status"]),
        "stage_code": str(runtime["stage_code"]),
        "stage_label": str(runtime["stage_label"]),
        "progress_percent": int(runtime["progress_percent"]),
        "processed_count": int(runtime["processed_count"]),
        "total_count": (
            int(runtime["total_count"])
            if runtime.get("total_count") is not None
            else None
        ),
        "progress_unit": str(runtime["progress_unit"]),
        "status_message": str(runtime["status_message"]),
        "updated_at": str(runtime["updated_at"]),
        "heartbeat_at": runtime.get("heartbeat_at"),
        "state_version": int(runtime["state_version"]),
    } | eta


def project_run_issue(runtime: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return allowlisted user guidance without exposing internal exceptions."""

    if runtime is None or runtime.get("failure_code") is None:
        return None
    try:
        steps = json.loads(str(runtime["resolution_steps_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        steps = []
    if not isinstance(steps, list):
        steps = []
    return {
        "code": str(runtime["failure_code"]),
        "category": str(runtime["failure_category"]),
        "summary": str(runtime["failure_summary"]),
        "resolution_steps": [str(step) for step in steps[:8]],
        "retryable": bool(runtime["retryable"]),
    }


__all__ = (
    "ACTIVE_LIFECYCLE_STATUSES",
    "MAX_ESTIMATE_SECONDS",
    "TERMINAL_LIFECYCLE_STATUSES",
    "project_run_issue",
    "project_run_progress",
)
