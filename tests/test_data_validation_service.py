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
