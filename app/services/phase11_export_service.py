"""Governed, streaming Phase 11 result-snapshot downloads.

Analytical membership remains in the immutable no-PII snapshot. Contact and
activation fields are joined from the current demographics source only while a
response is streamed; only aggregate audit metadata is persisted.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import io
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Request
from starlette.responses import StreamingResponse

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.omnichannel_profile_contracts import (
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    EXPORT_PROFILE_DISPLAY_AUDIENCE_V1,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
    EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
    EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
    EXPORT_PROFILE_SMS_CONTACT_V1,
    EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
    EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
    EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
    PROFILE_AVAILABILITY_AVAILABLE,
    OmnichannelExportProfile,
    build_profile_filename,
    get_omnichannel_profile,
    mitigate_csv_formula_injection,
    project_profile_row,
    resolve_profile_availability,
)
from app.services.phase11_result_contracts import RESULT_MEMBERSHIP_COLUMNS
from app.services.phase11_result_snapshot_service import validate_result_snapshot


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_JOIN_CHUNK_SIZE = 250
EXPORT_RECOVERY_THRESHOLD_SECONDS = 3600

_PROFILE_SOURCE_FIELDS = {
    EXPORT_PROFILE_EMAIL_CONTACT_V1: (
        "first_name", "last_name", "email", "email_contactable",
    ),
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1: (
        "first_name", "last_name", "address_line_1", "address_line_2",
        "city", "state", "postal_code", "direct_mail_contactable",
    ),
    EXPORT_PROFILE_SMS_CONTACT_V1: (
        "first_name", "last_name", "phone_number", "sms_opt_in",
    ),
    EXPORT_PROFILE_WHATSAPP_CONTACT_V1: (
        "first_name", "last_name", "phone_number", "whatsapp_opt_in",
    ),
    EXPORT_PROFILE_TELEMARKETING_CONTACT_V1: (
        "first_name", "last_name", "phone_number",
        "telemarketing_contactable", "do_not_call",
    ),
    EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1: ("email", "phone_number"),
    EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1: ("email", "phone_number"),
    EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1: ("push_token", "push_opt_in"),
    EXPORT_PROFILE_DISPLAY_AUDIENCE_V1: (
        "advertising_id", "advertising_targetable",
    ),
    EXPORT_PROFILE_WEBSITE_AUDIENCE_V1: (
        "web_visitor_id", "onsite_targetable",
    ),
}

_UNAVAILABLE_MESSAGES = {
    "UNAVAILABLE_MISSING_IDENTIFIER": (
        "This download profile is unavailable because its governed identifier "
        "source is not present."
    ),
    "UNAVAILABLE_MISSING_CONSENT_CONTRACT": (
        "This download profile is unavailable because its governed "
        "contactability source is not present."
    ),
}


class Phase11ExportError(RuntimeError):
    """Base class for safe public export failures."""


class Phase11ExportNotFoundError(Phase11ExportError):
    """The requested search or its immutable lineage does not exist."""


class Phase11ExportValidationError(Phase11ExportError):
    """The caller supplied an invalid download request."""


class Phase11ExportConflictError(Phase11ExportError):
    """The saved result is not currently eligible for download."""


class Phase11ExportAbortedError(Phase11ExportError):
    """The client disconnected while the governed file was streaming."""


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    import_id: int
    source_checksum: str


@dataclass(frozen=True, slots=True)
class _ExportPlan:
    database_path: Path
    project_root: Path
    run: dict[str, Any]
    snapshot: dict[str, Any]
    generation: dict[str, Any]
    profile: OmnichannelExportProfile
    members_path: Path
    source_identity: _SourceIdentity
    selected_count: int
    deliverable_count: int
    undeliverable_count: int


def _current_demographic_source(connection: Any) -> _SourceIdentity:
    row = connection.execute(
        """
        SELECT import_id, source_checksum
        FROM data_import_runs
        WHERE dataset_name='demographics' AND status='COMPLETED'
        ORDER BY import_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise Phase11ExportConflictError(
            "The governed contact source is not currently available."
        )
    return _SourceIdentity(int(row["import_id"]), str(row["source_checksum"]))


def _source_matches_generation(
    identity: _SourceIdentity, generation: Mapping[str, Any]
) -> bool:
    return (
        identity.import_id == generation.get("demographic_import_id")
        and identity.source_checksum == generation.get("demographic_source_checksum")
    )


def _available_demographic_fields(connection: Any) -> frozenset[str]:
    return frozenset(
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(demographics)").fetchall()
    )


def _members_path(
    project_root: Path, snapshot: Mapping[str, Any]
) -> Path:
    try:
        snapshot_id = int(snapshot["result_snapshot_id"])
        storage_uri = str(snapshot["storage_uri"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase11ExportConflictError(
            "The result snapshot is unavailable for download."
        ) from exc
    expected_uri = (
        f"artifacts/results/result_snapshot_{snapshot_id:06d}/members.csv.gz"
    )
    path = (project_root / storage_uri).resolve()
    if (
        storage_uri != expected_uri
        or not path.is_relative_to(project_root)
        or not path.is_file()
        or snapshot.get("storage_format") != "CSV_GZIP"
    ):
        raise Phase11ExportConflictError(
            "The result snapshot is unavailable for download."
        )
    return path


def _membership_chunks(path: Path) -> Iterator[list[dict[str, Any]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != RESULT_MEMBERSHIP_COLUMNS:
            raise Phase11ExportConflictError(
                "The result snapshot is unavailable for download."
            )
        chunk: list[dict[str, Any]] = []
        for raw in reader:
            try:
                member = {
                    "person_id": str(raw["person_id"]),
                    "propensity_score": float(raw["propensity_score"]),
                    "percentile_bucket": int(raw["percentile_bucket"]),
                    "decile": int(raw["decile"]),
                    "rank_band": str(raw["rank_band"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise Phase11ExportConflictError(
                    "The result snapshot is unavailable for download."
                ) from exc
            chunk.append(member)
            if len(chunk) == EXPORT_JOIN_CHUNK_SIZE:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def _joined_profile_rows(
    connection: Any,
    *,
    members_path: Path,
    profile: OmnichannelExportProfile,
) -> Iterator[tuple[dict[str, Any], dict[str, Any] | None]]:
    source_fields = _PROFILE_SOURCE_FIELDS[profile.export_profile]
    for members in _membership_chunks(members_path):
        person_ids = [member["person_id"] for member in members]
        placeholders = ",".join("?" for _ in person_ids)
        columns = ",".join(f'"{field}"' for field in source_fields)
        rows = connection.execute(
            f'SELECT person_id,{columns} FROM demographics '
            f"WHERE person_id IN ({placeholders})",
            tuple(person_ids),
        ).fetchall()
        contacts = {str(row["person_id"]): dict(row) for row in rows}
        for member in members:
            contact = contacts.get(member["person_id"])
            if contact is None:
                yield member, None
                continue
            combined = member | contact
            yield member, project_profile_row(profile.export_profile, combined)


def _count_deliverability(
    database_path: Path,
    *,
    members_path: Path,
    profile: OmnichannelExportProfile,
) -> tuple[int, int, int]:
    selected = deliverable = 0
    with get_connection(database_path) as connection:
        connection.execute("BEGIN")
        for _member, projected in _joined_profile_rows(
            connection, members_path=members_path, profile=profile
        ):
            selected += 1
            if projected is not None:
                deliverable += 1
    return selected, deliverable, selected - deliverable


def _prepare_export(
    database_path: str | Path,
    *,
    search_run_id: int,
    project_root: str | Path | None,
) -> _ExportPlan:
    if isinstance(search_run_id, bool) or not isinstance(search_run_id, int) or search_run_id <= 0:
        raise Phase11ExportValidationError("search_run_id must be a positive integer.")
    path = Path(database_path)
    root = (DEFAULT_PROJECT_ROOT if project_root is None else Path(project_root)).resolve()
    repository = CampaignResultRegistryRepository(path)
    run = repository.fetch_search_run(search_run_id)
    if run is None:
        raise Phase11ExportNotFoundError("The saved result was not found.")
    if run.get("status") != "COMPLETED" or run.get("result_snapshot_id") is None:
        raise Phase11ExportConflictError(
            "The saved result is not completed and current for download."
        )
    snapshot = repository.fetch_snapshot(int(run["result_snapshot_id"]))
    if snapshot is None or run.get("generation_id") is None:
        raise Phase11ExportNotFoundError("The saved result lineage was not found.")
    generation = Phase10IntelligenceRepository(path).fetch_generation(
        int(run["generation_id"])
    )
    if generation is None:
        raise Phase11ExportNotFoundError("The saved result lineage was not found.")
    try:
        profile = get_omnichannel_profile(str(run["export_profile"]))
    except ValueError as exc:
        raise Phase11ExportValidationError(
            "The saved download profile is invalid."
        ) from exc
    if profile.channel_code != run.get("delivery_channel"):
        raise Phase11ExportConflictError(
            "The saved delivery channel and download profile do not match."
        )

    validation = validate_result_snapshot(
        snapshot,
        run,
        generation,
        str(snapshot["result_cache_key_sha256"]),
        project_root=root,
    )
    if not validation.is_valid:
        repository.update_snapshot_currentness(
            int(snapshot["result_snapshot_id"]), state="STALE"
        )
        raise Phase11ExportConflictError(
            "The result snapshot is not current for download."
        )
    members_path = _members_path(root, snapshot)

    with get_connection(path) as connection:
        availability = resolve_profile_availability(
            profile.export_profile,
            available_source_fields=_available_demographic_fields(connection),
        )
        if availability != PROFILE_AVAILABILITY_AVAILABLE:
            raise Phase11ExportConflictError(
                _UNAVAILABLE_MESSAGES.get(
                    availability, "This download profile is currently unavailable."
                )
            )
        source_identity = _current_demographic_source(connection)
    if not _source_matches_generation(source_identity, generation):
        repository.update_snapshot_currentness(
            int(snapshot["result_snapshot_id"]), state="STALE"
        )
        raise Phase11ExportConflictError(
            "The result is not current with the governed contact source."
        )

    selected, deliverable, undeliverable = _count_deliverability(
        path, members_path=members_path, profile=profile
    )
    expected = int(run["selected_count"])
    if (
        selected != expected
        or selected != int(snapshot["resolved_count"])
        or selected != deliverable + undeliverable
    ):
        raise Phase11ExportConflictError(
            "The immutable result count could not be reconciled for download."
        )
    return _ExportPlan(
        database_path=path,
        project_root=root,
        run=run,
        snapshot=snapshot,
        generation=generation,
        profile=profile,
        members_path=members_path,
        source_identity=source_identity,
        selected_count=selected,
        deliverable_count=deliverable,
        undeliverable_count=undeliverable,
    )


def _csv_bytes(
    values: list[Any], writer: Any, buffer: io.StringIO
) -> bytes:
    buffer.seek(0)
    buffer.truncate(0)
    writer.writerow([mitigate_csv_formula_injection(value) for value in values])
    return buffer.getvalue().encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_is_still_current(plan: _ExportPlan) -> bool:
    with get_connection(plan.database_path) as connection:
        return _current_demographic_source(connection) == plan.source_identity


def _finish_unsuccessful(
    repository: CampaignResultRegistryRepository,
    event_id: int,
    *,
    status: str,
    row_count: int,
    currentness_state: str,
) -> None:
    try:
        repository.finish_export_event(
            event_id,
            status=status,
            row_count=row_count,
            currentness_state=currentness_state,
        )
    except Exception:
        # Preserve the primary stream error. A stale RUNNING row is recoverable
        # and must never cause contact data to be logged or persisted.
        pass


def stream_phase11_result_export_csv(
    database_path: str | Path,
    *,
    search_run_id: int,
    request: Request,
    project_root: str | Path | None = None,
) -> StreamingResponse:
    """Preflight, audit, and stream one governed profile-specific CSV."""

    plan = _prepare_export(
        database_path, search_run_id=search_run_id, project_root=project_root
    )
    repository = CampaignResultRegistryRepository(plan.database_path)
    event_id = repository.create_export_event(
        search_run_id=int(plan.run["search_run_id"]),
        snapshot_id=int(plan.snapshot["result_snapshot_id"]),
        export_profile=plan.profile.export_profile,
        selected_count=plan.selected_count,
        deliverable_count=plan.deliverable_count,
        undeliverable_count=plan.undeliverable_count,
    )

    async def stream() -> AsyncIterator[bytes]:
        row_count = 0
        terminal_recorded = False
        digest = hashlib.sha256()
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        try:
            if await request.is_disconnected():
                raise Phase11ExportAbortedError("The download was interrupted.")
            with get_connection(plan.database_path) as connection:
                connection.execute("BEGIN")
                source_identity = _current_demographic_source(connection)
                if source_identity != plan.source_identity:
                    raise Phase11ExportConflictError(
                        "The governed contact source changed before download."
                    )
                header = _csv_bytes(list(plan.profile.output_columns), writer, buffer)
                digest.update(header)
                yield header
                for member_index, (_member, projected) in enumerate(
                    _joined_profile_rows(
                        connection,
                        members_path=plan.members_path,
                        profile=plan.profile,
                    )
                ):
                    if (
                        member_index % EXPORT_JOIN_CHUNK_SIZE == 0
                        and await request.is_disconnected()
                    ):
                        raise Phase11ExportAbortedError(
                            "The download was interrupted."
                        )
                    if projected is None:
                        continue
                    encoded = _csv_bytes(
                        [projected[column] for column in plan.profile.output_columns],
                        writer,
                        buffer,
                    )
                    digest.update(encoded)
                    row_count += 1
                    yield encoded

            if row_count != plan.deliverable_count:
                raise Phase11ExportConflictError(
                    "Download row counts changed during export."
                )
            if not _source_is_still_current(plan):
                raise Phase11ExportConflictError(
                    "The governed contact source changed during download."
                )
            if _file_sha256(plan.members_path) != plan.snapshot["snapshot_sha256"]:
                raise Phase11ExportConflictError(
                    "The result snapshot changed during download."
                )
            repository.finish_export_event(
                event_id,
                status="COMPLETED",
                row_count=row_count,
                csv_sha256=digest.hexdigest(),
                currentness_state="CURRENT",
            )
            terminal_recorded = True
        except asyncio.CancelledError:
            _finish_unsuccessful(
                repository,
                event_id,
                status="ABORTED",
                row_count=row_count,
                currentness_state="UNVERIFIED",
            )
            terminal_recorded = True
            raise
        except Phase11ExportAbortedError:
            _finish_unsuccessful(
                repository,
                event_id,
                status="ABORTED",
                row_count=row_count,
                currentness_state="UNVERIFIED",
            )
            terminal_recorded = True
        except Phase11ExportConflictError:
            repository.update_snapshot_currentness(
                int(plan.snapshot["result_snapshot_id"]), state="STALE"
            )
            _finish_unsuccessful(
                repository,
                event_id,
                status="FAILED",
                row_count=row_count,
                currentness_state="STALE",
            )
            terminal_recorded = True
            raise
        except Exception:
            _finish_unsuccessful(
                repository,
                event_id,
                status="FAILED",
                row_count=row_count,
                currentness_state="UNVERIFIED",
            )
            terminal_recorded = True
            raise
        finally:
            if not terminal_recorded:
                _finish_unsuccessful(
                    repository,
                    event_id,
                    status="ABORTED",
                    row_count=row_count,
                    currentness_state="UNVERIFIED",
                )

    filename = build_profile_filename(
        plan.profile.export_profile, search_run_id=search_run_id
    )
    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Export-Profile": plan.profile.export_profile,
        },
    )


def reconcile_stale_result_export_events(
    database_path: str | Path, *, limit: int = 100,
) -> int:
    """Mark bounded, hour-old RUNNING audits aborted after process restart."""

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=EXPORT_RECOVERY_THRESHOLD_SECONDS)
    return CampaignResultRegistryRepository(database_path).reconcile_stale_export_events(
        stale_started_at_max=cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
        timestamp=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        limit=limit,
    )


__all__ = (
    "EXPORT_JOIN_CHUNK_SIZE",
    "Phase11ExportConflictError",
    "Phase11ExportError",
    "Phase11ExportNotFoundError",
    "Phase11ExportValidationError",
    "reconcile_stale_result_export_events",
    "stream_phase11_result_export_csv",
)
