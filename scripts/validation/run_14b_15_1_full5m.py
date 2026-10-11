"""Resumable Prompt 16 certification for the support-aware V2 buyer split.

Phases are strictly sequential: audit, import, profiles, score, verify. All
writes are confined to a dedicated output/ child. The earlier V1 certification
database is read only and copied with SQLite's consistent backup API.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validation import run_14b_16_full5m as prior  # noqa: E402

from app.database.connection import get_connection  # noqa: E402
from app.repositories.buyer_similarity_profile_repository import publish_buyer_similarity_profile  # noqa: E402
from app.services.buyer_similarity_cohort_service import build_product_buyer_cohorts  # noqa: E402
from app.services.buyer_similarity_partition_service import freeze_partition_manifest  # noqa: E402
from app.services.buyer_similarity_profile_service import fit_buyer_similarity_profile  # noqa: E402
from app.services.buyer_similarity_scoring_service import (  # noqa: E402
    has_current_similarity_attestation,
    run_similarity_generation,
)
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight  # noqa: E402
from app.services import potential_customer_search_submission_service as submission  # noqa: E402
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository  # noqa: E402
from app.schemas.potential_customer_search import PotentialCustomerSearchV3Request  # noqa: E402
from app.services.buyer_similarity_search_orchestration_service import execute_similarity_search_safely  # noqa: E402
from app.services.buyer_similarity_selection_service import (  # noqa: E402
    count_similarity_selection,
    resolve_similarity_context,
)
from app.services.phase11_export_service import stream_phase11_result_export_csv  # noqa: E402
from app.services.phase11_results_service import get_result_detail, list_result_history  # noqa: E402


VERSION = "14B_15_1_SUPPORT_AWARE_FULL5M_V1"
DEFAULT_SCRATCH = prior.ROOT / "output" / "lookalike_stage15_1_full5m"
PRIOR_SCRATCH = prior.ROOT / "output" / "lookalike_stage16_full5m"
RECORDED_SCENARIOS = (prior.ROOT / "Prompts" /
                      "Campaign_Implementation_Tool_Demo_Readiness_20_Real_Runs_Prompt_Pack" /
                      "scenarios.json")


def save(scratch: Path, state: dict) -> None:
    prior._save_manifest(scratch, state)


def audit(scratch: Path, state: dict) -> None:
    prior.audit(scratch, state)
    state["runner_version"] = VERSION
    state["starting_sha"] = "336875c30fc32b00323d916ecc45b232016168a1"
    state["source_certification_db"] = str(PRIOR_SCRATCH.relative_to(prior.ROOT))
    save(scratch, state)


def import_copy(scratch: Path, state: dict) -> None:
    if state["phases"].get("audit", {}).get("status") != "PASS":
        raise RuntimeError("Audit the canonical source bytes before importing.")
    prior._require_capacity(scratch)
    destination = scratch / "certification.db"
    source = PRIOR_SCRATCH / "certification.db"
    if not source.is_file():
        raise RuntimeError("The earlier disposable full-5M import is missing.")
    if not destination.exists():
        prior._log("copying verified disposable full-5M import with SQLite backup")
        started = time.perf_counter()
        with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True) as reader:
            with sqlite3.connect(destination) as writer:
                reader.backup(writer, pages=4096, sleep=.1)
        state["copy_seconds"] = round(time.perf_counter() - started, 3)
        save(scratch, state)
    (scratch / "data").mkdir(exist_ok=True)
    shutil.copy2(PRIOR_SCRATCH / "data" / "product_master.csv",
                 scratch / "data" / "product_master.csv")
    if (PRIOR_SCRATCH / "artifacts").is_dir():
        shutil.copytree(PRIOR_SCRATCH / "artifacts", scratch / "artifacts", dirs_exist_ok=True)
    prior.import_full(scratch, state)  # independently verifies rows and source checksums
    with get_connection(destination) as connection:
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError("Copied full-5M database failed integrity checks.")
    state["copy_integrity"] = "PASS"
    save(scratch, state)


def profiles(scratch: Path, state: dict) -> None:
    if state["phases"].get("import", {}).get("status") != "PASS":
        raise RuntimeError("Verify the isolated full-5M import first.")
    prior._require_capacity(scratch)
    db = scratch / "certification.db"
    context = state["recorded_common_context"]
    started = time.perf_counter()
    cohort = build_product_buyer_cohorts(
        db, product_ids=context["product_ids"], window_start=prior.WINDOW_START,
        window_end=prior.WINDOW_END, campaign_types=context["campaign_types"],
        campaign_categories=context["campaign_categories"], offer_types=context["offer_types"],
        historical_campaign_channels=context["historical_campaign_channels"],
        demographic_reference_date=prior.WINDOW_END,
        product_catalog_path=scratch / "data" / "product_master.csv",
    )
    state["product_support"] = [asdict(item) for item in cohort.manifest.product_support]
    state["cohort_lineage"] = asdict(cohort.manifest)
    if (not cohort.manifest.eligible or cohort.manifest.split_status != "FEASIBLE"
        or sorted(item.product_id for item in cohort.manifest.product_support if item.status == "ELIGIBLE")
        != sorted(context["product_ids"])):
        state["common_context_status"] = "BLOCKED"
        save(scratch, state)
        raise RuntimeError("Exact recorded context is not support eligible under V2.")
    freeze_partition_manifest(cohort, project_root=scratch, database_path=db)
    state["common_context_status"] = "READY"
    save(scratch, state)
    for product in context["product_ids"]:
        if product in state.get("profiles", {}):
            continue
        began = time.perf_counter()
        profile = fit_buyer_similarity_profile(cohort, product_id=product)
        published = publish_buyer_similarity_profile(
            db, profile, project_root=scratch, execution_owner=f"stage15-1-{product}",
            execution_token=secrets.token_hex(32), now=prior._now(),
        )
        state.setdefault("profiles", {})[product] = {
            "profile_id": published.profile_id,
            "fit_publish_seconds": round(time.perf_counter() - began, 3),
        }
        save(scratch, state)
        prior._log(f"published V2 profile {product}")
    state["phases"]["profiles"] = {
        "status": "PASS", "elapsed_seconds": round(time.perf_counter() - started, 3),
        "resources_after": prior._resources(scratch),
    }
    save(scratch, state)


def crash_worker(scratch: Path, profile_id: int) -> None:
    def crash(stage: str, processed: int, _total: int, _message: str) -> None:
        if stage == "SCORING_PROSPECTS" and processed >= prior.CHUNK_SIZE:
            sys.stdout.flush()
            import os
            os._exit(77)

    run_similarity_generation(
        scratch / "certification.db", profile_id, project_root=scratch,
        execution_owner="stage15-1-interrupted-worker", execution_token=secrets.token_hex(32),
        chunk_size=prior.CHUNK_SIZE, progress_callback=crash,
    )
    raise RuntimeError("Controlled scoring interruption was not reached.")


def score(scratch: Path, state: dict) -> None:
    if state["phases"].get("profiles", {}).get("status") != "PASS":
        raise RuntimeError("Publish all three current V2 profiles first.")
    prior._require_capacity(scratch)
    db = scratch / "certification.db"
    for index, product in enumerate(state["recorded_common_context"]["product_ids"]):
        profile_id = int(state["profiles"][product]["profile_id"])
        existing = state.get("scores", {}).get(product)
        if existing and has_current_similarity_attestation(
            db, int(existing["generation_id"]), project_root=scratch
        ):
            prior._log(f"reusing current V2 full generation {product}")
            continue
        if index == 0 and "restart" not in state:
            began = time.perf_counter()
            child = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--phase", "crash-worker",
                 "--scratch-dir", str(scratch), "--profile-id", str(profile_id)],
                cwd=prior.ROOT, capture_output=True, text=True, timeout=900, check=False,
            )
            if child.returncode != 77:
                raise RuntimeError("Controlled V2 score worker did not reach the checkpoint.")
            with get_connection(db) as connection:
                row = connection.execute(
                    "SELECT similarity_generation_id,publication_state "
                    "FROM buyer_similarity_score_generations WHERE profile_id=? "
                    "ORDER BY similarity_generation_id DESC LIMIT 1", (profile_id,),
                ).fetchone()
                if row is None or row["publication_state"] == "PUBLISHED":
                    raise RuntimeError("Interrupted V2 score generation was falsely published.")
                staged = connection.execute(
                    "SELECT COUNT(*) FROM buyer_similarity_score_stage "
                    "WHERE similarity_generation_id=?", (row["similarity_generation_id"],),
                ).fetchone()[0]
            if staged != prior.CHUNK_SIZE:
                raise RuntimeError("V2 restart checkpoint row count is incorrect.")
            state["restart"] = {
                "product_id": product, "generation_id": row["similarity_generation_id"],
                "checkpoint_rows": staged,
                "interrupt_seconds": round(time.perf_counter() - began, 3),
                "published_before_restart": False,
            }
            save(scratch, state)
        began = time.perf_counter()
        last = 0

        def progress(stage: str, processed: int, total: int, _message: str) -> None:
            nonlocal last
            if stage in {"DEEP_VERIFY", "PUBLISH"} or processed - last >= 250_000:
                prior._log(f"{product} {stage}: {processed}/{total}")
                last = processed

        result = run_similarity_generation(
            db, profile_id, project_root=scratch,
            execution_owner=f"stage15-1-{product}-scorer", execution_token=secrets.token_hex(32),
            chunk_size=prior.CHUNK_SIZE,
            stale_before=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            if index == 0 else None,
            progress_callback=progress,
        )
        generation_id = int(result["similarity_generation_id"])
        if not has_current_similarity_attestation(db, generation_id, project_root=scratch):
            raise RuntimeError(f"V2 generation for {product} lacks current attestation.")
        if index == 0 and generation_id != state["restart"]["generation_id"]:
            raise RuntimeError("V2 restart did not retain the exact generation identity.")
        state.setdefault("scores", {})[product] = {
            "generation_id": generation_id,
            "published_person_count": result["published_person_count"],
            "elapsed_seconds": round(time.perf_counter() - began, 3),
            "restarted_from_stale_lease": bool(result.get("restarted_from_stale_lease")),
            "deep_verification_run": bool(result.get("deep_verification_run")),
            "db_bytes": db.stat().st_size,
            "resources_after": prior._resources(scratch),
        }
        save(scratch, state)
        prior._log(f"verified V2 {product} full population")
    state["phases"]["score"] = {"status": "PASS", "completed_at": prior._now()}
    save(scratch, state)


def verify(scratch: Path, state: dict) -> None:
    if state["phases"].get("score", {}).get("status") != "PASS":
        raise RuntimeError("Publish all three full-5M generations first.")
    prior.verify(scratch, state)  # deep independent per-product audit and scalar sample
    db = scratch / "certification.db"
    ids = [int(state["scores"][product]["generation_id"])
           for product in state["recorded_common_context"]["product_ids"]]
    with prior._readonly(db) as connection:
        aggregate = connection.execute(
            """WITH joined AS (
                SELECT a.person_id,
                       CASE WHEN a.is_valid=1 THEN a.buyer_similarity_score END sa,
                       CASE WHEN b.is_valid=1 THEN b.buyer_similarity_score END sb,
                       CASE WHEN c.is_valid=1 THEN c.buyer_similarity_score END sc
                FROM buyer_similarity_scores a
                JOIN buyer_similarity_scores b ON b.person_id=a.person_id
                JOIN buyer_similarity_scores c ON c.person_id=a.person_id
                WHERE a.similarity_generation_id=? AND b.similarity_generation_id=?
                  AND c.similarity_generation_id=?
            ), ranked AS (
                SELECT person_id, sa, sb, sc,
                       NULLIF(max(coalesce(sa,-1),coalesce(sb,-1),coalesce(sc,-1)),-1) best
                FROM joined
            )
            SELECT COUNT(*) total,
                   SUM(best IS NOT NULL) valid,
                   SUM(best IS NULL) invalid,
                   SUM(sa IS NOT NULL AND sa=best) first_wins_or_ties,
                   SUM(sb IS NOT NULL AND sb=best AND (sa IS NULL OR sb>sa)) second_wins,
                   SUM(sc IS NOT NULL AND sc=best AND (sa IS NULL OR sc>sa)
                       AND (sb IS NULL OR sc>sb)) third_wins,
                   SUM(best>=0.50) ge_50, SUM(best>=0.60) ge_60,
                   SUM(best>=0.70) ge_70, SUM(best>=0.80) ge_80,
                   SUM(best>=0.90) ge_90
            FROM ranked""", ids,
        ).fetchone()
    composite = dict(aggregate)
    if (composite["total"] != 5_000_000
        or composite["valid"] + composite["invalid"] != composite["total"]
        or sum(composite[key] for key in
               ("first_wins_or_ties", "second_wins", "third_wins")) != composite["valid"]):
        raise RuntimeError("Full three-product max/winner composite failed independent aggregate.")
    state["complete_context_composite"] = composite
    if (state["recorded_context_preflight"]["readiness"] != "CURRENT"
        or state["recorded_context_preflight"]["selected_count"] != composite["ge_70"]):
        raise RuntimeError("Exact three-product preflight differs from full composite threshold count.")
    state["phases"]["verify"]["status"] = "PASS_THREE_PRODUCT_CONTEXT"
    state["recorded_context_preflight"].pop("unsupported_product", None)
    state["recorded_context_preflight"]["status"] = "CURRENT"
    save(scratch, state)


def preflight(scratch: Path, state: dict) -> None:
    if state["phases"].get("score", {}).get("status") != "PASS":
        raise RuntimeError("Publish all three full-5M generations first.")
    db = scratch / "certification.db"
    started = time.perf_counter()
    options = submission.search_form_options(db)
    options_seconds = time.perf_counter() - started
    began = time.perf_counter()
    result = exact_similarity_preflight(
        db, context=state["recorded_common_context"], criteria={},
        similarity_minimum=.70, selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=scratch,
    )
    state["recorded_context_preflight"] = {
        "readiness": result["similarity_currentness"],
        "reason_code": result["reason_code"],
        "selected_count": result["selected_count"],
        "valid_similarity_count": result["valid_similarity_count"],
        "invalid_similarity_count": result["invalid_similarity_count"],
        "cache_hit": result["cache_hit"],
        "options_seconds": round(options_seconds, 3),
        "preflight_seconds": round(time.perf_counter() - began, 3),
    }
    state["phases"]["preflight"] = {
        "status": "PASS" if result["similarity_currentness"] == "CURRENT" else "BLOCKED",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    save(scratch, state)
    prior._log(f"exact recorded-context preflight: {result['similarity_currentness']} "
               f"selected={result['selected_count']}")


def _recorded_scenario_20() -> dict:
    payload = json.loads(RECORDED_SCENARIOS.read_text(encoding="utf-8"))
    scenario = next(item for item in payload["scenarios"] if item["id"] == 20)
    if scenario["match_strength"] != "VERY_STRONG":
        raise RuntimeError("Recorded scenario 20 threshold changed.")
    return scenario


def _scenario_criteria(scenario: dict) -> dict:
    return {name: scenario[name] for name in (
        "genders", "age_groups", "states", "income_groups", "marital_statuses",
        "education_levels", "employment_statuses", "resident_statuses",
        "resident_types", "employment_types", "family_member_count_min",
        "family_member_count_max",
    )}


def scenario_preflight(scratch: Path, state: dict) -> None:
    if state["phases"].get("verify", {}).get("status") != "PASS_THREE_PRODUCT_CONTEXT":
        raise RuntimeError("Certify the exact three-product context before a scenario probe.")
    db = scratch / "certification.db"
    scenario = _recorded_scenario_20()
    options = submission.search_form_options(db)
    started = time.perf_counter()
    response = exact_similarity_preflight(
        db, context=state["recorded_common_context"],
        criteria=_scenario_criteria(scenario), similarity_minimum=.90,
        selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=scratch,
    )
    state["scenario_20_preflight"] = {
        "scenario_id": 20, "scenario_name": scenario["name"],
        "recorded_threshold": "VERY_STRONG", "similarity_minimum": .90,
        "readiness": response["similarity_currentness"],
        "selected_count": response["selected_count"],
        "demographic_eligible_count": response["demographic_eligible_count"],
        "catalog_version": options["catalog_version"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "cache_hit": response["cache_hit"],
    }
    save(scratch, state)
    if response["similarity_currentness"] != "CURRENT":
        raise RuntimeError("Recorded scenario 20 is not current.")
    prior._log(f"recorded scenario 20 preflight selected={response['selected_count']}")


def scenario_search(scratch: Path, state: dict) -> None:
    prior_count = state.get("scenario_20_preflight", {}).get("selected_count")
    if prior_count is None:
        raise RuntimeError("Run the recorded scenario's exact preflight first.")
    db = scratch / "certification.db"
    scenario = _recorded_scenario_20()
    options = submission.search_form_options(db)
    if options["catalog_version"] != state["scenario_20_preflight"]["catalog_version"]:
        raise RuntimeError("The scenario catalog changed after exact preflight.")
    email = next((item for item in options["profiles"]
                  if item["channel_code"] == "EMAIL" and item["availability"] == "AVAILABLE"), None)
    if email is None:
        raise RuntimeError("The recorded EMAIL export profile is not available.")
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.90, campaign_name="14B16 S20 full-5M certification",
        context=state["recorded_common_context"], criteria=_scenario_criteria(scenario),
        selection_mode="ALL_MATCHING", export_profile=email["export_profile"],
        catalog_version=options["catalog_version"],
    )
    repository = CampaignResultRegistryRepository(db)
    if "scenario_20_search_run_id" not in state:
        # This runner owns execution synchronously; submission still uses the
        # normal transactional production API and durable attempt registry.
        submission.PHASE11_SEARCH_EXECUTOR = lambda *_args: True
        created = submission.submit_potential_customer_search(db, request)
        state["scenario_20_search_run_id"] = created["search_run_id"]
        save(scratch, state)
    run_id = int(state["scenario_20_search_run_id"])
    began = time.perf_counter()
    fence = repository.claim_search_attempt(run_id, lease_owner="14b16-s20-certification")
    outcome = execute_similarity_search_safely(
        db, run_id, **fence.as_kwargs(), project_root=scratch,
    )
    if outcome.status != "COMPLETED" or outcome.result_snapshot_id is None:
        state["scenario_20_search"] = {
            "status": outcome.status, "elapsed_seconds": round(time.perf_counter() - began, 3),
        }
        save(scratch, state)
        raise RuntimeError("Recorded scenario 20 did not complete a current snapshot.")
    with get_connection(db) as connection:
        snapshot = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots "
            "WHERE similarity_result_snapshot_id=?", (outcome.result_snapshot_id,),
        ).fetchone()
    if snapshot is None or int(snapshot["resolved_count"]) != int(prior_count):
        raise RuntimeError("Recorded scenario snapshot count differs from exact preflight.")
    state["scenario_20_search"] = {
        "status": outcome.status, "search_run_id": run_id,
        "result_snapshot_id": outcome.result_snapshot_id,
        "result_source": outcome.result_source,
        "resolved_count": snapshot["resolved_count"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "storage_uri": snapshot["storage_uri"],
        "elapsed_seconds": round(time.perf_counter() - began, 3),
    }
    save(scratch, state)
    prior._log(f"recorded scenario 20 snapshot count={snapshot['resolved_count']}")


def scenario_count_benchmark(scratch: Path, state: dict) -> None:
    expected = state.get("scenario_20_preflight", {}).get("selected_count")
    if expected is None:
        raise RuntimeError("Record an exact scenario preflight before the uncached benchmark.")
    db = scratch / "certification.db"
    scenario = _recorded_scenario_20()
    options = submission.search_form_options(db)
    context, criteria, _catalog = submission.normalize_similarity_search_definition(
        db, raw_context=state["recorded_common_context"],
        raw_criteria=_scenario_criteria(scenario), selection_mode="ALL_MATCHING",
        top_n=None, similarity_minimum=.90,
        catalog_version=options["catalog_version"],
    )
    resolution = resolve_similarity_context(db, context, project_root=scratch)
    if not resolution.ready:
        raise RuntimeError("Recorded three-product generation is not current.")
    started = time.perf_counter()
    with get_connection(db) as connection:
        counts = count_similarity_selection(
            connection, list(criteria.audience_filter_branches),
            resolution.generation_ids, .90,
            selection_mode="ALL_MATCHING", top_n=None,
        )
    duration = round(time.perf_counter() - started, 3)
    if counts[4] != expected:
        raise RuntimeError("Optimized uncached count differs from recorded exact preflight.")
    state["scenario_20_uncached_count_benchmark"] = {
        "counts": list(counts), "elapsed_seconds": duration,
        "budget_seconds": prior.BUDGETS_SECONDS["exact_preflight"],
        "status": "PASS" if duration <= prior.BUDGETS_SECONDS["exact_preflight"] else "OVER_BUDGET",
    }
    save(scratch, state)
    prior._log(f"uncached scenario 20 count={counts[4]} in {duration}s")


def scenario_preflight_refresh(scratch: Path, state: dict) -> None:
    original = state.get("scenario_20_preflight")
    if not original or original["readiness"] != "CURRENT":
        raise RuntimeError("The exact recorded scenario preflight must already exist.")
    db = scratch / "certification.db"
    with get_connection(db, write=True) as connection:
        rows = connection.execute(
            "SELECT cache_key_sha256 FROM similarity_preflight_cache "
            "WHERE similarity_minimum=.90 AND selected_count=? "
            "AND currentness_state='CURRENT'",
            (original["selected_count"],),
        ).fetchall()
        if len(rows) != 1:
            raise RuntimeError("The isolated scenario cache target is not unique.")
        connection.execute(
            "DELETE FROM similarity_preflight_cache WHERE cache_key_sha256=?",
            (rows[0]["cache_key_sha256"],),
        )
    state["scenario_20_preflight_before_optimization"] = original
    save(scratch, state)
    scenario_preflight(scratch, state)
    if (state["scenario_20_preflight"]["cache_hit"]
        or state["scenario_20_preflight"]["selected_count"] != original["selected_count"]):
        raise RuntimeError("Fresh optimized scenario preflight was not exact.")


def scenario_reuse_export(scratch: Path, state: dict) -> None:
    original = state.get("scenario_20_search")
    if not original or original.get("status") != "COMPLETED":
        raise RuntimeError("Complete the first recorded scenario snapshot before reuse.")
    db = scratch / "certification.db"
    options = submission.search_form_options(db)
    if options["catalog_version"] != state["scenario_20_preflight"]["catalog_version"]:
        raise RuntimeError("The scenario source catalog changed before reuse.")
    email = next(item for item in options["profiles"]
                 if item["channel_code"] == "EMAIL" and item["availability"] == "AVAILABLE")
    request = PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.90, campaign_name="14B16 S20 full-5M reuse certification",
        context=state["recorded_common_context"],
        criteria=_scenario_criteria(_recorded_scenario_20()),
        selection_mode="ALL_MATCHING", export_profile=email["export_profile"],
        catalog_version=options["catalog_version"],
    )
    repository = CampaignResultRegistryRepository(db)
    if "scenario_20_reuse_run_id" not in state:
        submission.PHASE11_SEARCH_EXECUTOR = lambda *_args: True
        created = submission.submit_potential_customer_search(db, request)
        state["scenario_20_reuse_run_id"] = created["search_run_id"]
        save(scratch, state)
    run_id = int(state["scenario_20_reuse_run_id"])
    started = time.perf_counter()
    fence = repository.claim_search_attempt(run_id, lease_owner="14b16-s20-reuse")
    outcome = execute_similarity_search_safely(
        db, run_id, **fence.as_kwargs(), project_root=scratch,
    )
    reuse_seconds = time.perf_counter() - started
    if (outcome.status != "COMPLETED" or outcome.result_source != "EXACT_RESULT_REUSE"
        or outcome.result_snapshot_id != original["result_snapshot_id"]):
        raise RuntimeError("Identical sequential scenario rebuilt or changed snapshot identity.")
    first_run_id = int(original["search_run_id"])
    started = time.perf_counter()
    history = list_result_history(db, limit=20, project_root=scratch)
    history_seconds = time.perf_counter() - started
    if {first_run_id, run_id} - {int(row["search_run_id"]) for row in history}:
        raise RuntimeError("Completed certification runs are missing from result history.")
    detail = get_result_detail(db, first_run_id, project_root=scratch)
    if (detail["snapshot_provenance"]["currentness"] != "CURRENT"
        or detail["snapshot_provenance"]["resolved_count"] != original["resolved_count"]):
        raise RuntimeError("Recorded immutable result detail is not current.")
    membership = scratch / original["storage_uri"]
    digest = hashlib.sha256()
    with membership.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    with gzip.open(membership, "rt", encoding="utf-8", newline="") as source:
        membership_count = sum(1 for _ in csv.DictReader(source))
    if (digest.hexdigest() != original["snapshot_sha256"]
        or membership_count != original["resolved_count"]):
        raise RuntimeError("Immutable snapshot file hash or member count changed.")

    class Connected:
        async def is_disconnected(self) -> bool:
            return False

    async def consume() -> tuple[float, int, str]:
        started = time.perf_counter()
        response = stream_phase11_result_export_csv(
            db, search_run_id=first_run_id, request=Connected(), project_root=scratch,
        )
        first_byte = None
        size = 0
        export_digest = hashlib.sha256()
        async for chunk in response.body_iterator:
            if first_byte is None:
                first_byte = time.perf_counter() - started
            export_digest.update(chunk)
            size += len(chunk)
        if first_byte is None:
            raise RuntimeError("The streamed contact export produced no bytes.")
        return first_byte, size, export_digest.hexdigest()

    first_byte, export_bytes, export_hash = asyncio.run(consume())
    state["scenario_20_reuse_export"] = {
        "reuse_run_id": run_id,
        "same_snapshot_id": outcome.result_snapshot_id,
        "reuse_seconds": round(reuse_seconds, 3),
        "history_seconds": round(history_seconds, 3),
        "history_run_count": len(history),
        "membership_count": membership_count,
        "membership_sha256_verified": True,
        "export_first_byte_seconds": round(first_byte, 3),
        "export_bytes": export_bytes,
        "export_sha256": export_hash,
    }
    save(scratch, state)
    prior._log(f"scenario 20 exact snapshot reused; export streamed {export_bytes} bytes")


def reconcile_evidence_state(scratch: Path, state: dict) -> None:
    """Correct the inherited V1 runner's obsolete blocked-product label."""

    composite = state.get("complete_context_composite")
    preflight = state.get("recorded_context_preflight")
    if (state["phases"].get("verify", {}).get("status") != "PASS_THREE_PRODUCT_CONTEXT"
        or not composite or not preflight
        or preflight["readiness"] != "CURRENT"
        or preflight["selected_count"] != composite["ge_70"]):
        raise RuntimeError("Completed three-product context is not independently supported.")
    preflight.pop("unsupported_product", None)
    preflight["status"] = "CURRENT"
    save(scratch, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("audit", "import", "profiles", "score", "preflight", "verify", "scenario-preflight", "scenario-preflight-refresh", "scenario-count-benchmark", "scenario-search", "scenario-reuse-export", "reconcile-evidence-state", "crash-worker"),
                        required=True)
    parser.add_argument("--scratch-dir", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--profile-id", type=int)
    args = parser.parse_args()
    scratch = args.scratch_dir.resolve()
    allowed = (prior.ROOT / "output").resolve()
    if not scratch.is_relative_to(allowed) or scratch in {allowed, PRIOR_SCRATCH.resolve()}:
        raise SystemExit("Scratch must be a dedicated output/ child distinct from earlier evidence.")
    scratch.mkdir(parents=True, exist_ok=True)
    if args.phase == "crash-worker":
        if args.profile_id is None:
            raise SystemExit("Controlled child needs --profile-id.")
        crash_worker(scratch, args.profile_id)
        return 1
    path = scratch / "run_manifest.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "runner_version": VERSION, "candidate": "UNCOMMITTED",
        "starting_sha": "336875c30fc32b00323d916ecc45b232016168a1",
        "created_at": prior._now(), "budgets_seconds": prior.BUDGETS_SECONDS, "phases": {},
    }
    if state["runner_version"] != VERSION:
        raise RuntimeError("Scratch manifest belongs to another certification runner.")
    {"audit": audit, "import": import_copy, "profiles": profiles,
     "score": score, "preflight": preflight, "verify": verify,
     "scenario-preflight": scenario_preflight,
     "scenario-preflight-refresh": scenario_preflight_refresh,
     "scenario-count-benchmark": scenario_count_benchmark,
     "scenario-search": scenario_search,
     "scenario-reuse-export": scenario_reuse_export,
     "reconcile-evidence-state": reconcile_evidence_state}[args.phase](scratch, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
