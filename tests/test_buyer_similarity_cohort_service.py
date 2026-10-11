from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import UNKNOWN_CATEGORY
from app.services.buyer_similarity_cohort_service import (
    BUYER_CONVERSION_DEFINITION,
    BUYER_SPLIT_SEED,
    BUYER_SPLIT_STRATEGY_VERSION,
    BuyerCohortSourceError,
    audit_buyer_similarity_sources,
    build_product_buyer_cohorts,
)
from data_generation_scripts.generate_campaign_sales import observed_product_ids


NOW = "2026-10-06T00:00:00Z"


def _catalog(path: Path) -> Path:
    path.write_text(
        "product_id,product_name,product_category\n"
        "P1,Exact Product One,Category A\n"
        "P2,Exact Product Two,Category A\n"
        "P3,Exact Product Three,Category B\n"
        "P4,Catalog Product Without History,Category B\n",
        encoding="utf-8",
    )
    return path


def _sale(
    sequence: int,
    customer_id: str,
    product_id: str,
    *,
    attributed: int = 1,
    contact_date: str = "2025-06-01",
    campaign_type: str = "Retention",
    campaign_category: str = "Lifecycle",
    offer_type: str = "Loyalty",
    campaign_channel: str = "Email",
) -> tuple[object, ...]:
    purchase_date = contact_date if attributed else None
    return (
        f"S{sequence:06d}", customer_id, "CMP", product_id,
        "Campaign", campaign_type, campaign_category, campaign_channel,
        offer_type, "Product", "Category", "2025-01-01", "2026-12-31",
        contact_date, 1, attributed, attributed, attributed, attributed, attributed,
        purchase_date, 0 if attributed else None, attributed,
    )


def _seed(path: Path, *, p1_buyers: int = 200, p3_buyers: int = 199) -> Path:
    initialize_database(path)
    customers = []
    for index in range(205):
        customers.append(
            (
                f"CUS{index:04d}", "1990-06-15",
                None if index == 0 else "Female",
                "Ohio", 50_000 + index, "Single", "Bachelor degree",
                "Employed full-time", "Citizen", "Urban", 2,
                "Salaried",
            )
        )
    sales: list[tuple[object, ...]] = []
    sequence = 0
    for index in range(p1_buyers):
        sequence += 1
        sales.append(_sale(sequence, f"CUS{index:04d}", "P1"))
    # A repeat attributed order must not change customer weight.
    sequence += 1
    sales.append(_sale(sequence, "CUS0000", "P1"))
    # The same customer can belong to several exact products.
    sequence += 1
    sales.append(_sale(sequence, "CUS0000", "P2"))
    for index in range(p3_buyers):
        sequence += 1
        sales.append(_sale(sequence, f"CUS{index:04d}", "P3"))
    # Unlabeled is not a buyer and a future contact is outside the window.
    sequence += 1
    sales.append(_sale(sequence, "CUS0200", "P1", attributed=0))
    sequence += 1
    sales.append(_sale(sequence, "CUS0201", "P1", contact_date="2026-01-01"))
    # Historical context may narrow evidence; prospect hard filters never do.
    sequence += 1
    sales.append(
        _sale(
            sequence,
            "CUS0202",
            "P1",
            campaign_type="Acquisition",
            campaign_category="Acquisition",
            offer_type="Discount",
            campaign_channel="SMS",
        )
    )
    with get_connection(path, write=True) as connection:
        connection.executemany(
            """INSERT INTO customers (
                customer_id,date_of_birth,gender,state,individual_yearly_income,
                marital_status,education,employment_status,resident_status,
                resident_type,family_member_count,type_of_employment
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            customers,
        )
        connection.executemany(
            """INSERT INTO campaign_sales (
                campaign_sales_id,customer_id,campaign_id,product_id,
                campaign_name,campaign_type,campaign_category,campaign_channel,
                offer_type,product_name,product_category,campaign_start_date,
                campaign_end_date,contact_date,contacted_flag,engagement_flag,response_flag,
                purchase_flag,campaign_attributed_sale_flag,pu_label,purchase_date,
                days_to_purchase,quantity
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            sales,
        )
        connection.executemany(
            """INSERT INTO demographics (
                person_id,age,gender,state,individual_yearly_income,
                marital_status,education,employment_status,resident_status,
                resident_type,family_member_count,type_of_employment,
                number_of_children_in_family,number_of_adults_in_family,
                family_yearly_income
            ) VALUES (?,30,'Female','Ohio',60000,'Single','Bachelor degree',
                'Employed full-time','Citizen','Urban',2,'Salaried',0,2,90000)""",
            ((f"PER{index:04d}",) for index in range(10)),
        )
        connection.executemany(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES (?,?,?,?,'COMPLETED',?,?,0,?)""",
            (
                ("customers", "customers.csv", NOW, NOW, len(customers), len(customers), "c" * 64),
                ("campaign_sales", "sales.csv", NOW, NOW, len(sales), len(sales), "d" * 64),
            ),
        )
    return path


@pytest.fixture
def cohort_sources(tmp_path: Path) -> tuple[Path, Path]:
    return _seed(tmp_path / "cohort.db"), _catalog(tmp_path / "products.csv")


def _build(path: Path, catalog: Path, product_ids: list[str]):
    return build_product_buyer_cohorts(
        path,
        product_ids=product_ids,
        window_start="2025-01-01",
        window_end="2025-12-31",
        product_catalog_path=catalog,
    )


def test_exact_product_join_repeat_dedup_and_customer_disjoint_split(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    build_args = {
        "product_ids": ["P1"],
        "window_start": "2025-01-01",
        "window_end": "2025-12-31",
        "campaign_types": ["Retention"],
        "product_catalog_path": catalog,
    }
    first = build_product_buyer_cohorts(path, **build_args)
    second = build_product_buyer_cohorts(path, **build_args)

    support = first.manifest.product_support[0]
    assert support.distinct_attributed_buyers == 200
    assert support.fit_buyers == 160
    assert support.holdout_buyers == 40
    assert support.status == "ELIGIBLE"
    assert first.manifest.eligible is True
    assert first.manifest.conversion_definition == BUYER_CONVERSION_DEFINITION
    assert first.manifest.product_match_policy == "ANY_SELECTED_PRODUCT_MAX_V1"
    assert first.manifest.split_strategy_version == BUYER_SPLIT_STRATEGY_VERSION
    assert first.manifest.split_seed == BUYER_SPLIT_SEED
    assert len(first.frame) == 200
    assert first.frame[["product_id", "customer_id"]].duplicated().sum() == 0
    fit = set(first.frame.loc[first.frame["split"] == "FIT", "customer_id"])
    holdout = set(first.frame.loc[first.frame["split"] == "HOLDOUT", "customer_id"])
    assert fit.isdisjoint(holdout)
    assert first.manifest.public_payload() == second.manifest.public_payload()
    assert first.frame.equals(second.frame)


def test_same_customer_two_products_has_one_union_assignment_and_unordered_products_normalize(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    result = _build(path, catalog, ["P2", "P1", "P1"])

    assert result.manifest.product_ids == ("P1", "P2")
    shared = result.frame[result.frame["customer_id"] == "CUS0000"]
    assert set(shared["product_id"]) == {"P1", "P2"}
    assert shared["split"].nunique() == 1
    assert result.manifest.eligible is False
    assert "INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT" in result.manifest.reason_codes


def test_context_precedes_dedup_prospect_filters_are_absent_and_future_rows_are_excluded(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    unfiltered = _build(path, catalog, ["P1"])
    retention = build_product_buyer_cohorts(
        path,
        product_ids=["P1"],
        window_start="2025-01-01",
        window_end="2025-12-31",
        campaign_types=["Retention"],
        campaign_categories=["Lifecycle"],
        offer_types=["Loyalty"],
        historical_campaign_channels=["Email"],
        product_catalog_path=catalog,
    )

    assert unfiltered.manifest.product_support[0].distinct_attributed_buyers == 201
    assert retention.manifest.product_support[0].distinct_attributed_buyers == 200
    assert "CUS0201" not in set(unfiltered.frame["customer_id"])
    parameters = inspect.signature(build_product_buyer_cohorts).parameters
    assert {"states", "income_groups", "delivery_channel"}.isdisjoint(parameters)


def test_floor_boundaries_and_bounded_unsupported_reasons(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    result = _build(path, catalog, ["P4", "P3", "UNKNOWN"])
    support = {item.product_id: item for item in result.manifest.product_support}

    assert support["P3"].distinct_attributed_buyers == 199
    assert support["P3"].reason_code == "INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT"
    assert support["P4"].reason_code == "NO_ATTRIBUTED_PURCHASE_HISTORY"
    assert support["UNKNOWN"].reason_code == "UNKNOWN_PRODUCT"
    assert result.manifest.eligible is False
    public_json = json.dumps(result.manifest.public_payload(), sort_keys=True)
    assert "CUS0000" not in public_json
    assert "Exact Product" not in public_json


def test_missing_categorical_demographics_are_canonical_unknown(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    result = _build(path, catalog, ["P1"])

    row = result.frame.set_index("customer_id").loc["CUS0000"]
    assert row["gender"] == UNKNOWN_CATEGORY
    assert result.manifest.demographic_reference_date == "2025-12-31"
    assert "wall-clock" in result.manifest.historical_age_semantics
    assert "unlabeled" in result.manifest.comparison_label_semantics


def test_wrong_customer_join_fails_closed(tmp_path: Path) -> None:
    path = _seed(tmp_path / "wrong-join.db", p1_buyers=200)
    catalog = _catalog(tmp_path / "products.csv")
    raw = sqlite3.connect(path)
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute(
            """INSERT INTO campaign_sales (
                campaign_sales_id,customer_id,campaign_id,product_id,
                campaign_name,campaign_type,campaign_category,campaign_channel,
                offer_type,product_name,product_category,campaign_start_date,
                campaign_end_date,contact_date,contacted_flag,engagement_flag,response_flag,
                purchase_flag,campaign_attributed_sale_flag,pu_label,purchase_date,
                days_to_purchase,quantity
            ) VALUES ('ORPHAN','NOT_A_CUSTOMER','CMP','P1','Campaign','Retention',
                'Lifecycle','Email','Loyalty','Product','Category','2025-01-01',
                '2025-12-31','2025-06-01',1,1,1,1,1,1,'2025-06-01',0,1)"""
        )
        raw.execute(
            """UPDATE data_import_runs SET rows_read=rows_read+1,
               rows_inserted=rows_inserted+1
               WHERE dataset_name='campaign_sales' AND status='COMPLETED'"""
        )
        raw.commit()
    finally:
        raw.close()

    with pytest.raises(BuyerCohortSourceError, match="exact customer join"):
        _build(path, catalog, ["P1"])


def test_source_checksum_change_rejects_stale_request_and_changes_identity(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    original = _build(path, catalog, ["P1"])
    with get_connection(path, write=True) as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0])
        connection.execute(
            """INSERT INTO data_import_runs (
                dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES ('customers','replacement.csv',?,?,'COMPLETED',?,?,0,?)""",
            (NOW, NOW, count, count, "e" * 64),
        )

    with pytest.raises(BuyerCohortSourceError, match="does not match"):
        build_product_buyer_cohorts(
            path,
            product_ids=["P1"],
            window_start="2025-01-01",
            window_end="2025-12-31",
            product_catalog_path=catalog,
            expected_customer_source_checksum="c" * 64,
        )
    current = _build(path, catalog, ["P1"])
    assert current.manifest.source_identity.customer_source_checksum == "e" * 64
    assert current.manifest.context_identity_sha256 != original.manifest.context_identity_sha256


def test_source_audit_proves_independent_namespaces_and_alignment(
    cohort_sources: tuple[Path, Path],
) -> None:
    path, catalog = cohort_sources
    audit = audit_buyer_similarity_sources(path, product_catalog_path=catalog)

    assert audit["status"] == "PASS"
    assert audit["counts"]["customers"] == 205
    assert audit["counts"]["prospects"] == 10
    assert audit["counts"]["customer_prospect_id_overlap"] == 0
    assert audit["counts"]["orphan_sales"] == 0
    assert audit["identity_contract"]["mapping_required"] is False
    assert audit["label_contract"]["comparison"] == "UNLABELED_NOT_VERIFIED_NONBUYER"
    assert audit["state_alignment"]["customer_states_missing_from_prospects"] == []
    assert all(
        not values["customer_only_values"]
        for values in audit["shared_vocabulary_alignment"].values()
    )


def test_generator_summary_counts_observed_products_not_catalog_products() -> None:
    campaigns = [
        SimpleNamespace(product_id="PRD002"),
        SimpleNamespace(product_id="PRD001"),
        SimpleNamespace(product_id="PRD002"),
    ]

    assert observed_product_ids(campaigns) == ["PRD001", "PRD002"]


def test_recorded_product_support_manifest_is_bounded_and_reconciles() -> None:
    manifest = json.loads(
        Path("docs/evidence/lookalike_v3/02_PRODUCT_SUPPORT_MANIFEST.json")
        .read_text(encoding="utf-8")
    )
    rows = manifest["product_support"]
    fields = manifest["product_support_tuple_contract"]
    records = [dict(zip(fields, row, strict=True)) for row in rows]

    assert len(records) == 48
    assert len({row["product_id"] for row in records}) == 48
    assert sum(row["status"] == "ELIGIBLE" for row in records) == 31
    assert sum(row["status"] == "NOT_ELIGIBLE" for row in records) == 17
    assert manifest["source_counts"] == {
        "customers": 125000,
        "campaign_sales": 570000,
        "prospects": 5000000,
        "catalog_products": 48,
        "observed_sales_products": 36,
        "customer_prospect_id_overlap": 0,
        "orphan_sales": 0,
    }
    assert manifest["single_product_boundary_proof"]["fit_buyers"] == 160
    assert manifest["single_product_boundary_proof"]["holdout_buyers"] == 40
    assert manifest["privacy"]["customer_ids_present"] is False
    assert "CUS000" not in json.dumps(manifest, sort_keys=True)
    historical = json.loads(
        Path("data/campaign_sales_summary.json").read_text(encoding="utf-8")
    )
    assert historical["distinct_products"] == 48
