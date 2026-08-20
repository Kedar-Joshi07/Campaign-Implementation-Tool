"""Dataset-specific row validation and SQLite value conversion."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date

from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
)


class DataValidationError(ValueError):
    """Raised when one source row violates the documented dataset contract."""


def _optional_text(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _required_text(row: Mapping[str, str], field: str) -> str:
    value = _optional_text(row[field])
    if value is None:
        raise DataValidationError(f"{field} must not be blank")
    return value


def _integer(value: str, field: str, *, required: bool = True) -> int | None:
    normalized = value.strip()
    if not normalized:
        if required:
            raise DataValidationError(f"{field} must not be blank")
        return None
    try:
        return int(normalized)
    except ValueError as exc:
        raise DataValidationError(f"{field} must be an integer; received {value!r}") from exc


def _number(value: str, field: str, *, required: bool = True) -> float | None:
    normalized = value.strip()
    if not normalized:
        if required:
            raise DataValidationError(f"{field} must not be blank")
        return None
    try:
        parsed = float(normalized)
    except ValueError as exc:
        raise DataValidationError(f"{field} must be numeric; received {value!r}") from exc
    if not math.isfinite(parsed):
        raise DataValidationError(f"{field} must be a finite number")
    return parsed


def _iso_date(value: str, field: str, *, required: bool = True) -> str | None:
    normalized = value.strip()
    if not normalized:
        if required:
            raise DataValidationError(f"{field} must not be blank")
        return None
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise DataValidationError(
            f"{field} must be a valid ISO date (YYYY-MM-DD); received {value!r}"
        ) from exc


def _flag(value: str, field: str) -> int:
    normalized = value.strip().lower()
    flag_values = {
        "0": 0,
        "false": 0,
        "no": 0,
        "n": 0,
        "1": 1,
        "true": 1,
        "yes": 1,
        "y": 1,
    }
    if normalized not in flag_values:
        raise DataValidationError(f"{field} must be a boolean flag (0 or 1)")
    return flag_values[normalized]


def _base_values(row: Mapping[str, str], columns: tuple[str, ...]) -> dict[str, object]:
    return {column: _optional_text(row[column]) for column in columns}


def validate_customer_row(row: Mapping[str, str]) -> tuple[object, ...]:
    """Validate and convert one customer source row."""
    values = _base_values(row, CUSTOMER_COLUMNS)
    values["customer_id"] = _required_text(row, "customer_id")
    values["date_of_birth"] = _iso_date(row["date_of_birth"], "date_of_birth")
    values["state"] = _required_text(row, "state")

    income = _number(row["individual_yearly_income"], "individual_yearly_income")
    if income is not None and income < 0:
        raise DataValidationError("individual_yearly_income must be nonnegative")
    values["individual_yearly_income"] = income

    family_count = _integer(row["family_member_count"], "family_member_count")
    if family_count is not None and family_count < 1:
        raise DataValidationError("family_member_count must be at least 1")
    values["family_member_count"] = family_count

    return tuple(values[column] for column in CUSTOMER_COLUMNS)


def validate_campaign_sales_row(row: Mapping[str, str]) -> tuple[object, ...]:
    """Validate and convert one campaign-sales source row."""
    values = _base_values(row, CAMPAIGN_SALES_COLUMNS)
    for field in ("campaign_sales_id", "customer_id", "campaign_id", "product_id"):
        values[field] = _required_text(row, field)

    for field in ("campaign_start_date", "campaign_end_date", "contact_date"):
        values[field] = _iso_date(row[field], field)
    for field in ("product_launch_date", "purchase_date"):
        values[field] = _iso_date(row[field], field, required=False)

    start = date.fromisoformat(str(values["campaign_start_date"]))
    end = date.fromisoformat(str(values["campaign_end_date"]))
    contact = date.fromisoformat(str(values["contact_date"]))
    if start > end:
        raise DataValidationError("campaign_start_date must not be after campaign_end_date")
    if contact < start or contact > end:
        raise DataValidationError("contact_date must fall within the campaign window")

    for field in (
        "contacted_flag",
        "engagement_flag",
        "response_flag",
        "purchase_flag",
        "campaign_attributed_sale_flag",
        "pu_label",
    ):
        values[field] = _flag(row[field], field)

    for field in ("quantity", "days_to_purchase"):
        parsed = _integer(row[field], field, required=False)
        if parsed is not None and parsed < 0:
            raise DataValidationError(f"{field} must be nonnegative")
        values[field] = parsed

    for field in (
        "offer_value",
        "product_price",
        "product_cost",
        "gross_sales_amount",
        "discount_amount",
        "net_sales_amount",
        "gross_margin_amount",
    ):
        values[field] = _number(row[field], field, required=False)

    for field in (
        "offer_value",
        "product_price",
        "product_cost",
        "gross_sales_amount",
        "discount_amount",
        "net_sales_amount",
    ):
        if values[field] is not None and float(values[field]) < 0:
            raise DataValidationError(f"{field} must be nonnegative")

    purchase_flag = int(values["purchase_flag"])
    attributed_flag = int(values["campaign_attributed_sale_flag"])
    pu_label = int(values["pu_label"])
    if pu_label == 1 and attributed_flag != 1:
        raise DataValidationError("pu_label=1 requires campaign_attributed_sale_flag=1")
    if attributed_flag == 1 and purchase_flag != 1:
        raise DataValidationError("campaign_attributed_sale_flag=1 requires purchase_flag=1")

    if purchase_flag == 1:
        values["order_id"] = _required_text(row, "order_id")
        purchase_date_value = values["purchase_date"]
        if purchase_date_value is None:
            raise DataValidationError("purchase_flag=1 requires purchase_date")
        purchase_date = date.fromisoformat(str(purchase_date_value))
        if purchase_date < contact:
            raise DataValidationError("purchase_date must not be before contact_date")
        quantity = values["quantity"]
        if quantity is None or int(quantity) < 1:
            raise DataValidationError("purchase_flag=1 requires quantity of at least 1")
        days_to_purchase = values["days_to_purchase"]
        if days_to_purchase is not None and int(days_to_purchase) != (purchase_date - contact).days:
            raise DataValidationError("days_to_purchase must match purchase_date minus contact_date")
    else:
        for field in (
            "quantity",
            "gross_sales_amount",
            "discount_amount",
            "net_sales_amount",
            "gross_margin_amount",
        ):
            if values[field] not in (None, 0, 0.0):
                raise DataValidationError(f"purchase_flag=0 requires {field} to be zero or blank")

    return tuple(values[column] for column in CAMPAIGN_SALES_COLUMNS)


def validate_demographic_row(row: Mapping[str, str]) -> tuple[object, ...]:
    """Validate and convert one demographic source row."""
    values = _base_values(row, DEMOGRAPHIC_COLUMNS)
    values["person_id"] = _required_text(row, "person_id")
    values["state"] = _required_text(row, "state")

    age = _integer(row["age"], "age")
    if age is None or not 0 <= age <= 120:
        raise DataValidationError("age must be between 0 and 120")
    values["age"] = age

    family_count = _integer(row["family_member_count"], "family_member_count")
    children = _integer(
        row["number_of_children_in_family"], "number_of_children_in_family"
    )
    adults = _integer(row["number_of_adults_in_family"], "number_of_adults_in_family")
    if family_count is None or family_count < 1:
        raise DataValidationError("family_member_count must be at least 1")
    if children is None or children < 0:
        raise DataValidationError("number_of_children_in_family must be nonnegative")
    if adults is None or adults < 0:
        raise DataValidationError("number_of_adults_in_family must be nonnegative")
    if children + adults != family_count:
        raise DataValidationError(
            "number_of_children_in_family + number_of_adults_in_family "
            "must equal family_member_count"
        )
    values["family_member_count"] = family_count
    values["number_of_children_in_family"] = children
    values["number_of_adults_in_family"] = adults

    individual_income = _number(
        row["individual_yearly_income"], "individual_yearly_income"
    )
    family_income = _number(row["family_yearly_income"], "family_yearly_income")
    if individual_income is None or individual_income < 0:
        raise DataValidationError("individual_yearly_income must be nonnegative")
    if family_income is None or family_income < 0:
        raise DataValidationError("family_yearly_income must be nonnegative")
    if family_income < individual_income:
        raise DataValidationError(
            "family_yearly_income must be greater than or equal to individual_yearly_income"
        )
    values["individual_yearly_income"] = individual_income
    values["family_yearly_income"] = family_income

    return tuple(values[column] for column in DEMOGRAPHIC_COLUMNS)
