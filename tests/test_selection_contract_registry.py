"""Cross-layer consistency checks for the approved v2 selection contract."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.selection_contracts import (
    CALIBRATED_SELECTION_CONTRACT_VERSION,
    DEFAULT_PROPENSITY_BUCKET,
    DEMO_QUALIFICATION_MINIMUM,
    PROPENSITY_BUCKET_DEFINITIONS,
    PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH,
    PROPENSITY_BUCKET_KEYS,
    PROPENSITY_BUCKET_REGISTRY,
)
from app.services import potential_customer_preflight_service
from app.services.calibrated_selection_contract_service import (
    propensity_bucket_bounds,
    propensity_bucket_case_sql,
)
from app.services.phase11_results_service import PROPENSITY_BUCKET_LABELS


def test_v2_registry_matches_runtime_bounds_labels_and_demo_policy() -> None:
    assert CALIBRATED_SELECTION_CONTRACT_VERSION == "2"
    assert DEFAULT_PROPENSITY_BUCKET == "0.70"
    assert DEMO_QUALIFICATION_MINIMUM == 10_000
    assert PROPENSITY_BUCKET_KEYS == ("0.90", "0.80", "0.70", "0.60", "0.50")
    assert PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH == {
        definition.legacy_match_strength: definition.key
        for definition in PROPENSITY_BUCKET_DEFINITIONS
    }
    for definition in PROPENSITY_BUCKET_DEFINITIONS:
        assert propensity_bucket_bounds(definition.key) == (
            definition.minimum,
            definition.maximum,
            definition.maximum_inclusive,
        )
        assert PROPENSITY_BUCKET_LABELS[definition.key] == definition.result_label
    assert "DEMO_QUALIFICATION_MINIMUM" in inspect.getsource(
        potential_customer_preflight_service
    )
    sql = propensity_bucket_case_sql("probability")
    assert all(key in sql for key in PROPENSITY_BUCKET_KEYS)


def test_fresh_schema_bucket_checks_match_registry(tmp_path: Path) -> None:
    path = initialize_database(tmp_path / "selection-contract.db")
    with get_connection(path) as connection:
        definitions = {
            row["name"]: row["sql"]
            for row in connection.execute(
                """SELECT name,sql FROM sqlite_master
                   WHERE type='table' AND name IN (
                       'campaign_search_attempts','calibrated_propensity_scores'
                   )"""
            )
        }
    assert set(definitions) == {
        "campaign_search_attempts",
        "calibrated_propensity_scores",
    }
    for definition in definitions.values():
        assert all(f"'{key}'" in definition for key in PROPENSITY_BUCKET_REGISTRY)


def test_frontend_does_not_redefine_probability_ranges() -> None:
    source = Path("frontend/js/business-search-form.js").read_text(encoding="utf-8")
    for definition in PROPENSITY_BUCKET_DEFINITIONS:
        assert definition.display_label not in source
        assert definition.result_label not in source


def test_demo_preflight_uses_registry_legacy_mapping() -> None:
    source = Path(
        "scripts/validation/preflight_demo_readiness_scenarios.py"
    ).read_text(encoding="utf-8")
    assert "PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH" in source
    assert '"VERY_STRONG": "0.90"' not in source
