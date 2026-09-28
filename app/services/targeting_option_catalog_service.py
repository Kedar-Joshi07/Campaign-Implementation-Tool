"""Small durable targeting catalogs keyed to current imported source checksums."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_checksums(path: Path) -> dict[str, str | None]:
    with get_connection(path) as connection:
        rows = connection.execute(
            """SELECT dataset_name,source_checksum FROM data_import_runs
               WHERE status='COMPLETED' AND dataset_name IN ('customers','campaign_sales','demographics')
               AND import_id IN (
                   SELECT MAX(import_id) FROM data_import_runs
                   WHERE status='COMPLETED' GROUP BY dataset_name
               )"""
        ).fetchall()
    found = {str(row["dataset_name"]): row["source_checksum"] for row in rows}
    return {name: found.get(name) for name in ("customers", "campaign_sales", "demographics")}


def _catalog_version(checksums: dict[str, str | None]) -> str:
    payload = json.dumps(checksums, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _replace_product_catalog(
    connection, catalog_version: str, context: dict[str, Any],
) -> None:
    products = {
        str(item["product_id"]): (
            str(item.get("product_name") or item["product_id"]),
            str(item.get("product_category") or ""),
        )
        for item in context.get("products", [])
        if isinstance(item, dict) and str(item.get("product_id") or "").strip()
    }
    connection.execute(
        "DELETE FROM targeting_product_catalog WHERE catalog_version=?",
        (catalog_version,),
    )
    connection.executemany(
        """INSERT INTO targeting_product_catalog (
               catalog_version,product_id,product_name,product_category
           ) VALUES (?,?,?,?)""",
        (
            (catalog_version, product_id, values[0], values[1])
            for product_id, values in sorted(products.items())
        ),
    )


def _ensure_product_catalog(
    database_path: Path, catalog_version: str, context: dict[str, Any],
) -> None:
    expected = len({
        str(item.get("product_id"))
        for item in context.get("products", [])
        if isinstance(item, dict) and item.get("product_id")
    })
    with get_connection(database_path) as connection:
        actual = int(connection.execute(
            "SELECT COUNT(*) FROM targeting_product_catalog WHERE catalog_version=?",
            (catalog_version,),
        ).fetchone()[0])
    if actual == expected:
        return
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _replace_product_catalog(connection, catalog_version, context)


def get_or_build_targeting_catalog(path: str | Path) -> dict[str, Any]:
    """Return a compact catalog; demographics are sourced from the analytics snapshot."""

    database_path = Path(path)
    checksums = _source_checksums(database_path)
    version = _catalog_version(checksums)
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT context_options_json,targeting_options_json,created_at
               FROM targeting_option_catalogs WHERE catalog_version=?""",
            (version,),
        ).fetchone()
    if row is not None:
        context = json.loads(str(row["context_options_json"]))
        _ensure_product_catalog(database_path, version, context)
        return {
            "catalog_version": version,
            "catalog_created_at": str(row["created_at"]),
            "context": context,
            "targeting": json.loads(str(row["targeting_options_json"])),
        }

    repository = CampaignTargetingContextRepository(database_path)
    context = repository.fetch_context_options()
    targeting = repository.fetch_targeting_options()
    context_json = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    targeting_json = json.dumps(targeting, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    created_at = _now()
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE targeting_option_catalogs SET is_current=0 WHERE is_current=1")
        connection.execute(
            """INSERT INTO targeting_option_catalogs (
                   catalog_version,customer_source_checksum,campaign_sales_source_checksum,
                   demographic_source_checksum,context_options_json,targeting_options_json,
                   created_at,is_current
               ) VALUES (?,?,?,?,?,?,?,1)
               ON CONFLICT(catalog_version) DO UPDATE SET is_current=1""",
            (version, checksums["customers"], checksums["campaign_sales"],
             checksums["demographics"], context_json, targeting_json, created_at),
        )
        _replace_product_catalog(connection, version, context)
    return {
        "catalog_version": version,
        "catalog_created_at": created_at,
        "context": context,
        "targeting": targeting,
    }


def get_targeting_catalog(path: str | Path, catalog_version: str) -> dict[str, Any] | None:
    if not isinstance(catalog_version, str) or len(catalog_version) != 64:
        return None
    with get_connection(path) as connection:
        row = connection.execute(
            """SELECT context_options_json,targeting_options_json,created_at,is_current
               FROM targeting_option_catalogs WHERE catalog_version=?""",
            (catalog_version,),
        ).fetchone()
    if row is None:
        return None
    context = json.loads(str(row["context_options_json"]))
    _ensure_product_catalog(Path(path), catalog_version, context)
    return {
        "catalog_version": catalog_version,
        "catalog_created_at": str(row["created_at"]),
        "is_current": bool(row["is_current"]),
        "context": context,
        "targeting": json.loads(str(row["targeting_options_json"])),
    }


def get_product_catalog_entries(
    path: str | Path, product_ids: list[str],
) -> dict[str, dict[str, str]]:
    """Read normalized product labels from the compact current catalog."""

    identifiers = list(dict.fromkeys(str(value) for value in product_ids if value))
    if not identifiers:
        return {}
    marks = ",".join("?" for _ in identifiers)
    with get_connection(path) as connection:
        rows = connection.execute(
            f"""SELECT p.product_id,p.product_name,p.product_category
                FROM targeting_product_catalog AS p
                JOIN targeting_option_catalogs AS c
                  ON c.catalog_version=p.catalog_version
                WHERE c.is_current=1 AND p.product_id IN ({marks})""",
            tuple(identifiers),
        ).fetchall()
    return {str(row["product_id"]): dict(row) for row in rows}


__all__ = (
    "get_or_build_targeting_catalog", "get_product_catalog_entries",
    "get_targeting_catalog",
)
