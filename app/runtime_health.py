"""Bounded, non-sensitive health state for critical runtime composition."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeHealthState:
    phase11_search_available: bool = False
    feedback_recalibration_available: bool = False
    issue_codes: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.phase11_search_available = False
        self.feedback_recalibration_available = False
        self.issue_codes = []

    def mark_ready(self) -> None:
        self.phase11_search_available = True
        self.feedback_recalibration_available = True
        self.issue_codes = []

    def mark_composition_failure(self) -> None:
        self.phase11_search_available = False
        self.feedback_recalibration_available = False
        self.issue_codes = ["PHASE11_RUNTIME_COMPOSITION_UNAVAILABLE"]


__all__ = ("RuntimeHealthState",)
