"""Authoritative candidate-role and selection policy for Phase 3 models."""

from __future__ import annotations

from typing import Literal

from app.ml.pu_estimators import BAGGING_PU_NAME, ELKAN_NOTO_NAME, NAIVE_BASELINE_NAME


MODEL_ROLE_POLICY_VERSION = "2"

PRIMARY_ROLE = "PRIMARY"
CHALLENGER_1_ROLE = "CHALLENGER_1"
DIAGNOSTIC_CONTROL_ROLE = "DIAGNOSTIC_CONTROL"
PRIMARY_ROLE_GOVERNED_SELECTION = "PRIMARY_ROLE_GOVERNED"

PRIMARY_MODEL_NAME = BAGGING_PU_NAME
CHALLENGER_1_MODEL_NAME = ELKAN_NOTO_NAME
DIAGNOSTIC_CONTROL_NAME = NAIVE_BASELINE_NAME

CandidateRole = Literal["PRIMARY", "CHALLENGER_1", "DIAGNOSTIC_CONTROL"]

CANDIDATE_ROLE_BY_NAME: dict[str, CandidateRole] = {
    PRIMARY_MODEL_NAME: PRIMARY_ROLE,
    CHALLENGER_1_MODEL_NAME: CHALLENGER_1_ROLE,
    DIAGNOSTIC_CONTROL_NAME: DIAGNOSTIC_CONTROL_ROLE,
}


def expected_candidate_role(candidate_name: str) -> CandidateRole:
    """Return the governed role for an exact supported candidate name."""
    try:
        return CANDIDATE_ROLE_BY_NAME[candidate_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported model candidate: {candidate_name}.") from exc


__all__ = (
    "CANDIDATE_ROLE_BY_NAME",
    "CHALLENGER_1_MODEL_NAME",
    "CHALLENGER_1_ROLE",
    "CandidateRole",
    "DIAGNOSTIC_CONTROL_NAME",
    "DIAGNOSTIC_CONTROL_ROLE",
    "MODEL_ROLE_POLICY_VERSION",
    "PRIMARY_MODEL_NAME",
    "PRIMARY_ROLE",
    "PRIMARY_ROLE_GOVERNED_SELECTION",
    "expected_candidate_role",
)
