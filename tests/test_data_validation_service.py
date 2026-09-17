from __future__ import annotations

import pytest

from app.database.schema import DEMOGRAPHIC_COLUMNS
from app.services.data_validation_service import (
    DataValidationError,
    validate_demographic_row,
)


def _base_demographic_row() -> dict[str, str]:
    row = {column: "" for column in DEMOGRAPHIC_COLUMNS}
    row.update(
        {
            "person_id": "PER_001",
            "state": "California",
            "age": "35",
            "individual_yearly_income": "60000",
            "family_member_count": "3",
            "number_of_children_in_family": "1",
            "number_of_adults_in_family": "2",
            "family_yearly_income": "100000",
            "email_contactable": "0",
            "direct_mail_contactable": "0",
            "sms_opt_in": "0",
            "whatsapp_opt_in": "0",
            "telemarketing_contactable": "0",
            "do_not_call": "0",
            "push_opt_in": "0",
            "advertising_targetable": "0",
            "onsite_targetable": "0",
        }
    )
    return row


@pytest.mark.parametrize("age", ("18", "100"))
def test_demographic_validation_accepts_age_contract_boundaries(age: str) -> None:
    row = _base_demographic_row()
    row["age"] = age

    validated = validate_demographic_row(row)

    assert validated[DEMOGRAPHIC_COLUMNS.index("age")] == int(age)


@pytest.mark.parametrize(
    ("age", "message"),
    (
        ("17", "age must be between 18 and 100"),
        ("101", "age must be between 18 and 100"),
    ),
)
def test_demographic_validation_rejects_age_outside_contract(
    age: str,
    message: str,
) -> None:
    row = _base_demographic_row()
    row["age"] = age

    with pytest.raises(DataValidationError, match=message):
        validate_demographic_row(row)


def test_demographic_validation_requires_at_least_one_adult() -> None:
    row = _base_demographic_row()
    row["family_member_count"] = "1"
    row["number_of_children_in_family"] = "1"
    row["number_of_adults_in_family"] = "0"

    with pytest.raises(DataValidationError, match="number_of_adults_in_family must be at least 1"):
        validate_demographic_row(row)


def test_demographic_validation_still_enforces_income_and_family_arithmetic() -> None:
    row = _base_demographic_row()
    row["family_yearly_income"] = "50000"

    with pytest.raises(
        DataValidationError,
        match="family_yearly_income must be greater than or equal to individual_yearly_income",
    ):
        validate_demographic_row(row)

    row = _base_demographic_row()
    row["number_of_children_in_family"] = "0"
    row["number_of_adults_in_family"] = "1"

    with pytest.raises(
        DataValidationError,
        match=r"number_of_children_in_family \+ number_of_adults_in_family must equal family_member_count",
    ):
        validate_demographic_row(row)


def test_demographic_validation_accepts_governed_contactability_identifiers() -> None:
    row = _base_demographic_row()
    row.update(
        {
            "address_line_1": "100 Example Rd",
            "city": "Example City",
            "postal_code": "90210",
            "email": "person@example.net",
            "phone_number": "+1-310-555-0101",
            "email_contactable": "1",
            "direct_mail_contactable": "1",
            "sms_opt_in": "1",
            "whatsapp_opt_in": "1",
            "telemarketing_contactable": "1",
            "push_token": "pt_0123456789abcdef0123456789abcdef",
            "push_opt_in": "1",
            "advertising_id": "12345678-1234-4abc-8def-1234567890ab",
            "advertising_targetable": "1",
            "web_visitor_id": "wv_0123456789abcdef0123456789abcdef",
            "onsite_targetable": "1",
        }
    )

    validated = validate_demographic_row(row)

    assert validated[DEMOGRAPHIC_COLUMNS.index("email_contactable")] == 1
    assert validated[DEMOGRAPHIC_COLUMNS.index("push_opt_in")] == 1
    assert validated[DEMOGRAPHIC_COLUMNS.index("advertising_targetable")] == 1
    assert validated[DEMOGRAPHIC_COLUMNS.index("onsite_targetable")] == 1


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"email_contactable": "1"}, "email_contactable=true requires email"),
        (
            {"direct_mail_contactable": "1"},
            "direct_mail_contactable=true requires address_line_1",
        ),
        ({"sms_opt_in": "1"}, "sms_opt_in=true requires phone_number"),
        ({"whatsapp_opt_in": "1"}, "whatsapp_opt_in=true requires phone_number"),
        (
            {"telemarketing_contactable": "1"},
            "telemarketing_contactable=true requires phone_number",
        ),
        (
            {
                "phone_number": "+1-310-555-0101",
                "telemarketing_contactable": "1",
                "do_not_call": "1",
            },
            "incompatible with do_not_call=true",
        ),
        ({"push_opt_in": "1"}, "push_opt_in=true requires push_token"),
        (
            {"advertising_targetable": "1"},
            "advertising_targetable=true requires advertising_id",
        ),
        (
            {"onsite_targetable": "1"},
            "onsite_targetable=true requires web_visitor_id",
        ),
        ({"push_token": "not-a-token"}, "push_token must be"),
        ({"advertising_id": "not-a-uuid"}, "advertising_id must be"),
        ({"web_visitor_id": "not-a-key"}, "web_visitor_id must be"),
    ),
)
def test_demographic_validation_rejects_untruthful_contactability(
    updates: dict[str, str],
    message: str,
) -> None:
    row = _base_demographic_row()
    row.update(updates)

    with pytest.raises(DataValidationError, match=message):
        validate_demographic_row(row)


@pytest.mark.parametrize(
    "field",
    (
        "email_contactable",
        "direct_mail_contactable",
        "sms_opt_in",
        "whatsapp_opt_in",
        "telemarketing_contactable",
        "do_not_call",
        "push_opt_in",
        "advertising_targetable",
        "onsite_targetable",
    ),
)
@pytest.mark.parametrize("value", ("", "2", "-1"))
def test_demographic_contactability_flags_are_required_binary_values(
    field: str,
    value: str,
) -> None:
    row = _base_demographic_row()
    row[field] = value

    with pytest.raises(DataValidationError):
        validate_demographic_row(row)
