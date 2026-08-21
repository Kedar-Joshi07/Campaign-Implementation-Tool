"""Business response composition for Phase 2 historical aggregates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.repositories.historical_repository import HistoricalRepository


CONVERSION_DEFINITIONS = (
    {
        "value": "ATTRIBUTED_PURCHASE",
        "label": "Campaign-attributed purchase",
        "description": (
            "A confirmed purchase attributed to the selected campaign context."
        ),
    },
    {
        "value": "ANY_PURCHASE",
        "label": "Any purchase",
        "description": "Any observed purchase inside the selected campaign context.",
    },
    {
        "value": "RESPONSE",
        "label": "Campaign response",
        "description": "Any observed response inside the selected campaign context.",
    },
)

_COUNT_FIELDS = (
    "observation_count",
    "contacted_count",
    "engaged_count",
    "response_count",
    "purchase_count",
    "attributed_purchase_count",
)
_MONEY_FIELDS = ("net_sales_amount", "gross_margin_amount")
_RATE_NUMERATORS = {
    "engagement_rate": "engaged_count",
    "response_rate": "response_count",
    "purchase_rate": "purchase_count",
    "attributed_purchase_rate": "attributed_purchase_count",
}


def _safe_rate(numerator: int, denominator: int) -> float:
    """Return a fraction rounded to six decimals; zero contacts produce 0.0."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _normalize_aggregate(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for field in _COUNT_FIELDS:
        normalized[field] = int(normalized.get(field) or 0)
    for field in _MONEY_FIELDS:
        value = round(float(normalized.get(field) or 0), 2)
        normalized[field] = 0.0 if value == 0 else value

    contacted_count = normalized["contacted_count"]
    for rate_field, numerator_field in _RATE_NUMERATORS.items():
        normalized[rate_field] = _safe_rate(
            normalized[numerator_field],
            contacted_count,
        )
    return normalized


def get_historical_options(database_path: str | Path) -> dict[str, Any]:
    options = HistoricalRepository(database_path).fetch_options()
    available_date_from = options["available_date_from"]
    available_date_to = options["available_date_to"]
    return {
        **options,
        "conversion_definitions": [dict(item) for item in CONVERSION_DEFINITIONS],
        "defaults": {
            "campaign_ids": [],
            "product_ids": [],
            "product_categories": [],
            "campaign_channels": [],
            "campaign_types": [],
            "contact_date_from": available_date_from,
            "contact_date_to": available_date_to,
            "contacted_only": True,
            "conversion_definition": "ATTRIBUTED_PURCHASE",
        },
    }


def get_historical_overview(database_path: str | Path) -> dict[str, Any]:
    raw = HistoricalRepository(database_path).fetch_overview()
    summary = _normalize_aggregate(raw["summary"])
    for field in (
        "distinct_customer_count",
        "distinct_campaign_count",
        "distinct_product_count",
    ):
        summary[field] = int(summary.get(field) or 0)

    return {
        "summary": summary,
        "monthly_trend": [
            _normalize_aggregate(row) for row in raw["monthly_trend"]
        ],
        "channel_performance": [
            _normalize_aggregate(row) for row in raw["channel_performance"]
        ],
        "product_category_performance": [
            _normalize_aggregate(row)
            for row in raw["product_category_performance"]
        ],
        "top_campaigns": [
            _normalize_aggregate(row) for row in raw["top_campaigns"]
        ],
        "top_products": [
            _normalize_aggregate(row) for row in raw["top_products"]
        ],
        "label_distribution": [
            {
                "pu_label": int(row["pu_label"]),
                "label": (
                    "Known positive observations"
                    if row["pu_label"] == 1
                    else "Unlabeled observations"
                ),
                "observation_count": int(row["observation_count"]),
            }
            for row in raw["label_distribution"]
        ],
    }
