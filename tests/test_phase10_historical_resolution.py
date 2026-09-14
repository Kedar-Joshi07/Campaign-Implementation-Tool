from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.schemas.phase10_intelligence import PHASE10_INSUFFICIENT_HISTORY_MESSAGE
from app.services.historical_analysis_service import create_historical_analysis
from app.services.phase10_context_identity_service import (
    derive_modeling_context_from_campaign_context,
    normalize_modeling_context,
)
from app.services.phase10_historical_resolution_service import (
    Phase10HistoricalResolutionError,
    evaluate_training_eligibility,
    resolve_or_create_phase10_historical_analysis,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase10-historical-resolution.db"
    initialize_database(path)
    customers = [
        (f"C{index:02d}", f"19{70 + index:02d}-01-01", "Ohio", 50_000, 2)
        for index in range(1, 21)
    ]
    observations: list[tuple[object, ...]] = []
    for index in range(1, 15):
        positive = 1 if index <= 7 else 0
        observations.append(
            (
                f"S{index:02d}",
                f"C{index:02d}",
                "P1",
                "Lifecycle",
                "Loyalty",
                f"2025-01-{index:02d}",
                positive,
                positive,
                positive,
            )
        )
    for index in range(15, 21):
        positive = 1 if index <= 18 else 0
        observations.append(
            (
                f"S{index:02d}",
                f"C{index:02d}",
                "P2",
                "Acquisition",
                "Discount",
                f"2025-02-{index - 14:02d}",
                positive,
                positive,
                positive,
            )
        )

    with get_connection(path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            customers,
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_category,
                campaign_channel, offer_type, product_name, product_category,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (
                ?, ?, 'CMP', ?, 'Campaign', 'Retention', ?,
                'Email', ?, 'Product', 'Product category',
                '2025-01-01', '2025-12-31', ?,
                1, 0, 0, ?, ?, ?
            )
            """,
            observations,
        )
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, '2026-09-14T00:00:00Z',
                      '2026-09-14T00:00:01Z', 'COMPLETED', ?, ?, 0, ?)
            """,
            (
                ("customers", "data/customers.csv", 20, 20, "c" * 64),
                ("campaign_sales", "data/campaign_sales.csv", 20, 20, "d" * 64),
            ),
        )
    return path


def _context(*products: str, **dimensions: object):
    return normalize_modeling_context(
        {
            "product_ids": list(products),
            "campaign_types": dimensions.get("campaign_types", []),
            "campaign_categories": dimensions.get("campaign_categories", []),
            "offer_types": dimensions.get("offer_types", []),
            "historical_campaign_channels": dimensions.get(
                "historical_campaign_channels", []
            ),
        }
    )


def test_creates_then_exactly_reuses_current_analysis(database_path: Path) -> None:
    first = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )
    second = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )

    assert first.status == "READY"
    assert first.created is True and first.reused is False
    assert first.eligibility.status == "ELIGIBLE"
    assert first.eligibility.deterministic_split_viable is True
    assert second.status == "READY"
    assert second.reused is True and second.created is False
    assert second.analysis_run_id == first.analysis_run_id
    assert second.compatible_candidate_ids == (first.analysis_run_id,)


def test_exact_filter_identity_rejects_subset_and_creates_new(database_path: Path) -> None:
    subset = create_historical_analysis(
        database_path,
        {"product_ids": ["P1"], "offer_types": ["Loyalty"]},
    )

    resolved = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )

    assert resolved.created is True
    assert resolved.analysis_run_id != subset["analysis_run_id"]
    assert (subset["analysis_run_id"], "FILTER_IDENTITY_MISMATCH") in {
        (item.analysis_run_id, item.reason_code)
        for item in resolved.rejected_candidates
    }


def test_source_drift_rejects_old_analysis_and_builds_current_one(
    database_path: Path,
) -> None:
    original = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, '2026-09-14T01:00:00Z',
                      '2026-09-14T01:00:01Z', 'COMPLETED', 20, 20, 0, ?)
            """,
            (
                ("customers", "data/customers-v2.csv", "e" * 64),
                ("campaign_sales", "data/campaign-sales-v2.csv", "f" * 64),
            ),
        )

    resolved = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )

    assert resolved.created is True
    assert resolved.analysis_run_id != original["analysis_run_id"]
    assert (original["analysis_run_id"], "SOURCE_PROVENANCE_MISMATCH") in {
        (item.analysis_run_id, item.reason_code)
        for item in resolved.rejected_candidates
    }


def test_failed_and_incomplete_analyses_are_never_reused(database_path: Path) -> None:
    failed = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    incomplete = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE historical_analysis_runs
            SET status = 'FAILED', error_message = 'synthetic failure'
            WHERE analysis_run_id = ?
            """,
            (failed["analysis_run_id"],),
        )
        connection.execute(
            """
            UPDATE historical_analysis_runs
            SET status = 'RUNNING', completed_at = NULL, results_json = NULL
            WHERE analysis_run_id = ?
            """,
            (incomplete["analysis_run_id"],),
        )

    resolved = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )

    assert resolved.created is True
    assert resolved.analysis_run_id not in {
        failed["analysis_run_id"],
        incomplete["analysis_run_id"],
    }
    assert resolved.compatible_candidate_ids == ()


def test_delivery_and_prospect_targeting_do_not_change_analysis_identity(
    database_path: Path,
) -> None:
    base = {
        "product_ids": ["P1"],
        "campaign_types": [],
        "campaign_categories": [],
        "offer_types": [],
        "historical_campaign_channels": [],
        "campaign_channel": "EMAIL",
        "targeting_criteria": {"match_strength": "GOOD", "age_buckets": ["25-34"]},
    }
    changed = {
        **base,
        "campaign_channel": "DIRECT_MAIL",
        "targeting_criteria": {
            "match_strength": "VERY_STRONG",
            "age_buckets": ["65-74"],
            "states": ["Texas"],
        },
    }
    first_context = derive_modeling_context_from_campaign_context(base)
    second_context = derive_modeling_context_from_campaign_context(changed)
    assert first_context.modeling_context_sha256 == second_context.modeling_context_sha256

    first = resolve_or_create_phase10_historical_analysis(database_path, first_context)
    second = resolve_or_create_phase10_historical_analysis(database_path, second_context)
    assert second.reused is True
    assert second.analysis_run_id == first.analysis_run_id


def test_multi_product_and_restrictive_category_offer_contexts(
    database_path: Path,
) -> None:
    multi = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1", "P2"),
    )
    restrictive = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context(
            "P2",
            campaign_categories=["Acquisition"],
            offer_types=["Discount"],
        ),
    )

    assert multi.status == "READY"
    assert (
        multi.eligibility.selected_customer_count,
        multi.eligibility.positive_customer_count,
        multi.eligibility.unlabeled_customer_count,
    ) == (20, 11, 9)
    assert restrictive.status == "BLOCKED"
    assert restrictive.resolved_filters.campaign_categories == ["Acquisition"]
    assert restrictive.resolved_filters.offer_types == ["Discount"]
    assert (
        restrictive.eligibility.selected_customer_count,
        restrictive.eligibility.positive_customer_count,
        restrictive.eligibility.unlabeled_customer_count,
    ) == (6, 4, 2)


def test_old_analysis_json_without_new_keys_is_discovered(database_path: Path) -> None:
    saved = create_historical_analysis(database_path, {"product_ids": ["P1"]})
    with get_connection(database_path, write=True) as connection:
        row = connection.execute(
            "SELECT filters_json FROM historical_analysis_runs WHERE analysis_run_id = ?",
            (saved["analysis_run_id"],),
        ).fetchone()
        filters = json.loads(row["filters_json"])
        filters.pop("campaign_categories")
        filters.pop("offer_types")
        connection.execute(
            "UPDATE historical_analysis_runs SET filters_json = ? WHERE analysis_run_id = ?",
            (json.dumps(filters, sort_keys=True, separators=(",", ":")), saved["analysis_run_id"]),
        )

    resolved = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("P1"),
    )

    assert resolved.reused is True
    assert resolved.analysis_run_id == saved["analysis_run_id"]
    assert resolved.resolved_filters.campaign_categories == []
    assert resolved.resolved_filters.offer_types == []


def test_zero_history_blocks_without_model_or_scoring(database_path: Path) -> None:
    resolved = resolve_or_create_phase10_historical_analysis(
        database_path,
        _context("DOES_NOT_EXIST"),
    )

    assert resolved.status == "BLOCKED"
    assert resolved.analysis_run_id is None
    assert resolved.business_message == PHASE10_INSUFFICIENT_HISTORY_MESSAGE
    assert resolved.eligibility.reason_codes == [
        "INSUFFICIENT_SELECTED_CUSTOMERS",
        "INSUFFICIENT_POSITIVE_CUSTOMERS",
        "INSUFFICIENT_UNLABELED_CUSTOMERS",
        "DETERMINISTIC_SPLIT_NOT_VIABLE",
    ]
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("selected", "positive", "unlabeled", "expected_status", "reason"),
    (
        (14, 7, 7, "ELIGIBLE", None),
        (13, 6, 7, "BLOCKED", "INSUFFICIENT_SELECTED_CUSTOMERS"),
        (14, 6, 8, "BLOCKED", "INSUFFICIENT_POSITIVE_CUSTOMERS"),
        (14, 8, 6, "BLOCKED", "INSUFFICIENT_UNLABELED_CUSTOMERS"),
    ),
)
def test_training_eligibility_v1_count_boundaries(
    selected: int,
    positive: int,
    unlabeled: int,
    expected_status: str,
    reason: str | None,
) -> None:
    decision = evaluate_training_eligibility(
        {
            "selected_customer_count": selected,
            "positive_customer_count": positive,
            "unlabeled_customer_count": unlabeled,
        },
        deterministic_split_viable=True,
    )

    assert decision.status == expected_status
    if reason is None:
        assert decision.reason_codes == []
    else:
        assert reason in decision.reason_codes


def test_split_viability_is_an_independent_blocking_gate() -> None:
    decision = evaluate_training_eligibility(
        {
            "selected_customer_count": 14,
            "positive_customer_count": 7,
            "unlabeled_customer_count": 7,
        },
        deterministic_split_viable=False,
    )
    assert decision.status == "BLOCKED"
    assert decision.reason_codes == ["DETERMINISTIC_SPLIT_NOT_VIABLE"]


def test_nonreconciling_counts_fail_closed() -> None:
    with pytest.raises(Phase10HistoricalResolutionError, match="reconcile"):
        evaluate_training_eligibility(
            {
                "selected_customer_count": 14,
                "positive_customer_count": 7,
                "unlabeled_customer_count": 6,
            },
            deterministic_split_viable=True,
        )
