"""Step 13 governed omnichannel result-snapshot export coverage."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.main import app
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services import phase11_export_service as export_service
from app.services.omnichannel_profile_contracts import (
    OMNICHANNEL_PROFILE_REGISTRY,
    get_omnichannel_profile,
)
from app.services.phase11_result_snapshot_service import materialize_result_snapshot
from tests.test_phase11_search_result_registry import _complete, _search, case


class NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


class DisconnectOnSecondCheck:
    def __init__(self) -> None:
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls >= 2


async def _consume(response) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
    return b"".join(chunks)


def _source_rows() -> list[dict[str, object]]:
    base = {
        "age": 40,
        "state": "Ohio",
        "individual_yearly_income": 70000,
        "family_member_count": 2,
        "number_of_children_in_family": 1,
        "number_of_adults_in_family": 1,
        "family_yearly_income": 90000,
        "email_contactable": 0,
        "direct_mail_contactable": 0,
        "sms_opt_in": 0,
        "whatsapp_opt_in": 0,
        "telemarketing_contactable": 0,
        "do_not_call": 0,
        "push_opt_in": 0,
        "advertising_targetable": 0,
        "onsite_targetable": 0,
    }
    return [
        base | {
            "person_id": "P1", "first_name": "=CMD()",
            "last_name": 'Zoë, "Q"\nLine', "email": " Person@Example.COM ",
            "phone_number": "(202) 555-0123", "address_line_1": "+1 Main,\nRoad",
            "address_line_2": 'Suite "2"', "city": "München", "postal_code": "@44101",
            "email_contactable": 1, "direct_mail_contactable": 1,
            "sms_opt_in": 1, "whatsapp_opt_in": 1,
            "telemarketing_contactable": 1, "push_token": "pt_" + "a" * 32,
            "push_opt_in": 1,
            "advertising_id": "123E4567-E89B-42D3-A456-426614174000",
            "advertising_targetable": 1, "web_visitor_id": "wv_" + "b" * 32,
            "onsite_targetable": 1,
        },
        base | {
            "person_id": "P2", "first_name": "Blank permissions",
            "email": "second@example.com", "phone_number": "invalid",
            "address_line_1": "2 Main", "city": "Columbus", "postal_code": "43004",
        },
        base | {
            "person_id": "P3", "first_name": "-minus", "last_name": "@handle",
            "email": "invalid", "phone_number": "303-555-0199",
            "address_line_1": "3 Main", "city": "Cleveland", "postal_code": "44102",
            "direct_mail_contactable": 1, "whatsapp_opt_in": 1, "do_not_call": 1,
            "push_token": "pt_" + "c" * 32,
            "advertising_id": "223E4567-E89B-42D3-A456-426614174001",
            "advertising_targetable": 1, "web_visitor_id": "wv_" + "d" * 32,
            "onsite_targetable": 1,
        },
        base | {"person_id": "P4", "first_name": "No identifiers"},
    ]


def _members():
    for index, person_id in enumerate(("P1", "P2", "P3", "P4"), 1):
        yield {
            "person_id": person_id,
            "propensity_score": 1.0 - index / 10,
            "percentile_bucket": index,
            "decile": 1,
            "rank_band": "ELITE" if index == 1 else "VERY_HIGH",
        }


@pytest.fixture
def export_case(case):
    database_path, ids, _, repository = case
    for row in _source_rows():
        columns = tuple(row)
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                f"INSERT INTO demographics ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )

    first_run = _search(case)
    run = repository.fetch_search_run(first_run)
    generation = Phase10IntelligenceRepository(database_path).fetch_generation(
        ids["generation_id"]
    )
    snapshot_id = materialize_result_snapshot(
        database_path,
        run,
        generation,
        "9" * 64,
        None,
        _members(),
        project_root=database_path.parent,
    )
    _complete(case, first_run, snapshot_id)
    runs = {repository.fetch_search_run(first_run)["export_profile"]: first_run}
    for profile in OMNICHANNEL_PROFILE_REGISTRY.values():
        if profile.export_profile in runs:
            continue
        run_id = _search(
            case,
            delivery_channel=profile.channel_code,
            export_profile=profile.export_profile,
        )
        _complete(case, run_id, snapshot_id, "EXACT_RESULT_REUSE")
        runs[profile.export_profile] = run_id
    return database_path, repository, snapshot_id, runs


EXPECTED_DELIVERABLE = {
    "EMAIL_CONTACT_V1": 1,
    "DIRECT_MAIL_CONTACT_V1": 2,
    "SMS_CONTACT_V1": 1,
    "WHATSAPP_CONTACT_V1": 2,
    "TELEMARKETING_CONTACT_V1": 1,
    "PAID_SOCIAL_AUDIENCE_V1": 3,
    "PAID_SEARCH_AUDIENCE_V1": 3,
    "MOBILE_PUSH_CONTACT_V1": 1,
    "DISPLAY_AUDIENCE_V1": 2,
    "WEBSITE_AUDIENCE_V1": 2,
}


@pytest.mark.parametrize("profile_name", tuple(OMNICHANNEL_PROFILE_REGISTRY))
def test_every_profile_streams_exact_header_counts_checksum_and_privacy(
    export_case, profile_name,
):
    path, repository, snapshot_id, runs = export_case
    run_id = runs[profile_name]
    response = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=run_id,
        request=NeverDisconnected(),
        project_root=path.parent,
    )
    body = asyncio.run(_consume(response))
    profile = get_omnichannel_profile(profile_name)
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))

    assert response.headers["x-export-profile"] == profile_name
    assert response.headers["cache-control"] == "no-store"
    assert f"potential_customers_{run_id}_{profile_name.lower()}.csv" in response.headers[
        "content-disposition"
    ]
    assert tuple(rows[0]) == profile.output_columns
    assert len(rows) == EXPECTED_DELIVERABLE[profile_name]
    for row in rows:
        assert tuple(row) == profile.output_columns
        assert not set(profile.prohibited_fields).intersection(row)

    event = repository.list_export_events(run_id)[0]
    assert event["snapshot_id"] == snapshot_id
    assert event["status"] == "COMPLETED"
    assert event["selected_count"] == 4
    assert event["deliverable_count"] == EXPECTED_DELIVERABLE[profile_name]
    assert event["undeliverable_count"] == 4 - EXPECTED_DELIVERABLE[profile_name]
    assert event["row_count"] == event["deliverable_count"]
    assert event["csv_sha256"] == hashlib.sha256(body).hexdigest()
    assert event["currentness_state"] == "CURRENT"

    if profile_name in {"PAID_SOCIAL_AUDIENCE_V1", "PAID_SEARCH_AUDIENCE_V1"}:
        assert "email" not in rows[0] and "phone_number" not in rows[0]
        assert all(
            not value or len(value) == 64 and value == value.lower()
            for row in rows for value in (row["sha256_email"], row["sha256_phone"])
        )


def test_csv_edge_cases_normalization_and_formula_injection(export_case):
    path, _, _, runs = export_case
    email = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=runs["EMAIL_CONTACT_V1"],
        request=NeverDisconnected(),
        project_root=path.parent,
    )
    email_rows = list(csv.DictReader(io.StringIO(asyncio.run(_consume(email)).decode("utf-8"))))
    assert email_rows == [{
        "person_id": "P1", "propensity_score": "0.9", "percentile_bucket": "1",
        "decile": "1", "rank_band": "ELITE", "first_name": "'=CMD()",
        "last_name": 'Zoë, "Q"\nLine', "email": "person@example.com",
    }]

    direct = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=runs["DIRECT_MAIL_CONTACT_V1"],
        request=NeverDisconnected(),
        project_root=path.parent,
    )
    direct_rows = list(
        csv.DictReader(io.StringIO(asyncio.run(_consume(direct)).decode("utf-8")))
    )
    assert direct_rows[0]["address_line_1"] == "'+1 Main,\nRoad"
    assert direct_rows[0]["postal_code"] == "'@44101"
    assert direct_rows[0]["last_name"] == 'Zoë, "Q"\nLine'
    assert direct_rows[1]["first_name"] == "'-minus"
    assert direct_rows[1]["last_name"] == "'@handle"

    sms = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=runs["SMS_CONTACT_V1"],
        request=NeverDisconnected(),
        project_root=path.parent,
    )
    sms_rows = list(
        csv.DictReader(io.StringIO(asyncio.run(_consume(sms)).decode("utf-8")))
    )
    assert sms_rows[0]["phone_number"] == "'+12025550123"


def test_disconnect_records_aborted_audit_without_pii_snapshot(export_case):
    path, repository, snapshot_id, runs = export_case
    before_snapshots = repository.fetch_snapshot(snapshot_id)
    response = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=runs["EMAIL_CONTACT_V1"],
        request=DisconnectOnSecondCheck(),
        project_root=path.parent,
    )
    body = asyncio.run(_consume(response))
    assert body.decode("utf-8").splitlines() == [
        "person_id,propensity_score,percentile_bucket,decile,rank_band,first_name,last_name,email"
    ]
    event = repository.list_export_events(runs["EMAIL_CONTACT_V1"])[0]
    assert event["status"] == "ABORTED" and event["row_count"] == 0
    assert event["csv_sha256"] is None and event["safe_error_message"]
    assert repository.fetch_snapshot(snapshot_id) == before_snapshots
    with get_connection(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM campaign_result_snapshots").fetchone()[0] == 1
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%contact%export%snapshot%'"
        ).fetchall()


def test_consumer_closing_stream_records_aborted_audit(export_case):
    path, repository, _, runs = export_case
    run_id = runs["DIRECT_MAIL_CONTACT_V1"]
    response = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=run_id,
        request=NeverDisconnected(),
        project_root=path.parent,
    )

    async def consume_header_then_close() -> bytes:
        iterator = response.body_iterator
        header = await anext(iterator)
        await iterator.aclose()
        return header

    header = asyncio.run(consume_header_then_close())
    assert header.startswith(b"person_id,")
    event = repository.list_export_events(run_id)[0]
    assert event["status"] == "ABORTED"
    assert event["row_count"] == 0 and event["safe_error_message"]


def test_source_drift_fails_audit_and_marks_snapshot_stale(export_case):
    path, repository, snapshot_id, runs = export_case
    response = export_service.stream_phase11_result_export_csv(
        path,
        search_run_id=runs["EMAIL_CONTACT_V1"],
        request=NeverDisconnected(),
        project_root=path.parent,
    )
    with get_connection(path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','changed.csv','2026-09-17T00:00:00Z',
                '2026-09-17T00:00:01Z','COMPLETED',4,4,0,?)
            """,
            ("e" * 64,),
        )
    with pytest.raises(export_service.Phase11ExportConflictError):
        asyncio.run(_consume(response))
    event = repository.list_export_events(runs["EMAIL_CONTACT_V1"])[0]
    assert event["status"] == "FAILED" and event["currentness_state"] == "STALE"
    assert event["row_count"] == 0 and event["safe_error_message"]
    assert repository.fetch_snapshot(snapshot_id)["currentness_state"] == "STALE"


def test_stale_running_export_recovery_is_bounded_and_aggregate_only(export_case):
    path, repository, snapshot_id, runs = export_case
    run_id = runs["EMAIL_CONTACT_V1"]
    event_id = repository.create_export_event(
        search_run_id=run_id,
        snapshot_id=snapshot_id,
        export_profile="EMAIL_CONTACT_V1",
        selected_count=4,
        deliverable_count=1,
        undeliverable_count=3,
        timestamp="2026-09-10T00:00:00Z",
    )
    assert repository.reconcile_stale_export_events(
        stale_started_at_max="2026-09-10T01:00:00Z",
        timestamp="2026-09-10T02:00:00Z",
        limit=1,
    ) == 1
    event = repository.fetch_export_event(event_id)
    assert event["status"] == "ABORTED"
    assert event["row_count"] == 0 and event["csv_sha256"] is None
    assert event["selected_count"] == 4 and event["deliverable_count"] == 1
    assert event["undeliverable_count"] == 3 and event["safe_error_message"]


def test_unavailable_profile_and_incomplete_or_missing_run_return_safe_errors(
    export_case, case, monkeypatch,
):
    path, repository, _, runs = export_case
    monkeypatch.setattr(export_service, "_available_demographic_fields", lambda _: frozenset())
    with pytest.raises(export_service.Phase11ExportConflictError, match="identifier source"):
        export_service.stream_phase11_result_export_csv(
            path,
            search_run_id=runs["MOBILE_PUSH_CONTACT_V1"],
            request=NeverDisconnected(),
            project_root=path.parent,
        )
    assert repository.list_export_events(runs["MOBILE_PUSH_CONTACT_V1"]) == []
    queued = _search(case)
    with pytest.raises(export_service.Phase11ExportConflictError, match="not completed"):
        export_service.stream_phase11_result_export_csv(
            path, search_run_id=queued, request=NeverDisconnected(), project_root=path.parent
        )
    with pytest.raises(export_service.Phase11ExportNotFoundError):
        export_service.stream_phase11_result_export_csv(
            path, search_run_id=99999, request=NeverDisconnected(), project_root=path.parent
        )


def test_download_api_streams_governed_file_and_safe_statuses(
    export_case, case, monkeypatch,
):
    path, repository, _, runs = export_case
    monkeypatch.setattr(export_service, "DEFAULT_PROJECT_ROOT", path.parent)
    monkeypatch.setattr("app.main.DATABASE_PATH", path)
    app.dependency_overrides[get_database_path] = lambda: path
    try:
        with TestClient(app) as client:
            run_id = runs["PAID_SOCIAL_AUDIENCE_V1"]
            response = client.get(
                f"/api/potential-customer-search/runs/{run_id}/download"
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/csv")
            assert response.headers["x-export-profile"] == "PAID_SOCIAL_AUDIENCE_V1"
            header = next(csv.reader(io.StringIO(response.text)))
            assert "email" not in header and "phone_number" not in header
            assert header[-2:] == ["sha256_email", "sha256_phone"]
            assert repository.list_export_events(run_id)[0]["status"] == "COMPLETED"
            queued = _search(case)
            assert client.get(
                f"/api/potential-customer-search/runs/{queued}/download"
            ).status_code == 409
            assert client.get(
                "/api/potential-customer-search/runs/99999/download"
            ).status_code == 404
            assert client.get(
                "/api/potential-customer-search/runs/0/download"
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_engine_is_chunked_and_does_not_persist_contact_rows():
    source = (Path(__file__).resolve().parents[1] / "app/services/phase11_export_service.py").read_text(
        encoding="utf-8"
    )
    assert "EXPORT_JOIN_CHUNK_SIZE = 250" in source
    assert "list(reader)" not in source
    assert "campaign_result_export_events" not in source
    assert "INSERT INTO" not in source
