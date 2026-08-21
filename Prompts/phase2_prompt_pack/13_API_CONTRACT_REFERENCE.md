# Phase 2 Historical API Contract Reference

This is the concise public contract. Exact Pydantic class names may differ, but behavior and field meaning must not.

## Common conventions

- JSON keys use `snake_case`.
- Dates use ISO `YYYY-MM-DD`.
- Timestamps use UTC ISO 8601.
- Rates are fractions from 0 through 1, not percentage points.
- Money values are JSON numbers rounded consistently for display/storage.
- Counts are non-negative integers.
- Arrays are bounded and deterministically ordered.
- Public errors use a stable `detail` message and expose no internal diagnostics.
- No response includes person-level historical or demographic records.

## `GET /api/historical/options`

Example shape:

```json
{
  "available_date_from": "2024-01-01",
  "available_date_to": "2025-12-31",
  "campaigns": [
    {"campaign_id": "CMP001", "campaign_name": "Example Campaign"}
  ],
  "product_categories": ["Electronics"],
  "products": [
    {
      "product_id": "PRD001",
      "product_name": "Example Product",
      "product_category": "Electronics"
    }
  ],
  "campaign_channels": ["Email"],
  "campaign_types": ["Acquisition"],
  "conversion_definitions": [
    {
      "value": "ATTRIBUTED_PURCHASE",
      "label": "Campaign-attributed purchase",
      "description": "A confirmed purchase attributed to the selected campaign context."
    },
    {
      "value": "ANY_PURCHASE",
      "label": "Any purchase",
      "description": "Any observed purchase inside the selected campaign context."
    },
    {
      "value": "RESPONSE",
      "label": "Campaign response",
      "description": "Any observed response inside the selected campaign context."
    }
  ],
  "defaults": {
    "campaign_ids": [],
    "product_ids": [],
    "product_categories": [],
    "campaign_channels": [],
    "campaign_types": [],
    "contact_date_from": "2024-01-01",
    "contact_date_to": "2025-12-31",
    "contacted_only": true,
    "conversion_definition": "ATTRIBUTED_PURCHASE"
  }
}
```

If campaign history is empty, dates may be null and option arrays empty. The response must clearly indicate not-loaded/readiness state if needed.

## `GET /api/historical/overview`

Example top-level shape:

```json
{
  "summary": {
    "observation_count": 570000,
    "contacted_count": 0,
    "engaged_count": 0,
    "response_count": 0,
    "purchase_count": 0,
    "attributed_purchase_count": 0,
    "distinct_customer_count": 125000,
    "distinct_campaign_count": 96,
    "distinct_product_count": 36,
    "net_sales_amount": 0.0,
    "gross_margin_amount": 0.0,
    "engagement_rate": 0.0,
    "response_rate": 0.0,
    "purchase_rate": 0.0,
    "attributed_purchase_rate": 0.0,
    "contact_date_from": "2024-01-01",
    "contact_date_to": "2025-12-31"
  },
  "monthly_trend": [],
  "channel_performance": [],
  "product_category_performance": [],
  "top_campaigns": [],
  "top_products": [],
  "label_distribution": []
}
```

Do not hard-code example numbers. Use real database values.

Recommended breakdown fields include label/ID where applicable, observations, contacted, engaged, responses, purchases, attributed purchases, net sales, and documented rates.

## `POST /api/historical/analyses`

Request:

```json
{
  "analysis_name": "Holiday electronics attributed purchasers",
  "campaign_ids": ["CMP001"],
  "product_ids": [],
  "product_categories": ["Electronics"],
  "campaign_channels": ["Email"],
  "campaign_types": [],
  "contact_date_from": "2024-01-01",
  "contact_date_to": "2025-12-31",
  "contacted_only": true,
  "conversion_definition": "ATTRIBUTED_PURCHASE"
}
```

Empty arrays mean no restriction. Omitted dates normalize to the available range. Omitted name receives a server-generated name.

Success: HTTP 201.

Example response shape:

```json
{
  "analysis_run_id": 7,
  "analysis_name": "Holiday electronics attributed purchasers",
  "created_at": "2026-08-20T12:00:00Z",
  "completed_at": "2026-08-20T12:00:01Z",
  "status": "COMPLETED",
  "filters": {
    "campaign_ids": ["CMP001"],
    "product_ids": [],
    "product_categories": ["Electronics"],
    "campaign_channels": ["Email"],
    "campaign_types": [],
    "contact_date_from": "2024-01-01",
    "contact_date_to": "2025-12-31",
    "contacted_only": true,
    "conversion_definition": "ATTRIBUTED_PURCHASE"
  },
  "summary": {
    "observation_count": 0,
    "selected_customer_count": 0,
    "positive_customer_count": 0,
    "unlabeled_customer_count": 0,
    "positive_customer_rate": 0.0,
    "response_count": 0,
    "purchase_count": 0,
    "attributed_purchase_count": 0,
    "net_sales_amount": 0.0,
    "gross_margin_amount": 0.0
  },
  "monthly_trend": [],
  "channel_performance": [],
  "product_category_performance": [],
  "top_campaigns": [],
  "top_products": [],
  "profiles": {
    "selected": {},
    "positive": {},
    "unlabeled": {},
    "historical_baseline": {}
  }
}
```

The zero values above illustrate shape only; a successful completed run must contain at least one matching observation. A zero-match request returns a stable 4xx domain response.

Each profile dimension should have a stable structure such as:

```json
{
  "group_count": 100,
  "categories": [
    {"label": "35–44", "count": 25, "share": 0.25}
  ]
}
```

## `GET /api/historical/analyses?limit=20&offset=0`

Returns summary list items, newest first. A list item includes:

- analysis run ID/name
- created/completed timestamps
- status
- conversion definition
- compact normalized filters
- observation/selected/positive/unlabeled counts
- positive-customer rate
- sanitized public failure message if failed

It does not include all profile/breakdown result JSON.

## `GET /api/historical/analyses/{analysis_run_id}`

- Completed run: HTTP 200 with the full saved analysis response.
- Failed run: HTTP 200 with metadata and a stable sanitized failure message, or another consistently documented safe contract.
- Unknown run: HTTP 404.
- Invalid non-positive identifier: HTTP 422.

Never return the database's stored internal `error_message` verbatim.

## Domain validation summary

- unsupported conversion definition: 422
- reversed date range: 422
- excessive list size: 422
- blank/too-long analysis name: 422
- no matching observations: documented 400 or 422 with stable detail
- missing campaign history: documented stable empty/not-ready response
- unknown saved run: 404
- database unavailable: 503 through the existing sanitized handler

