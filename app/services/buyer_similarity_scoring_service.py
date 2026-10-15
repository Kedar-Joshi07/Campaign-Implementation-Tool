"""Bounded, resumable v3 prospect scoring and lightweight verified reuse."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from app.database.connection import get_connection
from app.ml.feature_contract import FeatureContractError, ORDERED_FEATURES
from app.repositories.buyer_similarity_scoring_repository import (
    ATTESTATION_INTEGRITY_CONTRACT_VERSION,
    ATTESTATION_VERIFICATION_CONTRACT_VERSION,
    BuyerSimilarityGenerationSourceStale,
    BuyerSimilarityScoringRepository,
    SCORER_CONTRACT_VERSION,
)
from app.repositories.prospect_scoring_repository import (
    MAX_SCORING_CHUNK_LIMIT,
    ProspectScoringRepository,
)
from app.services.buyer_similarity_profile_service import (
    BuyerSimilarityScore,
    SCORE_METHOD_VERSION,
    load_profile_artifact,
    score_buyer_similarity_frame,
    score_buyer_similarity_record,
)


DEFAULT_SIMILARITY_SCORING_CHUNK_SIZE = 25_000
MINIMUM_SIMILARITY_SCORING_CHUNK_SIZE = 1
MAXIMUM_PRODUCTS_PER_PREPARATION = 50
ESTIMATED_BYTES_PER_STAGED_AND_PUBLISHED_SCORE = 256
ProgressCallback = Callable[[str, int, int, str], None]
CancellationCheck = Callable[[], bool]


class BuyerSimilarityScoringServiceError(RuntimeError):
    """Base class for v3 scoring service failures."""


class BuyerSimilarityScoringCancelled(BuyerSimilarityScoringServiceError):
    """Raised after a safely cancelled generation publishes nothing."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_chunk_size(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MINIMUM_SIMILARITY_SCORING_CHUNK_SIZE <= value <= MAX_SCORING_CHUNK_LIMIT
    ):
        raise BuyerSimilarityScoringServiceError(
            f"chunk_size must be between {MINIMUM_SIMILARITY_SCORING_CHUNK_SIZE} "
            f"and {MAX_SCORING_CHUNK_LIMIT}."
        )
    return value


def _profile_lineage_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "historical_context_sha256": str(row["historical_context_sha256"]),
        "customer_import_id": int(row["customer_import_id"]),
        "customer_source_checksum": str(row["customer_source_checksum"]),
        "campaign_sales_import_id": int(row["campaign_sales_import_id"]),
        "campaign_sales_source_checksum": str(row["campaign_sales_source_checksum"]),
        "fit_identity_sha256": str(row["fit_identity_sha256"]),
        "holdout_identity_sha256": str(row["holdout_identity_sha256"]),
    }


def _load_current_profile(
    repository: BuyerSimilarityScoringRepository,
    profile_id: int,
    *,
    project_root: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = repository.fetch_profile_for_scoring(profile_id)
    artifact = load_profile_artifact(
        project_root=project_root,
        storage_uri=str(row["storage_uri"]),
        expected_artifact_sha256=str(row["artifact_sha256"]),
        expected_product_id=str(row["product_id"]),
        expected_lineage=_profile_lineage_from_row(row),
    )
    return row, artifact


def _metadata_current(
    database_path: str | Path,
    row: Mapping[str, Any],
) -> bool:
    """Check latest import identities without scanning score/demographic tables."""

    with get_connection(database_path) as connection:
        for dataset, id_field, checksum_field in (
            ("customers", "customer_import_id", "customer_source_checksum"),
            ("campaign_sales", "campaign_sales_import_id", "campaign_sales_source_checksum"),
            ("demographics", "demographic_import_id", "demographic_source_checksum"),
        ):
            current = connection.execute(
                """SELECT import_id,source_checksum,rows_inserted
                   FROM data_import_runs WHERE dataset_name=? AND status='COMPLETED'
                   ORDER BY import_id DESC LIMIT 1""",
                (dataset,),
            ).fetchone()
            if (
                current is None
                or int(current["import_id"]) != int(row[id_field])
                or str(current["source_checksum"] or "").strip().lower()
                != str(row[checksum_field]).strip().lower()
            ):
                return False
            if dataset == "demographics" and int(current["rows_inserted"]) != int(
                row["expected_person_count"]
            ):
                return False
    return True


def has_current_similarity_attestation(
    database_path: str | Path,
    generation_id: int,
    *,
    project_root: str | Path,
) -> bool:
    """Bounded currentness lookup; deliberately never scans score rows."""

    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT g.*,p.customer_import_id,p.customer_source_checksum,
                      p.campaign_sales_import_id,p.campaign_sales_source_checksum,
                      p.publication_state profile_state,a.storage_uri,
                      a.artifact_sha256,a.artifact_state,
                      t.verification_contract_version,t.integrity_contract_version,
                      t.profile_artifact_sha256,t.expected_person_count att_expected,
                      t.verified_row_count,t.verification_status
               FROM buyer_similarity_score_generations g
               JOIN buyer_similarity_profiles p ON p.profile_id=g.profile_id
               JOIN buyer_similarity_profile_artifacts a
                 ON a.profile_id=p.profile_id AND a.artifact_state='PUBLISHED'
               JOIN buyer_similarity_generation_attestations t
                 ON t.similarity_generation_id=g.similarity_generation_id
               WHERE g.similarity_generation_id=?""",
            (int(generation_id),),
        ).fetchone()
    if row is None:
        return False
    values = dict(row)
    if (
        values["publication_state"] != "PUBLISHED"
        or values["profile_state"] != "PUBLISHED"
        or values["artifact_state"] != "PUBLISHED"
        or values["verification_status"] != "VERIFIED"
        or values["verification_contract_version"]
        != ATTESTATION_VERIFICATION_CONTRACT_VERSION
        or values["integrity_contract_version"]
        != ATTESTATION_INTEGRITY_CONTRACT_VERSION
        or values["score_method_version"] != SCORE_METHOD_VERSION
        or values["scorer_contract_version"] != SCORER_CONTRACT_VERSION
        or values["profile_artifact_sha256"] != values["artifact_sha256"]
        or int(values["published_person_count"]) != int(values["expected_person_count"])
        or int(values["verified_row_count"]) != int(values["expected_person_count"])
        or int(values["att_expected"]) != int(values["expected_person_count"])
        or not _metadata_current(database_path, values)
    ):
        return False
    try:
        load_profile_artifact(
            project_root=project_root,
            storage_uri=str(values["storage_uri"]),
            expected_artifact_sha256=str(values["artifact_sha256"]),
            expected_product_id=str(values["product_id"]),
        )
    except Exception:
        return False
    return True


def find_reusable_similarity_generation(
    database_path: str | Path,
    profile_id: int,
    *,
    project_root: str | Path,
) -> dict[str, Any] | None:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """SELECT * FROM buyer_similarity_score_generations
               WHERE profile_id=? AND publication_state='PUBLISHED'
               ORDER BY similarity_generation_id DESC""",
            (int(profile_id),),
        ).fetchall()
    for row in rows:
        generation = dict(row)
        if has_current_similarity_attestation(
            database_path,
            int(generation["similarity_generation_id"]),
            project_root=project_root,
        ):
            return generation
    return None


def estimate_similarity_preparation_work(
    database_path: str | Path,
    profile_ids: Sequence[int],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    ids = tuple(dict.fromkeys(int(value) for value in profile_ids))
    if not ids or len(ids) > MAXIMUM_PRODUCTS_PER_PREPARATION:
        raise BuyerSimilarityScoringServiceError("Choose between 1 and 50 profile IDs.")
    with get_connection(database_path) as connection:
        marks = ",".join("?" for _ in ids)
        profiles = connection.execute(
            f"""SELECT profile_id,product_id,realized_k FROM buyer_similarity_profiles
                 WHERE publication_state='PUBLISHED' AND profile_id IN ({marks})""",
            ids,
        ).fetchall()
        demographic = connection.execute(
            """SELECT rows_inserted FROM data_import_runs
               WHERE dataset_name='demographics' AND status='COMPLETED'
               ORDER BY import_id DESC LIMIT 1"""
        ).fetchone()
    if len(profiles) != len(ids) or demographic is None:
        raise BuyerSimilarityScoringServiceError(
            "Published profiles and current demographics are required for estimation."
        )
    reusable: list[int] = []
    builds: list[int] = []
    for profile in profiles:
        profile_id = int(profile["profile_id"])
        if find_reusable_similarity_generation(
            database_path, profile_id, project_root=project_root
        ) is None:
            builds.append(profile_id)
        else:
            reusable.append(profile_id)
    population = int(demographic["rows_inserted"])
    by_id = {int(row["profile_id"]): row for row in profiles}
    distance_terms = sum(
        population * int(by_id[value]["realized_k"]) * len(ORDERED_FEATURES)
        for value in builds
    )
    score_rows = population * len(builds)
    return {
        "requested_profile_count": len(ids),
        "reusable_profile_ids": sorted(reusable),
        "build_profile_ids": sorted(builds),
        "demographic_person_count": population,
        "estimated_new_score_rows": score_rows,
        "estimated_feature_distance_terms": distance_terms,
        "estimated_peak_persistent_bytes": (
            score_rows * ESTIMATED_BYTES_PER_STAGED_AND_PUBLISHED_SCORE
        ),
        "heavy_work_serialization_required": bool(builds),
        "operator_confirmation_recommended": len(builds) > 1,
        "estimate_only": True,
    }


def _invalid_result(reason: str) -> BuyerSimilarityScore:
    return BuyerSimilarityScore(
        is_valid=False,
        buyer_similarity_score=None,
        feature_coverage=0.0,
        prototype_key=None,
        prototype_distance=None,
        invalid_reason_code=reason,
        feature_distances=(),
    )


def _score_chunk_resilient(
    frame: pd.DataFrame,
    artifact: Mapping[str, Any],
) -> tuple[BuyerSimilarityScore, ...]:
    try:
        return score_buyer_similarity_frame(frame, artifact, chunk_size=len(frame) or 1)
    except FeatureContractError:
        results: list[BuyerSimilarityScore] = []
        for row in frame.to_dict(orient="records"):
            try:
                results.append(score_buyer_similarity_record(row, artifact))
            except FeatureContractError:
                results.append(_invalid_result("INVALID_FEATURE_VALUES"))
        return tuple(results)


def run_similarity_generation(
    database_path: str | Path,
    profile_id: int,
    *,
    project_root: str | Path,
    execution_owner: str,
    execution_token: str,
    chunk_size: int = DEFAULT_SIMILARITY_SCORING_CHUNK_SIZE,
    stale_before: str | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation_check: CancellationCheck | None = None,
    clock: Callable[[], str] = _utc_now,
    timing_sink: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Reuse or build one exact per-product generation in bounded chunks."""

    from app.qa_guard import assert_qa_runtime
    assert_qa_runtime(database_path, project_root=project_root,
                      operation="v3_score_generation", record_admission=True)

    limit = _validate_chunk_size(chunk_size)
    repository = BuyerSimilarityScoringRepository(database_path)
    profile_row, artifact = _load_current_profile(
        repository, profile_id, project_root=project_root
    )
    reusable = find_reusable_similarity_generation(
        database_path, profile_id, project_root=project_root
    )
    if reusable is not None:
        return {
            "similarity_generation_id": int(reusable["similarity_generation_id"]),
            "profile_id": int(profile_id),
            "product_id": str(reusable["product_id"]),
            "status": "PUBLISHED",
            "reused": True,
            "deep_verification_run": False,
            "published_person_count": int(reusable["published_person_count"]),
        }

    prospect_repository = ProspectScoringRepository(database_path)
    demographic = prospect_repository.fetch_completed_demographic_import_provenance()
    claim = repository.claim_generation(
        profile_id,
        demographic,
        execution_owner=execution_owner,
        execution_token=execution_token,
        now=clock(),
        stale_before=stale_before,
    )
    if claim.reused_published:
        if not has_current_similarity_attestation(
            database_path, claim.similarity_generation_id, project_root=project_root
        ):
            raise BuyerSimilarityScoringServiceError(
                "A published generation lacks a current verified attestation."
            )
        generation = repository.fetch_generation(claim.similarity_generation_id)
        assert generation is not None
        return {
            "similarity_generation_id": claim.similarity_generation_id,
            "profile_id": int(profile_id),
            "product_id": claim.product_id,
            "status": "PUBLISHED",
            "reused": True,
            "deep_verification_run": False,
            "published_person_count": int(generation["published_person_count"]),
        }

    generation_id = claim.similarity_generation_id
    checkpoint = claim.resumed_checkpoint_person_id
    processed = claim.processed_count
    if progress_callback is not None:
        progress_callback(
            "QUEUE_WAIT", 0, claim.expected_person_count,
            "Queue time is complete; bounded scoring is active.",
        )
    try:
        while True:
            if cancellation_check is not None and cancellation_check():
                repository.cancel(
                    generation_id,
                    execution_owner=execution_owner,
                    execution_token=execution_token,
                    now=clock(),
                )
                raise BuyerSimilarityScoringCancelled(
                    "Similarity generation was cancelled without publishing scores."
                )
            person_ids, frame = prospect_repository.fetch_scoring_chunk(
                after_person_id=checkpoint,
                limit=limit,
            )
            if not person_ids:
                break
            results = _score_chunk_resilient(frame, artifact)
            rows = [
                {
                    "person_id": person_id,
                    "is_valid": result.is_valid,
                    "buyer_similarity_score": result.buyer_similarity_score,
                    "feature_coverage": result.feature_coverage,
                    "prototype_key": result.prototype_key,
                    "invalid_reason_code": result.invalid_reason_code,
                }
                for person_id, result in zip(person_ids, results, strict=True)
            ]
            repository.persist_score_chunk(
                generation_id,
                rows,
                expected_checkpoint_person_id=checkpoint,
                execution_owner=execution_owner,
                execution_token=execution_token,
                now=clock(),
            )
            processed += len(rows)
            checkpoint = person_ids[-1]
            if progress_callback is not None:
                progress_callback(
                    "SCORING_PROSPECTS", processed, claim.expected_person_count,
                    f"Scored {processed} of {claim.expected_person_count} people.",
                )
        if progress_callback is not None:
            progress_callback(
                "DEEP_VERIFY", processed, claim.expected_person_count,
                "Verifying exact population, lineage, and score integrity.",
            )
        # Re-read the small artifact immediately before the atomic database gate.
        artifact = load_profile_artifact(
            project_root=project_root,
            storage_uri=str(profile_row["storage_uri"]),
            expected_artifact_sha256=str(profile_row["artifact_sha256"]),
            expected_product_id=str(profile_row["product_id"]),
            expected_lineage=_profile_lineage_from_row(profile_row),
        )
        attestation = repository.verify_and_publish(
            generation_id,
            allowed_prototype_keys=[
                str(value["prototype_key"]) for value in artifact["prototypes"]
            ],
            profile_artifact_sha256=str(profile_row["artifact_sha256"]),
            execution_owner=execution_owner,
            execution_token=execution_token,
            now=clock(),
            timing_sink=timing_sink,
        )
    except BuyerSimilarityGenerationSourceStale:
        repository.mark_source_stale(
            generation_id,
            execution_owner=execution_owner,
            execution_token=execution_token,
            now=clock(),
        )
        raise
    if progress_callback is not None:
        progress_callback(
            "PUBLISH", processed, claim.expected_person_count,
            "Verified similarity scores are published and reusable.",
        )
    return {
        "similarity_generation_id": generation_id,
        "profile_id": int(profile_id),
        "product_id": claim.product_id,
        "profile_set_sha256": claim.profile_set_sha256,
        "composite_context_sha256": claim.composite_context_sha256,
        "status": "PUBLISHED",
        "reused": False,
        "restarted_from_stale_lease": claim.restarted_from_stale_lease,
        "deep_verification_run": True,
        "published_person_count": claim.expected_person_count,
        "attestation": attestation,
    }


def composite_similarity_winners(
    database_path: str | Path,
    generation_ids: Sequence[int],
    *,
    project_root: str | Path,
    after_person_id: str | None = None,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    """Return max-score winners with product-ID ascending tie resolution."""

    ids = tuple(dict.fromkeys(int(value) for value in generation_ids))
    if not ids or len(ids) > MAXIMUM_PRODUCTS_PER_PREPARATION:
        raise BuyerSimilarityScoringServiceError("Choose between 1 and 50 generation IDs.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100_000:
        raise BuyerSimilarityScoringServiceError("limit must be between 1 and 100000.")
    for generation_id in ids:
        if not has_current_similarity_attestation(
            database_path, generation_id, project_root=project_root
        ):
            raise BuyerSimilarityScoringServiceError(
                "Every composite generation must be current and verified."
            )
    marks = ",".join("?" for _ in ids)
    cursor = "" if after_person_id is None else str(after_person_id)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""WITH ranked AS (
                    SELECT person_id,buyer_similarity_score,product_id,
                           feature_coverage,prototype_key,similarity_generation_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY person_id
                               ORDER BY buyer_similarity_score DESC,
                                        product_id ASC,similarity_generation_id ASC
                           ) winner_order
                    FROM buyer_similarity_scores
                    WHERE similarity_generation_id IN ({marks}) AND is_valid=1)
                SELECT person_id,buyer_similarity_score,product_id matched_product_id,
                       feature_coverage,prototype_key,similarity_generation_id
                FROM ranked WHERE winner_order=1 AND person_id>?
                ORDER BY person_id LIMIT ?""",
            (*ids, cursor, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def similarity_profile_set_sha256(profile_identities: Sequence[str]) -> str:
    """Canonical composite identity, independent of thresholds and filters."""

    return hashlib.sha256(
        _canonical(sorted(set(profile_identities))).encode("utf-8")
    ).hexdigest()


__all__ = (
    "BuyerSimilarityScoringCancelled",
    "BuyerSimilarityScoringServiceError",
    "DEFAULT_SIMILARITY_SCORING_CHUNK_SIZE",
    "composite_similarity_winners",
    "estimate_similarity_preparation_work",
    "find_reusable_similarity_generation",
    "has_current_similarity_attestation",
    "run_similarity_generation",
    "similarity_profile_set_sha256",
)
