"""Transactional persistence for Phase 10 intelligence and orchestration state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection


ORCHESTRATION_STATUSES = frozenset({"QUEUED", "RUNNING", "READY", "BLOCKED", "FAILED"})
ACTIVE_ORCHESTRATION_STATUSES = frozenset({"QUEUED", "RUNNING"})
LIFECYCLE_STATES = frozenset(
    {"CURRENT", "REUSABLE", "SUPERSEDED", "STALE", "RETIREMENT_ELIGIBLE", "PROTECTED"}
)
BINDING_STATUSES = frozenset({"PREPARING", "READY", "BLOCKED", "FAILED", "STALE"})

_GENERATION_INSERT_COLUMNS = (
    "intelligence_generation_contract_version",
    "compatibility_contract_version",
    "intelligence_key_sha256",
    "modeling_context_json",
    "modeling_context_sha256",
    "historical_filters_json",
    "historical_filters_sha256",
    "historical_window_policy_version",
    "multi_product_positive_policy_version",
    "training_eligibility_policy_version",
    "customer_import_id",
    "customer_source_checksum",
    "campaign_sales_import_id",
    "campaign_sales_source_checksum",
    "demographic_import_id",
    "demographic_source_checksum",
    "feature_contract_version",
    "feature_contract_sha256",
    "model_role_policy_version",
    "evaluation_contract_version",
    "automated_training_policy_version",
    "analysis_run_id",
    "model_run_id",
    "scoring_run_id",
    "artifact_sha256",
    "score_semantics_json",
    "score_semantics_sha256",
    "rank_contract_version",
    "analytics_contract_version",
    "lifecycle_policy_version",
    "generation_status",
    "lifecycle_state",
    "created_at",
    "last_verified_at",
    "last_used_at",
)

_GENERATION_JSON_HASH_PAIRS = (
    ("modeling_context_json", "modeling_context_sha256"),
    ("historical_filters_json", "historical_filters_sha256"),
    ("score_semantics_json", "score_semantics_sha256"),
)
_FORBIDDEN_PII_KEYS = frozenset(
    {
        "customer_id",
        "person_id",
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "street",
        "postal_code",
        "phone_number",
        "email",
    }
)


class Phase10RepositoryError(RuntimeError):
    """Base error for invalid or conflicting Phase 10 persistence operations."""


class Phase10RepositoryValidationError(Phase10RepositoryError):
    pass


class Phase10RepositoryStateError(Phase10RepositoryError):
    pass


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Phase10RepositoryValidationError(f"{field_name} must be a positive integer.")
    return value


def _optional_positive_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name=field_name)


def _text(value: Any, *, field_name: str, maximum: int, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise Phase10RepositoryValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise Phase10RepositoryValidationError(
            f"{field_name} must contain between 1 and {maximum} characters."
        )
    return normalized


def _sha256(value: Any, *, field_name: str) -> str:
    normalized = _text(value, field_name=field_name, maximum=64)
    assert normalized is not None
    normalized = normalized.lower()
    if len(normalized) != 64 or any(character not in hexdigits for character in normalized):
        raise Phase10RepositoryValidationError(f"{field_name} must be a valid SHA-256 value.")
    return normalized


def _json_object(value: Any, *, field_name: str) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise Phase10RepositoryValidationError(f"{field_name} must be valid JSON.") from exc
    elif isinstance(value, Mapping):
        decoded = dict(value)
    else:
        raise Phase10RepositoryValidationError(f"{field_name} must be a JSON object.")
    if not isinstance(decoded, dict):
        raise Phase10RepositoryValidationError(f"{field_name} must be a JSON object.")

    def assert_no_pii_keys(item: Any) -> None:
        if isinstance(item, dict):
            if _FORBIDDEN_PII_KEYS.intersection(item):
                raise Phase10RepositoryValidationError(
                    f"{field_name} contains prohibited contact or identity fields."
                )
            for nested in item.values():
                assert_no_pii_keys(nested)
        elif isinstance(item, list):
            for nested in item:
                assert_no_pii_keys(nested)

    assert_no_pii_keys(decoded)
    try:
        encoded = json.dumps(
            decoded,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise Phase10RepositoryValidationError(f"{field_name} is not finite JSON.") from exc
    if len(encoded.encode("utf-8")) > 65536:
        raise Phase10RepositoryValidationError(f"{field_name} exceeds 65536 bytes.")
    return encoded


def _json_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Phase10IntelligenceRepository:
    """Own atomic registry, orchestration, binding, and lifecycle mutations."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    @staticmethod
    def _assert_ready_lineage(
        connection: sqlite3.Connection,
        values: Mapping[str, Any],
    ) -> None:
        """Fail closed unless all READY IDs form one completed lineage."""

        row = connection.execute(
            """
            SELECT
                analysis.status AS analysis_status,
                analysis.customer_import_id AS analysis_customer_import_id,
                analysis.customer_source_checksum AS analysis_customer_checksum,
                analysis.campaign_sales_import_id AS analysis_campaign_import_id,
                analysis.campaign_sales_source_checksum AS analysis_campaign_checksum,
                model.status AS model_status,
                model.analysis_run_id AS model_analysis_run_id,
                model.artifact_sha256 AS model_artifact_sha256,
                scoring.status AS scoring_status,
                scoring.model_run_id AS scoring_model_run_id,
                scoring.artifact_sha256 AS scoring_artifact_sha256,
                scoring.feature_contract_version AS scoring_feature_version,
                scoring.feature_contract_sha256 AS scoring_feature_sha256,
                scoring.model_role_policy_version AS scoring_role_version,
                customer_import.dataset_name AS customer_dataset,
                customer_import.status AS customer_import_status,
                customer_import.source_checksum AS customer_import_checksum,
                campaign_import.dataset_name AS campaign_dataset,
                campaign_import.status AS campaign_import_status,
                campaign_import.source_checksum AS campaign_import_checksum,
                demographic_import.dataset_name AS demographic_dataset,
                demographic_import.status AS demographic_import_status,
                demographic_import.source_checksum AS demographic_import_checksum
            FROM historical_analysis_runs AS analysis
            JOIN model_runs AS model ON model.model_run_id = ?
            JOIN scoring_runs AS scoring ON scoring.scoring_run_id = ?
            JOIN data_import_runs AS customer_import ON customer_import.import_id = ?
            JOIN data_import_runs AS campaign_import ON campaign_import.import_id = ?
            JOIN data_import_runs AS demographic_import ON demographic_import.import_id = ?
            WHERE analysis.analysis_run_id = ?
            """,
            (
                values["model_run_id"],
                values["scoring_run_id"],
                values["customer_import_id"],
                values["campaign_sales_import_id"],
                values["demographic_import_id"],
                values["analysis_run_id"],
            ),
        ).fetchone()
        if row is None:
            raise Phase10RepositoryStateError(
                "READY generation analytical lineage is incomplete."
            )
        expected = {
            "analysis_status": "COMPLETED",
            "analysis_customer_import_id": values["customer_import_id"],
            "analysis_customer_checksum": values["customer_source_checksum"],
            "analysis_campaign_import_id": values["campaign_sales_import_id"],
            "analysis_campaign_checksum": values["campaign_sales_source_checksum"],
            "model_status": "COMPLETED",
            "model_analysis_run_id": values["analysis_run_id"],
            "model_artifact_sha256": values["artifact_sha256"],
            "scoring_status": "COMPLETED",
            "scoring_model_run_id": values["model_run_id"],
            "scoring_artifact_sha256": values["artifact_sha256"],
            "scoring_feature_version": values["feature_contract_version"],
            "scoring_feature_sha256": values["feature_contract_sha256"],
            "scoring_role_version": values["model_role_policy_version"],
            "customer_dataset": "customers",
            "customer_import_status": "COMPLETED",
            "customer_import_checksum": values["customer_source_checksum"],
            "campaign_dataset": "campaign_sales",
            "campaign_import_status": "COMPLETED",
            "campaign_import_checksum": values["campaign_sales_source_checksum"],
            "demographic_dataset": "demographics",
            "demographic_import_status": "COMPLETED",
            "demographic_import_checksum": values["demographic_source_checksum"],
        }
        if any(row[field] != expected_value for field, expected_value in expected.items()):
            raise Phase10RepositoryStateError(
                "READY generation analytical lineage is not valid."
            )

    @staticmethod
    def _assert_generation_payload_hashes(values: Mapping[str, Any]) -> None:
        for json_field, hash_field in _GENERATION_JSON_HASH_PAIRS:
            canonical = _json_object(values[json_field], field_name=json_field)
            if canonical != values[json_field] or _json_sha256(canonical) != values[hash_field]:
                raise Phase10RepositoryStateError(
                    f"Stored {json_field} is not canonical or does not match {hash_field}."
                )

    def fetch_generation(self, generation_id: int) -> dict[str, Any] | None:
        normalized_id = _positive_int(generation_id, field_name="generation_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM phase10_intelligence_generations WHERE generation_id = ?",
                (normalized_id,),
            ).fetchone()
        return _row_dict(row)

    def find_generation_by_intelligence_key(
        self,
        intelligence_key_sha256: str,
    ) -> dict[str, Any] | None:
        key = _sha256(intelligence_key_sha256, field_name="intelligence_key_sha256")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM phase10_intelligence_generations
                WHERE intelligence_key_sha256 = ? AND generation_status = 'READY'
                ORDER BY
                    CASE lifecycle_state
                        WHEN 'CURRENT' THEN 0
                        WHEN 'REUSABLE' THEN 1
                        WHEN 'PROTECTED' THEN 2
                        WHEN 'SUPERSEDED' THEN 3
                        WHEN 'STALE' THEN 4
                        ELSE 5
                    END,
                    created_at DESC,
                    generation_id DESC
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        return _row_dict(row)

    def find_generations_by_modeling_context(
        self,
        modeling_context_sha256: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        context_sha = _sha256(modeling_context_sha256, field_name="modeling_context_sha256")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise Phase10RepositoryValidationError("limit must be between 1 and 100.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM phase10_intelligence_generations
                WHERE modeling_context_sha256 = ?
                ORDER BY created_at DESC, generation_id DESC
                LIMIT ?
                """,
                (context_sha, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_ready_generation(self, values: Mapping[str, Any]) -> int:
        """Insert a complete immutable READY generation after boundary validation."""

        missing = set(_GENERATION_INSERT_COLUMNS).difference(values)
        extra = set(values).difference(_GENERATION_INSERT_COLUMNS)
        if missing or extra:
            raise Phase10RepositoryValidationError(
                "Generation fields do not match the registry contract."
            )
        normalized = dict(values)
        for field in (
            "intelligence_generation_contract_version",
            "compatibility_contract_version",
            "historical_window_policy_version",
            "multi_product_positive_policy_version",
            "training_eligibility_policy_version",
            "feature_contract_version",
            "model_role_policy_version",
            "evaluation_contract_version",
            "automated_training_policy_version",
            "rank_contract_version",
            "analytics_contract_version",
            "lifecycle_policy_version",
        ):
            normalized[field] = _text(values[field], field_name=field, maximum=24)
        for field in (
            "intelligence_key_sha256",
            "modeling_context_sha256",
            "historical_filters_sha256",
            "customer_source_checksum",
            "campaign_sales_source_checksum",
            "demographic_source_checksum",
            "feature_contract_sha256",
            "artifact_sha256",
            "score_semantics_sha256",
        ):
            normalized[field] = _sha256(values[field], field_name=field)
        for json_field, hash_field in _GENERATION_JSON_HASH_PAIRS:
            normalized[json_field] = _json_object(values[json_field], field_name=json_field)
            if _json_sha256(normalized[json_field]) != normalized[hash_field]:
                raise Phase10RepositoryValidationError(
                    f"{hash_field} does not match canonical {json_field}."
                )
        for field in (
            "customer_import_id",
            "campaign_sales_import_id",
            "demographic_import_id",
            "analysis_run_id",
            "model_run_id",
            "scoring_run_id",
        ):
            normalized[field] = _positive_int(values[field], field_name=field)
        if values["generation_status"] != "READY":
            raise Phase10RepositoryValidationError("generation_status must be READY.")
        if values["lifecycle_state"] not in LIFECYCLE_STATES:
            raise Phase10RepositoryValidationError("lifecycle_state is invalid.")
        for field in ("created_at", "last_verified_at", "last_used_at"):
            normalized[field] = _text(values[field], field_name=field, maximum=64)

        placeholders = ", ".join("?" for _ in _GENERATION_INSERT_COLUMNS)
        columns = ", ".join(_GENERATION_INSERT_COLUMNS)
        try:
            with get_connection(self.database_path, write=True) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._assert_ready_lineage(connection, normalized)
                cursor = connection.execute(
                    f"INSERT INTO phase10_intelligence_generations ({columns}) "
                    f"VALUES ({placeholders})",
                    tuple(normalized[column] for column in _GENERATION_INSERT_COLUMNS),
                )
        except sqlite3.IntegrityError as exc:
            raise Phase10RepositoryStateError(
                "The READY intelligence generation could not be registered."
            ) from exc
        return int(cursor.lastrowid)

    def verify_generation_record(self, generation_id: int) -> dict[str, Any]:
        """Verify canonical payload hashes and the complete persisted READY lineage."""

        normalized_id = _positive_int(generation_id, field_name="generation_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM phase10_intelligence_generations WHERE generation_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None or row["generation_status"] != "READY":
                raise Phase10RepositoryStateError("READY generation was not found.")
            values = dict(row)
            self._assert_generation_payload_hashes(values)
            self._assert_ready_lineage(connection, values)
        return values

    def record_generation_verification(self, generation_id: int, *, verified_at: str) -> None:
        normalized_id = _positive_int(generation_id, field_name="generation_id")
        timestamp = _text(verified_at, field_name="verified_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM phase10_intelligence_generations WHERE generation_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None or row["generation_status"] != "READY":
                raise Phase10RepositoryStateError("READY generation was not found.")
            values = dict(row)
            self._assert_generation_payload_hashes(values)
            self._assert_ready_lineage(connection, values)
            cursor = connection.execute(
                """
                UPDATE phase10_intelligence_generations
                SET last_verified_at = ?
                WHERE generation_id = ? AND generation_status = 'READY'
                """,
                (timestamp, normalized_id),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("READY generation was not found.")

    def touch_generation_usage(self, generation_id: int, *, used_at: str) -> None:
        normalized_id = _positive_int(generation_id, field_name="generation_id")
        timestamp = _text(used_at, field_name="used_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE phase10_intelligence_generations
                SET last_used_at = ?
                WHERE generation_id = ? AND generation_status = 'READY'
                """,
                (timestamp, normalized_id),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("READY generation was not found.")

    def update_generation_lifecycle(
        self,
        generation_id: int,
        *,
        lifecycle_state: str,
        verified_at: str,
    ) -> None:
        normalized_id = _positive_int(generation_id, field_name="generation_id")
        if lifecycle_state not in LIFECYCLE_STATES:
            raise Phase10RepositoryValidationError("lifecycle_state is invalid.")
        timestamp = _text(verified_at, field_name="verified_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE phase10_intelligence_generations
                SET lifecycle_state = ?, last_verified_at = ?
                WHERE generation_id = ? AND generation_status = 'READY'
                """,
                (lifecycle_state, timestamp, normalized_id),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("READY generation was not found.")

    def list_generations_by_lifecycle(
        self,
        lifecycle_states: list[str] | tuple[str, ...],
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        states = tuple(dict.fromkeys(lifecycle_states))
        if not states or any(state not in LIFECYCLE_STATES for state in states):
            raise Phase10RepositoryValidationError("lifecycle_states are invalid.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise Phase10RepositoryValidationError("limit must be between 1 and 100.")
        placeholders = ", ".join("?" for _ in states)
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM phase10_intelligence_generations
                WHERE lifecycle_state IN ({placeholders})
                ORDER BY last_used_at DESC, generation_id DESC
                LIMIT ?
                """,
                (*states, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_all_generations(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        """List immutable generation registry rows for lifecycle classification."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 10000
        ):
            raise Phase10RepositoryValidationError("limit must be between 1 and 10000.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM phase10_intelligence_generations
                ORDER BY generation_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def apply_generation_lifecycle_states(
        self,
        lifecycle_states: Mapping[int, str],
        *,
        verified_at: str,
    ) -> None:
        """Atomically classify generations without deleting analytical data."""

        timestamp = _text(verified_at, field_name="verified_at", maximum=64)
        normalized: dict[int, str] = {}
        for generation_id, lifecycle_state in lifecycle_states.items():
            normalized_id = _positive_int(generation_id, field_name="generation_id")
            if lifecycle_state not in LIFECYCLE_STATES:
                raise Phase10RepositoryValidationError("lifecycle_state is invalid.")
            normalized[normalized_id] = lifecycle_state
        if not normalized:
            return
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for generation_id, lifecycle_state in normalized.items():
                cursor = connection.execute(
                    """
                    UPDATE phase10_intelligence_generations
                    SET lifecycle_state = ?, last_verified_at = ?
                    WHERE generation_id = ? AND generation_status = 'READY'
                    """,
                    (lifecycle_state, timestamp, generation_id),
                )
                if cursor.rowcount != 1:
                    raise Phase10RepositoryStateError(
                        "READY generation was not found during lifecycle classification."
                    )

    def list_reusable_model_generations(
        self,
        modeling_context_sha256: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return retention-safe reusable model sources in priority order."""

        context_sha = _sha256(
            modeling_context_sha256,
            field_name="modeling_context_sha256",
        )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise Phase10RepositoryValidationError("limit must be between 1 and 100.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM phase10_intelligence_generations
                WHERE generation_status = 'READY'
                  AND lifecycle_state IN ('CURRENT', 'REUSABLE', 'PROTECTED')
                  AND modeling_context_sha256 = ?
                ORDER BY
                    CASE lifecycle_state
                        WHEN 'CURRENT' THEN 0
                        WHEN 'PROTECTED' THEN 1
                        ELSE 2
                    END,
                    created_at DESC,
                    generation_id DESC
                LIMIT ?
                """,
                (context_sha, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_active_orchestration(
        self,
        intelligence_key_sha256: str,
    ) -> dict[str, Any] | None:
        key = _sha256(intelligence_key_sha256, field_name="intelligence_key_sha256")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM phase10_orchestration_runs
                WHERE intelligence_key_sha256 = ? AND status IN ('QUEUED', 'RUNNING')
                ORDER BY orchestration_id DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
        return _row_dict(row)

    def find_ready_orchestration_for_context(
        self,
        targeting_context_id: int,
        intelligence_key_sha256: str,
    ) -> dict[str, Any] | None:
        """Return the exact READY workflow currently bound to one context."""

        context_id = _positive_int(
            targeting_context_id,
            field_name="targeting_context_id",
        )
        key = _sha256(
            intelligence_key_sha256,
            field_name="intelligence_key_sha256",
        )
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT orchestration.*
                FROM phase10_context_bindings AS binding
                JOIN phase10_orchestration_runs AS orchestration
                  ON orchestration.orchestration_id = binding.orchestration_id
                JOIN phase10_intelligence_generations AS generation
                  ON generation.generation_id = binding.generation_id
                WHERE binding.targeting_context_id = ?
                  AND binding.binding_status = 'READY'
                  AND orchestration.status = 'READY'
                  AND orchestration.intelligence_key_sha256 = ?
                  AND generation.generation_status = 'READY'
                  AND generation.intelligence_key_sha256 = ?
                LIMIT 1
                """,
                (context_id, key, key),
            ).fetchone()
        return _row_dict(row)

    def list_active_orchestrations(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        """List durable active parent workflows in deterministic restart order."""

        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise Phase10RepositoryValidationError("limit must be between 1 and 1000.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM phase10_orchestration_runs
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at, orchestration_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_or_get_active_orchestration(
        self,
        *,
        orchestration_contract_version: str,
        targeting_context_id: int,
        modeling_context_sha256: str,
        intelligence_key_sha256: str,
        business_message: str,
        reuse_plan: Mapping[str, Any],
        created_at: str,
    ) -> tuple[dict[str, Any], bool]:
        version = _text(
            orchestration_contract_version,
            field_name="orchestration_contract_version",
            maximum=24,
        )
        context_id = _positive_int(targeting_context_id, field_name="targeting_context_id")
        context_sha = _sha256(modeling_context_sha256, field_name="modeling_context_sha256")
        key = _sha256(intelligence_key_sha256, field_name="intelligence_key_sha256")
        message = _text(business_message, field_name="business_message", maximum=1000)
        plan_json = _json_object(reuse_plan, field_name="reuse_plan")
        timestamp = _text(created_at, field_name="created_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM phase10_orchestration_runs
                WHERE intelligence_key_sha256 = ? AND status IN ('QUEUED', 'RUNNING')
                ORDER BY orchestration_id DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
            if existing is not None:
                return dict(existing), False
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO phase10_orchestration_runs (
                        orchestration_contract_version, targeting_context_id,
                        modeling_context_sha256, intelligence_key_sha256,
                        status, stage, progress_percent, business_message,
                        reuse_plan_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'QUEUED', 'QUEUED', 0, ?, ?, ?, ?)
                    """,
                    (version, context_id, context_sha, key, message, plan_json, timestamp, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                raise Phase10RepositoryStateError(
                    "The orchestration could not be queued."
                ) from exc
            row = connection.execute(
                "SELECT * FROM phase10_orchestration_runs WHERE orchestration_id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
            assert row is not None
            return dict(row), True

    def fetch_orchestration(self, orchestration_id: int) -> dict[str, Any] | None:
        normalized_id = _positive_int(orchestration_id, field_name="orchestration_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM phase10_orchestration_runs WHERE orchestration_id = ?",
                (normalized_id,),
            ).fetchone()
        return _row_dict(row)

    def mark_orchestration_running(
        self,
        orchestration_id: int,
        *,
        stage: str,
        progress_percent: int,
        business_message: str,
        started_at: str,
        technical_message: str | None = None,
    ) -> None:
        normalized_id = _positive_int(orchestration_id, field_name="orchestration_id")
        if isinstance(progress_percent, bool) or not isinstance(progress_percent, int) or not 1 <= progress_percent <= 99:
            raise Phase10RepositoryValidationError("RUNNING progress must be between 1 and 99.")
        values = (
            _text(stage, field_name="stage", maximum=80),
            progress_percent,
            _text(business_message, field_name="business_message", maximum=1000),
            _text(technical_message, field_name="technical_message", maximum=8192, optional=True),
            _text(started_at, field_name="started_at", maximum=64),
            normalized_id,
        )
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE phase10_orchestration_runs
                SET status = 'RUNNING', stage = ?, progress_percent = ?,
                    business_message = ?, technical_message = ?,
                    started_at = ?, updated_at = ?
                WHERE orchestration_id = ? AND status = 'QUEUED'
                """,
                (*values[:5], values[4], values[5]),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("Only a QUEUED orchestration can start.")

    def update_orchestration_stage(
        self,
        orchestration_id: int,
        *,
        stage: str,
        progress_percent: int,
        business_message: str,
        updated_at: str,
        technical_message: str | None = None,
        reuse_plan: Mapping[str, Any] | None = None,
        analysis_run_id: int | None = None,
        model_run_id: int | None = None,
        scoring_run_id: int | None = None,
        training_job_id: int | None = None,
        scoring_job_id: int | None = None,
    ) -> None:
        normalized_id = _positive_int(orchestration_id, field_name="orchestration_id")
        if isinstance(progress_percent, bool) or not isinstance(progress_percent, int) or not 1 <= progress_percent <= 99:
            raise Phase10RepositoryValidationError("RUNNING progress must be between 1 and 99.")
        plan_json = None if reuse_plan is None else _json_object(reuse_plan, field_name="reuse_plan")
        ids = {
            field: _optional_positive_int(value, field_name=field)
            for field, value in (
                ("analysis_run_id", analysis_run_id),
                ("model_run_id", model_run_id),
                ("scoring_run_id", scoring_run_id),
                ("training_job_id", training_job_id),
                ("scoring_job_id", scoring_job_id),
            )
        }
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM phase10_orchestration_runs WHERE orchestration_id = ?",
                (normalized_id,),
            ).fetchone()
            if current is None or current["status"] != "RUNNING":
                raise Phase10RepositoryStateError("Only a RUNNING orchestration can advance.")
            if progress_percent < int(current["progress_percent"]):
                raise Phase10RepositoryStateError("Orchestration progress must be monotonic.")
            for field, value in ids.items():
                if current[field] is not None and value is not None and int(current[field]) != value:
                    raise Phase10RepositoryStateError(f"{field} cannot change once recorded.")
            cursor = connection.execute(
                """
                UPDATE phase10_orchestration_runs
                SET stage = ?, progress_percent = ?, business_message = ?,
                    technical_message = ?,
                    reuse_plan_json = COALESCE(?, reuse_plan_json),
                    analysis_run_id = COALESCE(analysis_run_id, ?),
                    model_run_id = COALESCE(model_run_id, ?),
                    scoring_run_id = COALESCE(scoring_run_id, ?),
                    training_job_id = COALESCE(training_job_id, ?),
                    scoring_job_id = COALESCE(scoring_job_id, ?),
                    updated_at = ?
                WHERE orchestration_id = ? AND status = 'RUNNING'
                    AND progress_percent <= ?
                """,
                (
                    _text(stage, field_name="stage", maximum=80),
                    progress_percent,
                    _text(business_message, field_name="business_message", maximum=1000),
                    _text(technical_message, field_name="technical_message", maximum=8192, optional=True),
                    plan_json,
                    ids["analysis_run_id"],
                    ids["model_run_id"],
                    ids["scoring_run_id"],
                    ids["training_job_id"],
                    ids["scoring_job_id"],
                    _text(updated_at, field_name="updated_at", maximum=64),
                    normalized_id,
                    progress_percent,
                ),
            )
            if cursor.rowcount != 1:
                raise Phase10RepositoryStateError("Orchestration stage update was rejected.")

    def mark_orchestration_ready(
        self,
        orchestration_id: int,
        *,
        generation_id: int,
        analysis_run_id: int,
        model_run_id: int,
        scoring_run_id: int,
        business_message: str,
        completed_at: str,
    ) -> None:
        normalized_id = _positive_int(orchestration_id, field_name="orchestration_id")
        identifiers = tuple(
            _positive_int(value, field_name=field)
            for field, value in (
                ("generation_id", generation_id),
                ("analysis_run_id", analysis_run_id),
                ("model_run_id", model_run_id),
                ("scoring_run_id", scoring_run_id),
            )
        )
        timestamp = _text(completed_at, field_name="completed_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM phase10_orchestration_runs WHERE orchestration_id = ?",
                (normalized_id,),
            ).fetchone()
            if current is None or current["status"] != "RUNNING":
                raise Phase10RepositoryStateError(
                    "Only a RUNNING orchestration can become READY."
                )
            for field, expected in zip(
                ("generation_id", "analysis_run_id", "model_run_id", "scoring_run_id"),
                identifiers,
                strict=True,
            ):
                if current[field] is not None and int(current[field]) != expected:
                    raise Phase10RepositoryStateError(
                        f"{field} cannot change once recorded."
                    )
            generation = connection.execute(
                """
                SELECT analysis_run_id, model_run_id, scoring_run_id
                FROM phase10_intelligence_generations
                WHERE generation_id = ? AND generation_status = 'READY'
                """,
                (identifiers[0],),
            ).fetchone()
            if generation is None or tuple(generation) != identifiers[1:]:
                raise Phase10RepositoryStateError(
                    "READY generation analytical lineage does not match orchestration."
                )
            cursor = connection.execute(
                """
                UPDATE phase10_orchestration_runs
                SET status = 'READY', stage = 'READY', progress_percent = 100,
                    business_message = ?, technical_message = NULL,
                    generation_id = ?, analysis_run_id = ?, model_run_id = ?,
                    scoring_run_id = ?, updated_at = ?, completed_at = ?,
                    safe_error_message = NULL
                WHERE orchestration_id = ? AND status = 'RUNNING'
                """,
                (
                    _text(business_message, field_name="business_message", maximum=1000),
                    *identifiers,
                    timestamp,
                    timestamp,
                    normalized_id,
                ),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("RUNNING orchestration could not become READY.")

    def mark_orchestration_terminal(
        self,
        orchestration_id: int,
        *,
        status: str,
        business_message: str,
        completed_at: str,
        safe_error_message: str | None = None,
        technical_message: str | None = None,
    ) -> None:
        if status not in {"BLOCKED", "FAILED"}:
            raise Phase10RepositoryValidationError("Terminal status must be BLOCKED or FAILED.")
        normalized_id = _positive_int(orchestration_id, field_name="orchestration_id")
        timestamp = _text(completed_at, field_name="completed_at", maximum=64)
        error = _text(
            safe_error_message,
            field_name="safe_error_message",
            maximum=1000,
            optional=True,
        )
        if status == "FAILED" and error is None:
            raise Phase10RepositoryValidationError("FAILED orchestration requires a safe error.")
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE phase10_orchestration_runs
                SET status = ?, stage = ?, business_message = ?,
                    technical_message = ?, updated_at = ?, completed_at = ?,
                    safe_error_message = ?
                WHERE orchestration_id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (
                    status,
                    status,
                    _text(business_message, field_name="business_message", maximum=1000),
                    _text(technical_message, field_name="technical_message", maximum=8192, optional=True),
                    timestamp,
                    timestamp,
                    error,
                    normalized_id,
                ),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE phase10_context_bindings
                    SET binding_status = ?, generation_id = NULL,
                        updated_at = ?, last_used_at = ?
                    WHERE orchestration_id = ?
                    """,
                    (status, timestamp, timestamp, normalized_id),
                )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("Active orchestration could not terminate.")

    def upsert_context_binding(
        self,
        *,
        targeting_context_id: int,
        modeling_context_sha256: str,
        orchestration_id: int,
        binding_status: str,
        timestamp: str,
        generation_id: int | None = None,
    ) -> None:
        context_id = _positive_int(targeting_context_id, field_name="targeting_context_id")
        orchestration = _positive_int(orchestration_id, field_name="orchestration_id")
        generation = _optional_positive_int(generation_id, field_name="generation_id")
        if binding_status not in BINDING_STATUSES:
            raise Phase10RepositoryValidationError("binding_status is invalid.")
        if binding_status == "READY" and generation is None:
            raise Phase10RepositoryValidationError("READY binding requires generation_id.")
        context_sha = _sha256(modeling_context_sha256, field_name="modeling_context_sha256")
        normalized_timestamp = _text(timestamp, field_name="timestamp", maximum=64)
        try:
            with get_connection(self.database_path, write=True) as connection:
                connection.execute("BEGIN IMMEDIATE")
                orchestration_row = connection.execute(
                    """
                    SELECT status, modeling_context_sha256, generation_id
                    FROM phase10_orchestration_runs
                    WHERE orchestration_id = ?
                    """,
                    (orchestration,),
                ).fetchone()
                if orchestration_row is None:
                    raise Phase10RepositoryStateError(
                        "Context binding orchestration was not found."
                    )
                if orchestration_row["modeling_context_sha256"] != context_sha:
                    raise Phase10RepositoryStateError(
                        "Context binding does not match orchestration Modeling Context."
                    )
                if binding_status == "READY":
                    generation_row = connection.execute(
                        """
                        SELECT modeling_context_sha256
                        FROM phase10_intelligence_generations
                        WHERE generation_id = ? AND generation_status = 'READY'
                        """,
                        (generation,),
                    ).fetchone()
                    if (
                        orchestration_row["status"] != "READY"
                        or orchestration_row["generation_id"] != generation
                        or generation_row is None
                        or generation_row["modeling_context_sha256"] != context_sha
                    ):
                        raise Phase10RepositoryStateError(
                            "READY binding requires matching READY orchestration and generation."
                        )
                connection.execute(
                    """
                    INSERT INTO phase10_context_bindings (
                        targeting_context_id, modeling_context_sha256,
                        orchestration_id, generation_id, binding_status,
                        created_at, updated_at, last_used_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(targeting_context_id) DO UPDATE SET
                        modeling_context_sha256 = excluded.modeling_context_sha256,
                        orchestration_id = excluded.orchestration_id,
                        generation_id = excluded.generation_id,
                        binding_status = excluded.binding_status,
                        updated_at = excluded.updated_at,
                        last_used_at = excluded.last_used_at
                    """,
                    (
                        context_id,
                        context_sha,
                        orchestration,
                        generation,
                        binding_status,
                        normalized_timestamp,
                        normalized_timestamp,
                        normalized_timestamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise Phase10RepositoryStateError("Context binding could not be persisted.") from exc

    def finalize_ready_context(
        self,
        *,
        targeting_context_id: int,
        modeling_context_sha256: str,
        orchestration_id: int,
        generation_id: int,
        analysis_run_id: int,
        model_run_id: int,
        scoring_run_id: int,
        business_message: str,
        timestamp: str,
    ) -> None:
        """Atomically finalize orchestration, Phase 10 binding, and Phase 9 source."""

        context_id = _positive_int(targeting_context_id, field_name="targeting_context_id")
        orchestration = _positive_int(orchestration_id, field_name="orchestration_id")
        generation = _positive_int(generation_id, field_name="generation_id")
        analysis = _positive_int(analysis_run_id, field_name="analysis_run_id")
        model = _positive_int(model_run_id, field_name="model_run_id")
        scoring = _positive_int(scoring_run_id, field_name="scoring_run_id")
        context_sha = _sha256(
            modeling_context_sha256,
            field_name="modeling_context_sha256",
        )
        message = _text(business_message, field_name="business_message", maximum=1000)
        normalized_timestamp = _text(timestamp, field_name="timestamp", maximum=64)

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            orchestration_row = connection.execute(
                "SELECT * FROM phase10_orchestration_runs WHERE orchestration_id = ?",
                (orchestration,),
            ).fetchone()
            if orchestration_row is None or orchestration_row["status"] not in {
                "RUNNING",
                "READY",
            }:
                raise Phase10RepositoryStateError(
                    "Only a matching RUNNING or READY orchestration can finalize."
                )
            generation_row = connection.execute(
                """
                SELECT intelligence_key_sha256, modeling_context_sha256,
                       analysis_run_id, model_run_id, scoring_run_id
                FROM phase10_intelligence_generations
                WHERE generation_id = ? AND generation_status = 'READY'
                """,
                (generation,),
            ).fetchone()
            if generation_row is None or (
                generation_row["modeling_context_sha256"] != context_sha
                or generation_row["analysis_run_id"] != analysis
                or generation_row["model_run_id"] != model
                or generation_row["scoring_run_id"] != scoring
            ):
                raise Phase10RepositoryStateError(
                    "READY generation does not match the requested context lineage."
                )
            if orchestration_row["modeling_context_sha256"] != context_sha:
                raise Phase10RepositoryStateError(
                    "Orchestration does not match the requested Modeling Context."
                )
            if (
                orchestration_row["intelligence_key_sha256"]
                != generation_row["intelligence_key_sha256"]
            ):
                raise Phase10RepositoryStateError(
                    "Orchestration does not match the READY intelligence identity."
                )
            recorded = {
                "generation_id": generation,
                "analysis_run_id": analysis,
                "model_run_id": model,
                "scoring_run_id": scoring,
            }
            for field, expected in recorded.items():
                value = orchestration_row[field]
                if value is not None and int(value) != expected:
                    raise Phase10RepositoryStateError(
                        f"Orchestration {field} does not match READY lineage."
                    )
            if orchestration_row["status"] == "RUNNING":
                cursor = connection.execute(
                    """
                    UPDATE phase10_orchestration_runs
                    SET status = 'READY', stage = 'READY', progress_percent = 100,
                        business_message = ?, technical_message = NULL,
                        generation_id = ?, analysis_run_id = ?, model_run_id = ?,
                        scoring_run_id = ?, updated_at = ?, completed_at = ?,
                        safe_error_message = NULL
                    WHERE orchestration_id = ? AND status = 'RUNNING'
                    """,
                    (
                        message,
                        generation,
                        analysis,
                        model,
                        scoring,
                        normalized_timestamp,
                        normalized_timestamp,
                        orchestration,
                    ),
                )
                if cursor.rowcount != 1:
                    raise Phase10RepositoryStateError(
                        "RUNNING orchestration could not become READY."
                    )
            elif (
                orchestration_row["progress_percent"] != 100
                or orchestration_row["generation_id"] != generation
                or orchestration_row["analysis_run_id"] != analysis
                or orchestration_row["model_run_id"] != model
                or orchestration_row["scoring_run_id"] != scoring
            ):
                raise Phase10RepositoryStateError(
                    "Existing READY orchestration does not match READY lineage."
                )

            context_exists = connection.execute(
                """
                SELECT 1 FROM campaign_targeting_contexts
                WHERE targeting_context_id = ?
                """,
                (context_id,),
            ).fetchone()
            if context_exists is None:
                raise Phase10RepositoryStateError(
                    "Campaign targeting context was not found."
                )
            connection.execute(
                """
                INSERT INTO phase10_context_bindings (
                    targeting_context_id, modeling_context_sha256,
                    orchestration_id, generation_id, binding_status,
                    created_at, updated_at, last_used_at
                ) VALUES (?, ?, ?, ?, 'READY', ?, ?, ?)
                ON CONFLICT(targeting_context_id) DO UPDATE SET
                    modeling_context_sha256 = excluded.modeling_context_sha256,
                    orchestration_id = excluded.orchestration_id,
                    generation_id = excluded.generation_id,
                    binding_status = 'READY',
                    updated_at = excluded.updated_at,
                    last_used_at = excluded.last_used_at
                """,
                (
                    context_id,
                    context_sha,
                    orchestration,
                    generation,
                    normalized_timestamp,
                    normalized_timestamp,
                    normalized_timestamp,
                ),
            )
            connection.execute(
                """
                UPDATE phase10_context_bindings
                SET generation_id = ?, binding_status = 'READY',
                    updated_at = ?, last_used_at = ?
                WHERE orchestration_id = ?
                  AND modeling_context_sha256 = ?
                """,
                (
                    generation,
                    normalized_timestamp,
                    normalized_timestamp,
                    orchestration,
                    context_sha,
                ),
            )
            cursor = connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET source_scoring_run_id = ?, updated_at = ?
                WHERE targeting_context_id IN (
                    SELECT targeting_context_id
                    FROM phase10_context_bindings
                    WHERE orchestration_id = ?
                      AND modeling_context_sha256 = ?
                      AND binding_status = 'READY'
                      AND generation_id = ?
                )
                """,
                (
                    scoring,
                    normalized_timestamp,
                    orchestration,
                    context_sha,
                    generation,
                ),
            )
            if cursor.rowcount < 1:
                raise Phase10RepositoryStateError(
                    "Campaign targeting context source could not be linked."
                )

    def fetch_context_binding(self, targeting_context_id: int) -> dict[str, Any] | None:
        context_id = _positive_int(targeting_context_id, field_name="targeting_context_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM phase10_context_bindings WHERE targeting_context_id = ?",
                (context_id,),
            ).fetchone()
        return _row_dict(row)

    def touch_context_binding(self, targeting_context_id: int, *, used_at: str) -> None:
        context_id = _positive_int(targeting_context_id, field_name="targeting_context_id")
        timestamp = _text(used_at, field_name="used_at", maximum=64)
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE phase10_context_bindings
                SET last_used_at = ?, updated_at = ?
                WHERE targeting_context_id = ?
                """,
                (timestamp, timestamp, context_id),
            )
        if cursor.rowcount != 1:
            raise Phase10RepositoryStateError("Context binding was not found.")

    def fetch_generation_reference_counts(self, generation_id: int) -> dict[str, int]:
        """Return no-PII direct/indirect reference counts for lifecycle decisions."""

        normalized_id = _positive_int(generation_id, field_name="generation_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM phase10_context_bindings b
                     WHERE b.generation_id = g.generation_id) AS context_binding_count,
                    (SELECT COUNT(*) FROM phase10_context_bindings b
                     WHERE b.generation_id = g.generation_id
                       AND b.binding_status = 'READY') AS ready_context_binding_count,
                    (SELECT COUNT(*) FROM phase10_orchestration_runs o
                     WHERE o.status IN ('QUEUED', 'RUNNING')
                       AND (o.generation_id = g.generation_id
                            OR o.scoring_run_id = g.scoring_run_id
                            OR o.intelligence_key_sha256 = g.intelligence_key_sha256
                            OR o.modeling_context_sha256 = g.modeling_context_sha256)
                    ) AS orchestration_count,
                    (SELECT COUNT(*) FROM saved_audiences a
                     WHERE a.scoring_run_id = g.scoring_run_id) AS saved_audience_count,
                    (SELECT COUNT(*) FROM phase9_saved_target_groups p
                     JOIN saved_audiences a ON a.audience_id = p.audience_id
                     WHERE a.scoring_run_id = g.scoring_run_id) AS saved_target_group_count,
                    (SELECT COUNT(*) FROM campaigns c
                     JOIN saved_audiences a ON a.audience_id = c.saved_audience_id
                     WHERE a.scoring_run_id = g.scoring_run_id) AS campaign_count,
                    (SELECT COUNT(*) FROM campaigns c
                     JOIN saved_audiences a ON a.audience_id = c.saved_audience_id
                     WHERE a.scoring_run_id = g.scoring_run_id
                       AND c.status = 'FINALIZED') AS finalized_campaign_count,
                    (SELECT COUNT(*) FROM campaign_export_events e
                     JOIN campaigns c ON c.campaign_id = e.campaign_id
                     JOIN saved_audiences a ON a.audience_id = c.saved_audience_id
                     WHERE a.scoring_run_id = g.scoring_run_id) AS export_event_count
                FROM phase10_intelligence_generations g
                WHERE g.generation_id = ?
                """,
                (normalized_id,),
            ).fetchone()
        if row is None:
            raise Phase10RepositoryStateError("READY generation was not found.")
        return {field: int(value) for field, value in dict(row).items()}

    def fetch_generation_context_ids(self, generation_id: int) -> list[int]:
        """Return non-PII READY Campaign Context references for one generation."""

        normalized_id = _positive_int(generation_id, field_name="generation_id")
        with get_connection(self.database_path) as connection:
            exists = connection.execute(
                "SELECT 1 FROM phase10_intelligence_generations WHERE generation_id = ?",
                (normalized_id,),
            ).fetchone()
            if exists is None:
                raise Phase10RepositoryStateError("READY generation was not found.")
            rows = connection.execute(
                """
                SELECT targeting_context_id
                FROM phase10_context_bindings
                WHERE generation_id = ? AND binding_status = 'READY'
                ORDER BY targeting_context_id
                """,
                (normalized_id,),
            ).fetchall()
        return [int(row["targeting_context_id"]) for row in rows]

    def count_generation_score_rows(self, generation_id: int) -> int:
        normalized_id = _positive_int(generation_id, field_name="generation_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS row_count
                FROM propensity_scores AS score
                JOIN phase10_intelligence_generations AS generation
                  ON generation.scoring_run_id = score.scoring_run_id
                WHERE generation.generation_id = ?
                """,
                (normalized_id,),
            ).fetchone()
        return int(row["row_count"])

    def count_registered_score_footprint(self) -> int:
        """Count physical score rows once across distinct registered scoring runs."""

        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS row_count
                FROM propensity_scores AS score
                WHERE EXISTS (
                    SELECT 1 FROM phase10_intelligence_generations AS generation
                    WHERE generation.scoring_run_id = score.scoring_run_id
                )
                """
            ).fetchone()
        return int(row["row_count"])


__all__ = (
    "ACTIVE_ORCHESTRATION_STATUSES",
    "BINDING_STATUSES",
    "LIFECYCLE_STATES",
    "ORCHESTRATION_STATUSES",
    "Phase10IntelligenceRepository",
    "Phase10RepositoryError",
    "Phase10RepositoryStateError",
    "Phase10RepositoryValidationError",
)
