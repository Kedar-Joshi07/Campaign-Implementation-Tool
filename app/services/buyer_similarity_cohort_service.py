"""Product-aware historical buyer cohorts for similarity contract v3.

This module is intentionally separate from PU model training.  Campaign sales
identify confirmed attributed buyers only; rows with ``pu_label=0`` are never
treated as verified nonbuyers.  Product/context/window filtering occurs before
customer-grain deduplication, and one union-level split assignment is reused by
every selected product.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_CONTRACT_SHA256,
    ORDERED_FEATURES,
    validate_and_normalize_feature_frame,
)
from app.services.buyer_similarity_split_service import (
    SUPPORT_AWARE_OBJECTIVE_VERSION,
    SUPPORT_AWARE_SPLIT_VERSION,
    solve_support_aware_split,
)
from app.selection_contracts import BUYER_SIMILARITY_PRODUCT_MATCH_POLICY


BUYER_COHORT_CONTRACT_VERSION = "1"
BUYER_CONVERSION_DEFINITION = "ATTRIBUTED_PURCHASE"
LEGACY_BUYER_SPLIT_STRATEGY_VERSION = "CUSTOMER_UNION_HASH_ORDER_80_20_V1"
BUYER_SPLIT_STRATEGY_VERSION = SUPPORT_AWARE_SPLIT_VERSION
BUYER_SPLIT_SEED = 20261005
MINIMUM_PRODUCT_BUYERS = 200
MINIMUM_PRODUCT_FIT_BUYERS = 160
MINIMUM_PRODUCT_HOLDOUT_BUYERS = 40
FIT_FRACTION = 0.80

_CONTEXT_FILTER_COLUMNS = {
    "campaign_types": "campaign_type",
    "campaign_categories": "campaign_category",
    "offer_types": "offer_type",
    "historical_campaign_channels": "campaign_channel",
}
_HEX = frozenset("0123456789abcdef")


class BuyerCohortError(RuntimeError):
    """Base class for bounded buyer-cohort failures."""


class BuyerCohortRequestError(BuyerCohortError):
    """Raised when exact products, context, or dates are invalid."""


class BuyerCohortSourceError(BuyerCohortError):
    """Raised when source identity or relational integrity is invalid."""


@dataclass(frozen=True)
class BuyerCohortSourceIdentity:
    customer_import_id: int
    customer_source_checksum: str
    campaign_sales_import_id: int
    campaign_sales_source_checksum: str
    product_catalog_sha256: str


@dataclass(frozen=True)
class ProductBuyerSupport:
    product_id: str
    distinct_attributed_buyers: int
    fit_buyers: int
    holdout_buyers: int
    fit_identity_sha256: str | None
    holdout_identity_sha256: str | None
    status: str
    reason_code: str


@dataclass(frozen=True)
class BuyerCohortManifest:
    cohort_contract_version: str
    conversion_definition: str
    product_match_policy: str
    product_ids: tuple[str, ...]
    historical_context: dict[str, tuple[str, ...]]
    window_start: str
    window_end: str
    demographic_reference_date: str
    split_strategy_version: str
    split_seed: int
    fit_fraction: float
    source_identity: BuyerCohortSourceIdentity
    feature_contract_sha256: str
    union_buyer_count: int
    union_fit_count: int
    union_holdout_count: int
    union_fit_identity_sha256: str
    union_holdout_identity_sha256: str
    context_identity_sha256: str
    product_support: tuple[ProductBuyerSupport, ...]
    eligible: bool
    reason_codes: tuple[str, ...]
    historical_age_semantics: str
    prospect_age_semantics: str
    comparison_label_semantics: str
    split_status: str = "FEASIBLE"
    split_reason_code: str = "ELIGIBLE"
    split_objective_version: str | None = None
    product_holdout_targets: dict[str, int] | None = None
    product_holdout_deviation: int | None = None
    union_holdout_target: int | None = None
    union_holdout_deviation: int | None = None
    baseline_assignment_changes: int | None = None
    membership_signature_count: int | None = None
    partition_manifest_sha256: str | None = None

    def partition_payload(self) -> dict[str, Any]:
        """Complete identity/count lineage without raw customer identifiers."""

        return {
            "cohort_contract_version": self.cohort_contract_version,
            "context_identity_sha256": self.context_identity_sha256,
            "split_strategy_version": self.split_strategy_version,
            "split_seed": self.split_seed,
            "split_status": self.split_status,
            "split_reason_code": self.split_reason_code,
            "split_objective_version": self.split_objective_version,
            "source_identity": asdict(self.source_identity),
            "feature_contract_sha256": self.feature_contract_sha256,
            "union_buyer_count": self.union_buyer_count,
            "union_fit_count": self.union_fit_count,
            "union_holdout_count": self.union_holdout_count,
            "union_fit_identity_sha256": self.union_fit_identity_sha256,
            "union_holdout_identity_sha256": self.union_holdout_identity_sha256,
            "product_support": [asdict(item) for item in self.product_support],
            "product_holdout_targets": self.product_holdout_targets,
            "product_holdout_deviation": self.product_holdout_deviation,
            "union_holdout_target": self.union_holdout_target,
            "union_holdout_deviation": self.union_holdout_deviation,
            "baseline_assignment_changes": self.baseline_assignment_changes,
            "membership_signature_count": self.membership_signature_count,
        }

    def public_payload(self) -> dict[str, Any]:
        """Return bounded public lineage without customer identities or PII."""

        payload = asdict(self)
        payload["product_ids"] = list(self.product_ids)
        payload["historical_context"] = {
            key: list(values) for key, values in self.historical_context.items()
        }
        payload["product_support"] = [asdict(value) for value in self.product_support]
        payload["reason_codes"] = list(self.reason_codes)
        return payload


@dataclass(frozen=True)
class BuyerCohortBuild:
    manifest: BuyerCohortManifest
    frame: pd.DataFrame


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_hash(values: Iterable[str]) -> str:
    return _sha256_json(sorted(str(value) for value in values))


def _read_only_connection(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    if not path.is_file():
        raise BuyerCohortSourceError("The buyer-evidence database was not found.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA query_only=ON")
    return connection


def _normalize_values(values: Sequence[str] | None, *, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise BuyerCohortRequestError(f"{field} must be a list of exact values.")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise BuyerCohortRequestError(f"{field} must contain text values.")
        item = value.strip()
        if not item or len(item) > 120:
            raise BuyerCohortRequestError(f"{field} contains an invalid value.")
        normalized.append(item)
    return tuple(sorted(set(normalized)))


def _normalize_date(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise BuyerCohortRequestError(f"{field} must be an ISO date.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise BuyerCohortRequestError(f"{field} must be an ISO date.") from exc


def _valid_checksum(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value.strip()) == 64
        and set(value.strip().lower()) <= _HEX
    )


def _latest_import(
    connection: sqlite3.Connection,
    *,
    dataset_name: str,
    table_name: str,
) -> tuple[int, str]:
    row = connection.execute(
        """SELECT import_id,source_checksum,rows_inserted
           FROM data_import_runs
           WHERE dataset_name=? AND status='COMPLETED'
           ORDER BY import_id DESC LIMIT 1""",
        (dataset_name,),
    ).fetchone()
    if row is None or not _valid_checksum(row["source_checksum"]):
        raise BuyerCohortSourceError(
            f"Current {dataset_name} import provenance is unavailable."
        )
    live_count = int(connection.execute(
        f'SELECT COUNT(*) FROM "{table_name}"'
    ).fetchone()[0])
    if int(row["rows_inserted"]) != live_count:
        raise BuyerCohortSourceError(
            f"Current {dataset_name} import provenance does not match live rows."
        )
    return int(row["import_id"]), str(row["source_checksum"]).strip().lower()


def _load_product_catalog(product_catalog_path: str | Path) -> tuple[dict[str, dict[str, str]], str]:
    path = Path(product_catalog_path)
    if not path.is_file():
        raise BuyerCohortSourceError("The exact product catalog was not found.")
    catalog: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "product_id" not in reader.fieldnames:
            raise BuyerCohortSourceError("The product catalog schema is invalid.")
        for row in reader:
            product_id = str(row.get("product_id") or "").strip()
            if not product_id or product_id in catalog:
                raise BuyerCohortSourceError(
                    "The product catalog contains a blank or duplicate product ID."
                )
            catalog[product_id] = {
                key: str(value or "").strip() for key, value in row.items()
            }
    if not catalog:
        raise BuyerCohortSourceError("The product catalog is empty.")
    return catalog, _sha256_file(path)


def _split_assignments(customer_ids: Iterable[str]) -> dict[str, str]:
    ordered = sorted(
        {str(value) for value in customer_ids},
        key=lambda customer_id: (
            hashlib.sha256(
                f"{BUYER_SPLIT_SEED}\0{customer_id}".encode("utf-8")
            ).digest(),
            customer_id,
        ),
    )
    fit_count = math.floor(len(ordered) * FIT_FRACTION)
    return {
        customer_id: ("FIT" if index < fit_count else "HOLDOUT")
        for index, customer_id in enumerate(ordered)
    }


def build_product_buyer_cohorts(
    database_path: str | Path,
    *,
    product_ids: Sequence[str],
    window_start: str,
    window_end: str,
    campaign_types: Sequence[str] | None = None,
    campaign_categories: Sequence[str] | None = None,
    offer_types: Sequence[str] | None = None,
    historical_campaign_channels: Sequence[str] | None = None,
    demographic_reference_date: str | None = None,
    product_catalog_path: str | Path = "data/product_master.csv",
    expected_customer_source_checksum: str | None = None,
    expected_campaign_sales_source_checksum: str | None = None,
    split_strategy_version: str = BUYER_SPLIT_STRATEGY_VERSION,
) -> BuyerCohortBuild:
    """Build exact, per-product attributed-buyer evidence and split lineage."""

    products = _normalize_values(product_ids, field="product_ids")
    if split_strategy_version not in {
        LEGACY_BUYER_SPLIT_STRATEGY_VERSION, BUYER_SPLIT_STRATEGY_VERSION,
    }:
        raise BuyerCohortRequestError("The buyer split policy is not supported.")
    if not products or len(products) > 50:
        raise BuyerCohortRequestError("Choose between 1 and 50 exact products.")
    start = _normalize_date(window_start, field="window_start")
    end = _normalize_date(window_end, field="window_end")
    if start > end:
        raise BuyerCohortRequestError("window_start must not be after window_end.")
    reference = _normalize_date(
        demographic_reference_date or end,
        field="demographic_reference_date",
    )
    if reference != end:
        raise BuyerCohortRequestError(
            "Historical demographic reference date must equal the fixed window end."
        )
    context = {
        "campaign_types": _normalize_values(campaign_types, field="campaign_types"),
        "campaign_categories": _normalize_values(
            campaign_categories, field="campaign_categories"
        ),
        "offer_types": _normalize_values(offer_types, field="offer_types"),
        "historical_campaign_channels": _normalize_values(
            historical_campaign_channels,
            field="historical_campaign_channels",
        ),
    }
    catalog, catalog_sha256 = _load_product_catalog(product_catalog_path)

    connection = _read_only_connection(database_path)
    try:
        customer_import_id, customer_checksum = _latest_import(
            connection, dataset_name="customers", table_name="customers"
        )
        sales_import_id, sales_checksum = _latest_import(
            connection,
            dataset_name="campaign_sales",
            table_name="campaign_sales",
        )
        for expected, actual, label in (
            (expected_customer_source_checksum, customer_checksum, "customers"),
            (expected_campaign_sales_source_checksum, sales_checksum, "campaign_sales"),
        ):
            if expected is not None and (
                not _valid_checksum(expected) or expected.strip().lower() != actual
            ):
                raise BuyerCohortSourceError(
                    f"The current {label} source checksum does not match the request."
                )

        clauses = [
            f"s.product_id IN ({','.join('?' for _ in products)})",
            "DATE(s.contact_date) >= DATE(?)",
            "DATE(s.contact_date) <= DATE(?)",
            "s.contacted_flag=1",
            "s.purchase_flag=1",
            "s.campaign_attributed_sale_flag=1",
        ]
        parameters: list[Any] = [*products, start, end]
        for field, column in _CONTEXT_FILTER_COLUMNS.items():
            values = context[field]
            if values:
                clauses.append(
                    f"s.{column} IN ({','.join('?' for _ in values)})"
                )
                parameters.extend(values)
        where = " AND ".join(clauses)
        query = f"""
            WITH selected_product_events AS MATERIALIZED (
                SELECT s.product_id,s.customer_id
                FROM campaign_sales s
                WHERE {where}
            ),
            distinct_product_buyers AS (
                SELECT product_id,customer_id
                FROM selected_product_events
                GROUP BY product_id,customer_id
            )
            SELECT
                b.product_id,b.customer_id,
                CASE
                    WHEN DATE(c.date_of_birth) IS NULL THEN NULL
                    ELSE CAST(STRFTIME('%Y', ?) AS INTEGER)
                       - CAST(SUBSTR(c.date_of_birth,1,4) AS INTEGER)
                       - CASE WHEN STRFTIME('%m-%d', ?) < SUBSTR(c.date_of_birth,6,5)
                              THEN 1 ELSE 0 END
                END AS age,
                c.gender,c.state,c.individual_yearly_income,c.marital_status,
                c.education,c.employment_status,c.resident_status,c.resident_type,
                c.family_member_count,c.type_of_employment
            FROM distinct_product_buyers b
            JOIN customers c ON c.customer_id=b.customer_id
            ORDER BY b.product_id,b.customer_id
        """
        rows = connection.execute(query, (*parameters, reference, reference)).fetchall()
        expected_join_count = int(connection.execute(
            f"""SELECT COUNT(*) FROM (
                SELECT s.product_id,s.customer_id
                FROM campaign_sales s WHERE {where}
                GROUP BY s.product_id,s.customer_id)""",
            tuple(parameters),
        ).fetchone()[0])
        if len(rows) != expected_join_count:
            raise BuyerCohortSourceError(
                "Attributed buyer evidence contains a customer without an exact customer join."
            )
    finally:
        connection.close()

    columns = ("product_id", "customer_id", *ORDERED_FEATURES)
    raw = pd.DataFrame.from_records([tuple(row) for row in rows], columns=columns)
    if raw.empty:
        raw = pd.DataFrame(columns=columns)
    if raw.duplicated(subset=["product_id", "customer_id"]).any():
        raise BuyerCohortSourceError(
            "Buyer evidence must contain one distinct customer per product."
        )
    normalized_features = validate_and_normalize_feature_frame(
        raw.loc[:, ORDERED_FEATURES]
    )
    frame = pd.concat(
        (
            raw.loc[:, ["product_id", "customer_id"]].reset_index(drop=True),
            normalized_features.reset_index(drop=True),
        ),
        axis="columns",
    )
    frame["product_id"] = frame["product_id"].astype("string")
    frame["customer_id"] = frame["customer_id"].astype("string")

    baseline = _split_assignments(frame["customer_id"].astype(str))
    split_result = None
    if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION and baseline:
        product_members = {
            product: set(frame.loc[frame["product_id"] == product, "customer_id"].astype(str))
            for product in products
        }
        split_result = solve_support_aware_split(
            product_members, baseline, seed=BUYER_SPLIT_SEED,
            minimum_buyers=MINIMUM_PRODUCT_BUYERS,
            minimum_fit=MINIMUM_PRODUCT_FIT_BUYERS,
            minimum_holdout=MINIMUM_PRODUCT_HOLDOUT_BUYERS,
        )
    assignments = (split_result.assignments if split_result is not None
                   and split_result.status == "FEASIBLE" else baseline)
    frame.insert(
        2,
        "split",
        frame["customer_id"].astype(str).map(assignments).astype("string"),
    )
    supports: list[ProductBuyerSupport] = []
    for product_id in products:
        members = frame.loc[frame["product_id"] == product_id]
        member_ids = members["customer_id"].astype(str).tolist()
        fit_ids = members.loc[members["split"] == "FIT", "customer_id"].astype(str)
        holdout_ids = members.loc[
            members["split"] == "HOLDOUT", "customer_id"
        ].astype(str)
        buyer_count = len(member_ids)
        fit_count = len(fit_ids)
        holdout_count = len(holdout_ids)
        if product_id not in catalog:
            status, reason = "NOT_ELIGIBLE", "UNKNOWN_PRODUCT"
        elif buyer_count == 0:
            status, reason = "NOT_ELIGIBLE", "NO_ATTRIBUTED_PURCHASE_HISTORY"
        elif buyer_count < MINIMUM_PRODUCT_BUYERS:
            status, reason = (
                "NOT_ELIGIBLE",
                "INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT",
            )
        elif (
            fit_count < MINIMUM_PRODUCT_FIT_BUYERS
            or holdout_count < MINIMUM_PRODUCT_HOLDOUT_BUYERS
        ):
            status, reason = "NOT_ELIGIBLE", "INSUFFICIENT_SPLIT_SUPPORT"
        elif split_result is not None and split_result.status != "FEASIBLE":
            status, reason = "NOT_ELIGIBLE", split_result.reason_code
        else:
            status, reason = "ELIGIBLE", "ELIGIBLE"
        supports.append(
            ProductBuyerSupport(
                product_id=product_id,
                distinct_attributed_buyers=buyer_count,
                fit_buyers=fit_count,
                holdout_buyers=holdout_count,
                fit_identity_sha256=_identity_hash(fit_ids) if fit_count else None,
                holdout_identity_sha256=(
                    _identity_hash(holdout_ids) if holdout_count else None
                ),
                status=status,
                reason_code=reason,
            )
        )

    union_fit_ids = sorted(
        customer_id for customer_id, split in assignments.items() if split == "FIT"
    )
    union_holdout_ids = sorted(
        customer_id
        for customer_id, split in assignments.items()
        if split == "HOLDOUT"
    )
    source_identity = BuyerCohortSourceIdentity(
        customer_import_id=customer_import_id,
        customer_source_checksum=customer_checksum,
        campaign_sales_import_id=sales_import_id,
        campaign_sales_source_checksum=sales_checksum,
        product_catalog_sha256=catalog_sha256,
    )
    context_payload = {
        "cohort_contract_version": BUYER_COHORT_CONTRACT_VERSION,
        "conversion_definition": BUYER_CONVERSION_DEFINITION,
        "product_match_policy": BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
        "product_ids": list(products),
        "historical_context": {
            key: list(values) for key, values in context.items()
        },
        "window_start": start,
        "window_end": end,
        "demographic_reference_date": reference,
        "split_strategy_version": split_strategy_version,
        "split_seed": BUYER_SPLIT_SEED,
        **({"split_objective_version": SUPPORT_AWARE_OBJECTIVE_VERSION}
           if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION else {}),
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "source_identity": asdict(source_identity),
    }
    reasons = tuple(sorted({value.reason_code for value in supports if value.reason_code != "ELIGIBLE"}))
    manifest = BuyerCohortManifest(
        cohort_contract_version=BUYER_COHORT_CONTRACT_VERSION,
        conversion_definition=BUYER_CONVERSION_DEFINITION,
        product_match_policy=BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
        product_ids=products,
        historical_context=context,
        window_start=start,
        window_end=end,
        demographic_reference_date=reference,
        split_strategy_version=split_strategy_version,
        split_seed=BUYER_SPLIT_SEED,
        fit_fraction=FIT_FRACTION,
        source_identity=source_identity,
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        union_buyer_count=len(assignments),
        union_fit_count=len(union_fit_ids),
        union_holdout_count=len(union_holdout_ids),
        union_fit_identity_sha256=_identity_hash(union_fit_ids),
        union_holdout_identity_sha256=_identity_hash(union_holdout_ids),
        context_identity_sha256=_sha256_json(context_payload),
        product_support=tuple(supports),
        eligible=not reasons,
        reason_codes=reasons,
        historical_age_semantics=(
            "Completed whole years from customer date_of_birth at the fixed "
            "historical window end; never wall-clock age."
        ),
        prospect_age_semantics=(
            "The prospect age column is the completed-age value at its declared "
            "demographic source snapshot; the later scorer must bind that reference."
        ),
        comparison_label_semantics=(
            "Only attributed purchasers are buyer members; all other sales rows are "
            "unlabeled, not verified nonbuyers."
        ),
        split_status=split_result.status if split_result is not None else (
            "INFEASIBLE" if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION else "FEASIBLE"
        ),
        split_reason_code=split_result.reason_code if split_result is not None else (
            "NO_ATTRIBUTED_PURCHASE_HISTORY" if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION
            else "ELIGIBLE"
        ),
        split_objective_version=(SUPPORT_AWARE_OBJECTIVE_VERSION
                                 if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION else None),
        product_holdout_targets=split_result.product_targets if split_result is not None else None,
        product_holdout_deviation=(split_result.product_holdout_deviation
                                   if split_result is not None else None),
        union_holdout_target=split_result.union_target if split_result is not None else None,
        union_holdout_deviation=split_result.union_holdout_deviation if split_result is not None else None,
        baseline_assignment_changes=(split_result.baseline_assignment_changes
                                     if split_result is not None else None),
        membership_signature_count=split_result.signature_count if split_result is not None else None,
    )
    if split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION:
        from dataclasses import replace

        manifest = replace(
            manifest, partition_manifest_sha256=_sha256_json(manifest.partition_payload())
        )
    return BuyerCohortBuild(manifest=manifest, frame=frame)


def audit_buyer_similarity_sources(
    database_path: str | Path,
    *,
    product_catalog_path: str | Path = "data/product_master.csv",
) -> dict[str, Any]:
    """Audit bounded source alignment without exposing identities or PII."""

    catalog, catalog_sha256 = _load_product_catalog(product_catalog_path)
    connection = _read_only_connection(database_path)
    try:
        customer_import_id, customer_checksum = _latest_import(
            connection, dataset_name="customers", table_name="customers"
        )
        sales_import_id, sales_checksum = _latest_import(
            connection,
            dataset_name="campaign_sales",
            table_name="campaign_sales",
        )
        customer_count = int(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0])
        sales_count = int(connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0])
        prospect_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])
        unique_customers = int(connection.execute(
            "SELECT COUNT(DISTINCT customer_id) FROM customers"
        ).fetchone()[0])
        orphan_sales = int(connection.execute(
            """SELECT COUNT(*) FROM campaign_sales s
               LEFT JOIN customers c ON c.customer_id=s.customer_id
               WHERE c.customer_id IS NULL"""
        ).fetchone()[0])
        invalid_sales = dict(connection.execute(
            """SELECT
                SUM(CASE WHEN DATE(contact_date) IS NULL THEN 1 ELSE 0 END) invalid_contact_dates,
                SUM(CASE WHEN campaign_attributed_sale_flag=1 AND (
                    purchase_flag<>1 OR pu_label<>1 OR DATE(purchase_date) IS NULL
                    OR DATE(purchase_date)<DATE(contact_date)
                    OR days_to_purchase IS NULL OR days_to_purchase>30)
                    THEN 1 ELSE 0 END) invalid_attributed_rows,
                SUM(CASE WHEN pu_label<>campaign_attributed_sale_flag THEN 1 ELSE 0 END)
                    label_flag_mismatches
               FROM campaign_sales"""
        ).fetchone())
        observed_products = [
            str(row[0]) for row in connection.execute(
                "SELECT DISTINCT product_id FROM campaign_sales ORDER BY product_id"
            )
        ]
        customer_states = {
            str(row[0]).strip() for row in connection.execute(
                "SELECT DISTINCT state FROM customers WHERE NULLIF(TRIM(state),'') IS NOT NULL"
            )
        }
        prospect_states = {
            str(row[0]).strip() for row in connection.execute(
                "SELECT DISTINCT state FROM demographics WHERE NULLIF(TRIM(state),'') IS NOT NULL"
            )
        }
        identity_overlap = int(connection.execute(
            """SELECT COUNT(*) FROM customers c
               JOIN demographics d ON d.person_id=c.customer_id"""
        ).fetchone()[0])
        numeric = dict(connection.execute(
            """WITH reference AS (
                SELECT MAX(DATE(contact_date)) AS reference_date FROM campaign_sales)
               SELECT
                MIN(individual_yearly_income) customer_income_min,
                MAX(individual_yearly_income) customer_income_max,
                MIN(family_member_count) customer_family_min,
                MAX(family_member_count) customer_family_max,
                MIN(CAST(STRFTIME('%Y',reference.reference_date) AS INTEGER)
                    - CAST(SUBSTR(date_of_birth,1,4) AS INTEGER)
                    - CASE WHEN STRFTIME('%m-%d',reference.reference_date)
                        < SUBSTR(date_of_birth,6,5) THEN 1 ELSE 0 END)
                    customer_age_min,
                MAX(CAST(STRFTIME('%Y',reference.reference_date) AS INTEGER)
                    - CAST(SUBSTR(date_of_birth,1,4) AS INTEGER)
                    - CASE WHEN STRFTIME('%m-%d',reference.reference_date)
                        < SUBSTR(date_of_birth,6,5) THEN 1 ELSE 0 END)
                    customer_age_max,
                reference.reference_date historical_reference_date
               FROM customers CROSS JOIN reference"""
        ).fetchone())
        prospect_numeric = dict(connection.execute(
            """SELECT
                MIN(age) prospect_age_min,MAX(age) prospect_age_max,
                MIN(individual_yearly_income) prospect_income_min,
                MAX(individual_yearly_income) prospect_income_max,
                MIN(family_member_count) prospect_family_min,
                MAX(family_member_count) prospect_family_max
               FROM demographics"""
        ).fetchone())
        missing_customer_features = dict(connection.execute(
            """SELECT
                SUM(CASE WHEN DATE(date_of_birth) IS NULL THEN 1 ELSE 0 END) age,
                SUM(CASE WHEN NULLIF(TRIM(gender),'') IS NULL THEN 1 ELSE 0 END) gender,
                SUM(CASE WHEN NULLIF(TRIM(state),'') IS NULL THEN 1 ELSE 0 END) state,
                SUM(CASE WHEN individual_yearly_income IS NULL THEN 1 ELSE 0 END) individual_yearly_income,
                SUM(CASE WHEN NULLIF(TRIM(marital_status),'') IS NULL THEN 1 ELSE 0 END) marital_status,
                SUM(CASE WHEN NULLIF(TRIM(education),'') IS NULL THEN 1 ELSE 0 END) education,
                SUM(CASE WHEN NULLIF(TRIM(employment_status),'') IS NULL THEN 1 ELSE 0 END) employment_status,
                SUM(CASE WHEN NULLIF(TRIM(resident_status),'') IS NULL THEN 1 ELSE 0 END) resident_status,
                SUM(CASE WHEN NULLIF(TRIM(resident_type),'') IS NULL THEN 1 ELSE 0 END) resident_type,
                SUM(CASE WHEN family_member_count IS NULL THEN 1 ELSE 0 END) family_member_count,
                SUM(CASE WHEN NULLIF(TRIM(type_of_employment),'') IS NULL THEN 1 ELSE 0 END) type_of_employment
               FROM customers"""
        ).fetchone())
        missing_prospect_features = dict(connection.execute(
            """SELECT
                SUM(CASE WHEN age IS NULL THEN 1 ELSE 0 END) age,
                SUM(CASE WHEN NULLIF(TRIM(gender),'') IS NULL THEN 1 ELSE 0 END) gender,
                SUM(CASE WHEN NULLIF(TRIM(state),'') IS NULL THEN 1 ELSE 0 END) state,
                SUM(CASE WHEN individual_yearly_income IS NULL THEN 1 ELSE 0 END) individual_yearly_income,
                SUM(CASE WHEN NULLIF(TRIM(marital_status),'') IS NULL THEN 1 ELSE 0 END) marital_status,
                SUM(CASE WHEN NULLIF(TRIM(education),'') IS NULL THEN 1 ELSE 0 END) education,
                SUM(CASE WHEN NULLIF(TRIM(employment_status),'') IS NULL THEN 1 ELSE 0 END) employment_status,
                SUM(CASE WHEN NULLIF(TRIM(resident_status),'') IS NULL THEN 1 ELSE 0 END) resident_status,
                SUM(CASE WHEN NULLIF(TRIM(resident_type),'') IS NULL THEN 1 ELSE 0 END) resident_type,
                SUM(CASE WHEN family_member_count IS NULL THEN 1 ELSE 0 END) family_member_count,
                SUM(CASE WHEN NULLIF(TRIM(type_of_employment),'') IS NULL THEN 1 ELSE 0 END) type_of_employment
               FROM demographics"""
        ).fetchone())
        vocabulary_alignment: dict[str, dict[str, Any]] = {}
        for column in CATEGORICAL_FEATURES:
            customer_values = {
                str(row[0]).strip()
                for row in connection.execute(
                    f"""SELECT DISTINCT {column} FROM customers
                         WHERE NULLIF(TRIM({column}),'') IS NOT NULL"""
                )
            }
            prospect_values = {
                str(row[0]).strip()
                for row in connection.execute(
                    f"""SELECT DISTINCT {column} FROM demographics
                         WHERE NULLIF(TRIM({column}),'') IS NOT NULL"""
                )
            }
            vocabulary_alignment[column] = {
                "customer_value_count": len(customer_values),
                "prospect_value_count": len(prospect_values),
                "customer_only_values": sorted(customer_values - prospect_values),
            }
    finally:
        connection.close()

    issues: list[str] = []
    if unique_customers != customer_count:
        issues.append("CUSTOMER_PRIMARY_KEY_NOT_UNIQUE")
    if orphan_sales:
        issues.append("CAMPAIGN_SALES_CUSTOMER_FK_GAP")
    if any(int(value or 0) for value in invalid_sales.values()):
        issues.append("ATTRIBUTION_OR_DATE_CONTRACT_INVALID")
    if identity_overlap:
        issues.append("CUSTOMER_PROSPECT_IDENTITY_OVERLAP")
    if not customer_states <= prospect_states:
        issues.append("CUSTOMER_STATE_NOT_IN_PROSPECT_VOCABULARY")
    if any(
        values["customer_only_values"] for values in vocabulary_alignment.values()
    ):
        issues.append("CUSTOMER_CATEGORY_NOT_IN_PROSPECT_VOCABULARY")
    if float(numeric["customer_income_min"]) < 0 or int(numeric["customer_family_min"]) < 1:
        issues.append("CUSTOMER_NUMERIC_UNIT_CONTRACT_INVALID")
    if (
        int(prospect_numeric["prospect_age_min"]) < 0
        or float(prospect_numeric["prospect_income_min"]) < 0
        or int(prospect_numeric["prospect_family_min"]) < 1
    ):
        issues.append("PROSPECT_NUMERIC_UNIT_CONTRACT_INVALID")
    return {
        "audit_contract_version": "BUYER_SIMILARITY_SOURCE_ALIGNMENT_V1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "counts": {
            "customers": customer_count,
            "campaign_sales": sales_count,
            "prospects": prospect_count,
            "catalog_products": len(catalog),
            "observed_sales_products": len(observed_products),
            "observed_catalog_products": len(set(observed_products) & set(catalog)),
            "customer_prospect_id_overlap": identity_overlap,
            "orphan_sales": orphan_sales,
        },
        "source_identity": {
            "customer_import_id": customer_import_id,
            "customer_source_checksum": customer_checksum,
            "campaign_sales_import_id": sales_import_id,
            "campaign_sales_source_checksum": sales_checksum,
            "product_catalog_sha256": catalog_sha256,
        },
        "observed_product_ids": observed_products,
        "catalog_without_observed_history": sorted(set(catalog) - set(observed_products)),
        "sales_validity": {key: int(value or 0) for key, value in invalid_sales.items()},
        "missing_customer_features": {
            key: int(value or 0) for key, value in missing_customer_features.items()
        },
        "missing_prospect_features": {
            key: int(value or 0) for key, value in missing_prospect_features.items()
        },
        "shared_vocabulary_alignment": vocabulary_alignment,
        "state_alignment": {
            "customer_distinct_states": len(customer_states),
            "prospect_distinct_states": len(prospect_states),
            "customer_states_missing_from_prospects": sorted(customer_states - prospect_states),
        },
        "numeric_units": {
            **numeric,
            **prospect_numeric,
            "income_unit": "nonnegative yearly currency amount",
            "family_unit": "whole members",
            "historical_age": "completed years at the fixed cohort reference date",
            "prospect_age": "completed years at the demographic source snapshot",
        },
        "identity_contract": {
            "customer_namespace": "customer_id",
            "prospect_namespace": "person_id",
            "mapping_required": False,
            "proof": "Independent namespaces with zero exact identifier overlap.",
        },
        "label_contract": {
            "positive": "campaign_attributed_sale_flag=1 AND purchase_flag=1",
            "comparison": "UNLABELED_NOT_VERIFIED_NONBUYER",
        },
    }


__all__ = (
    "BUYER_COHORT_CONTRACT_VERSION",
    "BUYER_CONVERSION_DEFINITION",
    "BUYER_SPLIT_SEED",
    "BUYER_SPLIT_STRATEGY_VERSION",
    "LEGACY_BUYER_SPLIT_STRATEGY_VERSION",
    "BuyerCohortBuild",
    "BuyerCohortError",
    "BuyerCohortManifest",
    "BuyerCohortRequestError",
    "BuyerCohortSourceError",
    "BuyerCohortSourceIdentity",
    "FIT_FRACTION",
    "MINIMUM_PRODUCT_BUYERS",
    "MINIMUM_PRODUCT_FIT_BUYERS",
    "MINIMUM_PRODUCT_HOLDOUT_BUYERS",
    "ProductBuyerSupport",
    "audit_buyer_similarity_sources",
    "build_product_buyer_cohorts",
)
