"""Bounded Stage 14B-07 export and outcome isolation checks."""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
import os
import time
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database import schema as database_schema
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.schemas.potential_customer_search import PotentialCustomerSearchV3Request
from app.services import potential_customer_search_submission_service as submission
from app.services.buyer_similarity_search_orchestration_service import execute_similarity_search_safely
from app.services.buyer_similarity_selection_service import resolve_similarity_context
from app.services.buyer_similarity_result_service import (
    materialize_similarity_result,
    reconcile_similarity_result_publications,
)
from app.services.phase11_result_contracts import (
    Phase11RegistryValidationError, result_membership_columns,
)
from app.services.phase11_export_service import (
    Phase11ExportConflictError, stream_phase11_result_export_csv,
)
from app.services.phase11_feedback_service import (
    FeedbackConflictError, FeedbackValidationError, ingest_feedback, list_feedback,
)
from app.services.phase11_feedback_lineage_service import get_completed_search_lineage
from app.services.phase11_results_service import get_result_detail
from app.services.omnichannel_profile_contracts import (
    get_omnichannel_profile, get_omnichannel_profile_for_channel,
    project_profile_row,
)
from tests.test_buyer_similarity_cohort_service import _seed


class _Connected:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterHeader:
    def __init__(self) -> None:
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls >= 2


def test_schema_32_to_33_adds_only_separate_similarity_audit_and_feedback_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "migration.db"
    with monkeypatch.context() as patch:
        patch.setattr(database_schema, "CURRENT_SCHEMA_VERSION", 32)
        database_schema.initialize_database(database)
    with get_connection(database) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "32"
        before_legacy = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_result_export_events'"
        ).fetchone()[0]
    database_schema.initialize_database(database)
    with get_connection(database) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "33"
        assert connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_result_export_events'"
        ).fetchone()[0] == before_legacy
        assert connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='buyer_similarity_export_events'"
        ).fetchone() is not None
        assert "matched_product_id" in {
            row["name"] for row in connection.execute("PRAGMA table_info(campaign_feedback_outcomes)")
        }
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_schema_33_has_exact_current_table_set(tmp_path: Path) -> None:
    database = database_schema.initialize_database(tmp_path / "fresh33.db")
    with get_connection(database) as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert tables == set(database_schema.EXPECTED_TABLES)


async def _body(response) -> bytes:
    return b"".join([chunk async for chunk in response.body_iterator])


@pytest.fixture
def completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = _seed(tmp_path / "stage07.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    catalog.write_text("product_id,product_name,product_category\nP1,Product One,Category A\n", encoding="utf-8")
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','fixture.csv',?,?,'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
        connection.execute(
            "UPDATE demographics SET email=lower(person_id)||'@example.test', email_contactable=1"
        )
        connection.execute("UPDATE demographics SET email_contactable=0 WHERE person_id='PER0000'")
    options = submission.search_form_options(database)
    profile = get_omnichannel_profile_for_channel("EMAIL", selection_contract_version="3")
    context = {
        "product_ids": ["P1"], "campaign_types": [], "campaign_categories": [],
        "offer_types": [], "historical_campaign_channels": [], "campaign_channel": "EMAIL",
    }
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.50, campaign_name="Stage 07 bounded check",
        context=context, criteria={}, selection_mode="ALL_MATCHING",
        export_profile=profile.export_profile, catalog_version=options["catalog_version"],
    )
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: True)
    created = submission.submit_potential_customer_search(database, request)
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="stage07-fixture")
    outcome = execute_similarity_search_safely(
        database, created["search_run_id"], **fence.as_kwargs(), project_root=tmp_path,
    )
    assert outcome.status == "COMPLETED"
    run = repository.fetch_search_run(created["search_run_id"])
    assert run["selected_count"] > 0
    return database, tmp_path, run


def test_v3_profile_projections_are_versioned_and_contact_gated() -> None:
    legacy = get_omnichannel_profile("EMAIL_CONTACT_V1")
    analytical = get_omnichannel_profile("EMAIL_CONTACT_V2")
    contact_only = get_omnichannel_profile("EMAIL_CONTACT_CONTACT_ONLY_V2")
    assert legacy.output_columns[:5] == (
        "person_id", "propensity_score", "percentile_bucket", "decile", "rank_band",
    )
    assert "propensity_score" not in analytical.output_columns
    assert "buyer_similarity_score" in analytical.output_columns
    assert "buyer_similarity_score" not in contact_only.output_columns
    member = {
        "person_id": "PER0001", "buyer_similarity_score": .9000000000000001,
        "similarity_tier": "VERY_STRONG", "matched_product_id": "P1",
        "score_method_version": "BUYER_PROFILE_DISTANCE_V1", "feature_coverage": 1.0,
        "similarity_generation_id": 1, "email": " PERSON@example.test ",
        "email_contactable": 1,
    }
    assert project_profile_row(analytical.export_profile, member)["email"] == "person@example.test"
    assert project_profile_row(contact_only.export_profile, member)["email"] == "person@example.test"
    assert project_profile_row(analytical.export_profile, member | {"email_contactable": 0}) is None
    assert result_membership_columns("3")[:4] == (
        "person_id", "buyer_similarity_score", "similarity_tier", "matched_product_id",
    )
    with pytest.raises(Phase11RegistryValidationError):
        result_membership_columns("4")


def test_v3_download_reconciles_contact_exclusions_and_keeps_score_semantics(completed) -> None:
    database, root, run = completed
    response = stream_phase11_result_export_csv(
        database, search_run_id=run["search_run_id"], request=_Connected(), project_root=root,
    )
    assert response.headers["X-Export-Score-Semantics"] == "PRODUCT_BUYER_SIMILARITY"
    assert response.headers["X-Result-Membership-Contract-Version"] == "3"
    assert int(response.headers["X-Selected-Count"]) == run["selected_count"]
    assert int(response.headers["X-Excluded-Count"]) >= 1
    body = asyncio.run(_body(response)).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(body)))
    assert len(rows) == int(response.headers["X-Exportable-Count"])
    assert "propensity_score" not in rows[0]
    assert "buyer_similarity_score" in rows[0]
    assert all(row["email"].endswith("@example.test") for row in rows)
    with get_connection(database) as connection:
        snapshot = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
            (run["similarity_result_snapshot_id"],),
        ).fetchone()
    with gzip.open(root / snapshot["storage_uri"], "rt", encoding="utf-8") as source:
        immutable = {row["person_id"]: row for row in csv.DictReader(source)}
    assert all(row["buyer_similarity_score"] == immutable[row["person_id"]]["buyer_similarity_score"] for row in rows)
    with get_connection(database) as connection:
        audit = connection.execute("SELECT * FROM buyer_similarity_export_events").fetchone()
    assert audit["status"] == "COMPLETED"
    assert audit["row_count"] == len(rows)
    assert audit["selected_count"] == audit["deliverable_count"] + audit["undeliverable_count"]
    detail = get_result_detail(database, run["search_run_id"], project_root=root)
    assert detail["export_summary"]["deliverable_count"] == len(rows)
    assert detail["export_summary"]["undeliverable_count"] >= 1
    assert detail["similarity_explanation"]["sample_count"] == min(50, run["selected_count"])
    if run["selected_count"] >= 5:
        assert detail["similarity_explanation"]["feature_drivers"]
    else:
        assert detail["similarity_explanation"]["scope"] == "INSUFFICIENT_AGGREGATE_SUPPORT"
    assert "person_id" not in str(detail["similarity_explanation"])
    lineage = get_completed_search_lineage(database, run["search_run_id"])
    assert lineage["result"]["membership_contract_version"] == "3"
    assert lineage["result"]["snapshot_sha256"] == snapshot["snapshot_sha256"]
    assert lineage["delivery"]["export_event_ids"] == [audit["export_event_id"]]
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','changed.csv',?,?,'COMPLETED',10,10,0,?)""",
            ("2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "f" * 64),
        )
    with pytest.raises(Phase11ExportConflictError):
        stream_phase11_result_export_csv(
            database, search_run_id=run["search_run_id"], request=_Connected(), project_root=root,
        )


def test_v3_feedback_records_selection_lineage_without_probability_recalibration(completed) -> None:
    database, root, run = completed
    with get_connection(database) as connection:
        snapshot = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
            (run["similarity_result_snapshot_id"],),
        ).fetchone()
    with gzip.open(root / snapshot["storage_uri"], "rt", encoding="utf-8") as stream:
        people = [row["person_id"] for row in csv.DictReader(stream)]
    rows = [{"person_id": people[0], "outcome": 1, "outcome_at": "2026-01-01T00:00:00Z"}]
    accepted = ingest_feedback(
        database, run["search_run_id"], rows=rows, source_name="stage07",
        idempotency_key="stage07-feedback-1", project_root=root,
    )
    assert accepted["recalibration_status"] == "NOT_AVAILABLE"
    assert "no independently valid purchase-probability" in accepted["recalibration_reason"]
    assert len(list_feedback(database, run["search_run_id"])) == 1
    assert ingest_feedback(
        database, run["search_run_id"], rows=rows, source_name="stage07",
        idempotency_key="stage07-feedback-1", project_root=root,
    )["feedback_batch_id"] == accepted["feedback_batch_id"]
    with pytest.raises(FeedbackConflictError):
        ingest_feedback(database, run["search_run_id"], rows=rows,
                        source_name="stage07", idempotency_key="stage07-feedback-2", project_root=root)
    with pytest.raises(FeedbackValidationError):
        ingest_feedback(database, run["search_run_id"], rows=[rows[0] | {"person_id": "UNKNOWN"}],
                        source_name="stage07", idempotency_key="stage07-feedback-3", project_root=root)
    with get_connection(database) as connection:
        batch = connection.execute("SELECT * FROM campaign_feedback_batches").fetchone()
        outcome = connection.execute("SELECT * FROM campaign_feedback_outcomes").fetchone()
        decisions = connection.execute("SELECT COUNT(*) FROM feedback_retraining_decisions").fetchone()[0]
    assert batch["selection_contract_version"] == "3"
    assert batch["similarity_result_snapshot_id"] == snapshot["similarity_result_snapshot_id"]
    assert batch["similarity_snapshot_sha256"] == snapshot["snapshot_sha256"]
    assert outcome["matched_product_id"] == "P1"
    assert outcome["similarity_generation_id"] == snapshot["similarity_generation_id"]
    assert outcome["buyer_similarity_score"] is not None
    assert decisions == 0
    lineage = get_completed_search_lineage(database, run["search_run_id"])
    assert lineage["feedback_batch_ids"] == [accepted["feedback_batch_id"]]
    assert lineage["feedback_grouping"]["observation_count"] == 1
    assert lineage["feedback_grouping"]["independent_group_count"] == 1
    assert lineage["learning_status"] == "NOT_AVAILABLE_WITHOUT_INDEPENDENT_PROBABILITY_LINEAGE"


def test_v3_disconnect_is_audited_without_completed_contact_output(completed) -> None:
    database, root, run = completed
    response = stream_phase11_result_export_csv(
        database, search_run_id=run["search_run_id"],
        request=_DisconnectAfterHeader(), project_root=root,
    )
    asyncio.run(_body(response))
    with get_connection(database) as connection:
        event = connection.execute("SELECT * FROM buyer_similarity_export_events").fetchone()
    assert event["status"] == "ABORTED"
    assert event["csv_sha256"] is None
    assert event["currentness_state"] == "UNVERIFIED"


def test_v3_tampered_snapshot_fails_export_and_feedback_closed(completed) -> None:
    database, root, run = completed
    with get_connection(database) as connection:
        snapshot = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
            (run["similarity_result_snapshot_id"],),
        ).fetchone()
    membership = root / snapshot["storage_uri"]
    with gzip.open(membership, "rt", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    original_person = rows[0]["person_id"]
    rows[0]["buyer_similarity_score"] = ".9999999999999999"
    with gzip.open(membership, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(Phase11ExportConflictError):
        stream_phase11_result_export_csv(
            database, search_run_id=run["search_run_id"], request=_Connected(), project_root=root,
        )
    with pytest.raises(FeedbackConflictError):
        ingest_feedback(
            database, run["search_run_id"], rows=[{
                "person_id": original_person, "outcome": 1,
                "outcome_at": "2026-01-01T00:00:00Z",
            }], source_name="stage07", idempotency_key="stage07-tamper",
            project_root=root,
        )


def test_contact_only_v3_export_never_projects_analytical_or_probability_fields(completed) -> None:
    database, root, first = completed
    with get_connection(database) as connection:
        context = connection.execute(
            "SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?",
            (first["targeting_context_id"],),
        ).fetchone()[0]
    import json
    context = json.loads(context)
    context.pop("campaign_targeting_context_contract_version", None)
    options = submission.search_form_options(database)
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.50, campaign_name="Contact-only v3",
        context=context, criteria={}, selection_mode="ALL_MATCHING",
        export_profile="EMAIL_CONTACT_CONTACT_ONLY_V2",
        catalog_version=options["catalog_version"],
    )
    created = submission.submit_potential_customer_search(database, request)
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="stage07-contact-only")
    with pytest.raises(Phase11ExportConflictError):
        stream_phase11_result_export_csv(
            database, search_run_id=created["search_run_id"], request=_Connected(), project_root=root,
        )
    outcome = execute_similarity_search_safely(
        database, created["search_run_id"], **fence.as_kwargs(), project_root=root,
    )
    assert outcome.status == "COMPLETED"
    assert outcome.result_source == "EXACT_RESULT_REUSE"
    response = stream_phase11_result_export_csv(
        database, search_run_id=created["search_run_id"], request=_Connected(), project_root=root,
    )
    rows = list(csv.DictReader(io.StringIO(asyncio.run(_body(response)).decode("utf-8"))))
    assert rows
    assert tuple(rows[0]) == ("person_id", "first_name", "last_name", "email")
    with get_connection(database) as connection:
        snapshot_uri = connection.execute(
            "SELECT storage_uri FROM buyer_similarity_result_snapshots WHERE similarity_result_snapshot_id=?",
            (first["similarity_result_snapshot_id"],),
        ).fetchone()[0]
    with gzip.open(root / snapshot_uri, "rt", encoding="utf-8") as source:
        people = [row["person_id"] for row in csv.DictReader(source)]
    assert len(people) >= 2
    def evidence(person: str) -> dict[str, object]:
        return {"person_id": person, "outcome": 1,
                "outcome_at": "2026-01-01T00:00:00Z"}
    ingest_feedback(
        database, first["search_run_id"], rows=[evidence(people[0]), evidence(people[1])],
        source_name="stage07", idempotency_key="stage07-shared-1", project_root=root,
    )
    ingest_feedback(
        database, created["search_run_id"], rows=[evidence(people[1])],
        source_name="stage07", idempotency_key="stage07-shared-2", project_root=root,
    )
    lineage = get_completed_search_lineage(database, first["search_run_id"])
    assert lineage["feedback_grouping"]["observation_count"] == 3
    assert lineage["feedback_grouping"]["independent_group_count"] == 1
    with get_connection(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM feedback_retraining_decisions").fetchone()[0] == 0


def test_v3_publication_crash_leaves_no_completed_partial_and_reconciles_orphan(
    completed, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, root, first = completed
    with get_connection(database) as connection:
        import json
        context = json.loads(connection.execute(
            "SELECT campaign_context_json FROM campaign_targeting_contexts WHERE targeting_context_id=?",
            (first["targeting_context_id"],),
        ).fetchone()[0])
    context.pop("campaign_targeting_context_contract_version", None)
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.90, campaign_name="Publication crash check",
        context=context, criteria={}, selection_mode="ALL_MATCHING",
        export_profile="EMAIL_CONTACT_V2",
        catalog_version=submission.search_form_options(database)["catalog_version"],
    )
    created = submission.submit_potential_customer_search(database, request)
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="stage07-crash")
    repository.mark_processing(created["search_run_id"], **fence.as_kwargs())
    saved = repository.fetch_search_run(created["search_run_id"])
    resolution = resolve_similarity_context(database, context, project_root=root)
    original_replace = os.replace

    def crash_after_publish(source, destination):
        original_replace(source, destination)
        raise OSError("simulated interruption after file publication")

    monkeypatch.setattr("app.services.buyer_similarity_result_service.os.replace", crash_after_publish)
    with pytest.raises(OSError, match="simulated interruption"):
        materialize_similarity_result(
            database, saved, context, resolution, project_root=root,
            **fence.as_kwargs(),
        )
    monkeypatch.setattr("app.services.buyer_similarity_result_service.os.replace", original_replace)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_result_snapshots WHERE similarity_minimum=.90"
        ).fetchone()[0] == 0
    orphan = next((root / "artifacts" / "similarity_results").glob("snapshot_000002"))
    assert orphan.is_dir()
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    assert reconcile_similarity_result_publications(
        database, project_root=root, minimum_age_seconds=3600,
    ) == 1
    assert not orphan.exists()
    assert repository.fetch_search_run(created["search_run_id"])["status"] == "PROCESSING"
