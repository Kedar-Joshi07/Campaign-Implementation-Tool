"""Bounded SQLite aggregates for Phase 2 historical campaign analysis."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.database.connection import get_connection


logger = logging.getLogger(__name__)

CAMPAIGN_OPTION_LIMIT = 250
PRODUCT_OPTION_LIMIT = 250
CATEGORY_OPTION_LIMIT = 100
CHANNEL_OPTION_LIMIT = 100
CAMPAIGN_TYPE_OPTION_LIMIT = 100
MONTHLY_TREND_LIMIT = 120
CHANNEL_BREAKDOWN_LIMIT = 10
CATEGORY_BREAKDOWN_LIMIT = 10
TOP_CAMPAIGN_LIMIT = 10
TOP_PRODUCT_LIMIT = 10
PROFILE_CATEGORY_LIMIT = 20
STATE_PROFILE_LIMIT = 10

_CONVERSION_EXPRESSIONS = {
    "ATTRIBUTED_PURCHASE": (
        "campaign_attributed_sale_flag = 1 AND purchase_flag = 1"
    ),
    "ANY_PURCHASE": "purchase_flag = 1",
    "RESPONSE": "response_flag = 1",
}
_FILTER_COLUMNS = {
    "campaign_ids": "campaign_id",
    "product_ids": "product_id",
    "product_categories": "product_category",
    "campaign_channels": "campaign_channel",
    "campaign_types": "campaign_type",
}


def build_matching_observations_cte(
    filters: dict[str, Any],
) -> tuple[str, tuple[Any, ...]]:
    """Build the authoritative parameterized Phase 2 cohort/label CTE."""
    clauses: list[str] = []
    parameters: list[Any] = []

    for filter_name, column in _FILTER_COLUMNS.items():
        values = filters[filter_name]
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        clauses.append(f"{column} IN ({placeholders})")
        parameters.extend(values)

    if filters["contact_date_from"] is not None:
        clauses.append("contact_date >= ?")
        parameters.append(filters["contact_date_from"])
    if filters["contact_date_to"] is not None:
        clauses.append("contact_date <= ?")
        parameters.append(filters["contact_date_to"])
    if filters["contacted_only"]:
        clauses.append("contacted_flag = 1")

    where_clause = " AND ".join(clauses) if clauses else "1 = 1"
    positive_expression = _CONVERSION_EXPRESSIONS[filters["conversion_definition"]]
    cte = f"""
        WITH matching_observations AS (
            SELECT *
            FROM campaign_sales
            WHERE {where_clause}
        ),
        customer_labels AS (
            SELECT
                customer_id,
                MAX(CASE WHEN {positive_expression} THEN 1 ELSE 0 END)
                    AS is_positive,
                COUNT(*) AS matching_observation_count
            FROM matching_observations
            GROUP BY customer_id
        )
    """
    return cte, tuple(parameters)

_AGGREGATE_COLUMNS_SQL = """
    COUNT(*) AS observation_count,
    COALESCE(SUM(CASE WHEN contacted_flag = 1 THEN 1 ELSE 0 END), 0)
        AS contacted_count,
    COALESCE(SUM(CASE WHEN engagement_flag = 1 THEN 1 ELSE 0 END), 0)
        AS engaged_count,
    COALESCE(SUM(CASE WHEN response_flag = 1 THEN 1 ELSE 0 END), 0)
        AS response_count,
    COALESCE(SUM(CASE WHEN purchase_flag = 1 THEN 1 ELSE 0 END), 0)
        AS purchase_count,
    COALESCE(SUM(
        CASE
            WHEN campaign_attributed_sale_flag = 1 AND purchase_flag = 1 THEN 1
            ELSE 0
        END
    ), 0) AS attributed_purchase_count,
    COALESCE(SUM(COALESCE(net_sales_amount, 0)), 0) AS net_sales_amount,
    COALESCE(SUM(COALESCE(gross_margin_amount, 0)), 0) AS gross_margin_amount
"""


class HistoricalRepository:
    """Run fixed, aggregate-only historical queries against one SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_options(self) -> dict[str, Any]:
        started = time.perf_counter()
        with get_connection(self.database_path) as connection:
            date_range = dict(
                connection.execute(
                    """
                    SELECT
                        MIN(contact_date) AS available_date_from,
                        MAX(contact_date) AS available_date_to
                    FROM campaign_sales
                    """
                ).fetchone()
            )
            campaigns = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        TRIM(campaign_id) AS campaign_id,
                        MIN(TRIM(campaign_name)) AS campaign_name,
                        COUNT(DISTINCT TRIM(campaign_name)) AS name_variant_count
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(campaign_id), '') IS NOT NULL
                      AND NULLIF(TRIM(campaign_name), '') IS NOT NULL
                    GROUP BY TRIM(campaign_id)
                    ORDER BY campaign_id COLLATE NOCASE, campaign_id
                    LIMIT ?
                    """,
                    (CAMPAIGN_OPTION_LIMIT,),
                ).fetchall()
            ]
            product_categories = [
                row["value"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT TRIM(product_category) AS value
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(product_category), '') IS NOT NULL
                    ORDER BY value COLLATE NOCASE, value
                    LIMIT ?
                    """,
                    (CATEGORY_OPTION_LIMIT,),
                ).fetchall()
            ]
            products = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        TRIM(product_id) AS product_id,
                        MIN(TRIM(product_name)) AS product_name,
                        MIN(TRIM(product_category)) AS product_category,
                        COUNT(DISTINCT TRIM(product_name)) AS name_variant_count,
                        COUNT(DISTINCT TRIM(product_category)) AS category_variant_count
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
                      AND NULLIF(TRIM(product_name), '') IS NOT NULL
                      AND NULLIF(TRIM(product_category), '') IS NOT NULL
                    GROUP BY TRIM(product_id)
                    ORDER BY product_id COLLATE NOCASE, product_id
                    LIMIT ?
                    """,
                    (PRODUCT_OPTION_LIMIT,),
                ).fetchall()
            ]
            campaign_channels = self._fetch_distinct_values(
                connection,
                column="campaign_channel",
                limit=CHANNEL_OPTION_LIMIT,
            )
            campaign_types = self._fetch_distinct_values(
                connection,
                column="campaign_type",
                limit=CAMPAIGN_TYPE_OPTION_LIMIT,
            )

        self._log_option_inconsistencies(campaigns, products)
        elapsed = time.perf_counter() - started
        logger.info(
            "Historical options queries completed | query_count=6 seconds=%.3f",
            elapsed,
        )
        return {
            **date_range,
            "campaigns": [
                {"campaign_id": row["campaign_id"], "campaign_name": row["campaign_name"]}
                for row in campaigns
            ],
            "product_categories": product_categories,
            "products": [
                {
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "product_category": row["product_category"],
                }
                for row in products
            ],
            "campaign_channels": campaign_channels,
            "campaign_types": campaign_types,
        }

    @staticmethod
    def _fetch_distinct_values(
        connection,
        *,
        column: str,
        limit: int,
    ) -> list[str]:
        if column not in {"campaign_channel", "campaign_type"}:
            raise ValueError(f"Unsupported historical option column: {column}")
        return [
            row["value"]
            for row in connection.execute(
                f"""
                SELECT DISTINCT TRIM({column}) AS value
                FROM campaign_sales
                WHERE NULLIF(TRIM({column}), '') IS NOT NULL
                ORDER BY value COLLATE NOCASE, value
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

    @staticmethod
    def _log_option_inconsistencies(
        campaigns: list[dict[str, Any]],
        products: list[dict[str, Any]],
    ) -> None:
        for campaign in campaigns:
            if campaign["name_variant_count"] > 1:
                logger.warning(
                    "Inconsistent campaign labels detected | campaign_id=%s variants=%s",
                    campaign["campaign_id"],
                    campaign["name_variant_count"],
                )
        for product in products:
            if product["name_variant_count"] > 1 or product["category_variant_count"] > 1:
                logger.warning(
                    "Inconsistent product labels detected | product_id=%s "
                    "name_variants=%s category_variants=%s",
                    product["product_id"],
                    product["name_variant_count"],
                    product["category_variant_count"],
                )

    def fetch_overview(self) -> dict[str, Any]:
        started = time.perf_counter()
        with get_connection(self.database_path) as connection:
            summary = dict(
                connection.execute(
                    f"""
                    SELECT
                        {_AGGREGATE_COLUMNS_SQL},
                        COUNT(DISTINCT customer_id) AS distinct_customer_count,
                        COUNT(DISTINCT campaign_id) AS distinct_campaign_count,
                        COUNT(DISTINCT product_id) AS distinct_product_count,
                        MIN(contact_date) AS contact_date_from,
                        MAX(contact_date) AS contact_date_to
                    FROM campaign_sales
                    """
                ).fetchone()
            )
            monthly_trend = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        SUBSTR(contact_date, 1, 7) AS month,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(contact_date), '') IS NOT NULL
                    GROUP BY SUBSTR(contact_date, 1, 7)
                    ORDER BY month
                    LIMIT ?
                    """,
                    (MONTHLY_TREND_LIMIT,),
                ).fetchall()
            ]
            channel_performance = self._fetch_labeled_breakdown(
                connection,
                column="campaign_channel",
                limit=CHANNEL_BREAKDOWN_LIMIT,
            )
            product_category_performance = self._fetch_labeled_breakdown(
                connection,
                column="product_category",
                limit=CATEGORY_BREAKDOWN_LIMIT,
            )
            top_campaigns = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        TRIM(campaign_id) AS campaign_id,
                        COALESCE(MIN(NULLIF(TRIM(campaign_name), '')), TRIM(campaign_id))
                            AS campaign_name,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(campaign_id), '') IS NOT NULL
                    GROUP BY TRIM(campaign_id)
                    ORDER BY observation_count DESC, campaign_id COLLATE NOCASE, campaign_id
                    LIMIT ?
                    """,
                    (TOP_CAMPAIGN_LIMIT,),
                ).fetchall()
            ]
            top_products = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        TRIM(product_id) AS product_id,
                        COALESCE(MIN(NULLIF(TRIM(product_name), '')), TRIM(product_id))
                            AS product_name,
                        COALESCE(MIN(NULLIF(TRIM(product_category), '')), 'Unknown/Other')
                            AS product_category,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
                    GROUP BY TRIM(product_id)
                    ORDER BY observation_count DESC, product_id COLLATE NOCASE, product_id
                    LIMIT ?
                    """,
                    (TOP_PRODUCT_LIMIT,),
                ).fetchall()
            ]
            label_distribution = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT pu_label, COUNT(*) AS observation_count
                    FROM campaign_sales
                    GROUP BY pu_label
                    ORDER BY pu_label DESC
                    """
                ).fetchall()
            ]

        elapsed = time.perf_counter() - started
        logger.info(
            "Historical overview queries completed | query_count=7 seconds=%.3f",
            elapsed,
        )
        return {
            "summary": summary,
            "monthly_trend": monthly_trend,
            "channel_performance": channel_performance,
            "product_category_performance": product_category_performance,
            "top_campaigns": top_campaigns,
            "top_products": top_products,
            "label_distribution": label_distribution,
        }

    @staticmethod
    def _fetch_labeled_breakdown(
        connection,
        *,
        column: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if column not in {"campaign_channel", "product_category"}:
            raise ValueError(f"Unsupported historical breakdown column: {column}")
        if limit < 2:
            raise ValueError("Historical breakdown limit must be at least 2")

        rows = connection.execute(
            f"""
            WITH grouped AS (
                SELECT
                    COALESCE(NULLIF(TRIM({column}), ''), 'Unknown/Other') AS label,
                    {_AGGREGATE_COLUMNS_SQL}
                FROM campaign_sales
                GROUP BY COALESCE(NULLIF(TRIM({column}), ''), 'Unknown/Other')
            ),
            ranked AS (
                SELECT
                    grouped.*,
                    ROW_NUMBER() OVER (
                        ORDER BY observation_count DESC, label COLLATE NOCASE, label
                    ) AS group_rank,
                    COUNT(*) OVER () AS group_count
                FROM grouped
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN group_count <= ? OR group_rank < ? THEN label
                        ELSE 'Other'
                    END AS label,
                    observation_count,
                    contacted_count,
                    engaged_count,
                    response_count,
                    purchase_count,
                    attributed_purchase_count,
                    net_sales_amount,
                    gross_margin_amount
                FROM ranked
            )
            SELECT
                label,
                SUM(observation_count) AS observation_count,
                SUM(contacted_count) AS contacted_count,
                SUM(engaged_count) AS engaged_count,
                SUM(response_count) AS response_count,
                SUM(purchase_count) AS purchase_count,
                SUM(attributed_purchase_count) AS attributed_purchase_count,
                ROUND(SUM(net_sales_amount), 2) AS net_sales_amount,
                ROUND(SUM(gross_margin_amount), 2) AS gross_margin_amount
            FROM bucketed
            GROUP BY label
            ORDER BY observation_count DESC, label COLLATE NOCASE, label
            """,
            (limit, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_available_date_range(self) -> dict[str, str | None]:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    MIN(contact_date) AS available_date_from,
                    MAX(contact_date) AS available_date_to
                FROM campaign_sales
                """
            ).fetchone()
        return dict(row)

    @staticmethod
    def _matching_cte(filters: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        return build_matching_observations_cte(filters)

    def analyze_cohort(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Return aggregate-only results for one normalized historical cohort."""
        started = time.perf_counter()
        cte, parameters = self._matching_cte(filters)

        with get_connection(self.database_path) as connection:
            summary = dict(
                connection.execute(
                    f"""
                    {cte}
                    SELECT
                        {_AGGREGATE_COLUMNS_SQL},
                        COUNT(DISTINCT customer_id) AS selected_customer_count,
                        (SELECT COUNT(*) FROM customer_labels WHERE is_positive = 1)
                            AS positive_customer_count,
                        (SELECT COUNT(*) FROM customer_labels WHERE is_positive = 0)
                            AS unlabeled_customer_count,
                        COALESCE(SUM(
                            CASE
                                WHEN pu_label != CASE
                                    WHEN campaign_attributed_sale_flag = 1
                                         AND purchase_flag = 1 THEN 1
                                    ELSE 0
                                END THEN 1
                                ELSE 0
                            END
                        ), 0) AS pu_consistency_violation_count
                    FROM matching_observations
                    """,
                    parameters,
                ).fetchone()
            )
            monthly_trend = [
                dict(row)
                for row in connection.execute(
                    f"""
                    {cte}
                    SELECT
                        SUBSTR(contact_date, 1, 7) AS month,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM matching_observations
                    GROUP BY SUBSTR(contact_date, 1, 7)
                    ORDER BY month
                    LIMIT ?
                    """,
                    (*parameters, MONTHLY_TREND_LIMIT),
                ).fetchall()
            ]
            channel_performance = self._fetch_filtered_breakdown(
                connection,
                cte=cte,
                parameters=parameters,
                column="campaign_channel",
                limit=CHANNEL_BREAKDOWN_LIMIT,
            )
            product_category_performance = self._fetch_filtered_breakdown(
                connection,
                cte=cte,
                parameters=parameters,
                column="product_category",
                limit=CATEGORY_BREAKDOWN_LIMIT,
            )
            top_campaigns = [
                dict(row)
                for row in connection.execute(
                    f"""
                    {cte}
                    SELECT
                        TRIM(campaign_id) AS campaign_id,
                        COALESCE(MIN(NULLIF(TRIM(campaign_name), '')), TRIM(campaign_id))
                            AS campaign_name,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM matching_observations
                    GROUP BY TRIM(campaign_id)
                    ORDER BY observation_count DESC, campaign_id COLLATE NOCASE, campaign_id
                    LIMIT ?
                    """,
                    (*parameters, TOP_CAMPAIGN_LIMIT),
                ).fetchall()
            ]
            top_products = [
                dict(row)
                for row in connection.execute(
                    f"""
                    {cte}
                    SELECT
                        TRIM(product_id) AS product_id,
                        COALESCE(MIN(NULLIF(TRIM(product_name), '')), TRIM(product_id))
                            AS product_name,
                        COALESCE(MIN(NULLIF(TRIM(product_category), '')), 'Unknown/Other')
                            AS product_category,
                        {_AGGREGATE_COLUMNS_SQL}
                    FROM matching_observations
                    GROUP BY TRIM(product_id)
                    ORDER BY observation_count DESC, product_id COLLATE NOCASE, product_id
                    LIMIT ?
                    """,
                    (*parameters, TOP_PRODUCT_LIMIT),
                ).fetchall()
            ]
            profile_rows = self._fetch_profile_rows(
                connection,
                cte=cte,
                parameters=parameters,
                reference_date=filters["contact_date_to"],
            )

        elapsed = time.perf_counter() - started
        logger.info(
            "Historical cohort queries completed | query_count=7 seconds=%.3f",
            elapsed,
        )
        return {
            "summary": summary,
            "monthly_trend": monthly_trend,
            "channel_performance": channel_performance,
            "product_category_performance": product_category_performance,
            "top_campaigns": top_campaigns,
            "top_products": top_products,
            "profile_rows": profile_rows,
        }

    @staticmethod
    def _fetch_filtered_breakdown(
        connection: sqlite3.Connection,
        *,
        cte: str,
        parameters: tuple[Any, ...],
        column: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if column not in {"campaign_channel", "product_category"}:
            raise ValueError(f"Unsupported historical breakdown column: {column}")
        if limit < 2:
            raise ValueError("Historical breakdown limit must be at least 2")

        rows = connection.execute(
            f"""
            {cte},
            grouped AS (
                SELECT
                    COALESCE(NULLIF(TRIM({column}), ''), 'Unknown/Other') AS label,
                    {_AGGREGATE_COLUMNS_SQL}
                FROM matching_observations
                GROUP BY COALESCE(NULLIF(TRIM({column}), ''), 'Unknown/Other')
            ),
            ranked AS (
                SELECT
                    grouped.*,
                    ROW_NUMBER() OVER (
                        ORDER BY observation_count DESC, label COLLATE NOCASE, label
                    ) AS group_rank,
                    COUNT(*) OVER () AS group_count
                FROM grouped
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN group_count <= ? OR group_rank < ? THEN label
                        ELSE 'Other'
                    END AS label,
                    observation_count,
                    contacted_count,
                    engaged_count,
                    response_count,
                    purchase_count,
                    attributed_purchase_count,
                    net_sales_amount,
                    gross_margin_amount
                FROM ranked
            )
            SELECT
                label,
                SUM(observation_count) AS observation_count,
                SUM(contacted_count) AS contacted_count,
                SUM(engaged_count) AS engaged_count,
                SUM(response_count) AS response_count,
                SUM(purchase_count) AS purchase_count,
                SUM(attributed_purchase_count) AS attributed_purchase_count,
                ROUND(SUM(net_sales_amount), 2) AS net_sales_amount,
                ROUND(SUM(gross_margin_amount), 2) AS gross_margin_amount
            FROM bucketed
            GROUP BY label
            ORDER BY observation_count DESC, label COLLATE NOCASE, label
            """,
            (*parameters, limit, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _fetch_profile_rows(
        connection: sqlite3.Connection,
        *,
        cte: str,
        parameters: tuple[Any, ...],
        reference_date: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            f"""
            {cte},
            analysis_reference AS (
                SELECT DATE(?) AS reference_date
            ),
            selected_customers AS MATERIALIZED (
                SELECT
                    c.*,
                    labels.is_positive,
                    CASE
                        WHEN DATE(c.date_of_birth) IS NULL THEN NULL
                        ELSE
                            CAST(STRFTIME('%Y', reference.reference_date) AS INTEGER)
                            - CAST(SUBSTR(c.date_of_birth, 1, 4) AS INTEGER)
                            - CASE
                                WHEN STRFTIME('%m-%d', reference.reference_date)
                                     < SUBSTR(c.date_of_birth, 6, 5) THEN 1
                                ELSE 0
                              END
                    END AS derived_age
                FROM customer_labels AS labels
                JOIN customers AS c ON c.customer_id = labels.customer_id
                CROSS JOIN analysis_reference AS reference
            ),
            baseline_customers AS MATERIALIZED (
                SELECT
                    c.*,
                    NULL AS is_positive,
                    CASE
                        WHEN DATE(c.date_of_birth) IS NULL THEN NULL
                        ELSE
                            CAST(STRFTIME('%Y', reference.reference_date) AS INTEGER)
                            - CAST(SUBSTR(c.date_of_birth, 1, 4) AS INTEGER)
                            - CASE
                                WHEN STRFTIME('%m-%d', reference.reference_date)
                                     < SUBSTR(c.date_of_birth, 6, 5) THEN 1
                                ELSE 0
                              END
                    END AS derived_age
                FROM customers AS c
                CROSS JOIN analysis_reference AS reference
            ),
            profile_members AS MATERIALIZED (
                SELECT 'selected' AS group_name, * FROM selected_customers
                UNION ALL
                SELECT 'positive' AS group_name, *
                FROM selected_customers WHERE is_positive = 1
                UNION ALL
                SELECT 'unlabeled' AS group_name, *
                FROM selected_customers WHERE is_positive = 0
                UNION ALL
                SELECT 'historical_baseline' AS group_name, * FROM baseline_customers
            ),
            normalized_members AS MATERIALIZED (
                SELECT
                    group_name,
                    CASE
                        WHEN derived_age BETWEEN 18 AND 24 THEN '18–24'
                        WHEN derived_age BETWEEN 25 AND 34 THEN '25–34'
                        WHEN derived_age BETWEEN 35 AND 44 THEN '35–44'
                        WHEN derived_age BETWEEN 45 AND 54 THEN '45–54'
                        WHEN derived_age BETWEEN 55 AND 64 THEN '55–64'
                        WHEN derived_age >= 65 THEN '65+'
                        ELSE 'Unknown/Other'
                    END AS age_band,
                    COALESCE(NULLIF(TRIM(gender), ''), 'Unknown/Other') AS gender,
                    COALESCE(NULLIF(TRIM(state), ''), 'Unknown/Other') AS state,
                    CASE
                        WHEN individual_yearly_income < 25000 THEN '<25K'
                        WHEN individual_yearly_income < 50000 THEN '25K–49,999'
                        WHEN individual_yearly_income < 75000 THEN '50K–74,999'
                        WHEN individual_yearly_income < 100000 THEN '75K–99,999'
                        WHEN individual_yearly_income < 150000 THEN '100K–149,999'
                        WHEN individual_yearly_income < 250000 THEN '150K–249,999'
                        WHEN individual_yearly_income >= 250000 THEN '250K+'
                        ELSE 'Unknown/Other'
                    END AS individual_income_band,
                    COALESCE(NULLIF(TRIM(marital_status), ''), 'Unknown/Other')
                        AS marital_status,
                    COALESCE(NULLIF(TRIM(education), ''), 'Unknown/Other') AS education,
                    COALESCE(NULLIF(TRIM(employment_status), ''), 'Unknown/Other')
                        AS employment_status,
                    COALESCE(NULLIF(TRIM(resident_status), ''), 'Unknown/Other')
                        AS resident_status,
                    COALESCE(NULLIF(TRIM(resident_type), ''), 'Unknown/Other')
                        AS resident_type,
                    CASE
                        WHEN family_member_count = 1 THEN '1'
                        WHEN family_member_count = 2 THEN '2'
                        WHEN family_member_count BETWEEN 3 AND 4 THEN '3–4'
                        WHEN family_member_count >= 5 THEN '5+'
                        ELSE 'Unknown/Other'
                    END AS family_member_count_band,
                    COALESCE(NULLIF(TRIM(type_of_employment), ''), 'Unknown/Other')
                        AS type_of_employment
                FROM profile_members
            ),
            profile_values AS (
                SELECT group_name, 'age_band' AS dimension, age_band AS category,
                       ? AS category_limit FROM normalized_members
                UNION ALL
                SELECT group_name, 'gender', gender, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'state', state, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'individual_income_band', individual_income_band, ?
                FROM normalized_members
                UNION ALL
                SELECT group_name, 'marital_status', marital_status, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'education', education, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'employment_status', employment_status, ?
                FROM normalized_members
                UNION ALL
                SELECT group_name, 'resident_status', resident_status, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'resident_type', resident_type, ? FROM normalized_members
                UNION ALL
                SELECT group_name, 'family_member_count_band', family_member_count_band, ?
                FROM normalized_members
                UNION ALL
                SELECT group_name, 'type_of_employment', type_of_employment, ?
                FROM normalized_members
            ),
            category_counts AS (
                SELECT
                    group_name,
                    dimension,
                    category,
                    category_limit,
                    COUNT(*) AS category_count
                FROM profile_values
                GROUP BY group_name, dimension, category, category_limit
            ),
            ranked AS (
                SELECT
                    category_counts.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_name, dimension
                        ORDER BY category_count DESC, category COLLATE NOCASE, category
                    ) AS category_rank,
                    COUNT(*) OVER (PARTITION BY group_name, dimension) AS distinct_categories
                FROM category_counts
            ),
            bucketed AS (
                SELECT
                    group_name,
                    dimension,
                    CASE
                        WHEN distinct_categories <= category_limit
                             OR category_rank < category_limit THEN category
                        ELSE 'Other'
                    END AS category,
                    category_count
                FROM ranked
            )
            SELECT
                group_name,
                dimension,
                category,
                SUM(category_count) AS category_count
            FROM bucketed
            GROUP BY group_name, dimension, category
            ORDER BY group_name, dimension, category_count DESC,
                     category COLLATE NOCASE, category
            """,
            (
                *parameters,
                reference_date,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                STATE_PROFILE_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
                PROFILE_CATEGORY_LIMIT,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_analysis_run(
        self,
        *,
        analysis_name: str,
        created_at: str,
        conversion_definition: str,
        filters_json: str,
    ) -> int:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO historical_analysis_runs (
                    analysis_name,
                    created_at,
                    status,
                    conversion_definition,
                    filters_json
                ) VALUES (?, ?, 'RUNNING', ?, ?)
                """,
                (analysis_name, created_at, conversion_definition, filters_json),
            )
            return int(cursor.lastrowid)

    def complete_analysis_run(
        self,
        *,
        analysis_run_id: int,
        completed_at: str,
        summary: dict[str, Any],
        results_json: str,
    ) -> None:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE historical_analysis_runs
                SET
                    completed_at = ?,
                    status = 'COMPLETED',
                    results_json = ?,
                    observation_count = ?,
                    selected_customer_count = ?,
                    positive_customer_count = ?,
                    unlabeled_customer_count = ?,
                    positive_customer_rate = ?,
                    error_message = NULL
                WHERE analysis_run_id = ? AND status = 'RUNNING'
                """,
                (
                    completed_at,
                    results_json,
                    summary["observation_count"],
                    summary["selected_customer_count"],
                    summary["positive_customer_count"],
                    summary["unlabeled_customer_count"],
                    summary["positive_customer_rate"],
                    analysis_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Analysis run was not in RUNNING state during completion")

    def fail_analysis_run(
        self,
        *,
        analysis_run_id: int,
        completed_at: str,
        error_message: str,
    ) -> None:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE historical_analysis_runs
                SET
                    completed_at = ?,
                    status = 'FAILED',
                    results_json = NULL,
                    error_message = ?
                WHERE analysis_run_id = ? AND status = 'RUNNING'
                """,
                (completed_at, error_message, analysis_run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Analysis run was not in RUNNING state during failure")

    def fetch_analysis_run(self, analysis_run_id: int) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    analysis_run_id,
                    analysis_name,
                    created_at,
                    completed_at,
                    status,
                    conversion_definition,
                    filters_json,
                    results_json,
                    observation_count,
                    selected_customer_count,
                    positive_customer_count,
                    unlabeled_customer_count,
                    positive_customer_rate,
                    error_message
                FROM historical_analysis_runs
                WHERE analysis_run_id = ?
                """,
                (analysis_run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_analysis_runs(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    analysis_run_id,
                    analysis_name,
                    created_at,
                    completed_at,
                    status,
                    conversion_definition,
                    filters_json,
                    observation_count,
                    selected_customer_count,
                    positive_customer_count,
                    unlabeled_customer_count,
                    positive_customer_rate,
                    error_message
                FROM historical_analysis_runs
                ORDER BY created_at DESC, analysis_run_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
