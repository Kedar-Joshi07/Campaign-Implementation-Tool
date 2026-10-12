"""Fenced lifecycle and transactional publication for v3 buyer profiles."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.services.buyer_similarity_profile_service import (
    PREPROCESSOR_CONTRACT_SHA256,
    SERIALIZATION_CONTRACT_VERSION,
    StoredProfileArtifact,
    load_profile_artifact,
    serialize_profile_artifact,
    write_profile_artifact,
)


_TOKEN = re.compile(r"[0-9a-f]{64}")


class BuyerSimilarityProfileRegistryError(RuntimeError):
    """Base class for safe profile lifecycle failures."""


class BuyerSimilarityProfileLeaseBusy(BuyerSimilarityProfileRegistryError):
    """Raised when a current fenced builder owns the exact profile."""


class BuyerSimilarityProfileFenceLost(BuyerSimilarityProfileRegistryError):
    """Raised when an old owner/token attempts to mutate a profile."""


class BuyerSimilarityProfileSourceStale(BuyerSimilarityProfileRegistryError):
    """Raised when the artifact no longer matches the latest sources."""


@dataclass(frozen=True)
class ProfileBuildClaim:
    profile_id: int
    reuse_published: bool
    execution_owner: str | None
    execution_token: str | None
    storage_uri: str | None
    artifact_sha256: str | None


@dataclass(frozen=True)
class PublishedBuyerSimilarityProfile:
    profile_id: int
    reused: bool
    storage: StoredProfileArtifact
    artifact: dict[str, Any]


def _validate_owner_token(owner: str, token: str) -> tuple[str, str]:
    normalized_owner = str(owner).strip()
    normalized_token = str(token).strip().lower()
    if not normalized_owner or len(normalized_owner) > 128:
        raise BuyerSimilarityProfileRegistryError("The execution owner is invalid.")
    if _TOKEN.fullmatch(normalized_token) is None:
        raise BuyerSimilarityProfileRegistryError("The execution token is invalid.")
    return normalized_owner, normalized_token


def _assert_current_sources(connection: sqlite3.Connection, lineage: Mapping[str, Any]) -> None:
    for dataset, id_field, checksum_field in (
        ("customers", "customer_import_id", "customer_source_checksum"),
        ("campaign_sales", "campaign_sales_import_id", "campaign_sales_source_checksum"),
    ):
        row = connection.execute(
            """SELECT import_id,source_checksum FROM data_import_runs
               WHERE dataset_name=? AND status='COMPLETED'
               ORDER BY import_id DESC LIMIT 1""",
            (dataset,),
        ).fetchone()
        if (
            row is None
            or int(row["import_id"]) != int(lineage[id_field])
            or str(row["source_checksum"]).strip().lower() != lineage[checksum_field]
        ):
            raise BuyerSimilarityProfileSourceStale(
                f"The current {dataset} source no longer matches this profile."
            )


class BuyerSimilarityProfileRepository:
    """Own exact profile claims, leases, cancellation, and publication."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def claim_build(
        self,
        artifact: Mapping[str, Any],
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
        stale_before: str | None = None,
    ) -> ProfileBuildClaim:
        payload = dict(artifact)
        serialize_profile_artifact(payload)
        owner, token = _validate_owner_token(execution_owner, execution_token)
        identity = payload["immutable_identity_sha256"]
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _assert_current_sources(connection, payload["lineage"])
            published = connection.execute(
                """SELECT p.profile_id,a.storage_uri,a.artifact_sha256
                   FROM buyer_similarity_profiles p
                   JOIN buyer_similarity_profile_artifacts a
                     ON a.profile_id=p.profile_id AND a.artifact_state='PUBLISHED'
                   WHERE p.immutable_identity_sha256=?
                     AND p.publication_state='PUBLISHED'
                   ORDER BY p.profile_id DESC LIMIT 1""",
                (identity,),
            ).fetchone()
            if published is not None:
                return ProfileBuildClaim(
                    profile_id=int(published["profile_id"]),
                    reuse_published=True,
                    execution_owner=None,
                    execution_token=None,
                    storage_uri=str(published["storage_uri"]),
                    artifact_sha256=str(published["artifact_sha256"]),
                )

            active = connection.execute(
                """SELECT profile_id,execution_owner,execution_token,lease_heartbeat_at
                   FROM buyer_similarity_profiles
                   WHERE immutable_identity_sha256=? AND publication_state='BUILDING'
                   ORDER BY profile_id DESC LIMIT 1""",
                (identity,),
            ).fetchone()
            if active is not None:
                if active["execution_owner"] == owner and active["execution_token"] == token:
                    return ProfileBuildClaim(
                        profile_id=int(active["profile_id"]),
                        reuse_published=False,
                        execution_owner=owner,
                        execution_token=token,
                        storage_uri=None,
                        artifact_sha256=None,
                    )
                heartbeat = str(active["lease_heartbeat_at"] or "")
                if stale_before is None or not heartbeat or heartbeat >= stale_before:
                    raise BuyerSimilarityProfileLeaseBusy(
                        "The exact buyer profile already has an active builder."
                    )
                changed = connection.execute(
                    """UPDATE buyer_similarity_profiles
                       SET execution_owner=?,execution_token=?,lease_heartbeat_at=?,safe_error_code=NULL
                       WHERE profile_id=? AND publication_state='BUILDING'
                         AND execution_token=? AND lease_heartbeat_at=?""",
                    (
                        owner,
                        token,
                        now,
                        int(active["profile_id"]),
                        active["execution_token"],
                        active["lease_heartbeat_at"],
                    ),
                ).rowcount
                if changed != 1:
                    raise BuyerSimilarityProfileFenceLost(
                        "The stale profile lease changed before recovery."
                    )
                return ProfileBuildClaim(
                    profile_id=int(active["profile_id"]),
                    reuse_published=False,
                    execution_owner=owner,
                    execution_token=token,
                    storage_uri=None,
                    artifact_sha256=None,
                )

            lineage = payload["lineage"]
            profile_id = int(
                connection.execute(
                    """INSERT INTO buyer_similarity_profiles (
                        immutable_identity_sha256,product_id,historical_context_sha256,
                        resolved_window_start,resolved_window_end,buyer_conversion_definition,
                        customer_import_id,customer_source_checksum,campaign_sales_import_id,
                        campaign_sales_source_checksum,feature_contract_sha256,
                        score_method_version,preprocessor_contract_sha256,
                        fit_identity_sha256,holdout_identity_sha256,split_seed,
                        prototype_support,realized_k,publication_state,
                        execution_owner,execution_token,lease_heartbeat_at,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'BUILDING',?,?,?,?)""",
                    (
                        identity,
                        payload["product_id"],
                        lineage["historical_context_sha256"],
                        lineage["resolved_window_start"],
                        lineage["resolved_window_end"],
                        lineage["buyer_conversion_definition"],
                        int(lineage["customer_import_id"]),
                        lineage["customer_source_checksum"],
                        int(lineage["campaign_sales_import_id"]),
                        lineage["campaign_sales_source_checksum"],
                        payload["feature_contract_sha256"],
                        payload["score_method_version"],
                        PREPROCESSOR_CONTRACT_SHA256,
                        lineage["fit_identity_sha256"],
                        lineage["holdout_identity_sha256"],
                        int(lineage["split_seed"]),
                        int(payload["fit_support"]),
                        int(payload["realized_k"]),
                        owner,
                        token,
                        now,
                        now,
                    ),
                ).lastrowid
            )
            return ProfileBuildClaim(
                profile_id=profile_id,
                reuse_published=False,
                execution_owner=owner,
                execution_token=token,
                storage_uri=None,
                artifact_sha256=None,
            )

    def heartbeat(
        self,
        profile_id: int,
        *,
        execution_owner: str,
        execution_token: str,
        now: str,
    ) -> None:
        owner, token = _validate_owner_token(execution_owner, execution_token)
        with get_connection(self.database_path, write=True) as connection:
            changed = connection.execute(
                """UPDATE buyer_similarity_profiles SET lease_heartbeat_at=?
                   WHERE profile_id=? AND publication_state='BUILDING'
                     AND execution_owner=? AND execution_token=?""",
                (now, int(profile_id), owner, token),
            ).rowcount
            if changed != 1:
                raise BuyerSimilarityProfileFenceLost("The profile build lease was lost.")

    def cancel(
        self,
        profile_id: int,
        *,
        execution_owner: str,
        execution_token: str,
    ) -> None:
        owner, token = _validate_owner_token(execution_owner, execution_token)
        with get_connection(self.database_path, write=True) as connection:
            changed = connection.execute(
                """UPDATE buyer_similarity_profiles
                   SET publication_state='FAILED',execution_owner=NULL,
                       execution_token=NULL,lease_heartbeat_at=NULL,
                       safe_error_code='CANCELLED'
                   WHERE profile_id=? AND publication_state='BUILDING'
                     AND execution_owner=? AND execution_token=?""",
                (int(profile_id), owner, token),
            ).rowcount
            if changed != 1:
                raise BuyerSimilarityProfileFenceLost("The profile build lease was lost.")

    def publish(
        self,
        profile_id: int,
        artifact: Mapping[str, Any],
        storage: StoredProfileArtifact,
        *,
        project_root: str | Path,
        execution_owner: str,
        execution_token: str,
        now: str,
    ) -> None:
        payload = dict(artifact)
        _, expected_artifact_sha, expected_payload_sha = serialize_profile_artifact(payload)
        if (
            storage.artifact_sha256 != expected_artifact_sha
            or storage.profile_payload_sha256 != expected_payload_sha
        ):
            raise BuyerSimilarityProfileRegistryError(
                "The durable artifact identity does not match the profile."
            )
        durable_payload = load_profile_artifact(
            project_root=project_root,
            storage_uri=storage.storage_uri,
            expected_artifact_sha256=storage.artifact_sha256,
            expected_product_id=str(payload["product_id"]),
            expected_lineage=dict(payload["lineage"]),
        )
        if serialize_profile_artifact(durable_payload)[2] != storage.profile_payload_sha256:
            raise BuyerSimilarityProfileRegistryError(
                "The durable profile payload checksum does not match."
            )
        owner, token = _validate_owner_token(execution_owner, execution_token)
        source_stale = False
        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT immutable_identity_sha256,execution_owner,execution_token,
                          publication_state
                   FROM buyer_similarity_profiles WHERE profile_id=?""",
                (int(profile_id),),
            ).fetchone()
            if (
                row is None
                or row["publication_state"] != "BUILDING"
                or row["execution_owner"] != owner
                or row["execution_token"] != token
                or row["immutable_identity_sha256"]
                != payload["immutable_identity_sha256"]
            ):
                raise BuyerSimilarityProfileFenceLost("The profile build lease was lost.")
            try:
                _assert_current_sources(connection, payload["lineage"])
            except BuyerSimilarityProfileSourceStale:
                connection.execute(
                    """UPDATE buyer_similarity_profiles
                       SET publication_state='STALE',execution_owner=NULL,
                           execution_token=NULL,lease_heartbeat_at=NULL,
                           safe_error_code='SOURCE_REPLACED'
                       WHERE profile_id=? AND execution_token=?""",
                    (int(profile_id), token),
                )
                source_stale = True
            if not source_stale:
                artifact_id = int(
                    connection.execute(
                        """INSERT INTO buyer_similarity_profile_artifacts (
                            profile_id,serialization_contract_version,storage_uri,
                            artifact_sha256,profile_payload_sha256,artifact_state,created_at
                        ) VALUES (?,?,?,?,?,'STAGED',?)""",
                        (
                            int(profile_id),
                            SERIALIZATION_CONTRACT_VERSION,
                            storage.storage_uri,
                            storage.artifact_sha256,
                            storage.profile_payload_sha256,
                            now,
                        ),
                    ).lastrowid
                )
                connection.execute(
                    """UPDATE buyer_similarity_profile_artifacts
                       SET artifact_state='PUBLISHED',published_at=?
                       WHERE profile_artifact_id=? AND artifact_state='STAGED'""",
                    (now, artifact_id),
                )
                changed = connection.execute(
                    """UPDATE buyer_similarity_profiles
                       SET publication_state='PUBLISHED',published_at=?,
                           execution_owner=NULL,execution_token=NULL,
                           lease_heartbeat_at=NULL,safe_error_code=NULL
                       WHERE profile_id=? AND publication_state='BUILDING'
                         AND execution_owner=? AND execution_token=?""",
                    (now, int(profile_id), owner, token),
                ).rowcount
                if changed != 1:
                    raise BuyerSimilarityProfileFenceLost("The profile build lease was lost.")
        if source_stale:
            raise BuyerSimilarityProfileSourceStale(
                "The source was replaced before profile publication."
            )


def publish_buyer_similarity_profile(
    database_path: str | Path,
    artifact: Mapping[str, Any],
    *,
    project_root: str | Path,
    execution_owner: str,
    execution_token: str,
    now: str,
    stale_before: str | None = None,
) -> PublishedBuyerSimilarityProfile:
    """Claim/reuse and publish one already-fitted deterministic profile."""

    repository = BuyerSimilarityProfileRepository(database_path)
    claim = repository.claim_build(
        artifact,
        execution_owner=execution_owner,
        execution_token=execution_token,
        now=now,
        stale_before=stale_before,
    )
    if claim.reuse_published:
        assert claim.storage_uri is not None and claim.artifact_sha256 is not None
        _, requested_artifact_sha, _ = serialize_profile_artifact(dict(artifact))
        if requested_artifact_sha != claim.artifact_sha256:
            raise BuyerSimilarityProfileRegistryError(
                "The published immutable identity has different artifact content."
            )
        loaded = load_profile_artifact(
            project_root=project_root,
            storage_uri=claim.storage_uri,
            expected_artifact_sha256=claim.artifact_sha256,
            expected_product_id=str(artifact["product_id"]),
            expected_lineage=dict(artifact["lineage"]),
        )
        _, artifact_sha, payload_sha = serialize_profile_artifact(loaded)
        return PublishedBuyerSimilarityProfile(
            profile_id=claim.profile_id,
            reused=True,
            storage=StoredProfileArtifact(claim.storage_uri, artifact_sha, payload_sha),
            artifact=loaded,
        )
    storage = write_profile_artifact(artifact, project_root=project_root)
    repository.publish(
        claim.profile_id,
        artifact,
        storage,
        project_root=project_root,
        execution_owner=execution_owner,
        execution_token=execution_token,
        now=now,
    )
    return PublishedBuyerSimilarityProfile(
        profile_id=claim.profile_id,
        reused=False,
        storage=storage,
        artifact=dict(artifact),
    )


__all__ = (
    "BuyerSimilarityProfileFenceLost",
    "BuyerSimilarityProfileLeaseBusy",
    "BuyerSimilarityProfileRegistryError",
    "BuyerSimilarityProfileRepository",
    "BuyerSimilarityProfileSourceStale",
    "ProfileBuildClaim",
    "PublishedBuyerSimilarityProfile",
    "publish_buyer_similarity_profile",
)
