"""Exact, deterministic support-aware split over historical buyer identities only.

No prospect, demographic feature, score, response metric, or campaign yield is an
input. The bounded MILP has one integer holdout count per membership signature,
not one variable per customer or prospect. Every optimization stage is solved to
proven optimality before the next lexicographic stage is considered.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


SUPPORT_AWARE_SPLIT_VERSION = "SIMILARITY_CUSTOMER_SPLIT_V2"
SUPPORT_AWARE_OBJECTIVE_VERSION = "PRODUCT_L1_UNION_L1_BASELINE_FLIPS_SIGNATURE_LEX_V1"
MAX_EXACT_SIGNATURES = 64
MAX_SOLVE_SECONDS = 30.0


@dataclass(frozen=True)
class SupportAwareSplit:
    status: str
    assignments: dict[str, str] | None
    reason_code: str
    product_targets: dict[str, int]
    product_holdout_deviation: int | None
    union_target: int
    union_holdout_deviation: int | None
    baseline_assignment_changes: int | None
    signature_count: int


def _identity_key(customer_id: str, seed: int) -> tuple[bytes, str]:
    return hashlib.sha256(f"{seed}\0{customer_id}".encode("utf-8")).digest(), customer_id


def _nearest_fifth(count: int) -> int:
    # Integer arithmetic is exact for floor(0.20*n + 0.5), including ties.
    return (2 * count + 5) // 10


def solve_support_aware_split(
    product_members: Mapping[str, Iterable[str]],
    baseline: Mapping[str, str],
    *,
    seed: int,
    minimum_buyers: int = 200,
    minimum_fit: int = 160,
    minimum_holdout: int = 40,
    max_signatures: int = MAX_EXACT_SIGNATURES,
    time_limit_seconds: float = MAX_SOLVE_SECONDS,
) -> SupportAwareSplit:
    """Return FEASIBLE, proved INFEASIBLE, or UNRESOLVED without heuristics."""

    products = tuple(sorted(product_members))
    members = {product: frozenset(str(value) for value in product_members[product])
               for product in products}
    union = frozenset().union(*members.values()) if members else frozenset()
    if not products or set(baseline) != union or any(
        value not in {"FIT", "HOLDOUT"} for value in baseline.values()
    ):
        raise ValueError("The exact buyer membership and baseline assignment are invalid.")
    targets = {product: _nearest_fifth(len(members[product])) for product in products}
    union_target = _nearest_fifth(len(union))
    signatures: dict[tuple[str, ...], list[str]] = {}
    for customer_id in union:
        signature = tuple(product for product in products if customer_id in members[product])
        signatures.setdefault(signature, []).append(customer_id)
    signature_order = tuple(sorted(
        signatures, key=lambda signature: (
            hashlib.sha256(
                f"{seed}\0{'|'.join(signature)}".encode("utf-8")
            ).digest(), signature,
        ),
    ))
    base = dict(
        assignments=None, product_targets=targets, union_target=union_target,
        product_holdout_deviation=None, union_holdout_deviation=None,
        baseline_assignment_changes=None, signature_count=len(signature_order),
    )
    if any(len(members[product]) < minimum_buyers for product in products):
        return SupportAwareSplit("INFEASIBLE", reason_code="INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT", **base)
    if any(len(members[product]) < minimum_fit + minimum_holdout for product in products):
        return SupportAwareSplit("INFEASIBLE", reason_code="INSUFFICIENT_SPLIT_SUPPORT", **base)
    if len(signature_order) > max_signatures or not 0 < time_limit_seconds <= 300:
        return SupportAwareSplit("UNRESOLVED", reason_code="SPLIT_SOLVER_CAPACITY", **base)

    m = len(signature_order)
    p = len(products)
    x = slice(0, m)
    deviation = slice(m, m + p)
    union_deviation = m + p
    baseline_deviation = slice(m + p + 1, 2 * m + p + 1)
    width = 2 * m + p + 1
    sizes = np.array([len(signatures[sig]) for sig in signature_order], dtype=float)
    baseline_holdouts = np.array([
        sum(baseline[customer_id] == "HOLDOUT" for customer_id in signatures[sig])
        for sig in signature_order
    ], dtype=float)
    upper = np.concatenate((sizes, np.array([len(members[product]) for product in products], dtype=float),
                            [float(len(union))], sizes))
    rows: list[np.ndarray] = []
    lower: list[float] = []
    limits: list[float] = []

    def add(row: np.ndarray, lo: float = -np.inf, hi: float = np.inf) -> None:
        rows.append(row.copy())
        lower.append(lo)
        limits.append(hi)

    for product_index, product in enumerate(products):
        incidence = np.array([float(product in sig) for sig in signature_order])
        row = np.zeros(width)
        row[x] = incidence
        add(row, minimum_holdout, len(members[product]) - minimum_fit)
        row = row.copy()
        row[m + product_index] = -1
        add(row, hi=targets[product])
        row[x] = -incidence
        add(row, hi=-targets[product])
    row = np.zeros(width)
    row[x] = 1
    row[union_deviation] = -1
    add(row, hi=union_target)
    row[x] = -1
    add(row, hi=-union_target)
    for index, count in enumerate(baseline_holdouts):
        row = np.zeros(width)
        row[index] = 1
        row[baseline_deviation.start + index] = -1
        add(row, hi=float(count))
        row[index] = -1
        add(row, hi=-float(count))

    deadline = time.monotonic() + time_limit_seconds

    def optimal(objective: np.ndarray) -> tuple[str, np.ndarray | None]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "UNRESOLVED", None
        result = milp(
            objective, integrality=np.ones(width), bounds=Bounds(np.zeros(width), upper),
            constraints=LinearConstraint(np.vstack(rows), np.array(lower), np.array(limits)),
            options={"time_limit": remaining, "mip_rel_gap": 0.0, "disp": False},
        )
        if result.status == 2:
            return "INFEASIBLE", None
        if result.status != 0 or result.x is None:
            return "UNRESOLVED", None
        rounded = np.rint(result.x)
        if not np.allclose(result.x, rounded, atol=1e-5, rtol=0):
            return "UNRESOLVED", None
        return "FEASIBLE", rounded.astype(int)

    objectives: list[np.ndarray] = []
    product_objective = np.zeros(width)
    product_objective[deviation] = 1
    objectives.append(product_objective)
    union_objective = np.zeros(width)
    union_objective[union_deviation] = 1
    objectives.append(union_objective)
    baseline_objective = np.zeros(width)
    baseline_objective[baseline_deviation] = 1
    objectives.append(baseline_objective)
    for index in range(m):
        objective = np.zeros(width)
        objective[index] = 1
        objectives.append(objective)
    solution: np.ndarray | None = None
    for objective_index, objective in enumerate(objectives):
        status, solution = optimal(objective)
        if status != "FEASIBLE":
            if status == "INFEASIBLE" and objective_index == 0:
                return SupportAwareSplit("INFEASIBLE", reason_code="SPLIT_CONSTRAINTS_INFEASIBLE", **base)
            return SupportAwareSplit("UNRESOLVED", reason_code="SPLIT_SOLVER_UNRESOLVED", **base)
        assert solution is not None
        add(objective.copy(), float(objective @ solution), float(objective @ solution))

    assert solution is not None
    assignments = dict(baseline)
    for index, signature in enumerate(signature_order):
        desired = int(solution[index])
        candidates = signatures[signature]
        kept = sorted((customer_id for customer_id in candidates
                       if baseline[customer_id] == "HOLDOUT"), key=lambda cid: _identity_key(cid, seed))
        promoted = sorted((customer_id for customer_id in candidates
                           if baseline[customer_id] == "FIT"), key=lambda cid: _identity_key(cid, seed))
        selected = set((kept + promoted)[:desired])
        for customer_id in candidates:
            assignments[customer_id] = "HOLDOUT" if customer_id in selected else "FIT"
    holdouts = {product: sum(assignments[cid] == "HOLDOUT" for cid in members[product])
                for product in products}
    if any(not minimum_holdout <= holdouts[product] <= len(members[product]) - minimum_fit
           for product in products):
        return SupportAwareSplit("UNRESOLVED", reason_code="SPLIT_VERIFICATION_FAILED", **base)
    union_holdouts = sum(value == "HOLDOUT" for value in assignments.values())
    changes = sum(assignments[cid] != baseline[cid] for cid in union)
    if (sum(abs(holdouts[product] - targets[product]) for product in products)
        != int(product_objective @ solution)
        or abs(union_holdouts - union_target) != int(union_objective @ solution)
        or changes != int(baseline_objective @ solution)):
        return SupportAwareSplit("UNRESOLVED", reason_code="SPLIT_VERIFICATION_FAILED", **base)
    return SupportAwareSplit(
        "FEASIBLE", assignments, "ELIGIBLE", targets,
        sum(abs(holdouts[product] - targets[product]) for product in products),
        union_target, abs(union_holdouts - union_target), changes, m,
    )


__all__ = ["MAX_EXACT_SIGNATURES", "MAX_SOLVE_SECONDS", "SUPPORT_AWARE_OBJECTIVE_VERSION",
           "SUPPORT_AWARE_SPLIT_VERSION", "SupportAwareSplit", "solve_support_aware_split"]
