from __future__ import annotations

import hashlib
import json

import pytest

from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import MODEL_ROLE_POLICY_VERSION
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION,
    PHASE10_LIFECYCLE_POLICY_VERSION,
    PHASE10_MODELING_CONTEXT_CONTRACT_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_ORCHESTRATION_CONTRACT_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
)
from app.services.campaign_targeting_contract_service import (
    normalize_campaign_targeting_context,
)
from app.services.phase10_context_identity_service import (
    Phase10ContextIdentityError,
    build_historical_compatibility_fingerprint,
    build_model_compatibility_fingerprint,
    build_scoring_compatibility_fingerprint,
    derive_modeling_context_from_campaign_context,
    normalize_modeling_context,
    validate_current_modeling_context_policy,
)


def _campaign_context() -> dict[str, object]:
    return {
        "campaign_name": "Autumn retention",
        "description": "Business-only copy",
        "planned_launch_date": "2026-10-15",
        "product_ids": ["PRD002", "PRD001", "PRD002"],
        "campaign_types": ["Retention", "Cross-sell"],
        "campaign_categories": ["Retention Offer", "Cross-sell Promotion"],
        "offer_types": ["Percent Discount", "Bundle Offer"],
        "campaign_channel": "EMAIL",
        "historical_campaign_channels": ["Paid Social", "Email"],
        "match_strength": "VERY_STRONG",
        "age_groups": ["25-34"],
        "states": ["California"],
        "selection_mode": "TOP_N",
        "target_count": 500,
        "target_group_name": "Priority customers",
    }


def _resolved_filters() -> dict[str, object]:
    return {
        "campaign_ids": [],
        "product_ids": ["PRD001", "PRD002"],
        "product_categories": [],
        "campaign_categories": ["Cross-sell Promotion", "Retention Offer"],
        "offer_types": ["Bundle Offer", "Percent Discount"],
        "campaign_channels": ["Email", "Paid Social"],
        "campaign_types": ["Cross-sell", "Retention"],
        "contact_date_from": "2024-01-01",
        "contact_date_to": "2025-12-31",
        "contacted_only": True,
        "conversion_definition": "ATTRIBUTED_PURCHASE",
    }


def _historical_fingerprint():
    return build_historical_compatibility_fingerprint(
        modeling_context=derive_modeling_context_from_campaign_context(
            _campaign_context()
        ),
        resolved_historical_filters=_resolved_filters(),
        customer_source_checksum="a" * 64,
        campaign_sales_source_checksum="b" * 64,
    )


def _model_fingerprint(**overrides):
    values = {
        "historical_fingerprint": _historical_fingerprint(),
        "analysis_run_id": 7,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
    }
    values.update(overrides)
    return build_model_compatibility_fingerprint(**values)


def test_phase10_policy_versions_are_explicit_and_frozen_at_v1() -> None:
    assert PHASE10_MODELING_CONTEXT_CONTRACT_VERSION == "1"
    assert PHASE10_COMPATIBILITY_CONTRACT_VERSION == "1"
    assert PHASE10_HISTORICAL_WINDOW_POLICY_VERSION == "1"
    assert PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION == "1"
    assert PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION == "1"
    assert PHASE10_AUTOMATED_TRAINING_POLICY_VERSION == "1"
    assert PHASE10_ORCHESTRATION_CONTRACT_VERSION == "1"
    assert PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION == "1"
    assert PHASE10_LIFECYCLE_POLICY_VERSION == "1"


def test_modeling_context_is_order_insensitive_compact_utf8_and_hashed() -> None:
    first = derive_modeling_context_from_campaign_context(_campaign_context())
    reordered = _campaign_context()
    reordered["product_ids"] = [" PRD001 ", "PRD002"]
    reordered["campaign_types"] = ["Cross-sell", "Retention", "Cross-sell"]
    reordered["historical_campaign_channels"] = ["Email", "Paid Social", "Email"]
    second = derive_modeling_context_from_campaign_context(reordered)

    assert first.payload == second.payload
    assert first.modeling_context_sha256 == second.modeling_context_sha256
    assert first.canonical_json == json.dumps(
        first.payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert '": ' not in first.canonical_json
    assert '", ' not in first.canonical_json
    assert first.modeling_context_sha256 == hashlib.sha256(
        first.canonical_json.encode("utf-8")
    ).hexdigest()
    assert first.payload["conversion_definition"] == "ATTRIBUTED_PURCHASE"
    assert first.payload["contacted_only"] is True


def test_campaign_and_targeting_fields_are_excluded_but_phase9_hash_is_unchanged() -> None:
    email = _campaign_context()
    direct_mail = {
        **email,
        "campaign_name": "Different campaign",
        "description": "Different description",
        "planned_launch_date": "2027-01-01",
        "campaign_channel": "DIRECT_MAIL",
        "match_strength": "BROAD",
        "age_groups": ["65-74"],
        "states": ["Texas"],
        "selection_mode": "ALL_MATCHING",
        "target_count": None,
        "target_group_name": "Different group",
    }

    email_modeling = derive_modeling_context_from_campaign_context(email)
    mail_modeling = derive_modeling_context_from_campaign_context(direct_mail)
    assert email_modeling.modeling_context_sha256 == mail_modeling.modeling_context_sha256
    assert "campaign_channel" not in email_modeling.payload
    assert "campaign_name" not in email_modeling.payload
    assert "match_strength" not in email_modeling.payload

    allowed = {
        "product_ids": {"PRD001", "PRD002"},
        "campaign_types": {"Cross-sell", "Retention"},
        "campaign_categories": {"Cross-sell Promotion", "Retention Offer"},
        "offer_types": {"Bundle Offer", "Percent Discount"},
        "campaign_channels": {"Email", "Paid Social"},
    }
    phase9_email = normalize_campaign_targeting_context(
        {
            key: email[key]
            for key in (
                "product_ids",
                "campaign_types",
                "campaign_categories",
                "offer_types",
                "campaign_channel",
                "historical_campaign_channels",
            )
        },
        allowed_values=allowed,
    )
    phase9_mail = normalize_campaign_targeting_context(
        {
            key: direct_mail[key]
            for key in (
                "product_ids",
                "campaign_types",
                "campaign_categories",
                "offer_types",
                "campaign_channel",
                "historical_campaign_channels",
            )
        },
        allowed_values=allowed,
    )
    assert phase9_email.sha256 != phase9_mail.sha256
    assert phase9_email.sha256 != email_modeling.modeling_context_sha256


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("product_ids", ["PRD003"]),
        ("campaign_types", ["Acquisition"]),
        ("campaign_categories", ["Welcome"]),
        ("offer_types", ["Free Gift"]),
        ("historical_campaign_channels", ["Direct Mail"]),
        ("conversion_definition", "ANY_PURCHASE"),
        ("contacted_only", False),
        ("historical_window_policy_version", "2"),
        ("multi_product_positive_policy_version", "2"),
        ("modeling_context_contract_version", "2"),
    ),
)
def test_modeling_dimensions_and_policy_versions_change_hash(
    field: str,
    replacement: object,
) -> None:
    baseline = derive_modeling_context_from_campaign_context(_campaign_context())
    changed_payload = {**baseline.payload, field: replacement}
    changed = normalize_modeling_context(changed_payload)
    assert changed.modeling_context_sha256 != baseline.modeling_context_sha256


def test_current_policy_validation_rejects_historical_policy_identity() -> None:
    baseline = derive_modeling_context_from_campaign_context(_campaign_context())
    validate_current_modeling_context_policy(baseline)
    changed = normalize_modeling_context(
        {**baseline.payload, "historical_window_policy_version": "2"}
    )
    with pytest.raises(Phase10ContextIdentityError, match="not current"):
        validate_current_modeling_context_policy(changed)


def test_historical_fingerprint_is_exact_and_order_insensitive() -> None:
    first = _historical_fingerprint()
    reordered = _resolved_filters()
    reordered["product_ids"] = ["PRD002", "PRD001", "PRD002"]
    reordered["campaign_channels"] = ["Paid Social", "Email"]
    second = build_historical_compatibility_fingerprint(
        modeling_context=derive_modeling_context_from_campaign_context(
            _campaign_context()
        ),
        resolved_historical_filters=reordered,
        customer_source_checksum="A" * 64,
        campaign_sales_source_checksum="B" * 64,
    )
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.payload["modeling_context_sha256"] == (
        derive_modeling_context_from_campaign_context(
            _campaign_context()
        ).modeling_context_sha256
    )

    changed_filters = {**_resolved_filters(), "contact_date_to": "2025-11-30"}
    changed_window = build_historical_compatibility_fingerprint(
        modeling_context=derive_modeling_context_from_campaign_context(
            _campaign_context()
        ),
        resolved_historical_filters=changed_filters,
        customer_source_checksum="a" * 64,
        campaign_sales_source_checksum="b" * 64,
    )
    changed_source = build_historical_compatibility_fingerprint(
        modeling_context=derive_modeling_context_from_campaign_context(
            _campaign_context()
        ),
        resolved_historical_filters=_resolved_filters(),
        customer_source_checksum="c" * 64,
        campaign_sales_source_checksum="b" * 64,
    )
    assert changed_window.fingerprint_sha256 != first.fingerprint_sha256
    assert changed_source.fingerprint_sha256 != first.fingerprint_sha256


def test_historical_fingerprint_rejects_context_filter_mismatch() -> None:
    mismatched = {**_resolved_filters(), "offer_types": ["Wrong offer"]}
    with pytest.raises(Phase10ContextIdentityError, match="do not match"):
        build_historical_compatibility_fingerprint(
            modeling_context=derive_modeling_context_from_campaign_context(
                _campaign_context()
            ),
            resolved_historical_filters=mismatched,
            customer_source_checksum="a" * 64,
            campaign_sales_source_checksum="b" * 64,
        )


@pytest.mark.parametrize(
    "override",
    (
        {"analysis_run_id": 8},
        {"feature_contract_version": "2"},
        {"feature_contract_sha256": "c" * 64},
        {"model_role_policy_version": "3"},
        {"evaluation_contract_version": "3"},
        {"training_eligibility_policy_version": "2"},
        {"automated_training_policy_version": "2"},
        {"random_seed": 43},
        {"validation_fraction": 0.25},
        {"run_elkan_challenger": False},
    ),
)
def test_model_fingerprint_changes_with_lineage_or_training_policy(override) -> None:
    assert _model_fingerprint(**override).fingerprint_sha256 != (
        _model_fingerprint().fingerprint_sha256
    )


@pytest.mark.parametrize(
    "override",
    (
        {"model_run_id": 8},
        {"artifact_sha256": "d" * 64},
        {"demographic_source_checksum": "e" * 64},
        {"demographic_count": 4_999_999},
        {
            "score_semantics": {
                "minimum_score": 0.0,
                "maximum_score": 1.0,
                "higher_is_better": True,
                "ordering": "propensity_score DESC, person_id DESC",
                "full_canonical_universe_required": True,
            }
        },
    ),
)
def test_scoring_fingerprint_changes_with_model_artifact_source_or_semantics(
    override,
) -> None:
    values = {
        "model_fingerprint": _model_fingerprint(),
        "model_run_id": 7,
        "artifact_sha256": "c" * 64,
        "demographic_source_checksum": "d" * 64,
        "demographic_count": 5_000_000,
    }
    baseline = build_scoring_compatibility_fingerprint(**values)
    values.update(override)
    changed = build_scoring_compatibility_fingerprint(**values)
    assert changed.fingerprint_sha256 != baseline.fingerprint_sha256


def test_fingerprints_reject_invalid_hash_and_wrong_layer() -> None:
    historical = _historical_fingerprint()
    with pytest.raises(Phase10ContextIdentityError, match="valid SHA-256"):
        build_model_compatibility_fingerprint(
            historical_fingerprint=historical,
            analysis_run_id=7,
            feature_contract_version="1",
            feature_contract_sha256="not-a-hash",
            model_role_policy_version="2",
            evaluation_contract_version="2",
        )
    with pytest.raises(Phase10ContextIdentityError, match="model compatibility"):
        build_scoring_compatibility_fingerprint(
            model_fingerprint=historical,
            model_run_id=7,
            artifact_sha256="c" * 64,
            demographic_source_checksum="d" * 64,
            demographic_count=5_000_000,
        )
