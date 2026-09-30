#!/usr/bin/env python3
"""Audit canonical campaign connectivity without exposing customer identities."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit("Canonical database does not exist.")

    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        parent[second] = first

    uri = database.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        schema_version = int(
            connection.execute(
                "SELECT value FROM app_metadata WHERE key='schema_version'"
            ).fetchone()[0]
        )
        cursor = connection.execute(
            """SELECT customer_id,campaign_id
               FROM campaign_sales
               GROUP BY customer_id,campaign_id
               ORDER BY customer_id,campaign_id"""
        )
        customer_count = 0
        pair_count = 0
        multi_campaign_customer_count = 0
        maximum_campaigns_per_customer = 0
        current_customer: str | None = None
        campaigns: list[str] = []

        def finish_customer() -> None:
            nonlocal customer_count, multi_campaign_customer_count
            nonlocal maximum_campaigns_per_customer
            if not campaigns:
                return
            customer_count += 1
            maximum_campaigns_per_customer = max(
                maximum_campaigns_per_customer, len(campaigns)
            )
            if len(campaigns) > 1:
                multi_campaign_customer_count += 1
            first = campaigns[0]
            find(first)
            for campaign_id in campaigns[1:]:
                union(first, campaign_id)

        for customer_id, campaign_id in cursor:
            customer = str(customer_id)
            campaign = str(campaign_id)
            if current_customer is not None and customer != current_customer:
                finish_customer()
                campaigns = []
            current_customer = customer
            campaigns.append(campaign)
            pair_count += 1
        finish_customer()
        component_count = len({find(campaign) for campaign in parent})
        report = {
            "audit_contract": "PHASE13_5_CANONICAL_CAMPAIGN_TOPOLOGY_V1",
            "recorded_at": _utc_now(),
            "database_path": "data/campaign_poc.db",
            "read_only": True,
            "schema_version": schema_version,
            "distinct_customer_count": customer_count,
            "distinct_campaign_count": len(parent),
            "distinct_customer_campaign_pair_count": pair_count,
            "multi_campaign_customer_count": multi_campaign_customer_count,
            "maximum_campaigns_per_customer": maximum_campaigns_per_customer,
            "campaign_connected_component_count": component_count,
            "governed_three_way_split_available": component_count >= 3,
        }
    finally:
        connection.close()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
