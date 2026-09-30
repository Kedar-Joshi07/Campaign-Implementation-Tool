"""Recovery Prompt 10: compact targeting-catalog lifecycle correctness."""

# ruff: noqa: F401, F811 - imported pytest fixtures are intentionally injected.

from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.services import potential_customer_search_submission_service as submission
from app.services import targeting_option_catalog_service as catalog_service
from app.services.source_currentness_service import reconcile_source_currentness
from app.services.targeting_option_catalog_service import (
    get_or_build_targeting_catalog,
    get_targeting_catalog,
)
from tests.test_phase11_business_search_form import request_payload
from tests.test_phase9_business_targeting import client, database_path


def _record_import(
    path, dataset_name: str, checksum: str | None, *, suffix: str,
) -> None:
    with get_connection(path, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES (?,?,?,?, 'COMPLETED',1,1,0,?)""",
            (
                dataset_name,
                f"data/{dataset_name}-{suffix}.csv",
                f"2026-09-29T10:00:{suffix}Z",
                f"2026-09-29T10:01:{suffix}Z",
                checksum,
            ),
        )


def test_a_to_b_to_a_repromotes_exact_catalog_without_large_rescan(
    database_path, monkeypatch,
) -> None:
    first = get_or_build_targeting_catalog(database_path)
    _record_import(database_path, "demographics", "b" * 64, suffix="01")
    second = get_or_build_targeting_catalog(database_path)
    assert second["catalog_version"] != first["catalog_version"]

    _record_import(database_path, "demographics", None, suffix="02")
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context_options",
        lambda *_: pytest.fail("existing A catalog must not rescan campaign options"),
    )
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_targeting_options",
        lambda *_: pytest.fail("existing A catalog must not scan demographics"),
    )
    returned = get_or_build_targeting_catalog(database_path)

    assert returned["catalog_version"] == first["catalog_version"]
    assert returned["catalog_created_at"] == first["catalog_created_at"]
    with get_connection(database_path) as connection:
        current = connection.execute(
            """SELECT catalog_version FROM targeting_option_catalogs
               WHERE is_current=1"""
        ).fetchall()
    assert [str(row[0]) for row in current] == [first["catalog_version"]]


def test_concurrent_catalog_build_rechecks_sources_before_promotion(
    database_path, monkeypatch,
) -> None:
    first = get_or_build_targeting_catalog(database_path)
    _record_import(database_path, "demographics", "c" * 64, suffix="03")
    scan_started = Event()
    allow_scan = Event()
    original = CampaignTargetingContextRepository.fetch_context_options

    def delayed_context(repository):
        scan_started.set()
        assert allow_scan.wait(timeout=10)
        return original(repository)

    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context_options",
        delayed_context,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(get_or_build_targeting_catalog, database_path)
        assert scan_started.wait(timeout=10)
        _record_import(database_path, "demographics", None, suffix="04")
        allow_scan.set()
        result = future.result(timeout=20)

    assert result["catalog_version"] == first["catalog_version"]
    with get_connection(database_path) as connection:
        current = connection.execute(
            """SELECT catalog_version FROM targeting_option_catalogs
               WHERE is_current=1"""
        ).fetchall()
    assert [str(row[0]) for row in current] == [first["catalog_version"]]


def test_existing_catalog_repairs_missing_or_wrong_product_rows_atomically(
    database_path, monkeypatch,
) -> None:
    catalog = get_or_build_targeting_catalog(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """UPDATE targeting_product_catalog SET product_name='Wrong label'
               WHERE catalog_version=? AND product_id='PRD-1'""",
            (catalog["catalog_version"],),
        )
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context_options",
        lambda *_: pytest.fail("product repair must use immutable parent JSON"),
    )
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_targeting_options",
        lambda *_: pytest.fail("product repair must not scan demographics"),
    )

    returned = get_or_build_targeting_catalog(database_path)
    assert returned["catalog_version"] == catalog["catalog_version"]
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT product_name,product_category
               FROM targeting_product_catalog
               WHERE catalog_version=? AND product_id='PRD-1'""",
            (catalog["catalog_version"],),
        ).fetchone()
        current_count = int(connection.execute(
            "SELECT COUNT(*) FROM targeting_option_catalogs WHERE is_current=1"
        ).fetchone()[0])
    assert tuple(row) == ("Savings", "Banking")
    assert current_count == 1


def test_warm_catalog_load_uses_only_compact_tables(database_path, monkeypatch) -> None:
    expected = get_or_build_targeting_catalog(database_path)
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_context_options",
        lambda *_: pytest.fail("warm options must not scan campaign_sales"),
    )
    monkeypatch.setattr(
        CampaignTargetingContextRepository,
        "fetch_targeting_options",
        lambda *_: pytest.fail("warm options must not scan demographics"),
    )
    monkeypatch.setattr(
        catalog_service,
        "_replace_product_catalog",
        lambda *_: pytest.fail("valid warm products must not be rebuilt"),
    )
    started = time.perf_counter()
    versions = {
        get_or_build_targeting_catalog(database_path)["catalog_version"]
        for _ in range(10)
    }
    elapsed = time.perf_counter() - started
    assert versions == {expected["catalog_version"]}
    assert elapsed < 2.0


def test_startup_reconciliation_repairs_missed_post_import_refresh(database_path) -> None:
    first = get_or_build_targeting_catalog(database_path)
    _record_import(database_path, "campaign_sales", "d" * 64, suffix="05")
    with get_connection(database_path) as connection:
        assert connection.execute(
            """SELECT catalog_version FROM targeting_option_catalogs
               WHERE is_current=1"""
        ).fetchone()[0] == first["catalog_version"]

    outcome = reconcile_source_currentness(database_path)
    assert outcome["catalog_version"] != first["catalog_version"]
    assert get_targeting_catalog(
        database_path, outcome["catalog_version"]
    )["is_current"] is True


def test_live_options_version_is_accepted_by_live_submission(
    client, monkeypatch,
) -> None:
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)
    options = client.get("/api/potential-customer-search/options")
    assert options.status_code == 200
    payload = request_payload() | {
        "propensity_bucket": "0.70",
        "catalog_version": options.json()["catalog_version"],
    }
    created = client.post("/api/potential-customer-search/runs", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["propensity_bucket"] == "0.70"


def test_historical_result_uses_its_recorded_product_catalog(
    client, database_path, monkeypatch,
) -> None:
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)
    first_options = client.get("/api/potential-customer-search/options").json()
    created = client.post(
        "/api/potential-customer-search/runs", json=request_payload()
    )
    assert created.status_code == 201, created.text

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """UPDATE campaign_sales
               SET product_id='PRD-2',product_name='Current Account',
                   product_category='Banking'"""
        )
    _record_import(database_path, "campaign_sales", "e" * 64, suffix="06")
    second = get_or_build_targeting_catalog(database_path)
    assert second["catalog_version"] != first_options["catalog_version"]

    history = client.get("/api/potential-customer-search/results?limit=20")
    assert history.status_code == 200, history.text
    saved = next(
        row for row in history.json()
        if row["search_run_id"] == created.json()["search_run_id"]
    )
    assert saved["selected_products"] == [{
        "product_id": "PRD-1",
        "product_name": "Savings",
        "product_category": "Banking",
    }]


def test_schema_28_repairs_duplicate_current_rows_before_unique_index(tmp_path) -> None:
    path = initialize_database(tmp_path / "catalog-upgrade.db")
    with get_connection(path, write=True) as connection:
        connection.execute("DROP INDEX idx_targeting_option_catalog_current")
        payload = json.dumps({})
        connection.executemany(
            """INSERT INTO targeting_option_catalogs (
                   catalog_version,context_options_json,targeting_options_json,
                   created_at,is_current
               ) VALUES (?,?,?,?,1)""",
            (
                ("a" * 64, payload, payload, "2026-09-29T10:00:00Z"),
                ("b" * 64, payload, payload, "2026-09-29T11:00:00Z"),
            ),
        )
        connection.execute(
            "UPDATE app_metadata SET value='27' WHERE key='schema_version'"
        )

    initialize_database(path)
    with get_connection(path) as connection:
        current = connection.execute(
            """SELECT catalog_version FROM targeting_option_catalogs
               WHERE is_current=1"""
        ).fetchall()
        indexes = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA index_list(targeting_option_catalogs)"
            ).fetchall()
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE targeting_option_catalogs SET is_current=1 WHERE catalog_version=?",
                ("a" * 64,),
            )
    assert [str(row[0]) for row in current] == ["b" * 64]
    assert "idx_targeting_option_catalog_current" in indexes
