"""Stage 14B_00 golden characterization of frozen v1/v2 behavior."""

from __future__ import annotations

import asyncio
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION
from app.main import app
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.schemas.potential_customer_search import (
    PotentialCustomerPreflightRequest,
    SearchResultHistoryItem,
)
from app.selection_contracts import (
    CALIBRATED_MEMBERSHIP_CONTRACT_VERSION,
    CALIBRATED_SELECTION_CONTRACT_VERSION,
    CALIBRATED_SELECTION_SEMANTICS,
    DEFAULT_PROPENSITY_BUCKET,
    DEMO_QUALIFICATION_MINIMUM,
    PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH,
    PROPENSITY_BUCKET_DEFINITIONS,
)
from app.services import phase11_export_service
from app.services import potential_customer_search_submission_service as submission
from app.services.phase11_result_contracts import RESULT_MEMBERSHIP_COLUMNS
from app.services.phase11_results_service import get_result_detail
from scripts.validation.audit_14b_00_baseline import (
    _disposable_schema_observations,
)
from tests.test_phase11_business_search_form import OPTIONS, RUNS, request_payload
from tests.test_phase11_omnichannel_export_engine import (
    NeverDisconnected,
)


pytest_plugins = (
    "tests.test_phase11_business_search_form",
    "tests.test_phase11_omnichannel_export_engine",
    "tests.test_phase11_search_result_registry",
)


FIXTURE_PATH = Path(
    "tests/fixtures/lookalike_v3/14b_00_legacy_contract_golden.json"
)


def _golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _boundary_value(label: str) -> float:
    if label == "nextafter(0.60,0)":
        return math.nextafter(0.60, 0.0)
    return float(label)


def _golden_bucket(value: object, definitions: dict[str, dict]) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Probability must be a finite number.")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("Probability must be finite and between zero and one.")
    for key in ("0.90", "0.80", "0.70", "0.60", "0.50"):
        definition = definitions[key]
        if number < definition["minimum"]:
            continue
        if number < definition["maximum"] or (
            definition["maximum_inclusive"] and number == definition["maximum"]
        ):
            return key
    return None


def test_literal_v1_v2_contracts_and_independent_boundary_oracle() -> None:
    golden = _golden()
    # The immutable Stage-00 golden records its observed schema.  Later
    # additive stages may advance code schema without rewriting that evidence.
    assert golden["schema_version"] == 31
    assert CURRENT_SCHEMA_VERSION >= golden["schema_version"]
    assert CALIBRATED_SELECTION_CONTRACT_VERSION == golden["v2"][
        "selection_contract_version"
    ]
    assert CALIBRATED_MEMBERSHIP_CONTRACT_VERSION == golden["v2"][
        "membership_contract_version"
    ]
    assert CALIBRATED_SELECTION_SEMANTICS == golden["v2"]["selection_semantics"]
    assert DEFAULT_PROPENSITY_BUCKET == golden["v2"]["default_bucket"] == "0.70"
    assert DEMO_QUALIFICATION_MINIMUM == golden["policy"][
        "demo_qualification_minimum"
    ] == 10_000
    assert list(RESULT_MEMBERSHIP_COLUMNS) == golden["v1"]["membership_columns"]
    assert PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH == golden["v2"][
        "legacy_to_bucket"
    ]
    assert PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH["BROAD"] == "0.60"

    runtime = {
        definition.key: {
            "minimum": definition.minimum,
            "maximum": definition.maximum,
            "maximum_inclusive": definition.maximum_inclusive,
            "legacy_match_strength": definition.legacy_match_strength,
        }
        for definition in PROPENSITY_BUCKET_DEFINITIONS
    }
    assert runtime == golden["v2"]["buckets"]
    for example in golden["v2"]["boundary_oracle"]:
        assert _golden_bucket(
            _boundary_value(example["value"]), golden["v2"]["buckets"]
        ) == example["bucket"]

    invalid = (math.nan, math.inf, -math.inf, True, False, -0.01, 1.0000000001)
    for value in invalid:
        with pytest.raises(ValueError):
            _golden_bucket(value, golden["v2"]["buckets"])


def test_all_twenty_scenario_hashes_and_distribution_are_frozen() -> None:
    golden = _golden()["scenarios"]
    path = Path(golden["path"])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == golden["file_sha256"]
    scenarios = json.loads(raw)["scenarios"]
    assert len(scenarios) == golden["count"] == 20
    assert Counter(item["match_strength"] for item in scenarios) == Counter(
        golden["strength_distribution"]
    )
    assert {
        str(item["id"]): _canonical_sha256(item) for item in scenarios
    } == golden["scenario_sha256"]


def test_disposable_schema_31_identity_is_stable_and_idempotent() -> None:
    expected = _golden()["disposable_schema_31"]
    if CURRENT_SCHEMA_VERSION != 31:
        # Stage-00 evidence is immutable historical characterization.  The
        # active schema is certified by its own forward-migration suite.
        assert _golden()["schema_version"] == 31
        assert expected["integrity_check"] == "ok"
        assert expected["foreign_key_violations"] == 0
        return
    observed = _disposable_schema_observations()
    assert observed["stored_schema_version"] == CURRENT_SCHEMA_VERSION
    assert observed["initialize_idempotent"] is True
    for key, value in expected.items():
        assert observed[key] == value


def test_unversioned_http_remains_v1_and_v2_is_explicit(
    client, database_path: Path, monkeypatch,
) -> None:
    golden = _golden()
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)

    legacy_response = client.post(RUNS, json=request_payload())
    assert legacy_response.status_code == 201, legacy_response.text
    legacy = legacy_response.json()
    assert set(legacy) == set(golden["unversioned_http"]["response_fields"])
    legacy_row = CampaignResultRegistryRepository(database_path).fetch_search_run(
        legacy["search_run_id"]
    )
    assert legacy_row["selection_contract_version"] == "1"
    assert legacy_row["propensity_bucket"] is None
    legacy_detail = get_result_detail(database_path, legacy["search_run_id"])
    assert legacy_detail["selection_contract_version"] == "1"
    assert legacy_detail["propensity_bucket"] is None
    assert legacy_detail["selection_semantics"] == golden["v1"][
        "selection_semantics"
    ]
    assert legacy_detail["selection_label"] == golden["v1"]["selection_label"]

    options = client.get(OPTIONS).json()
    assert options["targeting"]["default_propensity_bucket"] == "0.70"
    assert {
        item["value"]: {
            "minimum": item["minimum"],
            "maximum": item["maximum"],
            "maximum_inclusive": item["maximum_inclusive"],
            "legacy_match_strength": item["legacy_match_strength"],
        }
        for item in options["targeting"]["propensity_buckets"]
    } == golden["v2"]["buckets"]

    for bucket, bounds in golden["v2"]["buckets"].items():
        payload = request_payload() | {
            "campaign_name": f"Golden v2 {bucket}",
            "propensity_bucket": bucket,
            "catalog_version": options["catalog_version"],
        }
        response = client.post(RUNS, json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["selection_contract_version"] == "2"
        assert body["propensity_bucket"] == bucket
        with get_connection(database_path) as connection:
            attempt = connection.execute(
                """SELECT selection_contract_version,propensity_bucket,
                          bucket_minimum,bucket_maximum,bucket_maximum_inclusive
                   FROM campaign_search_attempts
                   WHERE search_run_id=? AND attempt_number=1""",
                (body["search_run_id"],),
            ).fetchone()
        assert tuple(attempt) == (
            "2",
            bucket,
            bounds["minimum"],
            bounds["maximum"],
            int(bounds["maximum_inclusive"]),
        )
        detail = get_result_detail(database_path, body["search_run_id"])
        assert detail["selection_contract_version"] == "2"
        assert detail["selection_semantics"] == golden["v2"][
            "selection_semantics"
        ]
        assert detail["selection_label"] == golden["v2"]["selection_label"]


def test_openapi_currentness_and_invalid_bucket_inputs_are_frozen() -> None:
    golden = _golden()
    schemas = app.openapi()["components"]["schemas"]
    legacy_fields = set(golden["unversioned_http"]["response_fields"])
    assert set(schemas["SearchSubmissionStatus"]["properties"]) == legacy_fields
    assert set(schemas["SearchSubmissionV2Status"]["properties"]) == (
        legacy_fields | set(golden["v2_http"]["additional_response_fields"])
    )
    currentness_schema = SearchResultHistoryItem.model_json_schema()["properties"][
        "currentness"
    ]
    assert set(currentness_schema["enum"]) == set(
        golden["policy"]["currentness_vocabulary"]
    )
    for value in golden["v2"]["invalid_bucket_values"]:
        with pytest.raises(ValidationError):
            PotentialCustomerPreflightRequest.model_validate(
                {
                    "context": {},
                    "criteria": {},
                    "propensity_bucket": value,
                }
            )


def test_historical_v1_snapshot_and_export_readback_remain_legacy(export_case) -> None:
    golden = _golden()["v1"]
    db_path, repository, snapshot_id, runs = export_case
    run_id = runs["EMAIL_CONTACT_V1"]
    run = repository.fetch_search_run(run_id)
    snapshot = repository.fetch_snapshot(snapshot_id)
    assert run["selection_contract_version"] == "1"
    assert snapshot["result_membership_contract_version"] == golden[
        "membership_contract_version"
    ]

    response = phase11_export_service.stream_phase11_result_export_csv(
        db_path,
        search_run_id=run_id,
        request=NeverDisconnected(),
        project_root=db_path.parent,
    )

    async def consume() -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        return b"".join(chunks)

    body = asyncio.run(consume())
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    assert rows
    assert response.headers["x-result-membership-contract-version"] == "1"
    assert response.headers["x-export-score-semantics"] == golden[
        "export_score_semantics"
    ]
