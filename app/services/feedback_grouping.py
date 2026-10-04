"""Deterministic leakage-safe grouping for immutable feedback events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


FEEDBACK_GROUPING_CONTRACT_VERSION = "SEARCH_PERSON_CONNECTED_COMPONENT_V1"


@dataclass(frozen=True)
class FeedbackGrouping:
    row_group_ids: tuple[str, ...]
    independent_group_ids: tuple[str, ...]
    grouping_sha256: str


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_feedback_grouping(rows: Sequence[Mapping[str, Any]]) -> FeedbackGrouping:
    """Group the search/person bipartite graph into stable components.

    Original rows are not deduplicated or rewritten. The returned row-level
    group IDs only control statistical partitioning, ensuring every observation
    for a person remains on one side of the fit/evaluation boundary.
    """

    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        parent[second] = first

    normalized: list[tuple[str, str]] = []
    for row in rows:
        search_run_id = row.get("search_run_id")
        person_id = row.get("person_id")
        if (
            isinstance(search_run_id, bool)
            or not isinstance(search_run_id, int)
            or search_run_id <= 0
            or not isinstance(person_id, str)
            or not person_id
        ):
            raise ValueError("Feedback grouping requires valid search and person IDs.")
        search_node = f"search:{search_run_id}"
        person_node = f"person:{person_id}"
        union(search_node, person_node)
        normalized.append((search_node, person_node))

    components: dict[str, dict[str, set[str]]] = {}
    for search_node, person_node in normalized:
        root = find(search_node)
        component = components.setdefault(root, {"searches": set(), "people": set()})
        component["searches"].add(search_node.removeprefix("search:"))
        component["people"].add(person_node.removeprefix("person:"))

    component_ids: dict[str, str] = {}
    component_lineage: list[dict[str, Any]] = []
    for root, component in components.items():
        identity = {
            "search_run_ids": sorted(component["searches"], key=int),
            "person_ids": sorted(component["people"]),
        }
        identifier = "feedback-component:" + _canonical_sha(identity)
        component_ids[root] = identifier
        component_lineage.append(
            {
                "component_id": identifier,
                "search_run_ids": identity["search_run_ids"],
                "person_count": len(identity["person_ids"]),
                "person_ids_sha256": _canonical_sha(identity["person_ids"]),
            }
        )
    row_group_ids = tuple(component_ids[find(search)] for search, _person in normalized)
    independent = tuple(sorted(set(row_group_ids)))
    grouping_sha256 = _canonical_sha(
        {
            "contract_version": FEEDBACK_GROUPING_CONTRACT_VERSION,
            "components": sorted(component_lineage, key=lambda item: item["component_id"]),
        }
    )
    return FeedbackGrouping(row_group_ids, independent, grouping_sha256)


__all__ = (
    "FEEDBACK_GROUPING_CONTRACT_VERSION",
    "FeedbackGrouping",
    "build_feedback_grouping",
)
