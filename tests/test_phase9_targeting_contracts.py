from __future__ import annotations

import json

import pytest

from app.schemas.campaign_targeting import (
    AGE_BUCKET_CONTRACT_VERSION,
    AGE_BUCKETS,
    BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION,
    CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION,
    INCOME_GROUP_CONTRACT_VERSION,
    INCOME_GROUPS,
    MATCH_SCORE_BANDS,
    MATCH_STRENGTH_THRESHOLDS,
    TARGETING_SEGMENT_CONTRACT_VERSION,
)
from app.services.campaign_targeting_contract_service import (
    CampaignTargetingContractValidationError,
    normalize_business_targeting_criteria,
    normalize_campaign_targeting_context,
)


REFERENCE_VALUES = {
    "product_ids": {"PRD-001", "PRD-002"},
    "campaign_types": {"Promotion", "Retention"},
    "campaign_categories": {"Seasonal", "Lifecycle"},
    "offer_types": {"Discount", "Loyalty"},
    "campaign_channels": {"Email", "Direct Mail"},
    "gender": {"Female", "Male", "Unknown/Other"},
    "state": {"California", "Ohio", "Texas"},
    "marital_status": {"Married", "Single"},
    "education": {"Graduate", "High School"},
    "employment_status": {"Employed", "Retired"},
    "resident_status": {"Owner", "Renter"},
    "resident_type": {"House", "Apartment"},
    "type_of_employment": {"Salaried", "Self-employed"},
}


def test_versioned_threshold_and_bucket_contracts_are_exact() -> None:
    assert TARGETING_SEGMENT_CONTRACT_VERSION == "1"
    assert CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION == "1"
    assert BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION == "1"
    assert AGE_BUCKET_CONTRACT_VERSION == "1"
    assert INCOME_GROUP_CONTRACT_VERSION == "1"
    assert MATCH_STRENGTH_THRESHOLDS == {
        "VERY_STRONG": 0.90,
        "STRONG": 0.80,
        "GOOD": 0.70,
        "BROAD": 0.60,
    }
    assert [(band.minimum, band.maximum, band.maximum_inclusive) for band in MATCH_SCORE_BANDS] == [
        (0.90, 1.00, True),
        (0.80, 0.90, False),
        (0.70, 0.80, False),
        (0.60, 0.70, False),
        (0.00, 0.60, False),
    ]
    assert [band.value for band in AGE_BUCKETS] == [
        "18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"
    ]
    assert [band.value for band in INCOME_GROUPS] == [
        "<25K",
        "25K-49,999",
        "50K-74,999",
        "75K-99,999",
        "100K-149,999",
        "150K-249,999",
        "250K+",
    ]


def test_campaign_context_is_trimmed_deduplicated_sorted_and_deterministic() -> None:
    first = normalize_campaign_targeting_context(
        {
            "product_ids": [" PRD-002 ", "PRD-001", "PRD-002"],
            "campaign_types": ["Retention", " Promotion "],
            "campaign_categories": ["Seasonal"],
            "offer_types": ["Discount", "Discount"],
            "campaign_channel": " email ",
            "historical_campaign_channels": ["Email"],
        },
        allowed_values=REFERENCE_VALUES,
    )
    repeated = normalize_campaign_targeting_context(
        {
            "offer_types": ["Discount"],
            "campaign_categories": ["Seasonal"],
            "campaign_types": ["Promotion", "Retention"],
            "product_ids": ["PRD-001", "PRD-002"],
            "historical_campaign_channels": ["Email"],
            "campaign_channel": "EMAIL",
        },
        allowed_values=REFERENCE_VALUES,
    )

    assert first.payload["product_ids"] == ["PRD-001", "PRD-002"]
    assert first.payload["campaign_types"] == ["Promotion", "Retention"]
    assert first.payload["campaign_channel"] == "EMAIL"
    assert first.canonical_json == repeated.canonical_json
    assert first.sha256 == repeated.sha256
    assert len(first.sha256) == 64
    assert json.loads(first.canonical_json) == first.payload


def test_campaign_context_rejects_unknown_references_and_extra_fields() -> None:
    base = {
        "product_ids": ["PRD-001"],
        "campaign_types": [],
        "campaign_categories": [],
        "offer_types": [],
        "campaign_channel": "EMAIL",
    }
    with pytest.raises(
        CampaignTargetingContractValidationError, match="no longer available"
    ):
        normalize_campaign_targeting_context(
            {**base, "product_ids": ["PRD-UNKNOWN"]},
            allowed_values=REFERENCE_VALUES,
        )
    with pytest.raises(
        CampaignTargetingContractValidationError,
        match="Review the campaign context choices",
    ):
        normalize_campaign_targeting_context(
            {**base, "unversioned_option": True},
            allowed_values=REFERENCE_VALUES,
        )


def test_business_targeting_maps_disjoint_buckets_without_widening() -> None:
    normalized = normalize_business_targeting_criteria(
        {
            "match_strength": " strong ",
            "genders": ["Female", "Female"],
            "states": ["Texas", "California"],
            "age_groups": ["35-44", "18-24"],
            "income_groups": ["50K-74,999", "<25K"],
            "selection_mode": "TOP_N",
            "target_count": 500,
        },
        allowed_values=REFERENCE_VALUES,
    )

    assert normalized.payload["match_strength"] == "STRONG"
    assert normalized.payload["age_groups"] == ["18-24", "35-44"]
    assert normalized.payload["income_groups"] == ["<25K", "50K-74,999"]
    assert normalized.audience_selection == {"mode": "TOP_N", "target_count": 500}
    assert len(normalized.audience_filter_branches) == 4
    mapped_ranges = {
        (
            branch["age_min"],
            branch["age_max"],
            branch["individual_yearly_income_min"],
            branch["individual_yearly_income_max"],
        )
        for branch in normalized.audience_filter_branches
    }
    assert mapped_ranges == {
        (18, 24, 0, 24_999),
        (18, 24, 50_000, 74_999),
        (35, 44, 0, 24_999),
        (35, 44, 50_000, 74_999),
    }
    for branch in normalized.audience_filter_branches:
        assert branch["score_min"] == 0.80
        assert branch["gender"] == ["Female"]
        assert branch["state"] == ["California", "Texas"]


def test_adjacent_buckets_collapse_only_when_union_is_contiguous() -> None:
    normalized = normalize_business_targeting_criteria(
        {
            "age_groups": ["18-24", "25-34"],
            "income_groups": ["25K-49,999", "50K-74,999"],
        },
        allowed_values=REFERENCE_VALUES,
    )

    assert len(normalized.audience_filter_branches) == 1
    branch = normalized.audience_filter_branches[0]
    assert (branch["age_min"], branch["age_max"]) == (18, 34)
    assert (
        branch["individual_yearly_income_min"],
        branch["individual_yearly_income_max"],
    ) == (25_000, 74_999)


def test_targeting_canonicalization_is_order_independent_and_validated() -> None:
    first = normalize_business_targeting_criteria(
        {"states": ["Texas", "California"], "age_groups": ["35-44", "18-24"]},
        allowed_values=REFERENCE_VALUES,
    )
    repeated = normalize_business_targeting_criteria(
        {"age_groups": ["18-24", "35-44"], "states": ["California", "Texas"]},
        allowed_values=REFERENCE_VALUES,
    )
    assert first.canonical_json == repeated.canonical_json
    assert first.sha256 == repeated.sha256

    with pytest.raises(
        CampaignTargetingContractValidationError, match="no longer available"
    ):
        normalize_business_targeting_criteria(
            {"states": ["Atlantis"]},
            allowed_values=REFERENCE_VALUES,
        )
    with pytest.raises(
        CampaignTargetingContractValidationError,
        match="Enter a whole number greater than zero",
    ):
        normalize_business_targeting_criteria(
            {"selection_mode": "TOP_N"},
            allowed_values=REFERENCE_VALUES,
        )
