"""Phase 11 omnichannel export-profile and privacy contracts.

The registry is the backend authority for profile metadata.  It intentionally
contains no database or frontend dependency so availability and row-level
privacy behavior can be tested independently of source import and reused by
the Step 13 streaming export engine. Step 4 provides the governed source fields
for every declared profile; runtime source availability is still checked.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from types import MappingProxyType
from typing import Any, Mapping


OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION = "1"

PROFILE_AVAILABILITY_AVAILABLE = "AVAILABLE"
PROFILE_AVAILABILITY_MISSING_IDENTIFIER = "UNAVAILABLE_MISSING_IDENTIFIER"
PROFILE_AVAILABILITY_MISSING_CONSENT = "UNAVAILABLE_MISSING_CONSENT_CONTRACT"
PROFILE_AVAILABILITIES = (
    PROFILE_AVAILABILITY_AVAILABLE,
    PROFILE_AVAILABILITY_MISSING_IDENTIFIER,
    PROFILE_AVAILABILITY_MISSING_CONSENT,
)

PROFILE_RELEASE_IMMEDIATE = "IMMEDIATE"
PROFILE_RELEASE_GATED = "GATED_SOURCE_EXTENSION"

CAMPAIGN_CHANNEL_EMAIL = "EMAIL"
CAMPAIGN_CHANNEL_DIRECT_MAIL = "DIRECT_MAIL"
CAMPAIGN_CHANNEL_SMS = "SMS"
CAMPAIGN_CHANNEL_WHATSAPP = "WHATSAPP"
CAMPAIGN_CHANNEL_TELEMARKETING = "TELEMARKETING"
CAMPAIGN_CHANNEL_PAID_SOCIAL = "PAID_SOCIAL"
CAMPAIGN_CHANNEL_PAID_SEARCH = "PAID_SEARCH"
CAMPAIGN_CHANNEL_MOBILE_PUSH = "MOBILE_PUSH"
CAMPAIGN_CHANNEL_DISPLAY = "DISPLAY"
CAMPAIGN_CHANNEL_WEBSITE_ONSITE = "WEBSITE_ONSITE"

EXPORT_PROFILE_EMAIL_CONTACT_V1 = "EMAIL_CONTACT_V1"
EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1 = "DIRECT_MAIL_CONTACT_V1"
EXPORT_PROFILE_SMS_CONTACT_V1 = "SMS_CONTACT_V1"
EXPORT_PROFILE_WHATSAPP_CONTACT_V1 = "WHATSAPP_CONTACT_V1"
EXPORT_PROFILE_TELEMARKETING_CONTACT_V1 = "TELEMARKETING_CONTACT_V1"
EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1 = "PAID_SOCIAL_AUDIENCE_V1"
EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1 = "PAID_SEARCH_AUDIENCE_V1"
EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1 = "MOBILE_PUSH_CONTACT_V1"
EXPORT_PROFILE_DISPLAY_AUDIENCE_V1 = "DISPLAY_AUDIENCE_V1"
EXPORT_PROFILE_WEBSITE_AUDIENCE_V1 = "WEBSITE_AUDIENCE_V1"

BASE_EXPORT_COLUMNS = (
    "person_id",
    "propensity_score",
    "percentile_bucket",
    "decile",
    "rank_band",
)

OMNICHANNEL_AUDIT_FIELDS = (
    "export_event_id",
    "search_run_id",
    "snapshot_id",
    "omnichannel_contract_version",
    "export_profile",
    "profile_version",
    "status",
    "selected_count",
    "deliverable_count",
    "undeliverable_count",
    "row_count",
    "csv_sha256",
    "started_at",
    "completed_at",
    "currentness_state",
    "safe_error_message",
)

COMMON_PROHIBITED_EXPORT_FIELDS = (
    "customer_id",
    "age",
    "gender",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "ethnicity",
    "type_of_employment",
    "occupation_industry",
    "family_yearly_income",
    "religion",
)

_CONTACT_AND_CONTROL_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "state",
    "country",
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
    "sha256_email",
    "sha256_phone",
)

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_US_E164_PATTERN = re.compile(r"^\+1[2-9]\d{2}[2-9]\d{6}$")
_SAFE_FILENAME_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class OmnichannelExportProfile:
    """Immutable profile metadata and privacy boundary."""

    channel_code: str
    export_profile: str
    profile_version: str
    release_state: str
    availability: str
    required_identifier_groups: tuple[tuple[str, ...], ...]
    consent_contactability_requirements: tuple[str, ...]
    required_consent_field_groups: tuple[tuple[str, ...], ...]
    output_columns: tuple[str, ...]
    field_allowlist: tuple[str, ...]
    prohibited_fields: tuple[str, ...]
    normalization_rules: tuple[str, ...]
    deliverability_rules: tuple[str, ...]
    hashing_rules: tuple[str, ...]
    filename_template: str
    output_format: str
    audit_fields: tuple[str, ...]
    csv_formula_injection_mitigation: bool = True


def _profile_prohibited_fields(output_columns: tuple[str, ...]) -> tuple[str, ...]:
    allowed = set(output_columns)
    prohibited = set(COMMON_PROHIBITED_EXPORT_FIELDS)
    prohibited.update(field for field in _CONTACT_AND_CONTROL_FIELDS if field not in allowed)
    return tuple(sorted(prohibited))


def _profile(
    *,
    channel_code: str,
    export_profile: str,
    release_state: str,
    availability: str,
    identifiers: tuple[tuple[str, ...], ...],
    consent: tuple[str, ...],
    consent_fields: tuple[tuple[str, ...], ...],
    columns: tuple[str, ...],
    normalization: tuple[str, ...],
    deliverability: tuple[str, ...],
    hashing: tuple[str, ...] = (),
) -> OmnichannelExportProfile:
    output_columns = (*BASE_EXPORT_COLUMNS, *columns)
    return OmnichannelExportProfile(
        channel_code=channel_code,
        export_profile=export_profile,
        profile_version="1",
        release_state=release_state,
        availability=availability,
        required_identifier_groups=identifiers,
        consent_contactability_requirements=consent,
        required_consent_field_groups=consent_fields,
        output_columns=output_columns,
        field_allowlist=output_columns,
        prohibited_fields=_profile_prohibited_fields(output_columns),
        normalization_rules=normalization,
        deliverability_rules=deliverability,
        hashing_rules=hashing,
        filename_template="potential_customers_{search_run_id}_{profile}.csv",
        output_format="CSV_UTF8_RFC4180",
        audit_fields=OMNICHANNEL_AUDIT_FIELDS,
    )


_PROFILES = (
    _profile(
        channel_code=CAMPAIGN_CHANNEL_EMAIL,
        export_profile=EXPORT_PROFILE_EMAIL_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("email",),),
        consent=("email_contactable=true",),
        consent_fields=(("email_contactable",),),
        columns=("first_name", "last_name", "email"),
        normalization=("email=trim+lowercase",),
        deliverability=("valid_normalized_email", "email_contactable=true"),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_DIRECT_MAIL,
        export_profile=EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(
            ("address_line_1",),
            ("city",),
            ("state",),
            ("postal_code",),
        ),
        consent=("direct_mail_contactable=true",),
        consent_fields=(("direct_mail_contactable",),),
        columns=(
            "first_name",
            "last_name",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
        ),
        normalization=("text=trim_for_validation",),
        deliverability=(
            "address_line_1+city+state+postal_code_present",
            "direct_mail_contactable=true",
        ),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_SMS,
        export_profile=EXPORT_PROFILE_SMS_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("phone_number",),),
        consent=("sms_opt_in=true",),
        consent_fields=(("sms_opt_in",),),
        columns=("first_name", "last_name", "phone_number"),
        normalization=("phone=canonical_us_e164",),
        deliverability=("valid_normalized_phone", "sms_opt_in=true"),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_WHATSAPP,
        export_profile=EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("phone_number",),),
        consent=("whatsapp_opt_in=true",),
        consent_fields=(("whatsapp_opt_in",),),
        columns=("first_name", "last_name", "phone_number"),
        normalization=("phone=canonical_us_e164",),
        deliverability=("valid_normalized_phone", "whatsapp_opt_in=true"),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_TELEMARKETING,
        export_profile=EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("phone_number",),),
        consent=("telemarketing_contactable=true_or_do_not_call=false",),
        consent_fields=(("telemarketing_contactable", "do_not_call"),),
        columns=("first_name", "last_name", "phone_number"),
        normalization=("phone=canonical_us_e164",),
        deliverability=(
            "valid_normalized_phone",
            "telemarketing_contactable=true_when_present",
            "do_not_call=false_when_present",
        ),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_PAID_SOCIAL,
        export_profile=EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("email", "phone_number"),),
        consent=("approved_match_identifier_present",),
        consent_fields=(),
        columns=("sha256_email", "sha256_phone"),
        normalization=("email=trim+lowercase", "phone=canonical_us_e164"),
        deliverability=("at_least_one_valid_match_identifier",),
        hashing=(
            "sha256(normalized_identifier)",
            "lowercase_hex",
            "raw_identifiers_excluded",
            "pseudonymous_not_anonymized",
        ),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_PAID_SEARCH,
        export_profile=EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("email", "phone_number"),),
        consent=("approved_match_identifier_present",),
        consent_fields=(),
        columns=("sha256_email", "sha256_phone"),
        normalization=("email=trim+lowercase", "phone=canonical_us_e164"),
        deliverability=("at_least_one_valid_match_identifier",),
        hashing=(
            "sha256(normalized_identifier)",
            "lowercase_hex",
            "raw_identifiers_excluded",
            "pseudonymous_not_anonymized",
        ),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_MOBILE_PUSH,
        export_profile=EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("push_token",),),
        consent=("push_opt_in=true",),
        consent_fields=(("push_opt_in",),),
        columns=("push_token",),
        normalization=("push_token=trim",),
        deliverability=("push_token_present", "push_opt_in=true"),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_DISPLAY,
        export_profile=EXPORT_PROFILE_DISPLAY_AUDIENCE_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("advertising_id",),),
        consent=("advertising_targetable=true",),
        consent_fields=(("advertising_targetable",),),
        columns=("advertising_id",),
        normalization=("advertising_id=trim+lowercase",),
        deliverability=("advertising_id_present", "advertising_targetable=true"),
    ),
    _profile(
        channel_code=CAMPAIGN_CHANNEL_WEBSITE_ONSITE,
        export_profile=EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
        release_state=PROFILE_RELEASE_IMMEDIATE,
        availability=PROFILE_AVAILABILITY_AVAILABLE,
        identifiers=(("web_visitor_id",),),
        consent=("onsite_targetable=true",),
        consent_fields=(("onsite_targetable",),),
        columns=("web_visitor_id",),
        normalization=("web_visitor_id=trim",),
        deliverability=("web_visitor_id_present", "onsite_targetable=true"),
    ),
)

OMNICHANNEL_PROFILE_REGISTRY: Mapping[str, OmnichannelExportProfile] = (
    MappingProxyType({profile.export_profile: profile for profile in _PROFILES})
)
CHANNEL_OMNICHANNEL_PROFILE: Mapping[str, str] = MappingProxyType(
    {profile.channel_code: profile.export_profile for profile in _PROFILES}
)


def get_omnichannel_profile(export_profile: str) -> OmnichannelExportProfile:
    """Return an exact profile or reject an unknown frontend-supplied value."""

    if not isinstance(export_profile, str):
        raise ValueError("export_profile must be text.")
    normalized = export_profile.strip().upper()
    try:
        return OMNICHANNEL_PROFILE_REGISTRY[normalized]
    except KeyError as exc:
        raise ValueError("export_profile is invalid.") from exc


def get_omnichannel_profile_for_channel(channel_code: str) -> OmnichannelExportProfile:
    """Resolve the backend-owned channel mapping."""

    if not isinstance(channel_code, str):
        raise ValueError("channel_code must be text.")
    normalized = channel_code.strip().upper()
    try:
        profile_name = CHANNEL_OMNICHANNEL_PROFILE[normalized]
    except KeyError as exc:
        raise ValueError("channel_code is invalid.") from exc
    return OMNICHANNEL_PROFILE_REGISTRY[profile_name]


def resolve_profile_availability(
    export_profile: str,
    *,
    available_source_fields: set[str] | frozenset[str] | tuple[str, ...],
) -> str:
    """Evaluate schema-level availability without inventing source fields."""

    profile = get_omnichannel_profile(export_profile)
    available = frozenset(available_source_fields)
    if any(not available.intersection(group) for group in profile.required_identifier_groups):
        return PROFILE_AVAILABILITY_MISSING_IDENTIFIER
    if any(not available.intersection(group) for group in profile.required_consent_field_groups):
        return PROFILE_AVAILABILITY_MISSING_CONSENT
    return PROFILE_AVAILABILITY_AVAILABLE


def normalize_email_identifier(value: Any) -> str | None:
    """Normalize a valid email for contact output or deterministic hashing."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 320:
        return None
    if _EMAIL_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def normalize_us_phone_identifier(value: Any) -> str | None:
    """Normalize a synthetic US number to canonical ``+1NXXNXXXXXX``."""

    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or re.search(r"[A-Za-z]", stripped):
        return None
    digits = re.sub(r"\D", "", stripped)
    if len(digits) == 10:
        normalized = "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        normalized = "+" + digits
    else:
        return None
    if _US_E164_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def sha256_match_key(normalized_identifier: str) -> str:
    """Hash an already normalized match identifier as lowercase hexadecimal."""

    if not isinstance(normalized_identifier, str) or not normalized_identifier:
        raise ValueError("normalized_identifier must not be blank.")
    return hashlib.sha256(normalized_identifier.encode("utf-8")).hexdigest()


def paid_media_match_keys(*, email: Any = None, phone_number: Any = None) -> dict[str, str]:
    """Return one or both approved hashes and never return a raw identifier."""

    keys: dict[str, str] = {}
    normalized_email = normalize_email_identifier(email)
    normalized_phone = normalize_us_phone_identifier(phone_number)
    if normalized_email is not None:
        keys["sha256_email"] = sha256_match_key(normalized_email)
    if normalized_phone is not None:
        keys["sha256_phone"] = sha256_match_key(normalized_phone)
    return keys


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value == 1)


def _is_false(value: Any) -> bool:
    return value is False or (isinstance(value, int) and not isinstance(value, bool) and value == 0)


def _present_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_profile_row_deliverable(export_profile: str, row: Mapping[str, Any]) -> bool:
    """Apply the exact identifier and consent rules for one selected person."""

    profile = get_omnichannel_profile(export_profile)
    code = profile.export_profile
    if code == EXPORT_PROFILE_EMAIL_CONTACT_V1:
        return normalize_email_identifier(row.get("email")) is not None and _is_true(
            row.get("email_contactable")
        )
    if code == EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1:
        required = ("address_line_1", "city", "state", "postal_code")
        return all(_present_text(row.get(field)) for field in required) and _is_true(
            row.get("direct_mail_contactable")
        )
    if code == EXPORT_PROFILE_SMS_CONTACT_V1:
        return normalize_us_phone_identifier(row.get("phone_number")) is not None and _is_true(
            row.get("sms_opt_in")
        )
    if code == EXPORT_PROFILE_WHATSAPP_CONTACT_V1:
        return normalize_us_phone_identifier(row.get("phone_number")) is not None and _is_true(
            row.get("whatsapp_opt_in")
        )
    if code == EXPORT_PROFILE_TELEMARKETING_CONTACT_V1:
        if normalize_us_phone_identifier(row.get("phone_number")) is None:
            return False
        has_contactability = "telemarketing_contactable" in row or "do_not_call" in row
        if "telemarketing_contactable" in row and not _is_true(row.get("telemarketing_contactable")):
            return False
        if "do_not_call" in row and not _is_false(row.get("do_not_call")):
            return False
        return has_contactability
    if code in {
        EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
        EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    }:
        return bool(
            paid_media_match_keys(
                email=row.get("email"),
                phone_number=row.get("phone_number"),
            )
        )
    if code == EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1:
        return _present_text(row.get("push_token")) and _is_true(row.get("push_opt_in"))
    if code == EXPORT_PROFILE_DISPLAY_AUDIENCE_V1:
        return _present_text(row.get("advertising_id")) and _is_true(
            row.get("advertising_targetable")
        )
    if code == EXPORT_PROFILE_WEBSITE_AUDIENCE_V1:
        return _present_text(row.get("web_visitor_id")) and _is_true(row.get("onsite_targetable"))
    return False


def project_profile_row(
    export_profile: str,
    row: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project a deliverable row through the exact profile allowlist."""

    profile = get_omnichannel_profile(export_profile)
    if not is_profile_row_deliverable(profile.export_profile, row):
        return None

    projected = {column: row.get(column, "") for column in profile.output_columns}
    if profile.export_profile == EXPORT_PROFILE_EMAIL_CONTACT_V1:
        projected["email"] = normalize_email_identifier(row.get("email")) or ""
    elif profile.export_profile in {
        EXPORT_PROFILE_SMS_CONTACT_V1,
        EXPORT_PROFILE_WHATSAPP_CONTACT_V1,
        EXPORT_PROFILE_TELEMARKETING_CONTACT_V1,
    }:
        projected["phone_number"] = normalize_us_phone_identifier(row.get("phone_number")) or ""
    elif profile.export_profile in {
        EXPORT_PROFILE_PAID_SOCIAL_AUDIENCE_V1,
        EXPORT_PROFILE_PAID_SEARCH_AUDIENCE_V1,
    }:
        match_keys = paid_media_match_keys(
            email=row.get("email"),
            phone_number=row.get("phone_number"),
        )
        projected["sha256_email"] = match_keys.get("sha256_email", "")
        projected["sha256_phone"] = match_keys.get("sha256_phone", "")
    elif profile.export_profile == EXPORT_PROFILE_DISPLAY_AUDIENCE_V1:
        projected["advertising_id"] = str(row.get("advertising_id", "")).strip().lower()
    elif profile.export_profile in {
        EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1,
        EXPORT_PROFILE_WEBSITE_AUDIENCE_V1,
    }:
        field = (
            "push_token"
            if profile.export_profile == EXPORT_PROFILE_MOBILE_PUSH_CONTACT_V1
            else "web_visitor_id"
        )
        projected[field] = str(row.get(field, "")).strip()
    return projected


def mitigate_csv_formula_injection(value: Any) -> str | int | float:
    """Preserve the Phase 7 CSV formula-injection mitigation contract."""

    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    stripped = text.lstrip()
    if stripped and stripped[0] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def build_profile_filename(export_profile: str, *, search_run_id: str | int) -> str:
    """Build a deterministic path-safe download filename."""

    profile = get_omnichannel_profile(export_profile)
    identifier = str(search_run_id).strip()
    if not identifier or _SAFE_FILENAME_ID_PATTERN.fullmatch(identifier) is None:
        raise ValueError("search_run_id is invalid for a filename.")
    return profile.filename_template.format(
        search_run_id=identifier,
        profile=profile.export_profile.lower(),
    )


__all__ = tuple(
    name
    for name in globals()
    if name.startswith(("CAMPAIGN_CHANNEL_", "EXPORT_PROFILE_", "PROFILE_"))
) + (
    "BASE_EXPORT_COLUMNS",
    "CHANNEL_OMNICHANNEL_PROFILE",
    "COMMON_PROHIBITED_EXPORT_FIELDS",
    "OMNICHANNEL_AUDIT_FIELDS",
    "OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION",
    "OMNICHANNEL_PROFILE_REGISTRY",
    "OmnichannelExportProfile",
    "build_profile_filename",
    "get_omnichannel_profile",
    "get_omnichannel_profile_for_channel",
    "is_profile_row_deliverable",
    "mitigate_csv_formula_injection",
    "normalize_email_identifier",
    "normalize_us_phone_identifier",
    "paid_media_match_keys",
    "project_profile_row",
    "resolve_profile_availability",
    "sha256_match_key",
)
