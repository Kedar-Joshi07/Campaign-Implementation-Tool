from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.database.connection import get_connection
from app.database import schema as database_schema
from app.database.schema import (
    CREATE_TABLE_STATEMENTS,
    EXPECTED_TABLES,
    MIGRATIONS,
    initialize_database,
)
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.schemas.potential_customer_search import (
    PotentialCustomerPreflightV3Request,
    PotentialCustomerSearchRequest,
    PotentialCustomerSearchV3Request,
)
from app.selection_contracts import (
    BUYER_SIMILARITY_MEMBERSHIP_CONTRACT_VERSION,
    BUYER_SIMILARITY_MINIMUMS,
    BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
    BUYER_SIMILARITY_SCORE_METHOD_VERSION,
    BUYER_SIMILARITY_SCORE_SEMANTICS,
    BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION,
    BUYER_SIMILARITY_THRESHOLD_PREDICATE,
    DEFAULT_BUYER_SIMILARITY_MINIMUM,
    buyer_similarity_meets_minimum,
    buyer_similarity_tier,
)
from app.services.phase11_result_contracts import (
    RESULT_MEMBERSHIP_V3_COLUMNS,
    result_membership_contract_for_selection,
)
from tests.test_phase11_business_search_form import request_payload
from tests.test_phase9_business_targeting import client, database_path


NOW = "2026-10-06T00:00:00Z"
SHA = "a" * 64


def _create_schema_31(path: Path) -> None:
    with get_connection(path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            "INSERT INTO app_metadata(key,value,updated_at) VALUES (?,?,?)",
            (
                ("schema_version", "1", NOW),
                ("application_version", "0.1.0", NOW),
                ("database_initialized_at", NOW, NOW),
            ),
        )
        for version in range(2, 32):
            MIGRATIONS[version](connection)
            connection.execute(
                "UPDATE app_metadata SET value=? WHERE key='schema_version'",
                (str(version),),
            )


def _insert_context_and_history(path: Path) -> tuple[int, int]:
    with get_connection(path, write=True) as connection:
        context_id = int(connection.execute(
            """INSERT INTO campaign_targeting_contexts (
                campaign_targeting_context_contract_version,
                targeting_segment_contract_version,
                business_match_strength_contract_version,
                campaign_context_json,campaign_context_sha256,
                targeting_criteria_json,targeting_criteria_sha256,
                created_at,updated_at
            ) VALUES ('1','1','1','{}',?,'{}',?,?,?)""",
            ("b" * 64, "c" * 64, NOW, NOW),
        ).lastrowid)
        base = (
            "1", "historical", context_id, SHA, "{}", "d" * 64,
            "[{}]", "e" * 64, "ALL_MATCHING", "EMAIL",
            "EMAIL_CONTACT_V1", "QUEUED", NOW, NOW, 1,
        )
        v1 = int(connection.execute(
            """INSERT INTO campaign_search_runs (
                search_run_contract_version,campaign_name,targeting_context_id,
                modeling_context_sha256,targeting_criteria_json,targeting_criteria_sha256,
                filter_branches_json,filter_branches_sha256,selection_mode,
                delivery_channel,export_profile,status,created_at,started_at,
                current_attempt_number,selection_contract_version,propensity_bucket
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'1',NULL)""",
            base,
        ).lastrowid)
        v2 = int(connection.execute(
            """INSERT INTO campaign_search_runs (
                search_run_contract_version,campaign_name,targeting_context_id,
                modeling_context_sha256,targeting_criteria_json,targeting_criteria_sha256,
                filter_branches_json,filter_branches_sha256,selection_mode,
                delivery_channel,export_profile,status,created_at,started_at,
                current_attempt_number,selection_contract_version,propensity_bucket
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'2','0.70')""",
            base,
        ).lastrowid)
    return v1, v2


def _v3_request(**changes: object) -> dict:
    payload = {
        "selection_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "similarity_minimum": 0.70,
        "campaign_name": "Lookalike",
        "context": {"product_ids": ["PRD001"]},
        "criteria": {},
        "selection_mode": "ALL_MATCHING",
        "top_n": None,
        "export_profile": "EMAIL_CONTACT_V1",
        "catalog_version": SHA,
    }
    payload.update(changes)
    return payload


def test_v3_registry_is_separate_and_has_literal_boundary_semantics() -> None:
    assert BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION == "3"
    assert BUYER_SIMILARITY_MEMBERSHIP_CONTRACT_VERSION == "3"
    assert BUYER_SIMILARITY_SCORE_SEMANTICS == "PRODUCT_BUYER_SIMILARITY"
    assert BUYER_SIMILARITY_SCORE_METHOD_VERSION == "BUYER_PROFILE_DISTANCE_V1"
    assert BUYER_SIMILARITY_THRESHOLD_PREDICATE == "GREATER_THAN_OR_EQUAL"
    assert BUYER_SIMILARITY_PRODUCT_MATCH_POLICY == "ANY_SELECTED_PRODUCT_MAX_V1"
    assert BUYER_SIMILARITY_MINIMUMS == (0.90, 0.80, 0.70, 0.60, 0.50)
    assert DEFAULT_BUYER_SIMILARITY_MINIMUM == 0.70
    for boundary, tier in (
        (0.50, "EXPLORATORY"), (0.60, "BROAD"), (0.70, "GOOD"),
        (0.80, "STRONG"), (0.90, "VERY_STRONG"), (1.00, "VERY_STRONG"),
    ):
        assert buyer_similarity_meets_minimum(boundary, boundary if boundary < 1 else .9)
        assert buyer_similarity_tier(boundary) == tier
    assert result_membership_contract_for_selection("3") == "3"
    assert RESULT_MEMBERSHIP_V3_COLUMNS == (
        "person_id", "buyer_similarity_score", "similarity_tier",
        "matched_product_id", "score_method_version", "feature_coverage",
        "similarity_generation_id",
    )


@pytest.mark.parametrize("bad", [True, 70, "0.70", float("nan"), float("inf"), 0.75])
def test_v3_request_strictly_rejects_nonliteral_similarity_values(bad: object) -> None:
    with pytest.raises(ValidationError):
        PotentialCustomerSearchV3Request.model_validate(
            _v3_request(similarity_minimum=bad)
        )


def test_v3_rejects_mixed_fields_and_unversioned_behavior_remains_legacy() -> None:
    with pytest.raises(ValidationError):
        PotentialCustomerSearchV3Request.model_validate(
            _v3_request(criteria={"match_strength": "GOOD"})
        )
    with pytest.raises(ValidationError):
        PotentialCustomerSearchV3Request.model_validate(
            _v3_request(propensity_bucket="0.70")
        )
    for changes in (
        {"selection_contract_version": "4"},
        {"score_semantics": "CALIBRATED_PURCHASE_PROBABILITY"},
        {"selection_mode": "TOP_N", "top_n": True},
        {"selection_mode": "UNKNOWN"},
    ):
        with pytest.raises(ValidationError):
            PotentialCustomerSearchV3Request.model_validate(_v3_request(**changes))
    legacy = PotentialCustomerSearchRequest.model_validate({
        "campaign_name": "Legacy", "context": {}, "criteria": {},
        "export_profile": "EMAIL_CONTACT_V1",
    })
    assert legacy.propensity_bucket is None


def test_fresh_schema_32_contains_isolated_v3_registry_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    # Preserve this frozen v32 assertion after the additive Stage 07 migration.
    monkeypatch.setattr(database_schema, "CURRENT_SCHEMA_VERSION", 32)
    monkeypatch.setitem(globals(), "EXPECTED_TABLES", database_schema.SCHEMA_32_EXPECTED_TABLES)
    path = initialize_database(tmp_path / "fresh.db")
    initialize_database(path)
    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0] == "32"
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert set(EXPECTED_TABLES) <= tables
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        run_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_search_runs'"
        ).fetchone()[0]
        attempt_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='campaign_search_attempts'"
        ).fetchone()[0]
    assert "('1','2','3')" in run_sql
    assert "selection_contract_version='3'" in attempt_sql


def test_populated_schema31_migration_preserves_v1_v2_ids_and_semantics(tmp_path: Path) -> None:
    path = tmp_path / "populated31.db"
    _create_schema_31(path)
    identifiers = _insert_context_and_history(path)
    with get_connection(path) as connection:
        before = [tuple(row) for row in connection.execute(
            "SELECT search_run_id,selection_contract_version,propensity_bucket FROM campaign_search_runs ORDER BY search_run_id"
        )]
        attempt_before = int(connection.execute(
            "SELECT COUNT(*) FROM campaign_search_attempts"
        ).fetchone()[0])
    initialize_database(path)
    with get_connection(path) as connection:
        after = [tuple(row) for row in connection.execute(
            "SELECT search_run_id,selection_contract_version,propensity_bucket FROM campaign_search_runs ORDER BY search_run_id"
        )]
        assert int(connection.execute(
            "SELECT COUNT(*) FROM campaign_search_attempts"
        ).fetchone()[0]) == attempt_before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert identifiers == (1, 2)
    assert after == before == [(1, "1", None), (2, "2", "0.70")]


def test_failed_schema32_step_rolls_back_atomically(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "rollback.db"
    _create_schema_31(path)

    def fail(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration32_partial(value TEXT)")
        raise RuntimeError("injected migration failure")

    monkeypatch.setitem(MIGRATIONS, 32, fail)
    with pytest.raises(RuntimeError, match="injected"):
        initialize_database(path)
    with get_connection(path) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0] == "31"
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='migration32_partial'"
        ).fetchone() is None


def test_database_rejects_mixed_v3_run_and_duplicate_published_profile(tmp_path: Path) -> None:
    path = initialize_database(tmp_path / "constraints.db")
    with get_connection(path, write=True) as connection:
        context_id = int(connection.execute(
            """INSERT INTO campaign_targeting_contexts (
                campaign_targeting_context_contract_version,
                targeting_segment_contract_version,
                business_match_strength_contract_version,
                campaign_context_json,campaign_context_sha256,
                targeting_criteria_json,targeting_criteria_sha256,
                created_at,updated_at
            ) VALUES ('1','1','1','{}',?,'{}',?,?,?)""",
            ("b" * 64, "c" * 64, NOW, NOW),
        ).lastrowid)
    repository = CampaignResultRegistryRepository(path)
    with pytest.raises(Exception):
        repository.create_search_run(
            campaign_name="mixed", targeting_context_id=context_id,
            modeling_context_sha256=SHA, targeting_criteria={},
            filter_branches=[{}], delivery_channel="EMAIL",
            export_profile="EMAIL_CONTACT_V1",
            selection_contract_version="3", propensity_bucket="0.70",
            score_semantics=BUYER_SIMILARITY_SCORE_SEMANTICS,
            similarity_minimum=0.70,
        )

    with get_connection(path, write=True) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO campaign_search_runs (
                    search_run_contract_version,campaign_name,targeting_context_id,
                    modeling_context_sha256,targeting_criteria_json,
                    targeting_criteria_sha256,filter_branches_json,
                    filter_branches_sha256,selection_mode,delivery_channel,
                    export_profile,status,created_at,started_at,
                    current_attempt_number,selection_contract_version,
                    propensity_bucket,score_semantics,similarity_minimum,
                    similarity_threshold_predicate,similarity_product_match_policy,
                    similarity_score_method_version
                ) VALUES ('1','mixed-sql',? ,?,'{}',?,'[{}]',?,
                    'ALL_MATCHING','EMAIL','EMAIL_CONTACT_V1','QUEUED',?,?,1,
                    '3','0.70','PRODUCT_BUYER_SIMILARITY',0.70,
                    'GREATER_THAN_OR_EQUAL','ANY_SELECTED_PRODUCT_MAX_V1',
                    'BUYER_PROFILE_DISTANCE_V1')""",
                (context_id, SHA, "b" * 64, "c" * 64, NOW, NOW),
            )

    legacy_run_id = repository.create_search_run(
        campaign_name="legacy", targeting_context_id=context_id,
        modeling_context_sha256=SHA, targeting_criteria={},
        filter_branches=[{}], delivery_channel="EMAIL",
        export_profile="EMAIL_CONTACT_V1",
    )
    with get_connection(path, write=True) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """UPDATE campaign_search_runs
                   SET similarity_score_method_version='BUYER_PROFILE_DISTANCE_V1'
                   WHERE search_run_id=?""",
                (legacy_run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """UPDATE campaign_search_attempts
                   SET similarity_score_method_version='BUYER_PROFILE_DISTANCE_V1'
                   WHERE search_run_id=? AND attempt_number=1""",
                (legacy_run_id,),
            )

    with get_connection(path, write=True) as connection:
        imports = []
        for dataset in ("customers", "campaign_sales", "demographics"):
            imports.append(int(connection.execute(
                """INSERT INTO data_import_runs (
                    dataset_name,source_path,started_at,completed_at,status,
                    rows_read,rows_inserted,rows_rejected,source_checksum
                ) VALUES (?,?,?,?,'COMPLETED',1,1,0,?)""",
                (dataset, f"{dataset}.csv", NOW, NOW, SHA),
            ).lastrowid))
        values = (
            SHA, "PRD001", "b" * 64, "2025-01-01", "2025-12-31",
            "ATTRIBUTED_PURCHASE", imports[0], SHA, imports[1], SHA,
            "c" * 64, "BUYER_PROFILE_DISTANCE_V1", "d" * 64,
            "e" * 64, "f" * 64, 42, 200, 2, "PUBLISHED", NOW, NOW,
        )
        sql = """INSERT INTO buyer_similarity_profiles (
            immutable_identity_sha256,product_id,historical_context_sha256,
            resolved_window_start,resolved_window_end,buyer_conversion_definition,
            customer_import_id,customer_source_checksum,campaign_sales_import_id,
            campaign_sales_source_checksum,feature_contract_sha256,
            score_method_version,preprocessor_contract_sha256,fit_identity_sha256,
            holdout_identity_sha256,split_seed,prototype_support,realized_k,
            publication_state,created_at,published_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        profile_id = int(connection.execute(sql, values).lastrowid)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql, values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE buyer_similarity_profiles SET product_id='PRD002' WHERE profile_id=?",
                (profile_id,),
            )

        active_token = "1" * 64
        stale_token = "2" * 64
        generation_id = int(connection.execute(
            """INSERT INTO buyer_similarity_score_generations (
                profile_id,product_id,composite_context_sha256,profile_set_sha256,
                demographic_import_id,demographic_source_checksum,reference_date,
                scorer_contract_version,score_method_version,publication_state,
                expected_person_count,execution_owner,execution_token,
                lease_heartbeat_at,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,'BUILDING',1,?,?,?,?)""",
            (
                profile_id, "PRD001", "6" * 64, "7" * 64,
                imports[2], SHA, "2026-10-06", "1",
                BUYER_SIMILARITY_SCORE_METHOD_VERSION, "worker-1", active_token,
                NOW, NOW,
            ),
        ).lastrowid)
        stage_sql = """INSERT INTO buyer_similarity_score_stage (
            similarity_generation_id,person_id,is_valid,buyer_similarity_score,
            feature_coverage,prototype_key,invalid_reason_code,execution_token
        ) VALUES (?, 'P0001', 1, 0.91, 1.0, 'prototype-1', NULL, ?)"""
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(stage_sql, (generation_id, stale_token))
        connection.execute(stage_sql, (generation_id, active_token))

        published_sql = """INSERT INTO buyer_similarity_scores (
            similarity_generation_id,person_id,product_id,is_valid,
            buyer_similarity_score,similarity_tier,feature_coverage,prototype_key,
            invalid_reason_code,score_method_version,execution_token,published_at
        ) VALUES (?, 'P0001', 'PRD001', 1, 0.91, 'VERY_STRONG', 1.0,
                  'prototype-1', NULL, ?, ?, ?)"""
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                published_sql,
                (generation_id, BUYER_SIMILARITY_SCORE_METHOD_VERSION, stale_token, NOW),
            )
        connection.execute(
            published_sql,
            (generation_id, BUYER_SIMILARITY_SCORE_METHOD_VERSION, active_token, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """UPDATE buyer_similarity_scores SET buyer_similarity_score=0.92
                   WHERE similarity_generation_id=? AND person_id='P0001'""",
                (generation_id,),
            )


def test_v3_preflight_model_has_unknown_not_zero_contract() -> None:
    request = PotentialCustomerPreflightV3Request.model_validate({
        key: value for key, value in _v3_request().items()
        if key not in {"campaign_name", "export_profile", "description", "planned_launch_date"}
    })
    assert request.similarity_minimum == 0.70
    assert math.isfinite(request.similarity_minimum)


def test_v3_options_preflight_and_submission_are_explicit_and_probability_independent(
    client, database_path: Path,
) -> None:
    options_response = client.get("/api/potential-customer-search/options")
    assert options_response.status_code == 200
    options = options_response.json()
    similarity = options["targeting"]["buyer_similarity"]
    assert similarity == {
        "selection_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "score_method_version": "BUYER_PROFILE_DISTANCE_V1",
        "threshold_predicate": "GREATER_THAN_OR_EQUAL",
        "product_match_policy": "ANY_SELECTED_PRODUCT_MAX_V1",
        "default_minimum": 0.70,
        "minimums": [
            {"value": value, "label": label, "recommended": value == 0.70}
            for value, label in (
                (0.90, "Very Strong"), (0.80, "Strong"), (0.70, "Good"),
                (0.60, "Broad"), (0.50, "Exploratory"),
            )
        ],
        "readiness": "INDEPENDENT_FROM_PURCHASE_PROBABILITY",
        "build_available": True,
    }
    legacy = request_payload()
    criteria = dict(legacy["criteria"])
    for field in (
        "match_strength", "top_matching_percent", "selection_mode", "target_count"
    ):
        criteria.pop(field, None)
    payload = {
        **legacy,
        "criteria": criteria,
        "selection_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "similarity_minimum": 0.70,
        "selection_mode": "ALL_MATCHING",
        "top_n": None,
        "catalog_version": options["catalog_version"],
    }
    preflight = client.post(
        "/api/potential-customer-search/preflight",
        json={key: value for key, value in payload.items() if key not in {
            "campaign_name", "description", "planned_launch_date", "export_profile"
        }},
    )
    assert preflight.status_code == 200, preflight.text
    readiness = preflight.json()
    assert readiness["selection_contract_version"] == "3"
    assert readiness["demographic_eligible_count"] == 1
    assert readiness["similarity_currentness"] == "NOT_AVAILABLE"
    assert readiness["similarity_eligibility"] == "NOT_ELIGIBLE"
    assert readiness["valid_similarity_count"] is None
    assert readiness["similarity_qualifying_count"] is None
    assert readiness["selected_count"] is None
    assert readiness["build_available"] is True
    assert readiness["probability_currentness"] is None

    created = client.post("/api/potential-customer-search/runs", json=payload)
    assert created.status_code == 201, created.text
    status = created.json()
    assert status["selection_contract_version"] == "3"
    assert status["score_semantics"] == "PRODUCT_BUYER_SIMILARITY"
    assert status["similarity_minimum"] == 0.70
    assert status["status"] == "QUEUED"
    with get_connection(database_path) as connection:
        run = connection.execute(
            "SELECT * FROM campaign_search_runs WHERE search_run_id=?",
            (status["search_run_id"],),
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM campaign_search_attempts WHERE search_run_id=?",
            (status["search_run_id"],),
        ).fetchone()
    assert run["propensity_bucket"] is None
    assert run["calibration_artifact_id"] is None
    assert attempt["propensity_bucket"] is None
    assert attempt["score_semantics"] == "PRODUCT_BUYER_SIMILARITY"
    history = client.get("/api/potential-customer-search/results").json()
    assert history[0]["selection_contract_version"] == "3"
    assert history[0]["selection_label"] == "Buyer Similarity"
    assert history[0]["selection_semantics"] == "PRODUCT_BUYER_SIMILARITY"
    assert history[0]["selection_value"] == "70% or higher"
    detail = client.get(
        f"/api/potential-customer-search/runs/{status['search_run_id']}/result"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["similarity_minimum"] == 0.70
    repository = CampaignResultRegistryRepository(database_path)
    fence = repository.claim_search_attempt(
        status["search_run_id"], lease_owner="v3-contract-test"
    )
    repository.fail_search_run(
        status["search_run_id"], **fence.as_kwargs(), blocked=True,
        failure_code="SIMILARITY_NOT_PREPARED",
        failure_category="BUYER_SIMILARITY",
        failure_summary="Buyer-similarity intelligence is not prepared.",
        resolution_steps=("Retry after preparation capacity is available.",),
        retryable=True,
    )
    retried = client.post(
        f"/api/potential-customer-search/runs/{status['search_run_id']}/retry",
        headers={"Idempotency-Key": "v3-retry-contract-0001"},
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["attempt_number"] == 2
    assert retried.json()["status"] == "QUEUED"
    with get_connection(database_path) as connection:
        retry_attempt = connection.execute(
            """SELECT * FROM campaign_search_attempts
               WHERE search_run_id=? AND attempt_number=2""",
            (status["search_run_id"],),
        ).fetchone()
    assert retry_attempt["selection_contract_version"] == "3"
    assert retry_attempt["propensity_bucket"] is None
    assert retry_attempt["similarity_minimum"] == 0.70
