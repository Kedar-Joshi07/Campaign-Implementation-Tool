"""Business-safe durable lifecycle, progress, issue, and ETA projections."""

from __future__ import annotations

import json
import math
import statistics
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
STALE_HEARTBEAT_SECONDS = 120


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
    stage_duration_samples: list[float] | None = None,
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

    samples = sorted(
        float(value) for value in (stage_duration_samples or [])
        if isinstance(value, (int, float)) and math.isfinite(float(value)) and value >= 0
    )
    started = _parse_timestamp(runtime.get("stage_started_at"))
    if started is None or len(samples) < 3:
        return {
            "estimated_seconds_remaining_low": None,
            "estimated_seconds_remaining_high": None,
            "estimated_completion_at": None,
            "estimate_confidence": "UNAVAILABLE",
            "estimate_basis": "INSUFFICIENT_STAGE_HISTORY",
        }
    elapsed = max(1.0, (now - started).total_seconds())
    low_duration = statistics.median(samples)
    p90_index = min(len(samples) - 1, math.ceil(len(samples) * .9) - 1)
    high_duration = samples[p90_index]
    low = max(0, min(MAX_ESTIMATE_SECONDS, math.ceil(low_duration - elapsed)))
    high = max(low, min(MAX_ESTIMATE_SECONDS, math.ceil(high_duration - elapsed)))
    return {
        "estimated_seconds_remaining_low": low,
        "estimated_seconds_remaining_high": high,
        "estimated_completion_at": _timestamp(now + timedelta(seconds=high)),
        "estimate_confidence": "HIGH" if len(samples) >= 10 else "MEDIUM",
        "estimate_basis": "HISTORICAL_STAGE_P50_P90",
    }


def project_run_progress(
    run: Mapping[str, Any],
    runtime: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    stage_duration_samples: list[float] | None = None,
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
    eta = _bounded_eta(
        run, runtime, now=current, stage_duration_samples=stage_duration_samples,
    )
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


def project_run_issue(
    runtime: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return allowlisted user guidance without exposing internal exceptions."""

    if runtime is None:
        return None
    if runtime.get("failure_code") is None:
        heartbeat = _parse_timestamp(runtime.get("heartbeat_at") or runtime.get("updated_at"))
        current = now or datetime.now(timezone.utc)
        if (
            runtime.get("lifecycle_status") == "PROCESSING"
            and heartbeat is not None
            and current - heartbeat >= timedelta(seconds=STALE_HEARTBEAT_SECONDS)
        ):
            return {
                "code": "STALE_PROCESSING_ATTEMPT",
                "category": "PROCESSING_FAILURE",
                "summary": "This search stopped sending progress updates and can be retried safely.",
                "resolution_steps": ["Retry the saved search."],
                "retryable": True,
                "affected_stage": str(runtime.get("stage_code") or "PROCESSING"),
                "technical_reference": "STALE_PROCESSING_ATTEMPT",
                "user_action_required": False,
            }
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
        "affected_stage": str(
            runtime.get("failure_stage_code") or runtime.get("stage_code") or "UNKNOWN"
        ),
        "technical_reference": str(runtime["failure_code"]),
        "user_action_required": str(runtime.get("failure_category")) in {
            "SAVED_TARGETING_CRITERIA", "TARGETING_INTELLIGENCE", "CALIBRATION",
        },
    }


__all__ = (
    "ACTIVE_LIFECYCLE_STATUSES",
    "MAX_ESTIMATE_SECONDS",
    "STALE_HEARTBEAT_SECONDS",
    "TERMINAL_LIFECYCLE_STATUSES",
    "project_run_issue",
    "project_run_progress",
)
