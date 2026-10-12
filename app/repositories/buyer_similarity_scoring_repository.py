"""Fenced staging and atomic publication for v3 similarity scores."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.database.connection import get_connection
from app.repositories.prospect_scoring_repository import DemographicImportProvenance
from app.services.buyer_similarity_profile_service import (
    MINIMUM_FEATURE_COVERAGE,
    SCORE_METHOD_VERSION,
)


SCORER_CONTRACT_VERSION = "1"
ATTESTATION_VERIFICATION_CONTRACT_VERSION = "1"
ATTESTATION_INTEGRITY_CONTRACT_VERSION = "1"
MAXIMUM_SAFE_MESSAGE_LENGTH = 500
_TOKEN = re.compile(r"[0-9a-f]{64}")


class BuyerSimilarityScoringRepositoryError(RuntimeError):
    """Base class for bounded similarity generation failures."""


class BuyerSimilarityGenerationBusy(BuyerSimilarityScoringRepositoryError):
    """Raised when an exact current generation already has a builder."""


class BuyerSimilarityGenerationFenceLost(BuyerSimilarityScoringRepositoryError):
    """Raised when an old owner/token attempts a generation mutation."""


class BuyerSimilarityGenerationSourceStale(BuyerSimilarityScoringRepositoryError):
    """Raised when a source changes during generation work."""


class BuyerSimilarityGenerationVerificationError(BuyerSimilarityScoringRepositoryError):
    """Raised after failed deep verification publishes no scores."""


@dataclass(frozen=True)
class SimilarityGenerationClaim:
    similarity_generation_id: int
    reused_published: bool
    restarted_from_stale_lease: bool
    resumed_checkpoint_person_id: str | None
    processed_count: int
    expected_person_count: int
    product_id: str
    profile_set_sha256: str
    composite_context_sha256: str


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _owner_token(owner: str, token: str) -> tuple[str, str]:
    normalized_owner = str(owner).strip()
    normalized_token = str(token).strip().lower()
    if not normalized_owner or len(normalized_owner) > 128:
        raise BuyerSimilarityScoringRepositoryError("The generation owner is invalid.")
    if _TOKEN.fullmatch(normalized_token) is None:
        raise BuyerSimilarityScoringRepositoryError("The generation token is invalid.")
    return normalized_owner, normalized_token


def _safe_message(value: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        normalized = "Similarity generation state updated."
    return normalized[:MAXIMUM_SAFE_MESSAGE_LENGTH]


def _latest_import(connection: sqlite3.Connection, dataset: str) -> sqlite3.Row:
    row = connection.execute(
        """SELECT import_id,source_checksum,rows_inserted,completed_at
           FROM data_import_runs
           WHERE dataset_name=? AND status='COMPLETED'
           ORDER BY import_id DESC LIMIT 1""",
        (dataset,),
    ).fetchone()
    if row is None or not isinstance(row["source_checksum"], str):
        raise BuyerSimilarityGenerationSourceStale(
            f"Current {dataset} source provenance is unavailable."
        )
    return row


def _assert_profile_sources_current(
    connection: sqlite3.Connection, profile: Mapping[str, Any]
) -> None:
    for dataset, id_field, checksum_field in (
        ("customers", "customer_import_id", "customer_source_checksum"),
        ("campaign_sales", "campaign_sales_import_id", "campaign_sales_source_checksum"),
    ):
        current = _latest_import(connection, dataset)
        if (
            int(current["import_id"]) != int(profile[id_field])
            or str(current["source_checksum"]).strip().lower()
            != str(profile[checksum_field]).strip().lower()
        ):
            raise BuyerSimilarityGenerationSourceStale(
                f"The published profile no longer matches current {dataset}."
            )


def _assert_demographic_current(
    connection: sqlite3.Connection,
    *,
    import_id: int,
    checksum: str,
    expected_count: int,
    deep_count: bool,
) -> None:
    current = _latest_import(connection, "demographics")
    if (
        int(current["import_id"]) != int(import_id)
        or str(current["source_checksum"]).strip().lower() != checksum
        or int(current["rows_inserted"]) != int(expected_count)
    ):
        raise BuyerSimilarityGenerationSourceStale(
            "The demographic source changed during similarity scoring."
        )
    if deep_count:
        live_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])
        if live_count != int(expected_count):
            raise BuyerSimilarityGenerationSourceStale(
                "The live demographic population no longer matches its import."
            )


def _profile_row(connection: sqlite3.Connection, profile_id: int) -> sqlite3.Row:
    row = connection.execute(
        """SELECT p.*,a.storage_uri,a.artifact_sha256,a.profile_payload_sha256,
                  a.serialization_contract_version,a.artifact_state
           FROM buyer_similarity_profiles p
           JOIN buyer_similarity_profile_artifacts a
             ON a.profile_id=p.profile_id AND a.artifact_state='PUBLISHED'
           WHERE p.profile_id=? AND p.publication_state='PUBLISHED'""",
        (int(profile_id),),
    ).fetchone()
    if row is None:
        raise BuyerSimilarityScoringRepositoryError(
            "A published buyer profile and artifact are required."
        )
    _assert_profile_sources_current(connection, row)
    return row


def _generation_identity(
    profile: Mapping[str, Any], demographic: DemographicImportProvenance
) -> tuple[str, str]:
    profile_set_sha256 = _digest([str(profile["immutable_identity_sha256"])])
    composite_context_sha256 = _digest(
        {
            "profile_identity_sha256": profile["immutable_identity_sha256"],
            "profile_artifact_sha256": profile["artifact_sha256"],
            "demographic_import_id": demographic.demographic_import_id,
            "demographic_source_checksum": demographic.demographic_source_checksum,
            "score_method_version": SCORE_METHOD_VERSION,
            "scorer_contract_version": SCORER_CONTRACT_VERSION,
        }
    )
    return profile_set_sha256, composite_context_sha256


def _insert_stages(
    connection: sqlite3.Connection,
    generation_id: int,
    token: str,
    *,
    now: str,
    expected_count: int,
) -> None:
    connection.executemany(
        """INSERT INTO buyer_similarity_generation_stages (
            similarity_generation_id,stage_sequence,stage_code,status,
            processed_count,total_count,checkpoint_person_id,execution_token,
            started_at,heartbeat_at,completed_at,safe_message
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            (
                generation_id, 1, "QUEUE_WAIT", "COMPLETED", 0, 0, None,
                token, now, now, now, "Queue wait recorded separately from scoring work.",
            ),
            (
                generation_id, 2, "SCORING_PROSPECTS", "RUNNING", 0,
                expected_count, None, token, now, now, None,
                "Scoring the immutable demographic snapshot in bounded chunks.",
            ),
            (
                generation_id, 3, "DEEP_VERIFY", "QUEUED", 0,
                expected_count, None, token, None, None, None,
                "Waiting to verify complete population integrity.",
            ),
            (
                generation_id, 4, "PUBLISH", "QUEUED", 0,
                expected_count, None, token, None, None, None,
                "Waiting for verified transactional publication.",
            ),
        ),
    )


class BuyerSimilarityScoringRepository:
    """Own resumable generation staging and verified publication."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_profile_for_scoring(self, profile_id: int) -> dict[str, Any]:
        with get_connection(self.database_path) as connection:
            return dict(_profile_row(connection, profile_id))

    def claim_generation(
        self,
        profile_id: int,
        demographic: DemographicImportProvenance,
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
        stale_before: str | None = None,
    ) -> SimilarityGenerationClaim:
        owner, token = _owner_token(execution_owner, execution_token)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            profile = _profile_row(connection, profile_id)
            _assert_demographic_current(
                connection,
                import_id=demographic.demographic_import_id,
                checksum=demographic.demographic_source_checksum,
                expected_count=demographic.demographic_snapshot_count,
                deep_count=True,
            )
            profile_set, context = _generation_identity(profile, demographic)
            row = connection.execute(
                """SELECT * FROM buyer_similarity_score_generations
                   WHERE profile_id=? AND demographic_import_id=?
                     AND composite_context_sha256=?""",
                (int(profile_id), demographic.demographic_import_id, context),
            ).fetchone()
            if row is not None and row["publication_state"] == "PUBLISHED":
                return SimilarityGenerationClaim(
                    int(row["similarity_generation_id"]), True, False, None,
                    int(row["published_person_count"]), int(row["expected_person_count"]),
                    str(row["product_id"]), str(row["profile_set_sha256"]),
                    str(row["composite_context_sha256"]),
                )
            if row is not None and row["publication_state"] == "BUILDING":
                generation_id = int(row["similarity_generation_id"])
                if row["execution_owner"] == owner and row["execution_token"] == token:
                    progress = connection.execute(
                        """SELECT processed_count,checkpoint_person_id
                           FROM buyer_similarity_generation_stages
                           WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'""",
                        (generation_id,),
                    ).fetchone()
                    return SimilarityGenerationClaim(
                        generation_id, False, False,
                        None if progress is None else progress["checkpoint_person_id"],
                        0 if progress is None else int(progress["processed_count"]),
                        int(row["expected_person_count"]), str(row["product_id"]),
                        str(row["profile_set_sha256"]), str(row["composite_context_sha256"]),
                    )
                heartbeat = str(row["lease_heartbeat_at"] or "")
                if stale_before is None or not heartbeat or heartbeat >= stale_before:
                    raise BuyerSimilarityGenerationBusy(
                        "The exact similarity generation already has an active builder."
                    )
                # A recovered worker restarts scoring.  This is deterministic and
                # cheaper/safer than token-rewriting millions of fenced stage rows.
                connection.execute(
                    "DELETE FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
                    (generation_id,),
                )
                connection.execute(
                    "DELETE FROM buyer_similarity_generation_stages WHERE similarity_generation_id=?",
                    (generation_id,),
                )
                changed = connection.execute(
                    """UPDATE buyer_similarity_score_generations
                       SET execution_owner=?,execution_token=?,lease_heartbeat_at=?,
                           safe_error_code=NULL,published_person_count=NULL
                       WHERE similarity_generation_id=? AND publication_state='BUILDING'
                         AND execution_token=?""",
                    (owner, token, now, generation_id, row["execution_token"]),
                ).rowcount
                if changed != 1:
                    raise BuyerSimilarityGenerationFenceLost(
                        "The stale generation lease changed during recovery."
                    )
                _insert_stages(
                    connection, generation_id, token, now=now,
                    expected_count=demographic.demographic_snapshot_count,
                )
                return SimilarityGenerationClaim(
                    generation_id, False, True, None, 0,
                    demographic.demographic_snapshot_count, str(profile["product_id"]),
                    profile_set, context,
                )
            if row is not None:
                generation_id = int(row["similarity_generation_id"])
                connection.execute(
                    "DELETE FROM buyer_similarity_generation_stages WHERE similarity_generation_id=?",
                    (generation_id,),
                )
                changed = connection.execute(
                    """UPDATE buyer_similarity_score_generations
                       SET publication_state='BUILDING',published_person_count=NULL,
                           execution_owner=?,execution_token=?,lease_heartbeat_at=?,
                           published_at=NULL,safe_error_code=NULL
                       WHERE similarity_generation_id=? AND publication_state IN ('FAILED','STALE')""",
                    (owner, token, now, generation_id),
                ).rowcount
                if changed != 1:
                    raise BuyerSimilarityGenerationFenceLost(
                        "The generation could not be reclaimed."
                    )
                _insert_stages(
                    connection, generation_id, token, now=now,
                    expected_count=demographic.demographic_snapshot_count,
                )
                return SimilarityGenerationClaim(
                    generation_id, False, True, None, 0,
                    demographic.demographic_snapshot_count, str(profile["product_id"]),
                    profile_set, context,
                )

            generation_id = int(connection.execute(
                """INSERT INTO buyer_similarity_score_generations (
                    profile_id,product_id,composite_context_sha256,profile_set_sha256,
                    demographic_import_id,demographic_source_checksum,reference_date,
                    scorer_contract_version,score_method_version,publication_state,
                    expected_person_count,execution_owner,execution_token,
                    lease_heartbeat_at,created_at
                ) VALUES (?,?,?,?,?,?,?,'1',?,'BUILDING',?,?,?,?,?)""",
                (
                    int(profile_id), str(profile["product_id"]), context, profile_set,
                    demographic.demographic_import_id,
                    demographic.demographic_source_checksum,
                    str(_latest_import(connection, "demographics")["completed_at"])[:10],
                    SCORE_METHOD_VERSION, demographic.demographic_snapshot_count,
                    owner, token, now, now,
                ),
            ).lastrowid)
            _insert_stages(
                connection, generation_id, token, now=now,
                expected_count=demographic.demographic_snapshot_count,
            )
            return SimilarityGenerationClaim(
                generation_id, False, False, None, 0,
                demographic.demographic_snapshot_count, str(profile["product_id"]),
                profile_set, context,
            )

    def persist_score_chunk(
        self,
        generation_id: int,
        rows: Sequence[Mapping[str, Any]],
        *,
        expected_checkpoint_person_id: str | None,
        execution_owner: str,
        execution_token: str,
        now: str,
    ) -> int:
        if not rows:
            return 0
        owner, token = _owner_token(execution_owner, execution_token)
        normalized: list[tuple[Any, ...]] = []
        last_person = expected_checkpoint_person_id
        seen: set[str] = set()
        for value in rows:
            person_id = str(value.get("person_id") or "").strip()
            if not person_id or person_id in seen or (last_person is not None and person_id <= last_person):
                raise BuyerSimilarityScoringRepositoryError(
                    "A score chunk must contain unique ascending person IDs after its checkpoint."
                )
            seen.add(person_id)
            last_person = person_id
            is_valid = bool(value.get("is_valid"))
            score = value.get("buyer_similarity_score")
            coverage = float(value.get("feature_coverage"))
            prototype_key = value.get("prototype_key")
            reason = value.get("invalid_reason_code")
            if not math.isfinite(coverage) or not 0 <= coverage <= 1:
                raise BuyerSimilarityScoringRepositoryError("Feature coverage is invalid.")
            if is_valid:
                if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not math.isfinite(float(score))
                    or not 0 <= float(score) <= 1
                    or not isinstance(prototype_key, str)
                    or not prototype_key
                    or len(prototype_key) > 80
                    or coverage + 1e-12 < MINIMUM_FEATURE_COVERAGE
                    or reason is not None
                ):
                    raise BuyerSimilarityScoringRepositoryError("A valid score row is inconsistent.")
            elif (
                score is not None
                or prototype_key is not None
                or not isinstance(reason, str)
                or not reason
                or len(reason) > 80
            ):
                raise BuyerSimilarityScoringRepositoryError("An invalid score row is inconsistent.")
            normalized.append(
                (
                    int(generation_id), person_id, int(is_valid),
                    None if score is None else float(score), coverage,
                    prototype_key, reason, token,
                )
            )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            generation = connection.execute(
                "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
                (int(generation_id),),
            ).fetchone()
            if (
                generation is None
                or generation["publication_state"] != "BUILDING"
                or generation["execution_owner"] != owner
                or generation["execution_token"] != token
            ):
                raise BuyerSimilarityGenerationFenceLost("The generation lease was lost.")
            _assert_demographic_current(
                connection,
                import_id=int(generation["demographic_import_id"]),
                checksum=str(generation["demographic_source_checksum"]),
                expected_count=int(generation["expected_person_count"]),
                deep_count=False,
            )
            progress = connection.execute(
                """SELECT processed_count,checkpoint_person_id,total_count
                   FROM buyer_similarity_generation_stages
                   WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'
                     AND status='RUNNING' AND execution_token=?""",
                (int(generation_id), token),
            ).fetchone()
            if progress is None or progress["checkpoint_person_id"] != expected_checkpoint_person_id:
                raise BuyerSimilarityGenerationFenceLost(
                    "The scoring checkpoint changed before chunk publication."
                )
            new_count = int(progress["processed_count"]) + len(normalized)
            if new_count > int(progress["total_count"]):
                raise BuyerSimilarityScoringRepositoryError(
                    "A score chunk exceeds the immutable population count."
                )
            try:
                connection.executemany(
                    """INSERT INTO buyer_similarity_score_stage (
                        similarity_generation_id,person_id,is_valid,buyer_similarity_score,
                        feature_coverage,prototype_key,invalid_reason_code,execution_token
                    ) VALUES (?,?,?,?,?,?,?,?)""",
                    normalized,
                )
            except sqlite3.IntegrityError as exc:
                raise BuyerSimilarityScoringRepositoryError(
                    "The score chunk violates uniqueness, state, or fencing constraints."
                ) from exc
            changed = connection.execute(
                """UPDATE buyer_similarity_generation_stages
                   SET processed_count=?,checkpoint_person_id=?,heartbeat_at=?,
                       safe_message=?
                   WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'
                     AND execution_token=? AND checkpoint_person_id IS ?""",
                (
                    new_count, normalized[-1][1], now,
                    _safe_message(f"Scored {new_count} of {progress['total_count']} people."),
                    int(generation_id), token, expected_checkpoint_person_id,
                ),
            ).rowcount
            if changed != 1:
                raise BuyerSimilarityGenerationFenceLost(
                    "The scoring checkpoint changed during chunk publication."
                )
            connection.execute(
                """UPDATE buyer_similarity_score_generations SET lease_heartbeat_at=?
                   WHERE similarity_generation_id=? AND execution_token=?""",
                (now, int(generation_id), token),
            )
        return len(normalized)

    def cancel(
        self,
        generation_id: int,
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
    ) -> None:
        self._terminate(
            generation_id,
            execution_owner=execution_owner,
            execution_token=execution_token,
            now=now,
            state="FAILED",
            error_code="CANCELLED",
            stage_status="CANCELLED",
        )

    def mark_source_stale(
        self,
        generation_id: int,
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
    ) -> None:
        self._terminate(
            generation_id,
            execution_owner=execution_owner,
            execution_token=execution_token,
            now=now,
            state="STALE",
            error_code="SOURCE_REPLACED",
            stage_status="FAILED",
        )

    def _terminate(
        self,
        generation_id: int,
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
        state: str,
        error_code: str,
        stage_status: str,
    ) -> None:
        owner, token = _owner_token(execution_owner, execution_token)
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
                (int(generation_id),),
            ).fetchone()
            if (
                row is None
                or row["publication_state"] != "BUILDING"
                or row["execution_owner"] != owner
                or row["execution_token"] != token
            ):
                raise BuyerSimilarityGenerationFenceLost("The generation lease was lost.")
            connection.execute(
                "DELETE FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
                (int(generation_id),),
            )
            connection.execute(
                """UPDATE buyer_similarity_generation_stages
                   SET status=CASE WHEN status IN ('RUNNING','QUEUED') THEN ? ELSE status END,
                       completed_at=CASE WHEN status IN ('RUNNING','QUEUED') THEN ? ELSE completed_at END,
                       heartbeat_at=?,safe_message=?
                   WHERE similarity_generation_id=? AND execution_token=?""",
                (
                    stage_status, now, now,
                    _safe_message("Generation stopped without publishing partial scores."),
                    int(generation_id), token,
                ),
            )
            changed = connection.execute(
                """UPDATE buyer_similarity_score_generations
                   SET publication_state=?,execution_owner=NULL,execution_token=NULL,
                       lease_heartbeat_at=NULL,safe_error_code=?
                   WHERE similarity_generation_id=? AND publication_state='BUILDING'
                     AND execution_owner=? AND execution_token=?""",
                (state, error_code, int(generation_id), owner, token),
            ).rowcount
            if changed != 1:
                raise BuyerSimilarityGenerationFenceLost("The generation lease was lost.")

    def verify_and_publish(
        self,
        generation_id: int,
        *,
        allowed_prototype_keys: Sequence[str],
        profile_artifact_sha256: str,
        execution_owner: str,
        execution_token: str,
        now: str,
        timing_sink: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        owner, token = _owner_token(execution_owner, execution_token)
        failures: list[str] = []
        verification_started = time.perf_counter()
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            generation = connection.execute(
                """SELECT g.*,p.immutable_identity_sha256,p.customer_import_id,
                          p.customer_source_checksum,p.campaign_sales_import_id,
                          p.campaign_sales_source_checksum,p.publication_state profile_state,
                          a.artifact_sha256 profile_artifact_sha256
                   FROM buyer_similarity_score_generations g
                   JOIN buyer_similarity_profiles p ON p.profile_id=g.profile_id
                   JOIN buyer_similarity_profile_artifacts a
                     ON a.profile_id=p.profile_id AND a.artifact_state='PUBLISHED'
                   WHERE g.similarity_generation_id=?""",
                (int(generation_id),),
            ).fetchone()
            if (
                generation is None
                or generation["publication_state"] != "BUILDING"
                or generation["execution_owner"] != owner
                or generation["execution_token"] != token
            ):
                raise BuyerSimilarityGenerationFenceLost("The generation lease was lost.")
            try:
                _assert_profile_sources_current(connection, generation)
                _assert_demographic_current(
                    connection,
                    import_id=int(generation["demographic_import_id"]),
                    checksum=str(generation["demographic_source_checksum"]),
                    expected_count=int(generation["expected_person_count"]),
                    deep_count=True,
                )
            except BuyerSimilarityGenerationSourceStale:
                failures.append("SOURCE_REPLACED")
            if generation["profile_state"] != "PUBLISHED":
                failures.append("PROFILE_NOT_PUBLISHED")
            if generation["profile_artifact_sha256"] != profile_artifact_sha256:
                failures.append("PROFILE_ARTIFACT_IDENTITY_MISMATCH")

            aggregate = connection.execute(
                """SELECT COUNT(*) row_count,COUNT(DISTINCT person_id) distinct_count,
                          SUM(CASE WHEN is_valid=1 THEN 1 ELSE 0 END) valid_count,
                          SUM(CASE WHEN is_valid=0 THEN 1 ELSE 0 END) invalid_count,
                          SUM(CASE WHEN is_valid=1 AND (
                                buyer_similarity_score IS NULL
                                OR buyer_similarity_score!=buyer_similarity_score
                                OR buyer_similarity_score<0 OR buyer_similarity_score>1
                                OR feature_coverage IS NULL
                                OR feature_coverage!=feature_coverage
                                OR feature_coverage<0.80 OR feature_coverage>1
                                OR prototype_key IS NULL OR invalid_reason_code IS NOT NULL)
                              THEN 1
                              WHEN is_valid=0 AND (
                                buyer_similarity_score IS NOT NULL
                                OR feature_coverage IS NULL
                                OR feature_coverage!=feature_coverage
                                OR feature_coverage<0 OR feature_coverage>1
                                OR prototype_key IS NOT NULL OR invalid_reason_code IS NULL)
                              THEN 1 ELSE 0 END) inconsistent_count
                   FROM buyer_similarity_score_stage
                   WHERE similarity_generation_id=?""",
                (int(generation_id),),
            ).fetchone()
            missing = int(connection.execute(
                """SELECT COUNT(*) FROM demographics d WHERE NOT EXISTS (
                    SELECT 1 FROM buyer_similarity_score_stage s
                    WHERE s.similarity_generation_id=? AND s.person_id=d.person_id)""",
                (int(generation_id),),
            ).fetchone()[0])
            extra = int(connection.execute(
                """SELECT COUNT(*) FROM buyer_similarity_score_stage s
                   WHERE s.similarity_generation_id=? AND NOT EXISTS (
                       SELECT 1 FROM demographics d WHERE d.person_id=s.person_id)""",
                (int(generation_id),),
            ).fetchone()[0])
            observed_keys = {
                str(row[0])
                for row in connection.execute(
                    """SELECT DISTINCT prototype_key FROM buyer_similarity_score_stage
                       WHERE similarity_generation_id=? AND is_valid=1""",
                    (int(generation_id),),
                )
            }
            expected = int(generation["expected_person_count"])
            row_count = int(aggregate["row_count"] or 0)
            distinct_count = int(aggregate["distinct_count"] or 0)
            valid_count = int(aggregate["valid_count"] or 0)
            invalid_count = int(aggregate["invalid_count"] or 0)
            if row_count != expected:
                failures.append("ROW_COUNT_MISMATCH")
            if distinct_count != expected or row_count != distinct_count:
                failures.append("PERSON_ID_UNIQUENESS_FAILED")
            if missing:
                failures.append("MISSING_PERSON_IDS")
            if extra:
                failures.append("EXTRA_PERSON_IDS")
            if valid_count + invalid_count != expected:
                failures.append("VALID_INVALID_COUNT_MISMATCH")
            if int(aggregate["inconsistent_count"] or 0):
                failures.append("SCORE_STATE_INCONSISTENT")
            if not observed_keys <= set(allowed_prototype_keys):
                failures.append("UNKNOWN_PROTOTYPE_KEY")
            progress = connection.execute(
                """SELECT processed_count,checkpoint_person_id FROM buyer_similarity_generation_stages
                   WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'
                     AND execution_token=?""",
                (int(generation_id), token),
            ).fetchone()
            if progress is None or int(progress["processed_count"]) != expected:
                failures.append("PROGRESS_COUNT_MISMATCH")

            failures = list(dict.fromkeys(failures))
            facts = {
                "similarity_generation_id": int(generation_id),
                "profile_id": int(generation["profile_id"]),
                "profile_artifact_sha256": profile_artifact_sha256,
                "product_id": str(generation["product_id"]),
                "score_method_version": str(generation["score_method_version"]),
                "scorer_contract_version": str(generation["scorer_contract_version"]),
                "demographic_import_id": int(generation["demographic_import_id"]),
                "demographic_source_checksum": str(generation["demographic_source_checksum"]),
                "expected_person_count": expected,
                "row_count": row_count,
                "distinct_person_count": distinct_count,
                "valid_score_count": valid_count,
                "invalid_score_count": invalid_count,
                "missing_person_count": missing,
                "extra_person_count": extra,
                "prototype_keys": sorted(observed_keys),
                "product_match_policy": "ANY_SELECTED_PRODUCT_MAX_V1",
                "winner_tie_policy": "SCORE_DESC_PRODUCT_ID_ASC",
                "failure_codes": failures,
            }
            facts_json = _canonical(facts)
            facts_sha = hashlib.sha256(facts_json.encode("utf-8")).hexdigest()
            attestation_key = _digest(
                {
                    "verification_contract_version": ATTESTATION_VERIFICATION_CONTRACT_VERSION,
                    "integrity_contract_version": ATTESTATION_INTEGRITY_CONTRACT_VERSION,
                    "facts_sha256": facts_sha,
                }
            )
            status = "VERIFIED" if not failures else "FAILED"
            connection.execute(
                """INSERT OR REPLACE INTO buyer_similarity_generation_attestations (
                    attestation_key_sha256,similarity_generation_id,
                    verification_contract_version,integrity_contract_version,
                    profile_artifact_sha256,demographic_import_id,
                    demographic_source_checksum,expected_person_count,verified_row_count,
                    valid_score_count,invalid_score_count,verified_facts_json,
                    verified_facts_sha256,failure_codes_json,verification_status,verified_at
                ) VALUES (?,?, '1','1',?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attestation_key, int(generation_id), profile_artifact_sha256,
                    int(generation["demographic_import_id"]),
                    str(generation["demographic_source_checksum"]), expected,
                    row_count, valid_count, invalid_count, facts_json, facts_sha,
                    _canonical(failures), status, now,
                ),
            )
            if timing_sink is not None:
                timing_sink["deep_verification_seconds"] = time.perf_counter() - verification_started
            if failures:
                connection.execute(
                    "DELETE FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
                    (int(generation_id),),
                )
                connection.execute(
                    """UPDATE buyer_similarity_generation_stages
                       SET status=CASE WHEN stage_code='DEEP_VERIFY' THEN 'FAILED'
                                       WHEN status IN ('RUNNING','QUEUED') THEN 'CANCELLED'
                                       ELSE status END,
                           completed_at=CASE WHEN status IN ('RUNNING','QUEUED') THEN ? ELSE completed_at END,
                           heartbeat_at=?,safe_message=?
                       WHERE similarity_generation_id=? AND execution_token=?""",
                    (
                        now, now, _safe_message("Deep verification failed; no scores were published."),
                        int(generation_id), token,
                    ),
                )
                connection.execute(
                    """UPDATE buyer_similarity_score_generations
                       SET publication_state=?,execution_owner=NULL,execution_token=NULL,
                           lease_heartbeat_at=NULL,safe_error_code=?
                       WHERE similarity_generation_id=? AND execution_token=?""",
                    (
                        "STALE" if "SOURCE_REPLACED" in failures else "FAILED",
                        failures[0][:80], int(generation_id), token,
                    ),
                )
            else:
                publication_started = time.perf_counter()
                connection.execute(
                    """UPDATE buyer_similarity_generation_stages
                       SET status='COMPLETED',processed_count=total_count,
                           heartbeat_at=?,completed_at=?,
                           safe_message='All demographic rows were scored.'
                       WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'
                         AND status='RUNNING' AND execution_token=?""",
                    (now, now, int(generation_id), token),
                )
                connection.execute(
                    """UPDATE buyer_similarity_generation_stages
                       SET status='COMPLETED',processed_count=total_count,
                           started_at=COALESCE(started_at,?),heartbeat_at=?,completed_at=?,
                           safe_message='Deep population verification passed.'
                       WHERE similarity_generation_id=? AND stage_code='DEEP_VERIFY'
                         AND execution_token=?""",
                    (now, now, now, int(generation_id), token),
                )
                connection.execute(
                    """INSERT INTO buyer_similarity_scores (
                        similarity_generation_id,person_id,product_id,is_valid,
                        buyer_similarity_score,similarity_tier,feature_coverage,
                        prototype_key,invalid_reason_code,score_method_version,
                        execution_token,published_at
                    )
                    SELECT similarity_generation_id,person_id,?,is_valid,
                           buyer_similarity_score,
                           CASE WHEN is_valid=0 THEN NULL
                                WHEN buyer_similarity_score>=0.90 THEN 'VERY_STRONG'
                                WHEN buyer_similarity_score>=0.80 THEN 'STRONG'
                                WHEN buyer_similarity_score>=0.70 THEN 'GOOD'
                                WHEN buyer_similarity_score>=0.60 THEN 'BROAD'
                                WHEN buyer_similarity_score>=0.50 THEN 'EXPLORATORY'
                                ELSE 'BELOW_MINIMUM' END,
                           feature_coverage,prototype_key,invalid_reason_code,?,
                           execution_token,?
                    FROM buyer_similarity_score_stage WHERE similarity_generation_id=?""",
                    (
                        str(generation["product_id"]), SCORE_METHOD_VERSION, now,
                        int(generation_id),
                    ),
                )
                if timing_sink is not None:
                    timing_sink["indexed_score_insert_seconds"] = (
                        time.perf_counter() - publication_started
                    )
                published_count = int(connection.execute(
                    "SELECT COUNT(*) FROM buyer_similarity_scores WHERE similarity_generation_id=?",
                    (int(generation_id),),
                ).fetchone()[0])
                if published_count != expected:
                    raise BuyerSimilarityGenerationVerificationError(
                        "Transactional publication count changed unexpectedly."
                    )
                connection.execute(
                    "DELETE FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
                    (int(generation_id),),
                )
                connection.execute(
                    """UPDATE buyer_similarity_generation_stages
                       SET status='COMPLETED',processed_count=total_count,
                           started_at=COALESCE(started_at,?),heartbeat_at=?,completed_at=?,
                           safe_message='Verified scores published transactionally.'
                       WHERE similarity_generation_id=? AND stage_code='PUBLISH'
                         AND execution_token=?""",
                    (now, now, now, int(generation_id), token),
                )
                changed = connection.execute(
                    """UPDATE buyer_similarity_score_generations
                       SET publication_state='PUBLISHED',published_person_count=?,
                           published_at=?,execution_owner=NULL,execution_token=NULL,
                           lease_heartbeat_at=NULL,safe_error_code=NULL
                       WHERE similarity_generation_id=? AND publication_state='BUILDING'
                         AND execution_owner=? AND execution_token=?""",
                    (expected, now, int(generation_id), owner, token),
                ).rowcount
                if changed != 1:
                    raise BuyerSimilarityGenerationFenceLost("The generation lease was lost.")
                if timing_sink is not None:
                    timing_sink["publication_transaction_body_seconds"] = (
                        time.perf_counter() - publication_started
                    )
        if timing_sink is not None:
            timing_sink["verify_and_publish_committed_seconds"] = (
                time.perf_counter() - verification_started
            )
        if failures:
            raise BuyerSimilarityGenerationVerificationError(
                "Similarity generation verification failed: " + ", ".join(failures)
            )
        return {
            "attestation_key_sha256": attestation_key,
            "verified_facts_sha256": facts_sha,
            "verified_row_count": row_count,
            "valid_score_count": valid_count,
            "invalid_score_count": invalid_count,
            "status": "VERIFIED",
        }

    def fetch_generation(self, generation_id: int) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
                (int(generation_id),),
            ).fetchone()
        return None if row is None else dict(row)


__all__ = (
    "ATTESTATION_INTEGRITY_CONTRACT_VERSION",
    "ATTESTATION_VERIFICATION_CONTRACT_VERSION",
    "BuyerSimilarityGenerationBusy",
    "BuyerSimilarityGenerationFenceLost",
    "BuyerSimilarityGenerationSourceStale",
    "BuyerSimilarityGenerationVerificationError",
    "BuyerSimilarityScoringRepository",
    "BuyerSimilarityScoringRepositoryError",
    "SCORER_CONTRACT_VERSION",
    "SimilarityGenerationClaim",
)
