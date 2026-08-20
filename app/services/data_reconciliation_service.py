"""Dataset reconciliation and structural data-quality checks."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app import config
from app.database.connection import get_connection
from app.database.schema import initialize_database


logger = logging.getLogger(__name__)

STATUS_NOT_LOADED = "NOT_LOADED"
STATUS_OK = "OK"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "ERROR"


def default_expected_counts() -> dict[str, dict[str, int | bool | float | None]]:
    """Return expected row-count policy using the current environment configuration."""
    return {
        "customers": {
            "expected_count": config.EXPECTED_CUSTOMER_ROWS,
            "exact_match_required": config.CUSTOMER_COUNT_EXACT_REQUIRED,
            "count_tolerance_percent": (
                None
                if config.CUSTOMER_COUNT_EXACT_REQUIRED
                else config.CUSTOMER_COUNT_TOLERANCE_PERCENT
            ),
        },
        "campaign_sales": {
            "expected_count": config.EXPECTED_CAMPAIGN_SALES_ROWS,
            "exact_match_required": config.CAMPAIGN_SALES_COUNT_EXACT_REQUIRED,
            "count_tolerance_percent": None,
        },
        "demographics": {
            "expected_count": config.EXPECTED_DEMOGRAPHIC_ROWS,
            "exact_match_required": config.DEMOGRAPHIC_COUNT_EXACT_REQUIRED,
            "count_tolerance_percent": None,
        },
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timed_query(connection: Any, dataset: str, sql: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    row = connection.execute(sql).fetchone()
    elapsed = time.perf_counter() - started
    logger.info("Reconciliation query completed | dataset=%s seconds=%.3f", dataset, elapsed)
    return dict(row), elapsed


def _count_status(
    *,
    actual_count: int,
    acceptable_count: bool,
    structural_error_count: int,
) -> str:
    if actual_count == 0:
        return STATUS_NOT_LOADED
    if structural_error_count:
        return STATUS_ERROR
    if not acceptable_count:
        return STATUS_WARNING
    return STATUS_OK


def _count_policy_result(
    *,
    actual_count: int,
    expected_count: int,
    exact_match_required: bool,
    count_tolerance_percent: float | None,
) -> dict[str, int | float | bool | None]:
    if exact_match_required:
        tolerance = None
        acceptable_min_rows = expected_count
        acceptable_max_rows = expected_count
    else:
        tolerance = 0.0 if count_tolerance_percent is None else float(
            count_tolerance_percent
        )
        if not math.isfinite(tolerance) or not 0 <= tolerance <= 100:
            raise ValueError("count_tolerance_percent must be from 0 through 100")
        acceptable_min_rows = math.ceil(expected_count * (1 - tolerance / 100))
        acceptable_max_rows = math.floor(expected_count * (1 + tolerance / 100))

    return {
        "count_tolerance_percent": tolerance,
        "acceptable_min_rows": acceptable_min_rows,
        "acceptable_max_rows": acceptable_max_rows,
        "acceptable_count": acceptable_min_rows <= actual_count <= acceptable_max_rows,
    }


def _dataset_result(
    *,
    metrics: dict[str, Any],
    policy: Mapping[str, int | bool | float | None],
    structural_issues: Mapping[str, int],
    query_seconds: float,
) -> dict[str, Any]:
    actual_count = int(metrics["total_rows"])
    expected_count = int(policy["expected_count"])
    exact_match_required = bool(policy["exact_match_required"])
    count_policy = _count_policy_result(
        actual_count=actual_count,
        expected_count=expected_count,
        exact_match_required=exact_match_required,
        count_tolerance_percent=policy.get("count_tolerance_percent"),
    )
    structural_error_count = sum(int(value) for value in structural_issues.values())
    return {
        "status": _count_status(
            actual_count=actual_count,
            acceptable_count=bool(count_policy["acceptable_count"]),
            structural_error_count=structural_error_count,
        ),
        "expected_count": expected_count,
        "actual_count": actual_count,
        "exact_match_required": exact_match_required,
        "expected_count_match": actual_count == expected_count,
        **count_policy,
        "structural_error_count": structural_error_count,
        "structural_issues": dict(structural_issues),
        "metrics": metrics,
        "query_seconds": round(query_seconds, 6),
    }


def _overall_status(dataset_statuses: list[str]) -> str:
    if STATUS_ERROR in dataset_statuses:
        return STATUS_ERROR
    if STATUS_NOT_LOADED in dataset_statuses:
        return STATUS_NOT_LOADED
    if STATUS_WARNING in dataset_statuses:
        return STATUS_WARNING
    return STATUS_OK


def run_reconciliation(
    database_path: str | Path | None = None,
    expected_counts: Mapping[str, Mapping[str, int | bool | float | None]] | None = None,
) -> dict[str, Any]:
    """Run machine-readable count, relationship, and consistency checks."""
    path = initialize_database(database_path)
    policies = expected_counts or default_expected_counts()
    started = time.perf_counter()

    with get_connection(path) as connection:
        customer_metrics, customer_seconds = _timed_query(
            connection,
            "customers",
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT customer_id) AS distinct_customer_id,
                MIN(date_of_birth) AS min_date_of_birth,
                MAX(date_of_birth) AS max_date_of_birth,
                COALESCE(SUM(
                    CASE WHEN customer_id IS NULL OR TRIM(customer_id) = '' THEN 1 ELSE 0 END
                ), 0)
                    AS null_or_blank_critical_identifiers
            FROM customers
            """,
        )
        customers = _dataset_result(
            metrics=customer_metrics,
            policy=policies["customers"],
            structural_issues={
                "duplicate_customer_id_count": (
                    customer_metrics["total_rows"] - customer_metrics["distinct_customer_id"]
                ),
                "null_or_blank_critical_identifiers": customer_metrics[
                    "null_or_blank_critical_identifiers"
                ],
            },
            query_seconds=customer_seconds,
        )

        campaign_metrics, campaign_seconds = _timed_query(
            connection,
            "campaign_sales",
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT campaign_sales_id) AS distinct_campaign_sales_id,
                COUNT(DISTINCT customer_id) AS distinct_customer_id,
                COUNT(DISTINCT campaign_id) AS distinct_campaign_id,
                COUNT(DISTINCT product_id) AS distinct_product_id,
                MIN(contact_date) AS min_contact_date,
                MAX(contact_date) AS max_contact_date,
                COALESCE(SUM(CASE WHEN purchase_flag = 1 THEN 1 ELSE 0 END), 0)
                    AS purchase_count,
                COALESCE(SUM(CASE WHEN campaign_attributed_sale_flag = 1 THEN 1 ELSE 0 END), 0)
                    AS attributed_purchase_count,
                COALESCE(SUM(CASE WHEN pu_label = 1 THEN 1 ELSE 0 END), 0)
                    AS pu_positive_count,
                COALESCE(SUM(
                    CASE
                        WHEN (pu_label = 1 AND campaign_attributed_sale_flag <> 1)
                          OR (campaign_attributed_sale_flag = 1 AND purchase_flag <> 1)
                        THEN 1 ELSE 0
                    END
                ), 0) AS pu_consistency_violation_count
            FROM campaign_sales
            """,
        )
        invalid_fk_metrics, invalid_fk_seconds = _timed_query(
            connection,
            "campaign_sales_invalid_customer_fk",
            """
            SELECT COUNT(*) AS invalid_customer_fk_count
            FROM campaign_sales AS campaign
            LEFT JOIN customers AS customer ON customer.customer_id = campaign.customer_id
            WHERE customer.customer_id IS NULL
            """,
        )
        campaign_metrics.update(invalid_fk_metrics)
        campaign_sales = _dataset_result(
            metrics=campaign_metrics,
            policy=policies["campaign_sales"],
            structural_issues={
                "duplicate_campaign_sales_id_count": (
                    campaign_metrics["total_rows"]
                    - campaign_metrics["distinct_campaign_sales_id"]
                ),
                "invalid_customer_fk_count": campaign_metrics["invalid_customer_fk_count"],
                "pu_consistency_violation_count": campaign_metrics[
                    "pu_consistency_violation_count"
                ],
            },
            query_seconds=campaign_seconds + invalid_fk_seconds,
        )

        demographic_metrics, demographic_seconds = _timed_query(
            connection,
            "demographics",
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT person_id) AS distinct_person_id,
                MIN(age) AS min_age,
                MAX(age) AS max_age,
                MIN(individual_yearly_income) AS min_individual_yearly_income,
                MAX(individual_yearly_income) AS max_individual_yearly_income,
                COALESCE(SUM(
                    CASE
                        WHEN family_member_count <>
                            number_of_children_in_family + number_of_adults_in_family
                        THEN 1 ELSE 0
                    END
                ), 0) AS family_arithmetic_violation_count,
                COALESCE(SUM(
                    CASE WHEN family_yearly_income < individual_yearly_income THEN 1 ELSE 0 END
                ), 0) AS family_income_below_individual_violation_count
            FROM demographics
            """,
        )
        demographics = _dataset_result(
            metrics=demographic_metrics,
            policy=policies["demographics"],
            structural_issues={
                "duplicate_person_id_count": (
                    demographic_metrics["total_rows"]
                    - demographic_metrics["distinct_person_id"]
                ),
                "family_arithmetic_violation_count": demographic_metrics[
                    "family_arithmetic_violation_count"
                ],
                "family_income_below_individual_violation_count": demographic_metrics[
                    "family_income_below_individual_violation_count"
                ],
            },
            query_seconds=demographic_seconds,
        )

    datasets = {
        "customers": customers,
        "campaign_sales": campaign_sales,
        "demographics": demographics,
    }
    total_seconds = time.perf_counter() - started
    result = {
        "overall_status": _overall_status(
            [dataset["status"] for dataset in datasets.values()]
        ),
        "database_path": str(path),
        "generated_at": _utc_timestamp(),
        "total_query_seconds": round(total_seconds, 6),
        "datasets": datasets,
    }
    logger.info(
        "Reconciliation completed | status=%s seconds=%.3f",
        result["overall_status"],
        total_seconds,
    )
    return result


def format_reconciliation_report(result: Mapping[str, Any]) -> str:
    """Format a concise human-readable reconciliation report."""
    lines = [
        f"Database: {result['database_path']}",
        f"Overall status: {result['overall_status']}",
        "",
        "Dataset          Status       Actual    Expected  Exact required  Issues  Seconds",
        "---------------  -----------  --------  --------  --------------  ------  -------",
    ]
    for name, dataset in result["datasets"].items():
        lines.append(
            f"{name:<15}  {dataset['status']:<11}  {dataset['actual_count']:>8,}  "
            f"{dataset['expected_count']:>8,}  {str(dataset['exact_match_required']):>14}  "
            f"{dataset['structural_error_count']:>6,}  {dataset['query_seconds']:>7.3f}"
        )

    lines.extend(["", "Key metrics:"])
    for name, dataset in result["datasets"].items():
        metrics = ", ".join(f"{key}={value}" for key, value in dataset["metrics"].items())
        lines.append(f"- {name}: {metrics}")
    lines.append(f"Total query time: {result['total_query_seconds']:.3f} seconds")
    return "\n".join(lines)
