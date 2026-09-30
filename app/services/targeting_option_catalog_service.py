"""Small durable targeting catalogs keyed to authoritative source checksums."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)


_SOURCE_DATASETS = ("customers", "campaign_sales", "demographics")
_BUILD_RETRY_LIMIT = 4


class TargetingCatalogIntegrityError(RuntimeError):
    """A persisted catalog no longer matches its immutable checksum identity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _source_checksums_on_connection(
    connection: sqlite3.Connection,
) -> dict[str, str | None]:
    rows = connection.execute(
        """SELECT dataset_name,source_checksum FROM data_import_runs AS run
           WHERE status='COMPLETED'
             AND dataset_name IN ('customers','campaign_sales','demographics')
             AND import_id=(
                 SELECT MAX(candidate.import_id)
                 FROM data_import_runs AS candidate
                 WHERE candidate.status='COMPLETED'
                   AND candidate.dataset_name=run.dataset_name
             )"""
    ).fetchall()
    found = {str(row["dataset_name"]): row["source_checksum"] for row in rows}
    return {name: found.get(name) for name in _SOURCE_DATASETS}


def _source_checksums(path: Path) -> dict[str, str | None]:
    with get_connection(path) as connection:
        return _source_checksums_on_connection(connection)


def _catalog_version(checksums: Mapping[str, str | None]) -> str:
    payload = json.dumps(dict(checksums), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _product_rows(context: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    products = {
        str(item["product_id"]): (
            str(item.get("product_name") or item["product_id"]),
            str(item.get("product_category") or ""),
        )
        for item in context.get("products", [])
        if isinstance(item, dict) and str(item.get("product_id") or "").strip()
    }
    return tuple(
        (product_id, values[0], values[1])
        for product_id, values in sorted(products.items())
    )


def _replace_product_catalog(
    connection: sqlite3.Connection,
    catalog_version: str,
    context: Mapping[str, Any],
) -> None:
    connection.execute(
        "DELETE FROM targeting_product_catalog WHERE catalog_version=?",
        (catalog_version,),
    )
    connection.executemany(
        """INSERT INTO targeting_product_catalog (
               catalog_version,product_id,product_name,product_category
           ) VALUES (?,?,?,?)""",
        (
            (catalog_version, product_id, name, category)
            for product_id, name, category in _product_rows(context)
        ),
    )


def _ensure_product_catalog_on_connection(
    connection: sqlite3.Connection,
    catalog_version: str,
    context: Mapping[str, Any],
) -> bool:
    """Repair normalized children from compact immutable parent JSON if needed."""

    expected = _product_rows(context)
    actual = tuple(
        (
            str(row["product_id"]),
            str(row["product_name"]),
            str(row["product_category"]),
        )
        for row in connection.execute(
            """SELECT product_id,product_name,product_category
               FROM targeting_product_catalog WHERE catalog_version=?
               ORDER BY product_id""",
            (catalog_version,),
        ).fetchall()
    )
    if actual == expected:
        return False
    _replace_product_catalog(connection, catalog_version, context)
    return True


def _decode_catalog_row(
    row: Mapping[str, Any],
    *,
    expected_checksums: Mapping[str, str | None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stored_checksums = {
        "customers": row["customer_source_checksum"],
        "campaign_sales": row["campaign_sales_source_checksum"],
        "demographics": row["demographic_source_checksum"],
    }
    version = str(row["catalog_version"])
    if _catalog_version(stored_checksums) != version or (
        expected_checksums is not None
        and stored_checksums != dict(expected_checksums)
    ):
        raise TargetingCatalogIntegrityError(
            "Targeting catalog source identity is invalid."
        )
    try:
        context = json.loads(str(row["context_options_json"]))
        targeting = json.loads(str(row["targeting_options_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TargetingCatalogIntegrityError(
            "Targeting catalog payload is invalid."
        ) from exc
    if not isinstance(context, dict) or not isinstance(targeting, dict):
        raise TargetingCatalogIntegrityError(
            "Targeting catalog payload is invalid."
        )
    return context, targeting


def _catalog_row(
    connection: sqlite3.Connection, catalog_version: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT catalog_version,customer_source_checksum,
                  campaign_sales_source_checksum,demographic_source_checksum,
                  context_options_json,targeting_options_json,created_at,is_current
           FROM targeting_option_catalogs WHERE catalog_version=?""",
        (catalog_version,),
    ).fetchone()


def _promote_catalog_on_connection(
    connection: sqlite3.Connection, catalog_version: str,
) -> None:
    current = connection.execute(
        """SELECT catalog_version FROM targeting_option_catalogs
           WHERE is_current=1"""
    ).fetchall()
    if len(current) == 1 and str(current[0]["catalog_version"]) == catalog_version:
        return
    # Clear the previous winner before setting the new one so the partial unique
    # index remains valid throughout the transaction.
    connection.execute(
        """UPDATE targeting_option_catalogs SET is_current=0
           WHERE is_current=1 AND catalog_version<>?""",
        (catalog_version,),
    )
    cursor = connection.execute(
        "UPDATE targeting_option_catalogs SET is_current=1 WHERE catalog_version=?",
        (catalog_version,),
    )
    if cursor.rowcount != 1:
        raise TargetingCatalogIntegrityError(
            "Targeting catalog could not be promoted."
        )


def _activate_existing_on_connection(
    connection: sqlite3.Connection,
    row: Mapping[str, Any],
    checksums: Mapping[str, str | None],
) -> dict[str, Any]:
    context, targeting = _decode_catalog_row(
        row, expected_checksums=checksums
    )
    version = str(row["catalog_version"])
    _ensure_product_catalog_on_connection(connection, version, context)
    _promote_catalog_on_connection(connection, version)
    return {
        "catalog_version": version,
        "catalog_created_at": str(row["created_at"]),
        "context": context,
        "targeting": targeting,
    }


def get_or_build_targeting_catalog(path: str | Path) -> dict[str, Any]:
    """Atomically return and promote the exact authoritative compact catalog.

    Warm loads inspect only import metadata plus the compact catalog/product
    tables. A large option scan occurs only when the exact checksum identity has
    never been materialized. The checksum identity is rechecked under the write
    transaction after that scan so an overlapping import cannot promote stale
    data.
    """

    database_path = Path(path)
    repository = CampaignTargetingContextRepository(database_path)
    for _attempt in range(_BUILD_RETRY_LIMIT):
        with get_connection(database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            checksums = _source_checksums_on_connection(connection)
            version = _catalog_version(checksums)
            row = _catalog_row(connection, version)
            if row is not None:
                return _activate_existing_on_connection(
                    connection, row, checksums
                )

        # The version is genuinely absent. Build outside the write transaction;
        # the second transaction below verifies that authoritative sources did
        # not change while the potentially large scan ran.
        context = repository.fetch_context_options()
        targeting = repository.fetch_targeting_options()
        context_json = json.dumps(
            context,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        targeting_json = json.dumps(
            targeting,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        created_at = _now()
        with get_connection(database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            locked_checksums = _source_checksums_on_connection(connection)
            locked_version = _catalog_version(locked_checksums)
            raced = _catalog_row(connection, locked_version)
            if raced is not None:
                return _activate_existing_on_connection(
                    connection, raced, locked_checksums
                )
            if locked_version != version:
                continue
            connection.execute(
                """INSERT INTO targeting_option_catalogs (
                       catalog_version,customer_source_checksum,
                       campaign_sales_source_checksum,demographic_source_checksum,
                       context_options_json,targeting_options_json,created_at,is_current
                   ) VALUES (?,?,?,?,?,?,?,0)""",
                (
                    version,
                    checksums["customers"],
                    checksums["campaign_sales"],
                    checksums["demographics"],
                    context_json,
                    targeting_json,
                    created_at,
                ),
            )
            _replace_product_catalog(connection, version, context)
            _promote_catalog_on_connection(connection, version)
            return {
                "catalog_version": version,
                "catalog_created_at": created_at,
                "context": context,
                "targeting": targeting,
            }
    raise TargetingCatalogIntegrityError(
        "Authoritative sources changed repeatedly while building campaign choices."
    )


def get_targeting_catalog(
    path: str | Path, catalog_version: str,
) -> dict[str, Any] | None:
    """Read one historical catalog and truthfully project live currentness."""

    if not isinstance(catalog_version, str) or len(catalog_version) != 64:
        return None
    database_path = Path(path)
    with get_connection(database_path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _catalog_row(connection, catalog_version)
        if row is None:
            return None
        context, targeting = _decode_catalog_row(row)
        _ensure_product_catalog_on_connection(
            connection, catalog_version, context
        )
        authoritative_version = _catalog_version(
            _source_checksums_on_connection(connection)
        )
        is_current = bool(row["is_current"]) and (
            catalog_version == authoritative_version
        )
        return {
            "catalog_version": catalog_version,
            "catalog_created_at": str(row["created_at"]),
            "is_current": is_current,
            "context": context,
            "targeting": targeting,
        }


def get_product_catalog_entries(
    path: str | Path,
    product_ids: list[str],
    *,
    catalog_version: str | None = None,
) -> dict[str, dict[str, str]]:
    """Read labels from an exact historical catalog or the current catalog."""

    identifiers = list(dict.fromkeys(str(value) for value in product_ids if value))
    if not identifiers:
        return {}
    marks = ",".join("?" for _ in identifiers)
    if catalog_version is None:
        predicate = "c.is_current=1"
        parameters: tuple[Any, ...] = tuple(identifiers)
    else:
        if not isinstance(catalog_version, str) or len(catalog_version) != 64:
            return {}
        predicate = "c.catalog_version=?"
        parameters = (catalog_version, *identifiers)
    with get_connection(path) as connection:
        rows = connection.execute(
            f"""SELECT p.product_id,p.product_name,p.product_category
                FROM targeting_product_catalog AS p
                JOIN targeting_option_catalogs AS c
                  ON c.catalog_version=p.catalog_version
                WHERE {predicate} AND p.product_id IN ({marks})""",
            parameters,
        ).fetchall()
    return {str(row["product_id"]): dict(row) for row in rows}


__all__ = (
    "TargetingCatalogIntegrityError",
    "get_or_build_targeting_catalog",
    "get_product_catalog_entries",
    "get_targeting_catalog",
)
