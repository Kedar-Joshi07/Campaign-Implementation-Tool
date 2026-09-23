from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CURRENT_SCHEMA_VERSION, DEMOGRAPHIC_COLUMNS, EXPECTED_TABLES, MIGRATIONS,
    CAMPAIGN_SEARCH_RUN_COLUMNS, CAMPAIGN_RESULT_SNAPSHOT_COLUMNS,
    CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS, PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS,
    CAMPAIGN_SEARCH_RUN_RUNTIME_COLUMNS,
    initialize_database,
)
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.repositories.phase10_intelligence_repository import Phase10IntelligenceRepository
from app.services.phase11_result_contracts import (
    RESULT_MEMBERSHIP_COLUMNS, Phase11RegistryStateError, Phase11RegistryValidationError,
    canonical_metadata_json,
)
from tests.test_phase10_schema_registry_repository import (
    NOW, _create_version_fourteen_database, _generation_values, _seed_lineage,
)


LATER = "2026-09-13T10:00:10Z"
TABLES = {
    "campaign_search_runs": CAMPAIGN_SEARCH_RUN_COLUMNS,
    "campaign_result_snapshots": CAMPAIGN_RESULT_SNAPSHOT_COLUMNS,
    "campaign_result_export_events": CAMPAIGN_RESULT_EXPORT_EVENT_COLUMNS,
    "campaign_search_run_runtime": CAMPAIGN_SEARCH_RUN_RUNTIME_COLUMNS,
}


@pytest.fixture
def case(tmp_path: Path):
    database_path = tmp_path / "registry.db"
    ids = _seed_lineage(database_path)
    values = _generation_values(ids)
    ids["generation_id"] = Phase10IntelligenceRepository(database_path).insert_ready_generation(values)
    return database_path, ids, values, CampaignResultRegistryRepository(database_path)


def _search(case, **overrides):
    _, ids, values, repository = case
    arguments = dict(
        campaign_name="Business submission", targeting_context_id=ids["targeting_context_id"],
        modeling_context_sha256=values["modeling_context_sha256"],
        targeting_criteria={"states": ["Ohio"]}, filter_branches=[{"state": ["Ohio"]}],
        delivery_channel="EMAIL", timestamp=NOW,
    )
    arguments.update(overrides)
    return repository.create_search_run(**arguments)


def _snapshot(case, search_id: int, **overrides):
    _, ids, _, repository = case
    run = repository.fetch_search_run(search_id)
    arguments = dict(
        generation_id=ids["generation_id"], targeting_criteria_sha256=run["targeting_criteria_sha256"],
        filter_branches_sha256=run["filter_branches_sha256"], result_cache_key_sha256="f" * 64,
        resolved_count=10, storage_format="CSV_GZIP", storage_uri="artifacts/results/result_snapshot_000001/members.csv.gz",
        snapshot_sha256="e" * 64, selection_mode=run["selection_mode"], target_count=run["target_count"], timestamp=NOW,
    )
    arguments.update(overrides)
    return repository.register_snapshot(**arguments)


def _complete(case, search_id: int, snapshot_id: int, source="INTELLIGENCE_REUSE"):
    repository = case[3]
    repository.mark_processing(search_id)
    repository.complete_search_run(search_id, result_snapshot_id=snapshot_id, result_source=source, timestamp=LATER)


def test_fresh_schema_has_exact_non_pii_columns_indexes_and_foreign_keys(tmp_path: Path):
    path = initialize_database(tmp_path / "fresh.db")
    with get_connection(path, write=True) as connection:
        MIGRATIONS[17](connection)
        MIGRATIONS[17](connection)
    with get_connection(path) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "19"
        tables = {r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        assert tables == set(EXPECTED_TABLES)
        for table, columns in TABLES.items():
            assert tuple(r["name"] for r in connection.execute(f"PRAGMA table_info({table})")) == columns
            assert connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        indexes = {r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert set(PHASE_ELEVEN_REQUIRED_INDEX_STATEMENTS) <= indexes
        assert any(r["unique"] for r in connection.execute("PRAGMA index_list(campaign_result_snapshots)"))
    assert not {"first_name", "last_name", "email", "phone_number", "postal_code", "address_line_1", "push_token", "advertising_id", "web_visitor_id"}.intersection(CAMPAIGN_RESULT_SNAPSHOT_COLUMNS)
    assert RESULT_MEMBERSHIP_COLUMNS == ("person_id", "propensity_score", "percentile_bucket", "decile", "rank_band")


@pytest.mark.parametrize("baseline", (15, 16))
def test_upgrade_from_15_and_16_preserves_all_legacy_rows_and_is_idempotent(tmp_path: Path, baseline: int):
    path = tmp_path / "upgrade.db"
    _create_version_fourteen_database(path)
    with get_connection(path, write=True) as connection:
        for version in range(15, baseline + 1):
            MIGRATIONS[version](connection)
        connection.execute("UPDATE app_metadata SET value=? WHERE key='schema_version'", (str(baseline),))
        connection.execute("INSERT INTO customers(customer_id, date_of_birth, state, individual_yearly_income, family_member_count) VALUES('C-preserved','1990-01-01','Ohio',10,1)")
        connection.execute("INSERT INTO demographics(person_id,age,state,individual_yearly_income,family_member_count,number_of_children_in_family,number_of_adults_in_family,family_yearly_income) VALUES('P-preserved',40,'Ohio',10,1,0,1,10)")
        before = {r["name"]: [tuple(row) for row in connection.execute('SELECT * FROM "' + r["name"] + '"')] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='app_metadata'").fetchall()}
    initialize_database(path)
    initialize_database(path)
    with get_connection(path) as connection:
        for table, rows in before.items():
            assert [tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')] == rows
        assert connection.execute("SELECT value FROM app_metadata WHERE key='phase10_migration_sentinel'").fetchone()[0] == "preserve-me"
        assert tuple(r["name"] for r in connection.execute("PRAGMA table_info(demographics)")) == DEMOGRAPHIC_COLUMNS
        for table in TABLES:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_failed_schema_17_migration_rolls_back_ddl_and_version(tmp_path: Path, monkeypatch):
    path = tmp_path / "rollback.db"
    _create_version_fourteen_database(path)
    with get_connection(path, write=True) as connection:
        MIGRATIONS[15](connection)
        MIGRATIONS[16](connection)
        connection.execute("UPDATE app_metadata SET value='16' WHERE key='schema_version'")
    real_migration = MIGRATIONS[17]
    def fail(connection):
        real_migration(connection)
        raise RuntimeError("forced schema 17 failure")
    monkeypatch.setitem(MIGRATIONS, 17, fail)
    with pytest.raises(RuntimeError):
        initialize_database(path)
    with get_connection(path) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "16"
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'campaign_result_%' OR name='campaign_search_runs'").fetchall()


def test_two_submissions_share_one_snapshot_but_keep_distinct_immutable_history(case):
    _, ids, _, repository = case
    first = _search(case)
    second = _search(case, campaign_name="Different campaign", delivery_channel="SMS")
    snapshot = _snapshot(case, first)
    _complete(case, first, snapshot)
    _complete(case, second, snapshot, "EXACT_RESULT_REUSE")
    first_row, second_row = repository.fetch_search_run(first), repository.fetch_search_run(second)
    assert first != second
    assert first_row["result_snapshot_id"] == second_row["result_snapshot_id"] == snapshot
    assert first_row["model_run_id"] == ids["model_run_id"]
    assert second_row["result_source"] == "EXACT_RESULT_REUSE"
    assert second_row["processing_seconds"] == 10.0
    assert second_row["export_profile"] == "SMS_CONTACT_V1"
    assert repository.find_snapshot_by_cache_key("f" * 64)["result_snapshot_id"] == snapshot
    assert [r["search_run_id"] for r in repository.list_search_runs(limit=1)] == [second]
    assert [r["search_run_id"] for r in repository.list_search_runs(before_search_run_id=second)] == [first]
    assert repository.fetch_snapshot(snapshot)["last_used_at"] == LATER
    with pytest.raises(Phase11RegistryStateError):
        repository.mark_processing(first)


@pytest.mark.parametrize("source", ("EXACT_RESULT_REUSE", "INTELLIGENCE_REUSE", "NEW_INTELLIGENCE_BUILD"))
def test_all_result_sources_are_recordable_without_launching_work(case, source):
    search = _search(case)
    snapshot = _snapshot(case, search)
    _complete(case, search, snapshot, source)
    assert case[3].fetch_search_run(search)["result_source"] == source


@pytest.mark.parametrize("blocked", (True, False))
def test_failure_and_blocked_records_are_safe_and_terminal(case, blocked):
    search = _search(case)
    case[3].fail_search_run(search, blocked=blocked, timestamp=LATER)
    row = case[3].fetch_search_run(search)
    assert row["status"] == ("BLOCKED" if blocked else "FAILED")
    assert row["result_snapshot_id"] is None and row["processing_seconds"] == 10.0
    assert row["safe_error_message"]
    with pytest.raises(Phase11RegistryStateError):
        case[3].fail_search_run(search, timestamp=LATER)


@pytest.mark.parametrize("change", (
    {"targeting_criteria_sha256": "a" * 64}, {"filter_branches_sha256": "a" * 64},
    {"selection_mode": "TOP_N", "target_count": 20},
))
def test_completion_rejects_wrong_snapshot_identity_and_rolls_back(case, change):
    search = _search(case)
    snapshot = _snapshot(case, search, **change)
    case[3].mark_processing(search)
    with pytest.raises(sqlite3.IntegrityError):
        case[3].complete_search_run(search, result_snapshot_id=snapshot, result_source="EXACT_RESULT_REUSE", timestamp=LATER)
    assert case[3].fetch_search_run(search)["status"] == "PROCESSING"
    assert case[3].fetch_snapshot(snapshot)["last_used_at"] == NOW


def test_stale_snapshot_and_stale_generation_are_rejected(case):
    path, ids, _, repository = case
    search = _search(case)
    snapshot = _snapshot(case, search)
    repository.mark_processing(search)
    repository.update_snapshot_currentness(snapshot, state="STALE", timestamp=LATER)
    with pytest.raises(Phase11RegistryStateError):
        repository.complete_search_run(search, result_snapshot_id=snapshot, result_source="EXACT_RESULT_REUSE", timestamp=LATER)
    with get_connection(path, write=True) as connection:
        connection.execute("UPDATE phase10_intelligence_generations SET lifecycle_state='STALE' WHERE generation_id=?", (ids["generation_id"],))
    with pytest.raises(Phase11RegistryStateError):
        _snapshot(case, search, result_cache_key_sha256="d" * 64)


def test_unique_cache_key_rejects_duplicate_snapshot(case):
    search = _search(case)
    _snapshot(case, search)
    with pytest.raises(sqlite3.IntegrityError):
        _snapshot(case, search)


def test_identical_submissions_are_not_deduplicated(case):
    ids = [_search(case), _search(case)]
    assert len(set(ids)) == 2


@pytest.mark.parametrize("key", ("email", "phone_number", "address_line_1", "push_token", "person_id", "customer_id"))
def test_json_metadata_rejects_nested_pii_and_membership_keys(case, key):
    with pytest.raises(Phase11RegistryValidationError):
        _search(case, targeting_criteria={"nested": [{key: "secret"}]})


@pytest.mark.parametrize("criteria,branches", (({"x": float("nan")}, [{}]), ({}, []), ({}, ["bad"]), ([], [{}])))
def test_json_metadata_rejects_nonfinite_or_wrong_shape(case, criteria, branches):
    with pytest.raises(Phase11RegistryValidationError):
        _search(case, targeting_criteria=criteria, filter_branches=branches)


def test_json_hashes_are_canonical_and_channel_profile_is_not_part_of_membership(case):
    first = _search(case, targeting_criteria={"states": ["Ohio"], "genders": ["Female"]})
    second = _search(case, targeting_criteria={"genders": ["Female"], "states": ["Ohio"]}, delivery_channel="DISPLAY")
    for field in ("targeting_criteria_sha256", "filter_branches_sha256"):
        assert case[3].fetch_search_run(first)[field] == case[3].fetch_search_run(second)[field]
    row = case[3].fetch_search_run(first)
    assert hashlib.sha256(row["targeting_criteria_json"].encode()).hexdigest() == row["targeting_criteria_sha256"]


@pytest.mark.parametrize("change", (
    {"delivery_channel": "EMAIL", "export_profile": "SMS_CONTACT_V1"},
    {"delivery_channel": "UNKNOWN"}, {"selection_mode": "TOP_N"},
    {"target_count": 10}, {"campaign_name": ""}, {"planned_launch_date": "tomorrow"},
    {"modeling_context_sha256": "invalid"}, {"targeting_context_id": True},
))
def test_invalid_submission_contract_is_rejected(case, change):
    with pytest.raises(Phase11RegistryValidationError):
        _search(case, **change)


@pytest.mark.parametrize("uri", ("../members.csv.gz", "C:/secret.csv.gz", "artifacts/results/person@example.net/members.csv.gz"))
def test_snapshot_uri_cannot_store_contact_or_nonportable_paths(case, uri):
    search = _search(case)
    with pytest.raises(Phase11RegistryValidationError):
        _snapshot(case, search, storage_uri=uri)


def test_top_n_and_zero_result_snapshots(case):
    search = _search(case, selection_mode="TOP_N", target_count=5)
    snapshot = _snapshot(case, search, resolved_count=0)
    _complete(case, search, snapshot)
    assert case[3].fetch_search_run(search)["selected_count"] == 0
    with pytest.raises(Phase11RegistryValidationError):
        _snapshot(case, search, resolved_count=6)


@pytest.mark.parametrize("table,field,value", (
    ("campaign_search_runs", "campaign_name", "Changed"),
    ("campaign_result_snapshots", "resolved_count", 9),
    ("campaign_result_snapshots", "snapshot_sha256", "b" * 64),
))
def test_database_triggers_protect_immutable_identity(case, table, field, value):
    search = _search(case)
    _snapshot(case, search)
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(case[0], write=True) as connection:
            connection.execute(f"UPDATE {table} SET {field}=?", (value,))


def test_terminal_search_cannot_be_updated_or_deleted_even_by_direct_sql(case):
    search = _search(case)
    snapshot = _snapshot(case, search)
    _complete(case, search, snapshot)
    for sql in ("UPDATE campaign_search_runs SET selected_count=10", "DELETE FROM campaign_search_runs", "DELETE FROM campaign_result_snapshots"):
        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(case[0], write=True) as connection:
                connection.execute(sql)


@pytest.mark.parametrize("status", ("COMPLETED", "FAILED", "ABORTED"))
def test_export_audit_reconciles_counts_checksums_and_terminal_safety(case, status):
    search = _search(case)
    snapshot = _snapshot(case, search)
    _complete(case, search, snapshot)
    repository = case[3]
    event = repository.create_export_event(search_run_id=search, snapshot_id=snapshot, export_profile="SMS_CONTACT_V1", selected_count=10, deliverable_count=8, undeliverable_count=2, timestamp=LATER)
    repository.finish_export_event(event, status=status, row_count=8 if status == "COMPLETED" else 3, csv_sha256="c" * 64 if status == "COMPLETED" else None, currentness_state="CURRENT", timestamp=LATER)
    row = repository.fetch_export_event(event)
    assert row["status"] == status and row["selected_count"] == row["deliverable_count"] + row["undeliverable_count"]
    assert bool(row["safe_error_message"]) == (status != "COMPLETED")
    assert repository.list_export_events(search)[0]["export_event_id"] == event
    with pytest.raises(Phase11RegistryStateError):
        repository.finish_export_event(event, status="FAILED", row_count=0, timestamp=LATER)
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(case[0], write=True) as connection:
            connection.execute("UPDATE campaign_result_export_events SET row_count=0 WHERE export_event_id=?", (event,))


def test_export_requires_completed_search_matching_snapshot_and_currentness(case):
    search = _search(case)
    snapshot = _snapshot(case, search)
    repository = case[3]
    with pytest.raises(sqlite3.IntegrityError):
        repository.create_export_event(search_run_id=search, snapshot_id=snapshot, export_profile="EMAIL_CONTACT_V1", selected_count=10, deliverable_count=8, undeliverable_count=2)
    _complete(case, search, snapshot)
    event = repository.create_export_event(search_run_id=search, snapshot_id=snapshot, export_profile="EMAIL_CONTACT_V1", selected_count=10, deliverable_count=8, undeliverable_count=2, timestamp=LATER)
    with pytest.raises(Phase11RegistryValidationError):
        repository.finish_export_event(event, status="COMPLETED", row_count=7, csv_sha256="c" * 64, currentness_state="CURRENT", timestamp=LATER)
    repository.update_snapshot_currentness(snapshot, state="STALE", timestamp=LATER)
    with pytest.raises(Phase11RegistryStateError):
        repository.finish_export_event(event, status="COMPLETED", row_count=8, csv_sha256="c" * 64, currentness_state="CURRENT", timestamp=LATER)
    assert repository.fetch_export_event(event)["status"] == "RUNNING"


def test_missing_foreign_key_and_invalid_history_limits_are_rejected(case):
    with pytest.raises(sqlite3.IntegrityError):
        _search(case, targeting_context_id=999999)
    for limit in (0, 101, True):
        with pytest.raises(Phase11RegistryValidationError):
            case[3].list_search_runs(limit=limit)


def test_history_cursor_uses_created_time_and_id_tie_break(case):
    older = _search(case, timestamp=NOW)
    newer = _search(case, timestamp=LATER)
    older_but_higher_id = _search(case, timestamp=NOW)
    repository = case[3]
    assert [r["search_run_id"] for r in repository.list_search_runs()] == [newer, older_but_higher_id, older]
    assert [r["search_run_id"] for r in repository.list_search_runs(before_search_run_id=newer)] == [older_but_higher_id, older]
    assert [r["search_run_id"] for r in repository.list_search_runs(before_search_run_id=older_but_higher_id)] == [older]
    with pytest.raises(Phase11RegistryStateError):
        repository.list_search_runs(before_search_run_id=999999)
