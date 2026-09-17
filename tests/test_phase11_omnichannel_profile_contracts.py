from __future__ import annotations

from types import MappingProxyType

import pytest

from app.database.schema import DEMOGRAPHIC_COLUMNS
from app.ml.feature_contract import ORDERED_FEATURES
from app.services.campaign_contracts import (
    CAMPAIGN_CHANNELS,
    DIRECT_MAIL_EXPORT_COLUMNS,
    EMAIL_EXPORT_COLUMNS,
    PROFILE_EXPORT_COLUMNS,
    PROFILE_PROHIBITED_FIELDS,
    PROHIBITED_EXPORT_FIELDS,
)
from app.services.omnichannel_profile_contracts import (
    BASE_EXPORT_COLUMNS,
    CAMPAIGN_CHANNEL_DIRECT_MAIL,
    CAMPAIGN_CHANNEL_DISPLAY,
    CAMPAIGN_CHANNEL_EMAIL,
    CAMPAIGN_CHANNEL_MOBILE_PUSH,
    CAMPAIGN_CHANNEL_PAID_SEARCH,
    CAMPAIGN_CHANNEL_PAID_SOCIAL,
    CAMPAIGN_CHANNEL_SMS,
    CAMPAIGN_CHANNEL_TELEMARKETING,
    CAMPAIGN_CHANNEL_WEBSITE_ONSITE,
    CAMPAIGN_CHANNEL_WHATSAPP,
    CHANNEL_OMNICHANNEL_PROFILE,
    COMMON_PROHIBITED_EXPORT_FIELDS,
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    EXPORT_PROFILE_DISPLAY_AUDIENCE_V1,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
    EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
    EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
    EXPORT_PROFILE_SMS_CONTACT_V1,
    EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
    EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
    EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
    OMNICHANNEL_AUDIT_FIELDS,
    OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION,
    OMNICHANNEL_PROFILE_REGISTRY,
    PROFILE_AVAILABILITY_AVAILABLE,
    PROFILE_AVAILABILITY_MISSING_CONSENT,
    PROFILE_AVAILABILITY_MISSING_IDENTIFIER,
    PROFILE_RELEASE_GATED,
    PROFILE_RELEASE_IMMEDIATE,
    build_profile_filename,
    get_omnichannel_profile,
    get_omnichannel_profile_for_channel,
    is_profile_row_deliverable,
    mitigate_csv_formula_injection,
    normalize_email_identifier,
    normalize_us_phone_identifier,
    paid_media_match_keys,
    project_profile_row,
    resolve_profile_availability,
)


EXPECTED_PROFILES_BY_CHANNEL = {
    CAMPAIGN_CHANNEL_EMAIL: EXPORT_PROFILE_EMAIL_CONTACT_V1,
    CAMPAIGN_CHANNEL_DIRECT_MAIL: EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    CAMPAIGN_CHANNEL_SMS: EXPORT_PROFILE_SMS_CONTACT_V1,
    CAMPAIGN_CHANNEL_WHATSAPP: EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
    CAMPAIGN_CHANNEL_TELEMARKETING: EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
    CAMPAIGN_CHANNEL_PAID_SOCIAL: EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
    CAMPAIGN_CHANNEL_PAID_SEARCH: EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    CAMPAIGN_CHANNEL_MOBILE_PUSH: EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
    CAMPAIGN_CHANNEL_DISPLAY: EXPORT_PROFILE_DISPLAY_AUDIENCE_V1,
    CAMPAIGN_CHANNEL_WEBSITE_ONSITE: EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
}

EXTENDED_SOURCE_FIELDS = {
    *DEMOGRAPHIC_COLUMNS,
    "email_contactable",
    "direct_mail_contactable",
    "sms_opt_in",
    "whatsapp_opt_in",
    "telemarketing_contactable",
    "do_not_call",
    "push_token",
    "push_opt_in",
    "advertising_id",
    "advertising_targetable",
    "web_visitor_id",
    "onsite_targetable",
}


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "person_id": "PER_000001",
        "propensity_score": 0.875,
        "percentile_bucket": 5,
        "decile": 1,
        "rank_band": "VERY_HIGH",
        "first_name": " Ada ",
        "last_name": " Lovelace ",
    }
    row.update(overrides)
    return row


def test_registry_is_immutable_complete_backend_authority() -> None:
    assert OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION == "1"
    assert isinstance(OMNICHANNEL_PROFILE_REGISTRY, MappingProxyType)
    assert isinstance(CHANNEL_OMNICHANNEL_PROFILE, MappingProxyType)
    assert dict(CHANNEL_OMNICHANNEL_PROFILE) == EXPECTED_PROFILES_BY_CHANNEL
    assert set(OMNICHANNEL_PROFILE_REGISTRY) == set(EXPECTED_PROFILES_BY_CHANNEL.values())

    with pytest.raises(TypeError):
        OMNICHANNEL_PROFILE_REGISTRY["UNSAFE"] = get_omnichannel_profile(  # type: ignore[index]
            EXPORT_PROFILE_EMAIL_CONTACT_V1
        )

    for channel, profile_name in EXPECTED_PROFILES_BY_CHANNEL.items():
        profile = get_omnichannel_profile_for_channel(channel.lower())
        assert profile.export_profile == profile_name
        assert get_omnichannel_profile(profile_name.lower()) is profile
        assert profile.channel_code == channel
        assert profile.profile_version == "1"
        assert profile.output_columns[: len(BASE_EXPORT_COLUMNS)] == BASE_EXPORT_COLUMNS
        assert profile.field_allowlist == profile.output_columns
        assert len(profile.output_columns) == len(set(profile.output_columns))
        assert profile.output_format == "CSV_UTF8_RFC4180"
        assert profile.audit_fields == OMNICHANNEL_AUDIT_FIELDS
        assert profile.csv_formula_injection_mitigation is True
        assert set(COMMON_PROHIBITED_EXPORT_FIELDS) <= set(profile.prohibited_fields)
        assert not set(profile.field_allowlist).intersection(profile.prohibited_fields)


def test_immediate_and_gated_release_states_are_exact() -> None:
    immediate = {
        profile.channel_code
        for profile in OMNICHANNEL_PROFILE_REGISTRY.values()
        if profile.release_state == PROFILE_RELEASE_IMMEDIATE
    }
    gated = {
        profile.channel_code
        for profile in OMNICHANNEL_PROFILE_REGISTRY.values()
        if profile.release_state == PROFILE_RELEASE_GATED
    }

    assert immediate == {
        CAMPAIGN_CHANNEL_EMAIL,
        CAMPAIGN_CHANNEL_DIRECT_MAIL,
        CAMPAIGN_CHANNEL_SMS,
        CAMPAIGN_CHANNEL_WHATSAPP,
        CAMPAIGN_CHANNEL_TELEMARKETING,
        CAMPAIGN_CHANNEL_PAID_SOCIAL,
        CAMPAIGN_CHANNEL_PAID_SEARCH,
        CAMPAIGN_CHANNEL_MOBILE_PUSH,
        CAMPAIGN_CHANNEL_DISPLAY,
        CAMPAIGN_CHANNEL_WEBSITE_ONSITE,
    }
    assert gated == set()


def test_legacy_source_availability_is_honest_and_step4_fields_unlock_contracts() -> None:
    legacy_expected = {
        EXPORT_PROFILE_EMAIL_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_CONSENT,
        EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_CONSENT,
        EXPORT_PROFILE_SMS_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_CONSENT,
        EXPORT_PROFILE_WHATSAPP_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_CONSENT,
        EXPORT_PROFILE_TELEMARKETING_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_CONSENT,
        EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1: PROFILE_AVAILABILITY_AVAILABLE,
        EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1: PROFILE_AVAILABILITY_AVAILABLE,
        EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1: PROFILE_AVAILABILITY_MISSING_IDENTIFIER,
        EXPORT_PROFILE_DISPLAY_AUDIENCE_V1: PROFILE_AVAILABILITY_MISSING_IDENTIFIER,
        EXPORT_PROFILE_WEBSITE_AUDIENCE_V1: PROFILE_AVAILABILITY_MISSING_IDENTIFIER,
    }
    legacy_source_fields = DEMOGRAPHIC_COLUMNS[:28]
    for profile_name, expected in legacy_expected.items():
        profile = get_omnichannel_profile(profile_name)
        assert profile.availability == PROFILE_AVAILABILITY_AVAILABLE
        assert resolve_profile_availability(
            profile_name,
            available_source_fields=legacy_source_fields,
        ) == expected
        assert resolve_profile_availability(
            profile_name,
            available_source_fields=DEMOGRAPHIC_COLUMNS,
        ) == PROFILE_AVAILABILITY_AVAILABLE


def test_profile_specific_allowlists_replace_global_phone_prohibition() -> None:
    assert "phone_number" not in PROHIBITED_EXPORT_FIELDS
    assert PROHIBITED_EXPORT_FIELDS == COMMON_PROHIBITED_EXPORT_FIELDS

    phone_profiles = {
        EXPORT_PROFILE_SMS_CONTACT_V1,
        EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
        EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
    }
    for profile_name, profile in OMNICHANNEL_PROFILE_REGISTRY.items():
        if profile_name in phone_profiles:
            assert "phone_number" in profile.field_allowlist
            assert "phone_number" not in profile.prohibited_fields
        else:
            assert "phone_number" not in profile.field_allowlist
            assert "phone_number" in profile.prohibited_fields

    for paid_profile in (
        EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
        EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    ):
        profile = get_omnichannel_profile(paid_profile)
        assert profile.output_columns == (*BASE_EXPORT_COLUMNS, "sha256_email", "sha256_phone")
        assert "email" in profile.prohibited_fields
        assert "phone_number" in profile.prohibited_fields
        assert "pseudonymous_not_anonymized" in profile.hashing_rules


def test_email_and_phone_normalization_are_deterministic_and_strict() -> None:
    assert normalize_email_identifier("  Person@Example.COM ") == "person@example.com"
    assert normalize_email_identifier("missing-at.example.com") is None
    assert normalize_email_identifier("person@example") is None
    assert normalize_email_identifier(None) is None

    assert normalize_us_phone_identifier("(202) 555-0123") == "+12025550123"
    assert normalize_us_phone_identifier("1-202-555-0123") == "+12025550123"
    assert normalize_us_phone_identifier("+1 202 555 0123") == "+12025550123"
    assert normalize_us_phone_identifier("202-055-0123") is None
    assert normalize_us_phone_identifier("202-555-0123 ext 4") is None
    assert normalize_us_phone_identifier(2025550123) is None


def test_paid_media_hashes_are_exact_pseudonymous_and_allow_one_identifier() -> None:
    both = paid_media_match_keys(
        email="  Person@Example.COM ",
        phone_number="(202) 555-0123",
    )
    assert both == {
        "sha256_email": "542d240129883c019e106e3b1b2d3f3cb3537c43c425364de8e951d5a3083345",
        "sha256_phone": "d5ab8b77e69a81dfc634c3556c620d5d6753df6fc28c73c88c79a9332b705382",
    }
    assert paid_media_match_keys(email="person@example.com") == {
        "sha256_email": both["sha256_email"]
    }
    assert paid_media_match_keys(phone_number="2025550123") == {
        "sha256_phone": both["sha256_phone"]
    }
    assert paid_media_match_keys(email="bad", phone_number="bad") == {}
    assert "person@example.com" not in str(both)
    assert "+12025550123" not in str(both)


@pytest.mark.parametrize(
    ("profile_name", "row", "expected"),
    (
        (
            EXPORT_PROFILE_EMAIL_CONTACT_V1,
            _base_row(email="valid@example.com", email_contactable=True),
            True,
        ),
        (
            EXPORT_PROFILE_EMAIL_CONTACT_V1,
            _base_row(email="valid@example.com", email_contactable=False),
            False,
        ),
        (
            EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
            _base_row(
                address_line_1="1 Main St",
                city="Austin",
                state="TX",
                postal_code="73301",
                direct_mail_contactable=1,
            ),
            True,
        ),
        (
            EXPORT_PROFILE_SMS_CONTACT_V1,
            _base_row(phone_number="202-555-0123", sms_opt_in=True),
            True,
        ),
        (
            EXPORT_PROFILE_SMS_CONTACT_V1,
            _base_row(phone_number="202-555-0123", sms_opt_in=False),
            False,
        ),
        (
            EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
            _base_row(phone_number="202-555-0123", whatsapp_opt_in=True),
            True,
        ),
        (
            EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
            _base_row(phone_number="202-555-0123", do_not_call=False),
            True,
        ),
        (
            EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
            _base_row(
                phone_number="202-555-0123",
                telemarketing_contactable=True,
                do_not_call=True,
            ),
            False,
        ),
        (
            EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
            _base_row(email="paid@example.com"),
            True,
        ),
        (
            EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
            _base_row(phone_number="202-555-0123"),
            True,
        ),
        (
            EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
            _base_row(push_token="opaque-token", push_opt_in=True),
            True,
        ),
        (
            EXPORT_PROFILE_DISPLAY_AUDIENCE_V1,
            _base_row(advertising_id="ABC-123", advertising_targetable=True),
            True,
        ),
        (
            EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
            _base_row(web_visitor_id="visitor-123", onsite_targetable=True),
            True,
        ),
    ),
)
def test_profile_deliverability_enforces_identifier_and_consent(
    profile_name: str,
    row: dict[str, object],
    expected: bool,
) -> None:
    assert is_profile_row_deliverable(profile_name, row) is expected


def test_projection_is_exact_allowlist_and_paid_media_excludes_raw_identifiers() -> None:
    row = _base_row(
        email=" Person@Example.COM ",
        phone_number="202-555-0123",
        ethnicity="must-not-export",
        religion="must-not-export",
        customer_id="must-not-export",
    )
    projected = project_profile_row(EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1, row)

    assert projected is not None
    profile = get_omnichannel_profile(EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1)
    assert tuple(projected) == profile.output_columns
    assert projected["sha256_email"] == (
        "542d240129883c019e106e3b1b2d3f3cb3537c43c425364de8e951d5a3083345"
    )
    assert projected["sha256_phone"] == (
        "d5ab8b77e69a81dfc634c3556c620d5d6753df6fc28c73c88c79a9332b705382"
    )
    for forbidden in ("email", "phone_number", "ethnicity", "religion", "customer_id"):
        assert forbidden not in projected


def test_csv_formula_mitigation_and_filename_contract_are_preserved() -> None:
    assert mitigate_csv_formula_injection("=SUM(1,1)") == "'=SUM(1,1)"
    assert mitigate_csv_formula_injection("  +value") == "'  +value"
    assert mitigate_csv_formula_injection("-value") == "'-value"
    assert mitigate_csv_formula_injection("@value") == "'@value"
    assert mitigate_csv_formula_injection("ordinary") == "ordinary"
    assert mitigate_csv_formula_injection(None) == ""
    assert mitigate_csv_formula_injection(7) == 7

    assert build_profile_filename(
        EXPORT_PROFILE_SMS_CONTACT_V1,
        search_run_id=42,
    ) == "potential_customers_42_sms_contact_v1.csv"
    with pytest.raises(ValueError, match="search_run_id"):
        build_profile_filename(
            EXPORT_PROFILE_SMS_CONTACT_V1,
            search_run_id="../unsafe",
        )


def test_legacy_campaign_exports_remain_compatible_without_global_phone_rule() -> None:
    assert CAMPAIGN_CHANNELS == (CAMPAIGN_CHANNEL_EMAIL, CAMPAIGN_CHANNEL_DIRECT_MAIL)
    assert EMAIL_EXPORT_COLUMNS == get_omnichannel_profile(
        EXPORT_PROFILE_EMAIL_CONTACT_V1
    ).output_columns
    assert DIRECT_MAIL_EXPORT_COLUMNS == get_omnichannel_profile(
        EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1
    ).output_columns
    assert PROFILE_EXPORT_COLUMNS[EXPORT_PROFILE_EMAIL_CONTACT_V1] == EMAIL_EXPORT_COLUMNS
    assert (
        PROFILE_EXPORT_COLUMNS[EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1]
        == DIRECT_MAIL_EXPORT_COLUMNS
    )
    assert PROFILE_PROHIBITED_FIELDS[EXPORT_PROFILE_SMS_CONTACT_V1] == (
        get_omnichannel_profile(EXPORT_PROFILE_SMS_CONTACT_V1).prohibited_fields
    )


def test_contactability_and_activation_fields_do_not_enter_model_contract() -> None:
    assert ORDERED_FEATURES == (
        "age",
        "gender",
        "state",
        "individual_yearly_income",
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "family_member_count",
        "type_of_employment",
    )
    for forbidden in (
        "email_contactable",
        "direct_mail_contactable",
        "sms_opt_in",
        "whatsapp_opt_in",
        "telemarketing_contactable",
        "do_not_call",
        "push_token",
        "push_opt_in",
        "advertising_id",
        "advertising_targetable",
        "web_visitor_id",
        "onsite_targetable",
    ):
        assert forbidden not in ORDERED_FEATURES


@pytest.mark.parametrize("value", ("unknown", "", None, 7))
def test_unknown_profile_or_channel_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        get_omnichannel_profile(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        get_omnichannel_profile_for_channel(value)  # type: ignore[arg-type]
