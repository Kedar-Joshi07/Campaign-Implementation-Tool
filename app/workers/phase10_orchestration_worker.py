"""Process-safe top-level target for a durable Phase 10 parent workflow."""

from __future__ import annotations

from pathlib import Path

from app.services.phase10_orchestration_service import run_phase10_orchestration


def run_phase10_orchestration_job(
    database_path: str | Path,
    orchestration_id: int,
    project_root: str | Path | None = None,
) -> None:
    run_phase10_orchestration(
        database_path,
        orchestration_id,
        project_root=project_root,
    )


__all__ = ("run_phase10_orchestration_job",)
