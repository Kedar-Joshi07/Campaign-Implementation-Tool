"""Exact v3 context resolution and one shared count/member selection predicate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.database.connection import get_connection
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256
from app.selection_contracts import BUYER_SIMILARITY_PRODUCT_MATCH_POLICY
from app.services.buyer_similarity_cohort_service import (
    BUYER_COHORT_CONTRACT_VERSION,
    BUYER_CONVERSION_DEFINITION,
    BUYER_SPLIT_SEED,
    BUYER_SPLIT_STRATEGY_VERSION,
)
from app.services.buyer_similarity_split_service import SUPPORT_AWARE_OBJECTIVE_VERSION
from app.services.buyer_similarity_scoring_service import (
    has_current_similarity_attestation,
    similarity_profile_set_sha256,
)
from app.services.calibrated_selection_contract_service import build_branch_predicates


class SimilaritySelectionError(ValueError):
    """The exact v3 selection identity or source snapshot is unavailable."""


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _current_sources(connection: Any) -> dict[str, tuple[int, str]]:
    rows = connection.execute(
        """SELECT dataset_name,import_id,source_checksum FROM data_import_runs r
           WHERE status='COMPLETED' AND dataset_name IN
             ('customers','campaign_sales','demographics')
             AND import_id=(SELECT MAX(import_id) FROM data_import_runs newer
                            WHERE newer.dataset_name=r.dataset_name
                              AND newer.status='COMPLETED')"""
    ).fetchall()
    result = {str(row["dataset_name"]):
              (int(row["import_id"]), str(row["source_checksum"])) for row in rows}
    for dataset in ("customers", "campaign_sales", "demographics"):
        result.setdefault(dataset, (0, ""))
    return result


def _historical_window(connection: Any) -> tuple[str, str]:
    row = connection.execute(
        "SELECT MIN(contact_date),MAX(contact_date) FROM campaign_sales"
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        raise SimilaritySelectionError("Historical campaign dates are unavailable.")
    return str(row[0])[:10], str(row[1])[:10]


@dataclass(frozen=True)
class SimilarityResolution:
    context_sha256: str
    source_identity: dict[str, tuple[int, str]]
    profile_rows: tuple[dict[str, Any], ...]
    generation_rows: tuple[dict[str, Any], ...]
    missing_products: tuple[str, ...]
    unready_products: tuple[str, ...]
    profile_set_sha256: str | None
    composite_context_sha256: str
    window_start: str
    window_end: str

    @property
    def ready(self) -> bool:
        return not self.missing_products and not self.unready_products

    @property
    def profile_ids(self) -> tuple[int, ...]:
        return tuple(int(row["profile_id"]) for row in self.profile_rows)

    @property
    def generation_ids(self) -> tuple[int, ...]:
        return tuple(int(row["similarity_generation_id"]) for row in self.generation_rows)


def resolve_similarity_context(
    database_path: str | Path,
    context: Mapping[str, Any],
    *,
    project_root: str | Path,
    product_catalog_path: str | Path | None = None,
) -> SimilarityResolution:
    """Resolve only profiles trained for this exact product set and history."""

    products = tuple(sorted(set(context.get("product_ids") or ())))
    if not products or len(products) > 50 or any(not isinstance(p, str) for p in products):
        raise SimilaritySelectionError("Choose between one and 50 exact products.")
    catalog_path = Path(product_catalog_path or Path(project_root) / "data" / "product_master.csv")
    if not catalog_path.is_file():
        raise SimilaritySelectionError("The exact product catalog is unavailable.")
    catalog_sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    with get_connection(database_path) as connection:
        sources = _current_sources(connection)
        start, end = _historical_window(connection)
        historical_context = {
            key: sorted(set(context.get(key) or ()))
            for key in ("campaign_types", "campaign_categories", "offer_types",
                        "historical_campaign_channels")
        }
        source_identity = {
            "customer_import_id": sources["customers"][0],
            "customer_source_checksum": sources["customers"][1],
            "campaign_sales_import_id": sources["campaign_sales"][0],
            "campaign_sales_source_checksum": sources["campaign_sales"][1],
            "product_catalog_sha256": catalog_sha,
        }
        context_sha = canonical_digest({
            "cohort_contract_version": BUYER_COHORT_CONTRACT_VERSION,
            "conversion_definition": BUYER_CONVERSION_DEFINITION,
            "product_match_policy": BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
            "product_ids": list(products),
            "historical_context": historical_context,
            "window_start": start,
            "window_end": end,
            "demographic_reference_date": end,
            "split_strategy_version": BUYER_SPLIT_STRATEGY_VERSION,
            "split_seed": BUYER_SPLIT_SEED,
            "split_objective_version": SUPPORT_AWARE_OBJECTIVE_VERSION,
            "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
            "source_identity": source_identity,
        })
        marks = ",".join("?" for _ in products)
        profiles = connection.execute(
            f"""SELECT p.*,a.artifact_sha256,a.storage_uri FROM buyer_similarity_profiles p
                JOIN buyer_similarity_profile_artifacts a ON a.profile_id=p.profile_id
                    AND a.artifact_state='PUBLISHED'
                WHERE p.publication_state='PUBLISHED' AND p.product_id IN ({marks})
                    AND p.historical_context_sha256=?
                    AND p.customer_import_id=? AND p.customer_source_checksum=?
                    AND p.campaign_sales_import_id=? AND p.campaign_sales_source_checksum=?
                    AND p.resolved_window_start=? AND p.resolved_window_end=?
                ORDER BY p.product_id,p.profile_id DESC""",
            (*products, context_sha, sources["customers"][0], sources["customers"][1],
             sources["campaign_sales"][0], sources["campaign_sales"][1], start, end),
        ).fetchall()
        by_product: dict[str, dict[str, Any]] = {}
        for row in profiles:
            by_product.setdefault(str(row["product_id"]), dict(row))
        selected_profiles = tuple(by_product[p] for p in products if p in by_product)
        generations: list[dict[str, Any]] = []
        unready: list[str] = []
        for profile in selected_profiles:
            rows = connection.execute(
                """SELECT * FROM buyer_similarity_score_generations
                   WHERE profile_id=? AND publication_state='PUBLISHED'
                     AND demographic_import_id=? AND demographic_source_checksum=?
                   ORDER BY similarity_generation_id DESC""",
                (profile["profile_id"], *sources["demographics"]),
            ).fetchall()
            current = next(
                (dict(row) for row in rows if has_current_similarity_attestation(
                    database_path, int(row["similarity_generation_id"]),
                    project_root=project_root)), None,
            )
            if current is None:
                unready.append(str(profile["product_id"]))
            else:
                generations.append(current)
    profile_set = (
        similarity_profile_set_sha256(
            [str(row["immutable_identity_sha256"]) for row in selected_profiles]
        ) if len(selected_profiles) == len(products) else None
    )
    composite = canonical_digest({
        "selection_contract_version": "3",
        "context_sha256": context_sha,
        "products": products,
        "profile_set_sha256": profile_set,
        "generation_identities": [
            (row["similarity_generation_id"], row["composite_context_sha256"])
            for row in generations
        ],
        "source_identity": sources,
        "product_match_policy": BUYER_SIMILARITY_PRODUCT_MATCH_POLICY,
    })
    return SimilarityResolution(
        context_sha, sources, selected_profiles, tuple(generations),
        tuple(p for p in products if p not in by_product), tuple(unready),
        profile_set, composite, start, end,
    )


def _eligible_predicate(branches: Sequence[Mapping[str, Any]]) -> tuple[str, list[Any]]:
    if not 1 <= len(branches) <= 49:
        raise SimilaritySelectionError("The saved filter branches are invalid.")
    clauses: list[str] = []
    params: list[Any] = []
    for branch in branches:
        if any(branch.get(key) is not None for key in
               ("score_min", "score_max", "top_percentile_max", "deciles", "rank_bands")):
            raise SimilaritySelectionError("Probability or rank filters are invalid in v3.")
        predicates, values = build_branch_predicates(branch, calibrated=False)
        clauses.append("(" + (" AND ".join(predicates) if predicates else "1") + ")")
        params.extend(values)
    return " OR ".join(clauses), params


def selection_sql(
    branches: Sequence[Mapping[str, Any]],
    generation_ids: Sequence[int],
    minimum: float,
    *,
    selection_mode: str,
    top_n: int | None,
) -> tuple[str, tuple[Any, ...]]:
    """One full precision SQL predicate for both exact count and member output."""

    ids = tuple(dict.fromkeys(generation_ids))
    if not 1 <= len(ids) <= 50 or any(isinstance(i, bool) or not isinstance(i, int) or i <= 0 for i in ids):
        raise SimilaritySelectionError("Verified score generations are required.")
    if isinstance(minimum, bool) or minimum not in {0.50, 0.60, 0.70, 0.80, 0.90}:
        raise SimilaritySelectionError("Choose a supported similarity minimum.")
    if selection_mode not in {"ALL_MATCHING", "TOP_N"} or (
        (selection_mode == "TOP_N" and (isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0))
        or (selection_mode == "ALL_MATCHING" and top_n is not None)
    ):
        raise SimilaritySelectionError("The selection mode is invalid.")
    predicate, parameters = _eligible_predicate(branches)
    marks = ",".join("?" for _ in ids)
    cte = f"""WITH eligible AS MATERIALIZED (
        SELECT d.person_id FROM demographics d WHERE {predicate}
    ), ranked AS (
        SELECT s.person_id,s.buyer_similarity_score,s.similarity_tier,
               s.product_id matched_product_id,s.score_method_version,
               s.feature_coverage,s.similarity_generation_id,
               ROW_NUMBER() OVER (PARTITION BY s.person_id
                 ORDER BY s.buyer_similarity_score DESC,s.product_id ASC,
                          s.similarity_generation_id ASC) winner_order
        FROM buyer_similarity_scores s
        JOIN eligible e ON e.person_id=s.person_id
        WHERE s.similarity_generation_id IN ({marks}) AND s.is_valid=1
          AND s.buyer_similarity_score IS NOT NULL
          AND s.buyer_similarity_score>=?
          AND s.feature_coverage>=0.80 AND s.feature_coverage<=1.0
    ), winners AS (
        SELECT person_id,buyer_similarity_score,similarity_tier,
               matched_product_id,score_method_version,feature_coverage,
               similarity_generation_id FROM ranked WHERE winner_order=1
    )"""
    return cte, tuple([*parameters, *ids, minimum, minimum])


def selected_members_sql(cte: str, *, selection_mode: str) -> str:
    return (
        cte + " SELECT * FROM winners WHERE buyer_similarity_score>=?"
        " ORDER BY buyer_similarity_score DESC,person_id ASC"
        + (" LIMIT ?" if selection_mode == "TOP_N" else "")
    )


def count_similarity_selection(
    connection: Any, branches: Sequence[Mapping[str, Any]],
    generation_ids: Sequence[int], minimum: float,
    *, selection_mode: str, top_n: int | None,
) -> tuple[int, int, int, int, int]:
    # Validate against the same saved selection contract used by materialization.
    # A window-rank over every row of every generation is unnecessary for an
    # exact *count*: score maxima have the same threshold membership. Each
    # attested generation has one score row per demographic person, so indexed
    # (generation, person) joins produce one bounded row per prospect.
    selection_sql(
        branches, generation_ids, minimum,
        selection_mode=selection_mode, top_n=top_n,
    )
    predicate, demographic_params = _eligible_predicate(branches)
    bindings: dict[str, Any] = {"minimum": minimum}
    for index, value in enumerate(demographic_params):
        predicate = predicate.replace("?", f":filter_{index}", 1)
        bindings[f"filter_{index}"] = value
    ids = tuple(dict.fromkeys(generation_ids))
    if minimum >= .80 and connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='buyer_similarity_generation_attestations'"
    ).fetchone() is not None:
        marks = ",".join("?" for _ in ids)
        attestations = connection.execute(
            "SELECT similarity_generation_id,expected_person_count,verified_row_count,"
            "invalid_score_count,verification_status "
            "FROM buyer_similarity_generation_attestations "
            f"WHERE similarity_generation_id IN ({marks})", ids,
        ).fetchall()
        total = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])
        if (len(attestations) == len(ids) and all(
            row["verification_status"] == "VERIFIED"
            and row["expected_person_count"] == total
            and row["verified_row_count"] == total for row in attestations
        )):
            # The score index starts with (generation, is_valid, score), so
            # high-threshold candidate union is far smaller than ranking all
            # generations. Full attestation makes the complement exact too.
            demographic = int(connection.execute(
                f"SELECT COUNT(*) FROM demographics d WHERE {predicate}", bindings,
            ).fetchone()[0])
            candidate_queries = []
            for index, generation_id in enumerate(ids):
                bindings[f"generation_{index}"] = generation_id
                candidate_queries.append(
                    "SELECT person_id FROM buyer_similarity_scores "
                    f"WHERE similarity_generation_id=:generation_{index} "
                    "AND is_valid=1 AND buyer_similarity_score>=:minimum "
                    "AND feature_coverage>=0.80 AND feature_coverage<=1.0"
                )
            qualifying = int(connection.execute(
                "WITH candidates AS (" + " UNION ".join(candidate_queries) + ") "
                "SELECT COUNT(*) FROM candidates c JOIN demographics d "
                f"ON d.person_id=c.person_id WHERE {predicate}", bindings,
            ).fetchone()[0])
            if any(row["invalid_score_count"] == 0 for row in attestations):
                valid = total
            else:
                by_id = {row["similarity_generation_id"]: row for row in attestations}
                ordered = sorted(ids, key=lambda value: by_id[value]["invalid_score_count"])
                invalid_joins = [
                    "JOIN buyer_similarity_scores s" + str(index) + " ON "
                    f"s{index}.similarity_generation_id=:generation_{index} "
                    f"AND s{index}.person_id=s0.person_id AND s{index}.is_valid=0"
                    for index in range(1, len(ordered))
                ]
                invalid_bindings = {f"generation_{index}": value
                                    for index, value in enumerate(ordered)}
                invalid = int(connection.execute(
                    "SELECT COUNT(*) FROM buyer_similarity_scores s0 "
                    + " ".join(invalid_joins)
                    + " WHERE s0.similarity_generation_id=:generation_0 AND s0.is_valid=0",
                    invalid_bindings,
                ).fetchone()[0])
                valid = total - invalid
            selected = min(qualifying, top_n) if selection_mode == "TOP_N" else qualifying
            return demographic, valid, total - valid, qualifying, selected
    joins = []
    score_values = []
    for index, generation_id in enumerate(ids):
        bindings[f"generation_{index}"] = generation_id
        joins.append(
            f"LEFT JOIN buyer_similarity_scores s{index} ON "
            f"s{index}.similarity_generation_id=:generation_{index} "
            f"AND s{index}.person_id=d.person_id"
        )
        score_values.append(
            f"CASE WHEN s{index}.is_valid=1 AND "
            f"s{index}.buyer_similarity_score IS NOT NULL AND "
            f"s{index}.feature_coverage>=0.80 AND "
            f"s{index}.feature_coverage<=1.0 "
            f"THEN s{index}.buyer_similarity_score ELSE -1 END"
        )
    maximum = f"max({','.join(score_values)})" if len(score_values) > 1 else score_values[0]
    aggregate = connection.execute(
        f"""SELECT COUNT(*) total,
                   COALESCE(SUM(eligible),0) demographic,
                   COALESCE(SUM(best>=0),0) valid,
                   COALESCE(SUM(eligible=1 AND best>=:minimum),0) qualifying
            FROM (SELECT CASE WHEN ({predicate}) THEN 1 ELSE 0 END eligible,
                         {maximum} best
                  FROM demographics d {' '.join(joins)})""",
        bindings,
    ).fetchone()
    total = int(aggregate["total"])
    demographic = int(aggregate["demographic"])
    valid = int(aggregate["valid"])
    qualifying = int(aggregate["qualifying"])
    selected = min(qualifying, top_n) if selection_mode == "TOP_N" else qualifying
    return demographic, valid, total - valid, qualifying, selected


__all__ = (
    "SimilarityResolution", "SimilaritySelectionError", "canonical_digest",
    "count_similarity_selection", "resolve_similarity_context", "selected_members_sql",
    "selection_sql",
)
