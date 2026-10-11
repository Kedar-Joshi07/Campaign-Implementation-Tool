"""Independent bounded expectations for the Stage 14B-05 shared predicate."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.buyer_similarity_selection_service import (
    SimilarityResolution, count_similarity_selection, selected_members_sql, selection_sql,
)
from app.services.buyer_similarity_result_service import result_cache_key
from app.services.buyer_similarity_result_service import (
    SimilarityResultError, materialize_similarity_result,
)
from app.services.buyer_similarity_selection_service import resolve_similarity_context
from app.database.connection import get_connection
from app.database import schema as database_schema
from app.database.schema import initialize_database
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.schemas.potential_customer_search import PotentialCustomerSearchV3Request
from app.services import potential_customer_search_submission_service as submission
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight
from app.services.buyer_similarity_search_orchestration_service import execute_similarity_search_safely
from app.services.phase11_results_service import get_result_detail
from tests.test_buyer_similarity_cohort_service import _catalog, _sale, _seed
from app.services.buyer_similarity_cohort_service import build_product_buyer_cohorts
from app.services.buyer_similarity_cohort_service import LEGACY_BUYER_SPLIT_STRATEGY_VERSION
from app.services import buyer_similarity_split_service as split_service


def test_existing_schema_32_repairs_v3_completion_trigger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Certify the historical v32 repair at v32; Stage 07 has its own v32->v33 test.
    monkeypatch.setattr(database_schema, "CURRENT_SCHEMA_VERSION", 32)
    database = initialize_database(tmp_path / "old32.db")
    with get_connection(database, write=True) as connection:
        connection.execute("DROP TRIGGER campaign_search_runs_immutable_identity")
        connection.execute(
            "CREATE TRIGGER campaign_search_runs_immutable_identity "
            "BEFORE UPDATE ON campaign_search_runs "
            "WHEN NEW.similarity_generation_id IS NOT OLD.similarity_generation_id "
            "BEGIN SELECT RAISE(ABORT,'immutable registry identity'); END"
        )
        connection.execute(
            "UPDATE app_metadata SET value='32' WHERE key='schema_version'"
        )
    initialize_database(database)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0] == "32"
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='campaign_search_runs_immutable_identity'"
        ).fetchone()[0]
    assert "NEW.similarity_generation_id IS NOT OLD.similarity_generation_id" not in trigger
    assert "NEW.targeting_criteria_sha256 IS NOT OLD.targeting_criteria_sha256" in trigger


def test_result_cache_identity_separates_threshold_filters_profiles_and_sources() -> None:
    run = {
        "similarity_minimum": .70,
        "targeting_criteria_sha256": "a" * 64,
        "filter_branches_sha256": "b" * 64,
        "catalog_version": "c" * 64,
        "selection_mode": "ALL_MATCHING",
        "target_count": None,
    }
    resolution = SimilarityResolution(
        "d" * 64,
        {"customers": (1, "e" * 64), "campaign_sales": (2, "f" * 64),
         "demographics": (3, "0" * 64)},
        ({"profile_id": 1},),
        ({"similarity_generation_id": 2, "published_at": "2026-10-07T00:00:00Z"},),
        (), (), "1" * 64, "2" * 64, "2025-01-01", "2025-12-31",
    )
    key = result_cache_key(run, resolution)
    assert key != result_cache_key(run | {"similarity_minimum": .80}, resolution)
    assert key != result_cache_key(run | {"filter_branches_sha256": "3" * 64}, resolution)
    assert key != result_cache_key(run | {"selection_mode": "TOP_N", "target_count": 5}, resolution)
    assert key != result_cache_key(run, replace(resolution, profile_set_sha256="4" * 64))
    assert key != result_cache_key(run, replace(resolution, source_identity={
        **resolution.source_identity, "demographics": (4, "5" * 64),
    }))


def _scores() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        "CREATE TABLE demographics(person_id TEXT PRIMARY KEY,gender TEXT);"
        "CREATE TABLE buyer_similarity_scores("
        "similarity_generation_id INTEGER,person_id TEXT,product_id TEXT,"
        "buyer_similarity_score REAL,similarity_tier TEXT,score_method_version TEXT,"
        "feature_coverage REAL,is_valid INTEGER);"
    )
    connection.executemany(
        "INSERT INTO demographics VALUES (?,?)",
        [(person, "Male" if person == "E" else "Female")
         for person in "ABCDEFG"],
    )
    values = [
        (1, "A", "P1", .96, 1.0, 1),
        (1, "B", "P1", .92, 1.0, 1),
        (1, "C", "P1", .88, 1.0, 1),
        (1, "D", "P1", .73, 1.0, 1),
        (1, "E", "P1", .97, 1.0, 1),
        (2, "A", "P2", .95, 1.0, 1),  # lower product winner is discarded
        (2, "F", "P2", .90, .79, 1),  # invalid coverage is excluded
        (2, "G", "P2", .99, 1.0, 0),  # invalid score is excluded
    ]
    def tier(score: float) -> str:
        for bound, name in ((.90, "VERY_STRONG"), (.80, "STRONG"),
                            (.70, "GOOD"), (.60, "BROAD"), (.50, "EXPLORATORY")):
            if score >= bound:
                return name
        return "EXPLORATORY"
    connection.executemany(
        "INSERT INTO buyer_similarity_scores VALUES (?,?,?,?,?,?,?,?)",
        [(generation, person, product, score, tier(score), "BUYER_PROFILE_DISTANCE_V1",
          coverage, valid)
         for generation, person, product, score, coverage, valid in values],
    )
    return connection


def _members(connection: sqlite3.Connection, branches: list[dict], minimum: float,
             *, mode: str = "ALL_MATCHING", top_n: int | None = None) -> list[str]:
    cte, params = selection_sql(
        branches, (1, 2), minimum, selection_mode=mode, top_n=top_n,
    )
    query = selected_members_sql(cte, selection_mode=mode)
    return [row["person_id"] for row in connection.execute(
        query, (*params, top_n) if top_n is not None else params,
    )]


def test_exact_cumulative_minima_or_dedup_and_top_n() -> None:
    connection = _scores()
    branches = [{"gender": ["Female"]}, {"gender": ["Female", "Unknown/Other"]}]
    assert _members(connection, branches, .90) == ["A", "B"]
    assert _members(connection, branches, .80) == ["A", "B", "C"]
    assert _members(connection, branches, .70) == ["A", "B", "C", "D"]
    assert _members(connection, branches, .90, mode="TOP_N", top_n=1) == ["A"]
    assert count_similarity_selection(
        connection, branches, (1, 2), .80,
        selection_mode="TOP_N", top_n=2,
    ) == (6, 5, 2, 3, 2)
    assert _members(connection, [{"gender": ["Unknown/Other"]}], .50) == []
    connection.close()


def test_joined_exact_count_matches_member_materialization_for_three_generations() -> None:
    connection = _scores()
    connection.executemany(
        "INSERT INTO buyer_similarity_scores VALUES (?,?,?,?,?,?,?,?)",
        [
            (3, "A", "P3", .97, "VERY_STRONG", "BUYER_PROFILE_DISTANCE_V1", 1.0, 1),
            (3, "C", "P3", .99, "VERY_STRONG", "BUYER_PROFILE_DISTANCE_V1", 1.0, 0),
            (3, "G", "P3", .83, "STRONG", "BUYER_PROFILE_DISTANCE_V1", 1.0, 1),
        ],
    )
    for branches in (
        [{"gender": ["Female"]}],
        [{"gender": ["Male"]}, {"gender": ["Female"]}],
        [{"gender": ["Unknown/Other"]}],
    ):
        for minimum in (.50, .60, .70, .80, .90):
            cte, params = selection_sql(
                branches, (1, 2, 3), minimum,
                selection_mode="ALL_MATCHING", top_n=None,
            )
            expected = len(connection.execute(
                selected_members_sql(cte, selection_mode="ALL_MATCHING"), params,
            ).fetchall())
            count = count_similarity_selection(
                connection, branches, (1, 2, 3), minimum,
                selection_mode="ALL_MATCHING", top_n=None,
            )
            assert count[3] == count[4] == expected
            assert count[1] == 6  # A-E and G; F has inadequate coverage.
            assert count[1] + count[2] == 7
    connection.close()


def test_attested_high_threshold_count_uses_exact_candidate_union() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        "CREATE TABLE demographics(person_id TEXT PRIMARY KEY,gender TEXT);"
        "CREATE TABLE buyer_similarity_scores("
        "similarity_generation_id INTEGER,person_id TEXT,product_id TEXT,"
        "buyer_similarity_score REAL,similarity_tier TEXT,score_method_version TEXT,"
        "feature_coverage REAL,is_valid INTEGER);"
        "CREATE TABLE buyer_similarity_generation_attestations("
        "similarity_generation_id INTEGER,expected_person_count INTEGER,"
        "verified_row_count INTEGER,invalid_score_count INTEGER,verification_status TEXT);"
        "CREATE INDEX score_threshold ON buyer_similarity_scores("
        "similarity_generation_id,is_valid,buyer_similarity_score,person_id);"
    )
    people = "ABCDEFG"
    connection.executemany(
        "INSERT INTO demographics VALUES (?,?)",
        [(person, "Male" if person in "BD" else "Female") for person in people],
    )
    for generation, invalid_people in ((1, "F"), (2, "G"), (3, "")):
        for person in people:
            valid = person not in invalid_people
            score = (.95 if person in "ACEG" else .65) if valid else None
            connection.execute(
                "INSERT INTO buyer_similarity_scores VALUES (?,?,?,?,?,?,?,?)",
                (generation, person, f"P{generation}", score,
                 "VERY_STRONG" if score and score >= .90 else "BROAD" if valid else None,
                 "BUYER_PROFILE_DISTANCE_V1", 1.0, int(valid)),
            )
        connection.execute(
            "INSERT INTO buyer_similarity_generation_attestations VALUES (?,?,?,?,?)",
            (generation, 7, 7, len(invalid_people), "VERIFIED"),
        )
    for branches in ([{"gender": ["Female"]}], [{"gender": ["Male"]}]):
        cte, params = selection_sql(
            branches, (1, 2, 3), .90, selection_mode="ALL_MATCHING", top_n=None,
        )
        expected = len(connection.execute(
            selected_members_sql(cte, selection_mode="ALL_MATCHING"), params,
        ).fetchall())
        actual = count_similarity_selection(
            connection, branches, (1, 2, 3), .90,
            selection_mode="ALL_MATCHING", top_n=None,
        )
        assert actual[1] == 7
        assert actual[3] == actual[4] == expected
    connection.close()


def test_full_precision_boundary_and_invalid_branches() -> None:
    connection = _scores()
    connection.execute(
        "UPDATE buyer_similarity_scores SET buyer_similarity_score=? "
        "WHERE person_id='B' AND product_id='P1'",
        (math.nextafter(.90, 0.0),),
    )
    assert _members(connection, [{"gender": ["Female"]}], .90) == ["A"]
    connection.execute(
        "UPDATE buyer_similarity_scores SET buyer_similarity_score=.90 "
        "WHERE person_id='B' AND product_id='P1'"
    )
    assert _members(connection, [{"gender": ["Female"]}], .90) == ["A", "B"]
    connection.execute(
        "UPDATE buyer_similarity_scores SET buyer_similarity_score=.90 "
        "WHERE person_id IN ('A','C') OR (person_id='A' AND product_id='P2')"
    )
    assert _members(
        connection, [{"gender": ["Female"]}], .90,
        mode="TOP_N", top_n=3,
    ) == ["A", "B", "C"]
    connection.execute("UPDATE demographics SET gender=NULL WHERE person_id='D'")
    assert _members(connection, [{"gender": ["Unknown/Other"]}], .70) == ["D"]
    with pytest.raises(ValueError):
        selection_sql([{"score_min": .90}], (1,), .90,
                      selection_mode="ALL_MATCHING", top_n=None)
    connection.close()


def test_preflight_blocks_exact_200_buyers_when_union_split_has_only_159_fit(
    tmp_path: Path,
) -> None:
    database = _seed(tmp_path / "split-support.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    _catalog(catalog)
    with get_connection(database, write=True) as connection:
        # The future P1 event remains in the historical window but is not a buyer.
        connection.execute(
            "UPDATE campaign_sales SET campaign_attributed_sale_flag=0 "
            "WHERE customer_id='CUS0201'"
        )
        connection.executemany(
            """INSERT INTO customers (
                customer_id,date_of_birth,gender,state,individual_yearly_income,
                marital_status,education,employment_status,resident_status,
                resident_type,family_member_count,type_of_employment
            ) VALUES (?,'1990-06-15','Female','Ohio',50000,'Single',
                      'Bachelor degree','Employed full-time','Citizen','Urban',2,'Salaried')""",
            ((f"EXTRA{index:04d}",) for index in range(11)),
        )
        connection.executemany(
            """INSERT INTO campaign_sales (
                campaign_sales_id,customer_id,campaign_id,product_id,
                campaign_name,campaign_type,campaign_category,campaign_channel,
                offer_type,product_name,product_category,campaign_start_date,
                campaign_end_date,contact_date,contacted_flag,engagement_flag,response_flag,
                purchase_flag,campaign_attributed_sale_flag,pu_label,purchase_date,
                days_to_purchase,quantity
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_sale(900000 + index, f"EXTRA{index:04d}", "P2")
             for index in range(11)),
        )
        for dataset, table in (("customers", "customers"),
                               ("campaign_sales", "campaign_sales")):
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            connection.execute(
                "UPDATE data_import_runs SET rows_read=?,rows_inserted=? "
                "WHERE dataset_name=?",
                (count, count, dataset),
            )
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
    cohort = build_product_buyer_cohorts(
        database, product_ids=["P1", "P2"], window_start="2025-06-01",
        window_end="2026-01-01", campaign_types=["Retention"],
        product_catalog_path=catalog,
        split_strategy_version=LEGACY_BUYER_SPLIT_STRATEGY_VERSION,
    )
    p1 = next(item for item in cohort.manifest.product_support
              if item.product_id == "P1")
    assert (p1.distinct_attributed_buyers, p1.fit_buyers, p1.holdout_buyers) == (
        200, 159, 41,
    )
    assert p1.reason_code == "INSUFFICIENT_SPLIT_SUPPORT"

    options = submission.search_form_options(database)
    result = exact_similarity_preflight(
        database,
        context={
            "product_ids": ["P1", "P2"], "campaign_types": ["Retention"],
            "campaign_categories": [], "offer_types": [],
            "historical_campaign_channels": [], "campaign_channel": "EMAIL",
        },
        criteria={}, similarity_minimum=.70, selection_mode="ALL_MATCHING",
        top_n=None, catalog_version=options["catalog_version"],
        project_root=tmp_path, product_catalog_path=catalog,
    )
    assert result["reason_code"] == "PROFILE_NOT_ELIGIBLE"
    assert result["build_available"] is False
    assert result["selected_count"] is None


def test_unresolved_split_preflight_is_retryable_not_proven_infeasible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _seed(tmp_path / "unresolved.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    _catalog(catalog)
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
    monkeypatch.setattr(
        split_service, "milp", lambda *_args, **_kwargs: SimpleNamespace(status=1, x=None),
    )
    options = submission.search_form_options(database)
    result = exact_similarity_preflight(
        database,
        context={
            "product_ids": ["P1"], "campaign_types": [], "campaign_categories": [],
            "offer_types": [], "historical_campaign_channels": [],
            "campaign_channel": "EMAIL",
        },
        criteria={}, similarity_minimum=.70, selection_mode="ALL_MATCHING",
        top_n=None, catalog_version=options["catalog_version"],
        project_root=tmp_path, product_catalog_path=catalog,
    )
    assert result["reason_code"] == "SPLIT_SOLVER_UNRESOLVED"
    assert result["build_available"] is True
    assert result["selected_count"] is None


def test_prepare_score_preflight_search_snapshot_and_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _seed(tmp_path / "similarity.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    catalog.write_text(
        "product_id,product_name,product_category\nP1,Product One,Category A\n",
        encoding="utf-8",
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:00Z", "e" * 64),
        )
    options = submission.search_form_options(database)
    context = {
        "product_ids": ["P1"], "campaign_types": [],
        "campaign_categories": [], "offer_types": [],
        "historical_campaign_channels": [], "campaign_channel": "EMAIL",
    }
    criteria: dict = {}
    parameters = dict(
        context=context, criteria=criteria, similarity_minimum=.50,
        selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=tmp_path,
    )
    before = exact_similarity_preflight(database, **parameters)
    assert before["selected_count"] is None
    assert before["build_available"] is True
    profile = next(item for item in options["profiles"]
                   if item["channel_code"] == "EMAIL" and item["availability"] == "AVAILABLE")
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.50, campaign_name="Bounded similarity search",
        context=context, criteria=criteria, selection_mode="ALL_MATCHING",
        export_profile=profile["export_profile"],
        catalog_version=options["catalog_version"],
    )
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: True)
    created = submission.submit_potential_customer_search(database, request)
    assert created["status"] == "QUEUED"
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="v3-test")
    outcome = execute_similarity_search_safely(
        database, created["search_run_id"], **fence.as_kwargs(),
        project_root=tmp_path,
    )
    assert outcome.status == "COMPLETED"
    after = exact_similarity_preflight(database, **parameters)
    assert after["similarity_currentness"] == "CURRENT"
    assert after["probability_currentness"] is None
    assert exact_similarity_preflight(database, **parameters)["cache_hit"] is True
    assert after["selected_count"] == repository.fetch_search_run(
        created["search_run_id"]
    )["selected_count"]
    detail = get_result_detail(database, created["search_run_id"], project_root=tmp_path)
    assert detail["snapshot_provenance"]["resolved_count"] == after["selected_count"]
    assert detail["snapshot_provenance"]["currentness"] == "CURRENT"
    with pytest.raises(SimilarityResultError, match="lease"):
        materialize_similarity_result(
            database, repository.fetch_search_run(created["search_run_id"]),
            context, resolve_similarity_context(database, context, project_root=tmp_path),
            project_root=tmp_path, **fence.as_kwargs(),
        )

    another = submission.submit_potential_customer_search(database, request)
    another_fence = repository.claim_search_attempt(
        another["search_run_id"], lease_owner="v3-reuse-test"
    )
    reused = execute_similarity_search_safely(
        database, another["search_run_id"], **another_fence.as_kwargs(),
        project_root=tmp_path,
    )
    assert reused.status == "COMPLETED"
    assert reused.result_source == "EXACT_RESULT_REUSE"
    assert reused.result_snapshot_id == outcome.result_snapshot_id
    assert repository.fetch_search_run(another["search_run_id"])["selected_count"] == after["selected_count"]

    higher_request = request.model_copy(update={"similarity_minimum": .90})
    higher = submission.submit_potential_customer_search(database, higher_request)
    higher_fence = repository.claim_search_attempt(
        higher["search_run_id"], lease_owner="v3-threshold-test"
    )
    higher_outcome = execute_similarity_search_safely(
        database, higher["search_run_id"], **higher_fence.as_kwargs(),
        project_root=tmp_path,
    )
    assert higher_outcome.status == "COMPLETED"
    assert higher_outcome.result_snapshot_id != outcome.result_snapshot_id
    higher_count = exact_similarity_preflight(
        database, **(parameters | {"similarity_minimum": .90})
    )["selected_count"]
    assert higher_count == repository.fetch_search_run(higher["search_run_id"])["selected_count"]

    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('demographics','new_demographics.csv',?,?,'COMPLETED',10,10,0,?)""",
            ("2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "f" * 64),
        )
    with pytest.raises(ValueError, match="Reload current campaign choices"):
        exact_similarity_preflight(database, **parameters)
    refreshed = submission.search_form_options(database)
    stale = exact_similarity_preflight(
        database, **(parameters | {"catalog_version": refreshed["catalog_version"]})
    )
    assert stale["similarity_currentness"] == "STALE"
    assert stale["selected_count"] is None

    pending = submission.submit_potential_customer_search(
        database, request.model_copy(update={"catalog_version": refreshed["catalog_version"]})
    )
    pending_id = pending["search_run_id"]
    old_fence = repository.claim_search_attempt(pending_id, lease_owner="v3-retry-test")
    repository.heartbeat_search_attempt(pending_id, **old_fence.as_kwargs())
    repository.fail_search_run(
        pending_id, **old_fence.as_kwargs(),
        failure_code="SIMILARITY_PREPARATION_FAILED", retryable=True,
    )
    retry = submission.retry_potential_customer_search(
        database, pending_id, idempotency_key="v3-retry-0001"
    )
    assert retry["attempt_number"] == 2 and retry["status"] == "QUEUED"
    again = submission.retry_potential_customer_search(
        database, pending_id, idempotency_key="v3-retry-0001"
    )
    assert again["attempt_number"] == 2
    with pytest.raises(Phase11RegistryStateError):
        repository.heartbeat_search_attempt(pending_id, **old_fence.as_kwargs())
