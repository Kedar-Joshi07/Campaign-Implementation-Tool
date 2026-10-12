"""Independent v3 readiness and exact buyer similarity preflight."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.services.buyer_similarity_cohort_service import build_product_buyer_cohorts
from app.selection_contracts import (
    BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
    BUYER_SIMILARITY_SCORE_METHOD_VERSION,
    BUYER_SIMILARITY_SCORE_SEMANTICS,
    BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION,
    BUYER_SIMILARITY_THRESHOLD_PREDICATE,
)
from app.services.buyer_similarity_selection_service import (
    _eligible_predicate,
    _current_sources,
    canonical_digest,
    count_similarity_selection,
    resolve_similarity_context,
)
from app.services.potential_customer_search_submission_service import (
    normalize_similarity_search_definition,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _unsupported_products(
    path: Path, context: dict, start: str, end: str, *,
    product_catalog_path: Path, source_identity: dict[str, tuple[int, str]],
) -> tuple[list[str], str]:
    """Use the training cohort's exact union split, not only raw buyer counts."""

    cohort = build_product_buyer_cohorts(
        path, product_ids=context["product_ids"], window_start=start,
        window_end=end, demographic_reference_date=end,
        campaign_types=context.get("campaign_types"),
        campaign_categories=context.get("campaign_categories"),
        offer_types=context.get("offer_types"),
        historical_campaign_channels=context.get("historical_campaign_channels"),
        product_catalog_path=product_catalog_path,
        expected_customer_source_checksum=source_identity["customers"][1],
        expected_campaign_sales_source_checksum=source_identity["campaign_sales"][1],
    )
    unsupported = [
        support.product_id for support in cohort.manifest.product_support
        if support.status != "ELIGIBLE"
    ]
    return unsupported, cohort.manifest.split_status


def _cache_key(resolution: Any, response: dict, products: list[str]) -> str:
    return canonical_digest({
        "cache_contract_version": "SIMILARITY_PREFLIGHT_V1",
        "selection_contract_version": "3",
        "score_semantics": BUYER_SIMILARITY_SCORE_SEMANTICS,
        "score_method_version": BUYER_SIMILARITY_SCORE_METHOD_VERSION,
        "threshold_predicate": BUYER_SIMILARITY_THRESHOLD_PREDICATE,
        "similarity_minimum": response["similarity_minimum"],
        "product_match_policy": BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
        "products": sorted(products),
        "profile_ids": resolution.profile_ids,
        "profile_set_sha256": resolution.profile_set_sha256,
        "generation_ids": resolution.generation_ids,
        "composite_context_sha256": resolution.composite_context_sha256,
        "source_identity_sha256": response["source_identity_sha256"],
        "criteria_sha256": response["criteria_sha256"],
        "filter_branches_sha256": response["filter_branches_sha256"],
        "catalog_version": response["catalog_version"],
        "selection_mode": response["selection_mode"],
        "top_n": response["top_n"],
        "ordering": "SCORE_DESC_PERSON_ID_ASC",
        "publication_cutoff": response["publication_cutoff"],
    })


def exact_similarity_preflight(
    database_path: str | Path,
    *, context: dict, criteria: dict, similarity_minimum: float,
    selection_mode: str, top_n: int | None, catalog_version: str,
    project_root: str | Path | None = None,
    product_catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(database_path)
    root = Path(project_root or Path(__file__).resolve().parents[2])
    normalized_context, normalized_criteria, catalog = normalize_similarity_search_definition(
        path, raw_context=context, raw_criteria=criteria,
        selection_mode=selection_mode, top_n=top_n,
        similarity_minimum=similarity_minimum, catalog_version=catalog_version,
    )
    resolution = resolve_similarity_context(
        path, normalized_context, project_root=root,
        product_catalog_path=product_catalog_path,
    )
    branches = list(normalized_criteria.audience_filter_branches)
    predicate, params = _eligible_predicate(branches)
    with get_connection(path) as connection:
        connection.execute("BEGIN")
        demographic_count = int(connection.execute(
            f"SELECT COUNT(*) FROM demographics d WHERE {predicate}", params,
        ).fetchone()[0])
    source_sha = canonical_digest({
        name: {"import_id": value[0], "checksum": value[1]}
        for name, value in sorted(resolution.source_identity.items())
    })
    missing_count = len(resolution.missing_products) + len(resolution.unready_products)
    response: dict[str, Any] = {
        "selection_contract_version": BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION,
        "score_semantics": BUYER_SIMILARITY_SCORE_SEMANTICS,
        "score_method_version": BUYER_SIMILARITY_SCORE_METHOD_VERSION,
        "similarity_minimum": similarity_minimum,
        "threshold_predicate": BUYER_SIMILARITY_THRESHOLD_PREDICATE,
        "product_match_policy": BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
        "demographic_eligible_count": demographic_count,
        "valid_similarity_count": None,
        "invalid_similarity_count": None,
        "similarity_qualifying_count": None,
        "selected_count": None,
        "similarity_currentness": "NOT_AVAILABLE",
        "similarity_eligibility": "NOT_ELIGIBLE",
        "reason_code": "SIMILARITY_NOT_PREPARED",
        "safe_message": "Buyer similarity can be prepared for this exact campaign context.",
        "build_available": True,
        "profile_ids": list(resolution.profile_ids),
        "profile_set_sha256": resolution.profile_set_sha256,
        "composite_context_sha256": resolution.composite_context_sha256,
        "similarity_generation_id": resolution.generation_ids[0] if resolution.ready else None,
        "similarity_generation_ids": list(resolution.generation_ids),
        "source_identity_sha256": source_sha,
        "source_snapshot_version": "LATEST_IMPORT_IDENTITY_V1",
        "publication_cutoff": (
            max(str(row["published_at"]) for row in resolution.generation_rows)
            if resolution.ready else None
        ),
        "catalog_version": str(catalog["catalog_version"]),
        "criteria_sha256": normalized_criteria.sha256,
        "filter_branches_sha256": canonical_digest(branches),
        "selection_mode": selection_mode,
        "top_n": top_n,
        "probability_currentness": None,
        "probability_eligibility": None,
        "work_estimate": {
            "product_count": len(normalized_context["product_ids"]),
            "missing_profile_count": len(resolution.missing_products),
            "missing_score_generation_count": missing_count,
            "operator_confirmation_recommended": missing_count > 1,
        },
        "cache_hit": False,
    }
    if not resolution.ready:
        with get_connection(path) as connection:
            products = normalized_context["product_ids"]
            prior = connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_profiles "
                "WHERE publication_state='PUBLISHED' AND product_id IN ("
                + ",".join("?" for _ in products) + ")",
                tuple(products),
            ).fetchone()[0]
            prior_generation = connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_score_generations g "
                "JOIN buyer_similarity_profiles p ON p.profile_id=g.profile_id "
                "WHERE g.publication_state='PUBLISHED' AND p.product_id IN ("
                + ",".join("?" for _ in products) + ")",
                tuple(products),
            ).fetchone()[0]
        unsupported: list[str] = []
        split_status = ""
        if (resolution.missing_products
            and all(item[0] > 0 for item in resolution.source_identity.values())):
            unsupported, split_status = _unsupported_products(
                path, normalized_context, resolution.window_start,
                resolution.window_end,
                product_catalog_path=Path(
                    product_catalog_path or root / "data" / "product_master.csv"
                ),
                source_identity=resolution.source_identity,
            )
        if split_status == "UNRESOLVED":
            response.update(
                reason_code="SPLIT_SOLVER_UNRESOLVED", build_available=True,
                safe_message=(
                    "The shared buyer split was not resolved within its bounded "
                    "computation limit. Preparation may be retried."
                ),
            )
        elif unsupported:
            response.update(
                reason_code="PROFILE_NOT_ELIGIBLE", build_available=False,
                safe_message=(
                    "At least one selected product lacks enough attributed buyers "
                    "in both the fit and holdout groups for this exact historical context."
                ),
            )
        elif prior and (resolution.missing_products or prior_generation):
            response.update(
                similarity_currentness="STALE", reason_code="SIMILARITY_SOURCE_STALE",
                safe_message="Earlier buyer similarity is no longer current for these sources or products. Prepare fresh intelligence.",
            )
        elif resolution.profile_rows:
            response.update(
                similarity_currentness="BUILDING",
                reason_code="SIMILARITY_BUILDING",
                safe_message="Buyer similarity preparation is available for this context.",
            )
        return response

    key = _cache_key(resolution, response, normalized_context["product_ids"])
    with get_connection(path) as connection:
        connection.execute("BEGIN")
        cached = connection.execute(
            "SELECT * FROM similarity_preflight_cache WHERE cache_key_sha256=? AND currentness_state='CURRENT'",
            (key,),
        ).fetchone()
        if cached is None:
            counts = count_similarity_selection(
                connection, branches, resolution.generation_ids,
                similarity_minimum, selection_mode=selection_mode, top_n=top_n,
            )
        else:
            counts = tuple(int(cached[field]) for field in (
                "demographic_eligible_count", "valid_similarity_count",
                "invalid_similarity_count", "similarity_qualifying_count",
                "selected_count",
            ))
    after = resolve_similarity_context(
        path, normalized_context, project_root=root,
        product_catalog_path=product_catalog_path,
    )
    if not after.ready or after.composite_context_sha256 != resolution.composite_context_sha256:
        response.update(
            similarity_currentness="STALE", reason_code="SOURCE_NOT_CURRENT",
            safe_message="Source data changed during the count. Refresh the search choices.",
        )
        return response
    demographic, valid, invalid, qualifying, selected = counts
    response.update(
        demographic_eligible_count=demographic, valid_similarity_count=valid,
        invalid_similarity_count=invalid, similarity_qualifying_count=qualifying,
        selected_count=selected, similarity_currentness="CURRENT",
        similarity_eligibility="ELIGIBLE", reason_code="ELIGIBLE",
        safe_message="Current buyer similarity is ready.", cache_hit=cached is not None,
        work_estimate={**response["work_estimate"], "missing_score_generation_count": 0},
    )
    if cached is None:
        now = _now()
        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if _current_sources(connection) != resolution.source_identity:
                response.update(
                    similarity_currentness="STALE", reason_code="SOURCE_NOT_CURRENT",
                    safe_message="Source data changed during the count. Refresh the search choices.",
                    selected_count=None, valid_similarity_count=None,
                    invalid_similarity_count=None, similarity_qualifying_count=None,
                    similarity_eligibility="NOT_ELIGIBLE",
                )
                return response
            connection.execute(
                """INSERT OR IGNORE INTO similarity_preflight_cache (
                    cache_key_sha256,selection_contract_version,score_semantics,
                    score_method_version,similarity_minimum,threshold_predicate,
                    product_match_policy,criteria_sha256,filter_branches_sha256,
                    catalog_version,source_identity_sha256,profile_ids_json,
                    profile_set_sha256,composite_context_sha256,
                    similarity_generation_id,demographic_eligible_count,
                    valid_similarity_count,invalid_similarity_count,
                    similarity_qualifying_count,selected_count,
                    similarity_currentness,similarity_eligibility,reason_code,
                    build_available,source_snapshot_version,publication_cutoff,
                    currentness_state,created_at,last_used_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, "3", BUYER_SIMILARITY_SCORE_SEMANTICS,
                 BUYER_SIMILARITY_SCORE_METHOD_VERSION, similarity_minimum,
                 BUYER_SIMILARITY_THRESHOLD_PREDICATE,
                 BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
                 normalized_criteria.sha256, response["filter_branches_sha256"],
                 catalog_version, source_sha, json.dumps(list(resolution.profile_ids)),
                 resolution.profile_set_sha256, resolution.composite_context_sha256,
                 resolution.generation_ids[0], demographic, valid, invalid,
                 qualifying, selected, "CURRENT", "ELIGIBLE", "ELIGIBLE", 1,
                 "LATEST_IMPORT_IDENTITY_V1", response["publication_cutoff"],
                 "CURRENT", now, now),
            )
    return response


__all__ = ("exact_similarity_preflight",)
