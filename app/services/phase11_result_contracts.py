"""Pure registry contracts shared by orchestration and artifact materialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.selection_contracts import (
    CALIBRATED_MEMBERSHIP_CONTRACT_VERSION,
    CALIBRATED_SELECTION_CONTRACT_VERSION,
)


SEARCH_RUN_CONTRACT_VERSION = "1"
RESULT_MEMBERSHIP_V1_CONTRACT_VERSION = "1"
RESULT_MEMBERSHIP_V2_CONTRACT_VERSION = CALIBRATED_MEMBERSHIP_CONTRACT_VERSION
# Frozen compatibility alias. New code must resolve the membership version from
# the immutable selection contract instead of treating this as a latest version.
RESULT_MEMBERSHIP_CONTRACT_VERSION = RESULT_MEMBERSHIP_V1_CONTRACT_VERSION
RESULT_EXPORT_CONTRACT_VERSION = "1"
RESULT_MEMBERSHIP_V1_COLUMNS = (
    "person_id", "propensity_score", "percentile_bucket", "decile", "rank_band",
)
RESULT_MEMBERSHIP_V2_COLUMNS = (
    "person_id", "calibrated_purchase_probability", "probability_bucket",
    "raw_propensity_score", "percentile_bucket", "decile", "rank_band",
)
# Frozen compatibility alias for legacy callers and v1 export schemas.
RESULT_MEMBERSHIP_COLUMNS = RESULT_MEMBERSHIP_V1_COLUMNS
SEARCH_RUN_STATUSES = frozenset({"QUEUED", "PROCESSING", "COMPLETED", "BLOCKED", "FAILED"})
RESULT_SOURCES = frozenset({"EXACT_RESULT_REUSE", "INTELLIGENCE_REUSE", "NEW_INTELLIGENCE_BUILD"})
RESULT_CURRENTNESS_STATES = frozenset({"CURRENT", "STALE", "UNVERIFIED"})
RESULT_STORAGE_FORMATS = frozenset({"CSV_GZIP", "JSONL_GZIP", "PARQUET"})
RESULT_EXPORT_STATUSES = frozenset({"RUNNING", "COMPLETED", "FAILED", "ABORTED"})
_PROHIBITED_KEYS = frozenset({
    "customer_id", "customer_ids", "person_id", "person_ids", "first_name", "last_name",
    "name", "email", "phone", "phone_number", "address", "address_line_1", "address_line_2",
    "street", "postal_code", "city", "push_token", "advertising_id", "web_visitor_id",
})


class Phase11RegistryValidationError(ValueError):
    """Invalid metadata, identity, or privacy boundary."""


class Phase11RegistryStateError(RuntimeError):
    """Missing lineage or conflicting/terminal state."""


def result_membership_contract_for_selection(selection_contract_version: Any) -> str:
    """Resolve the immutable analytical schema owned by a selection contract."""

    version = str(selection_contract_version or "1")
    if version == "1":
        return RESULT_MEMBERSHIP_V1_CONTRACT_VERSION
    if version == CALIBRATED_SELECTION_CONTRACT_VERSION:
        return RESULT_MEMBERSHIP_V2_CONTRACT_VERSION
    raise Phase11RegistryValidationError("Unsupported selection contract version.")


def result_membership_columns(contract_version: Any) -> tuple[str, ...]:
    version = str(contract_version)
    if version == RESULT_MEMBERSHIP_V1_CONTRACT_VERSION:
        return RESULT_MEMBERSHIP_V1_COLUMNS
    if version == RESULT_MEMBERSHIP_V2_CONTRACT_VERSION:
        return RESULT_MEMBERSHIP_V2_COLUMNS
    raise Phase11RegistryValidationError("Unsupported membership contract version.")


def canonical_metadata_json(value: Any, *, branches: bool = False) -> tuple[str, str]:
    """Canonicalize finite object/branch metadata and reject contact/identity keys."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise Phase11RegistryValidationError("Metadata must be valid JSON.") from exc
    if branches:
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 49:
            raise Phase11RegistryValidationError("Filter branches must contain 1 to 49 objects.")
        if not all(isinstance(branch, Mapping) for branch in value):
            raise Phase11RegistryValidationError("Every filter branch must be an object.")
        value = [dict(branch) for branch in value]
    elif isinstance(value, Mapping):
        value = dict(value)
    else:
        raise Phase11RegistryValidationError("Criteria must be a JSON object.")

    def check(item: Any) -> None:
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise Phase11RegistryValidationError("Metadata keys must be text.")
            if _PROHIBITED_KEYS.intersection(key.strip().lower() for key in item):
                raise Phase11RegistryValidationError("Contact or membership identity is prohibited in metadata.")
            for nested in item.values():
                check(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                check(nested)

    check(value)
    try:
        encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError) as exc:
        raise Phase11RegistryValidationError("Metadata must be finite JSON.") from exc
    if len(encoded) > 100_000:
        raise Phase11RegistryValidationError("Metadata exceeds the bounded registry limit.")
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()
