from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_export_repository import (
    CampaignExportRepository,
    EXPORT_CURRENTNESS_STATE_UNKNOWN,
    EXPORT_RECOVERY_INTERRUPTED_MESSAGE,
)
from app.services.audience_preparation_service import classify_percentile_bucket
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_service import (
    CampaignServiceConflictError,
    _classify_percentile_bucket_from_lookup,
    _compile_boundary_lookup,
    create_campaign,
    finalize_campaign,
    list_campaign_export_events,
    reconcile_stale_campaign_export_events,
    stream_campaign_export_csv,
)
from app.services.saved_audience_service import save_audience
from tests.test_saved_audience_service import _seed_fixture


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def _set_email_contacts(database_path: Path, contacts: dict[str, tuple[str, str, str]]) -> None:
    with get_connection(database_path, write=True) as connection:
        for person_id, values in contacts.items():
            first_name, last_name, email = values
            connection.execute(
                """
                UPDATE demographics
                SET first_name = ?, last_name = ?, email = ?
                WHERE person_id = ?
                """,
                (first_name, last_name, email, person_id),
            )


def _set_direct_mail_contacts(database_path: Path, contacts: dict[str, tuple[str, str, str, str, str, str, str]]) -> None:
    with get_connection(database_path, write=True) as connection:
        for person_id, values in contacts.items():
            (
                first_name,
                last_name,
                address_line_1,
                address_line_2,
                city,
                state,
                postal_code,
            ) = values
            connection.execute(
                """
                UPDATE demographics
                SET
                    first_name = ?,
                    last_name = ?,
                    address_line_1 = ?,
                    address_line_2 = ?,
                    city = ?,
                    state = ?,
                    postal_code = ?
                WHERE person_id = ?
                """,
                (
                    first_name,
                    last_name,
                    address_line_1,
                    address_line_2,
                    city,
                    state,
                    postal_code,
                    person_id,
                ),
            )


def _create_finalized_campaign(
    database_path: Path,
    *,
    channel: str,
    selection: dict[str, Any],
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    saved = save_audience(
        database_path,
        {
            "audience_name": f"Hardening {channel}",
            "description": "Campaign export hardening fixture",
            "scoring_run_id": scoring_run_id,
            "filters": filters or {},
            "selection": selection,
            "include_profile_snapshot": True,
        },
    )

    created = create_campaign(
        database_path,
        {
            "campaign_name": f"Hardening {channel} Campaign",
            "description": "Campaign export hardening fixture",
            "channel": channel,
            "planned_launch_date": "2026-12-30",
            "saved_audience_id": int(saved["audience_id"]),
        },
    )
    finalized = finalize_campaign(database_path, campaign_id=int(created["campaign_id"]))
    return {
        "saved": saved,
        "created": created,
        "finalized": finalized,
    }


def _read_csv_rows(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _read_stream_with_mid_export_mutation(
    database_path: Path,
    campaign_id: int,
    *,
    mutate_after_chunks: int,
) -> bytes:
    request = _ConnectedRequest()
    response = stream_campaign_export_csv(
        database_path,
        campaign_id=campaign_id,
        acknowledge_pii=True,
        request=request,  # type: ignore[arg-type]
    )

    async def _consume() -> bytes:
        chunks: list[bytes] = []
        chunk_count = 0
        mutated = False

        async for chunk in response.body_iterator:
            chunks.append(chunk)
            chunk_count += 1

            if not mutated and chunk_count >= mutate_after_chunks:
                mutated = True
                with get_connection(database_path, write=True) as connection:
                    connection.execute(
                        """
                        INSERT INTO data_import_runs (
                            dataset_name,
                            source_path,
                            started_at,
                            completed_at,
                            status,
                            rows_read,
                            rows_inserted,
                            rows_rejected,
                            source_checksum
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "demographics",
                            "demographics_mid_export_drift.csv",
                            "2026-12-30T00:00:00Z",
                            "2026-12-30T00:05:00Z",
                            "COMPLETED",
                            6,
                            6,
                            0,
                            "f" * 64,
                        ),
                    )

        return b"".join(chunks)

    return asyncio.run(_consume())


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "campaign-export-hardening.db"
    initialize_database(path)
    return path


def test_boundary_lookup_binary_matches_reference_semantics(database_path: Path) -> None:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)

    with get_connection(database_path) as connection:
        boundaries = [
            dict(row)
            for row in connection.execute(
                """
                SELECT percentile_bucket, boundary_score, boundary_person_id
                FROM audience_rank_boundaries
                WHERE scoring_run_id = ?
                ORDER BY percentile_bucket ASC
                """,
                (scoring_run_id,),
            ).fetchall()
        ]

    lookup, binary_safe = _compile_boundary_lookup(boundaries)
    assert binary_safe is True

    random = Random(42)
    for _ in range(500):
        score = random.random()
        person_id = f"PER_{random.randint(1, 999999):06d}"
        expected = classify_percentile_bucket(score, person_id, boundaries)
        actual = _classify_percentile_bucket_from_lookup(
            score,
            person_id,
            lookup,
            binary_safe=binary_safe,
        )
        assert actual == expected


def test_mid_export_drift_keeps_current_file_consistent_and_blocks_future_exports(database_path: Path) -> None:
    fixture = _create_finalized_campaign(
        database_path,
        channel="EMAIL",
        selection={"mode": "TOP_N", "target_count": 4},
    )
    _set_email_contacts(
        database_path,
        {
            "PER_000001": ("Ava", "North", "ava@example.com"),
            "PER_000002": ("Ben", "West", "ben@example.com"),
            "PER_000003": ("Cara", "East", "cara@example.com"),
            "PER_000004": ("Drew", "South", "drew@example.com"),
        },
    )
    campaign_id = int(fixture["created"]["campaign_id"])

    content = _read_stream_with_mid_export_mutation(
        database_path,
        campaign_id,
        mutate_after_chunks=2,
    )
    rows = _read_csv_rows(content)
    assert len(rows) == 4

    events = list_campaign_export_events(database_path, campaign_id=campaign_id, limit=5)
    latest = events[0]
    assert latest["status"] == "COMPLETED"
    assert latest["source_changed_during_export"] is True
    assert latest["completion_currentness_state"] == "STALE"
    assert latest["export_snapshot_contract_version"] == "1"
    assert isinstance(latest["start_provenance_sha256"], str)
    assert len(str(latest["start_provenance_sha256"])) == 64

    with pytest.raises(CampaignServiceConflictError):
        stream_campaign_export_csv(
            database_path,
            campaign_id=campaign_id,
            acknowledge_pii=True,
            request=_ConnectedRequest(),  # type: ignore[arg-type]
        )


def test_email_deliverability_reconciliation_rules(database_path: Path) -> None:
    fixture = _create_finalized_campaign(
        database_path,
        channel="EMAIL",
        selection={"mode": "TOP_N", "target_count": 3},
    )
    _set_email_contacts(
        database_path,
        {
            "PER_000001": ("Valid", "Email", "valid@example.com"),
            "PER_000002": ("Blank", "Email", "   "),
            "PER_000003": ("Bad", "Email", "broken@email"),
        },
    )

    campaign_id = int(fixture["created"]["campaign_id"])
    response = stream_campaign_export_csv(
        database_path,
        campaign_id=campaign_id,
        acknowledge_pii=True,
        request=_ConnectedRequest(),  # type: ignore[arg-type]
    )

    async def _collect() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    rows = _read_csv_rows(asyncio.run(_collect()))
    assert len(rows) == 1

    events = list_campaign_export_events(database_path, campaign_id=campaign_id, limit=5)
    latest = events[0]
    assert latest["selected_count"] == 3
    assert latest["deliverable_count"] == 1
    assert latest["undeliverable_count"] == 2
    assert latest["row_count"] == 1
    assert latest["selected_count"] == int(fixture["created"]["saved_audience_resolved_count"])


def test_direct_mail_deliverability_reconciliation_rules(database_path: Path) -> None:
    fixture = _create_finalized_campaign(
        database_path,
        channel="DIRECT_MAIL",
        selection={"mode": "TOP_N", "target_count": 5},
    )
    _set_direct_mail_contacts(
        database_path,
        {
            "PER_000001": ("", "", "101 Main St", "Apt 3", "Austin", "TX", "73301"),
            "PER_000002": ("", "", "", "", "Austin", "TX", "73301"),
            "PER_000003": ("", "", "102 Main St", "", "", "TX", "73301"),
            "PER_000004": ("", "", "103 Main St", "", "Austin", "", "73301"),
            "PER_000005": ("", "", "104 Main St", "", "Austin", "TX", ""),
        },
    )

    campaign_id = int(fixture["created"]["campaign_id"])
    response = stream_campaign_export_csv(
        database_path,
        campaign_id=campaign_id,
        acknowledge_pii=True,
        request=_ConnectedRequest(),  # type: ignore[arg-type]
    )

    async def _collect() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    rows = _read_csv_rows(asyncio.run(_collect()))
    assert len(rows) == 1

    events = list_campaign_export_events(database_path, campaign_id=campaign_id, limit=5)
    latest = events[0]
    assert latest["selected_count"] == 5
    assert latest["deliverable_count"] == 1
    assert latest["undeliverable_count"] == 4
    assert latest["row_count"] == 1


def test_csv_formula_protection_and_utf8_escaping(database_path: Path) -> None:
    fixture = _create_finalized_campaign(
        database_path,
        channel="EMAIL",
        selection={"mode": "TOP_N", "target_count": 3},
    )
    _set_email_contacts(
        database_path,
        {
            "PER_000001": ("=SUM(1,1)", "Comma,Name", "safe1@example.com"),
            "PER_000002": ("  +PLUS", "Quote \"Name\"", "safe2@example.com"),
            "PER_000003": ("-NEG", "Line\nBreak Ω", "safe3@example.com"),
        },
    )

    campaign_id = int(fixture["created"]["campaign_id"])
    response = stream_campaign_export_csv(
        database_path,
        campaign_id=campaign_id,
        acknowledge_pii=True,
        request=_ConnectedRequest(),  # type: ignore[arg-type]
    )

    async def _collect() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    csv_bytes = asyncio.run(_collect())
    csv_text = csv_bytes.decode("utf-8")
    rows = _read_csv_rows(csv_bytes)

    assert len(rows) == 3
    assert rows[0]["first_name"].startswith("'=")
    assert rows[1]["first_name"].startswith("'  +")
    assert rows[2]["first_name"].startswith("'-")
    assert "Ω" in csv_text
    assert '"Comma,Name"' in csv_text
    assert '"Quote ""Name"""' in csv_text

    with get_connection(database_path) as connection:
        original = connection.execute(
            "SELECT first_name FROM demographics WHERE person_id = 'PER_000001'"
        ).fetchone()
    assert original is not None
    assert str(original["first_name"]).startswith("=")


def test_startup_reconciliation_marks_old_started_events_aborted(database_path: Path) -> None:
    fixture = _create_finalized_campaign(
        database_path,
        channel="EMAIL",
        selection={"mode": "TOP_N", "target_count": 1},
    )
    campaign_id = int(fixture["created"]["campaign_id"])

    repository = CampaignExportRepository(database_path)
    repository.create_started_event(
        campaign_id=campaign_id,
        export_profile="EMAIL_CONTACT_V1",
        started_at="2020-01-01T00:00:00Z",
        export_snapshot_contract_version="1",
        start_provenance_sha256="a" * 64,
    )
    repository.create_started_event(
        campaign_id=campaign_id,
        export_profile="EMAIL_CONTACT_V1",
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        export_snapshot_contract_version="1",
        start_provenance_sha256="b" * 64,
    )

    reconciled = reconcile_stale_campaign_export_events(database_path)
    assert reconciled == 1

    events = list_campaign_export_events(database_path, campaign_id=campaign_id, limit=10)
    old_event = next(item for item in events if item["start_provenance_sha256"] == "a" * 64)
    new_event = next(item for item in events if item["start_provenance_sha256"] == "b" * 64)

    assert old_event["status"] == "ABORTED"
    assert old_event["safe_error_message"] == EXPORT_RECOVERY_INTERRUPTED_MESSAGE
    assert old_event["completion_currentness_state"] == EXPORT_CURRENTNESS_STATE_UNKNOWN

    assert new_event["status"] == "STARTED"
