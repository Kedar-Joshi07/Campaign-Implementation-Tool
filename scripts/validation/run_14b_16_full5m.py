"""Stage 16 full-population certification on an isolated, resumable SQLite DB.

Run phases in order: audit, import, profiles, score, verify, preflight. The operator's
canonical database is never opened for writing or copied by this runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import get_connection  # noqa: E402
from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database  # noqa: E402
from app.repositories.buyer_similarity_profile_repository import (  # noqa: E402
    publish_buyer_similarity_profile,
)
from app.services.buyer_similarity_cohort_service import (  # noqa: E402
    build_product_buyer_cohorts,
)
from app.services.buyer_similarity_profile_service import (  # noqa: E402
    fit_buyer_similarity_profile, load_profile_artifact,
    score_buyer_similarity_record,
)
from app.services.buyer_similarity_scoring_service import (  # noqa: E402
    has_current_similarity_attestation,
    run_similarity_generation,
)
from app.services.data_import_service import (  # noqa: E402
    import_campaign_sales,
    import_customers,
    import_demographics,
)
from app.ml.feature_contract import NUMERIC_FEATURES, ORDERED_FEATURES  # noqa: E402
from app.services.buyer_similarity_preflight_service import (  # noqa: E402
    exact_similarity_preflight,
)
from app.services import potential_customer_search_submission_service as submission  # noqa: E402

RUNNER_VERSION = "14B_16_FULL5M_V1"
INPUTS = (
    ("customers", "customer_master_125000.csv.gz", 125_000),
    ("campaign_sales", "campaign_sales_570000.csv.gz", 570_000),
    ("demographics", "usa_demographic_synthetic_5000000_rows.csv.gz", 5_000_000),
)
COMMON_CONTEXT_MANIFEST = (
    ROOT / "output" / "demo_preload" / "demo_20_scenario_checkpoint.json"
)
DEFAULT_SCRATCH = ROOT / "output" / "lookalike_stage16_full5m"
WINDOW_START = "2024-01-01"
WINDOW_END = "2025-12-31"
CHUNK_SIZE = 25_000
MIN_FREE_DISK_BYTES = 35 * 1024**3
MIN_AVAILABLE_MEMORY_BYTES = 2 * 1024**3

# Hardware-specific engineering budgets declared before the measured run.
# Exceeding one is reported, never silently relaxed after seeing a result.
BUDGETS_SECONDS = {
    "source_audit": 600,
    "fresh_import": 3600,
    "cohort_and_profiles": 1800,
    "score_one_product": 5400,
    "deep_verify_one_product": 1200,
    "warm_generation_reuse": 10,
    "exact_preflight": 180,
    "result_materialization": 600,
    "history_projection": 2,
    "export_first_byte": 10,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(message: str) -> None:
    print(f"[14B16 {_now()}] {message}", flush=True)


def _manifest_path(scratch: Path) -> Path:
    return scratch / "run_manifest.json"


def _read_manifest(scratch: Path) -> dict[str, Any]:
    path = _manifest_path(scratch)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("runner_version") != RUNNER_VERSION:
            raise RuntimeError("Scratch manifest belongs to another runner version.")
        return payload
    return {
        "runner_version": RUNNER_VERSION,
        "starting_sha": "336875c30fc32b00323d916ecc45b232016168a1",
        "candidate": "UNCOMMITTED",
        "created_at": _now(),
        "budgets_seconds": BUDGETS_SECONDS,
        "phases": {},
    }


def _save_manifest(scratch: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = _now()
    path = _manifest_path(scratch)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _resources(scratch: Path) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(scratch))
    return {
        "utc": _now(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "memory_total_bytes": memory.total,
        "memory_available_bytes": memory.available,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
    }


def _require_capacity(scratch: Path) -> None:
    status = _resources(scratch)
    if status["disk_free_bytes"] < MIN_FREE_DISK_BYTES:
        raise RuntimeError("Disposable full-scale run requires at least 35 GiB free.")
    if status["memory_available_bytes"] < MIN_AVAILABLE_MEMORY_BYTES:
        raise RuntimeError("Disposable full-scale run requires at least 2 GiB available RAM.")


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size < 1_000:
        raise RuntimeError(f"Canonical input is missing or an LFS pointer: {path.name}")
    raw_digest = hashlib.sha256()
    import_digest = hashlib.sha256()
    import_digest.update(path.name.encode("utf-8"))
    import_digest.update(b"\0")
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            raw_digest.update(block)
            import_digest.update(block)
    import_digest.update(b"\0")
    import gzip

    payload_digest = hashlib.sha256()
    newline_count = 0
    last_byte = b""
    with gzip.open(path, "rb") as handle:
        header = handle.readline()
        payload_digest.update(header)
        newline_count += header.count(b"\n")
        last_byte = header[-1:]
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            payload_digest.update(block)
            newline_count += block.count(b"\n")
            last_byte = block[-1:]
    if last_byte != b"\n":
        newline_count += 1
    if not header or b"," not in header:
        raise RuntimeError(f"Canonical input is not a CSV gzip: {path.name}")
    return {
        "filename": path.name,
        "compressed_bytes": path.stat().st_size,
        "compressed_sha256": raw_digest.hexdigest(),
        "payload_sha256": payload_digest.hexdigest(),
        "import_source_checksum": import_digest.hexdigest(),
        "data_line_count": newline_count - 1,
        "count_method": "streamed LF-delimited generator CSV; header excluded",
        "header_column_count": len(header.rstrip(b"\r\n").split(b",")),
    }


def _common_context() -> dict[str, Any]:
    if not COMMON_CONTEXT_MANIFEST.is_file():
        raise RuntimeError("Recorded common scenario context manifest is missing.")
    payload = json.loads(COMMON_CONTEXT_MANIFEST.read_text(encoding="utf-8"))
    context = payload.get("common_context")
    if not isinstance(context, dict) or context.get("product_ids") != [
        "PRD001", "PRD003", "PRD004"
    ]:
        raise RuntimeError("Recorded common context differs from the audited manifest.")
    return context


def audit(scratch: Path, state: dict[str, Any]) -> None:
    _require_capacity(scratch)
    started = time.perf_counter()
    identities = {}
    for name, filename, expected in INPUTS:
        _log(f"streaming source identity for {name}")
        identity = _file_identity(ROOT / "data" / filename)
        if identity["data_line_count"] != expected:
            raise RuntimeError(f"Canonical {name} line count is not {expected}.")
        identities[name] = identity
    state["inputs"] = identities
    state["recorded_common_context"] = _common_context()
    state["recorded_context_manifest"] = str(COMMON_CONTEXT_MANIFEST.relative_to(ROOT))
    state["initial_resources"] = _resources(scratch)
    state["phases"]["audit"] = {
        "status": "PASS", "elapsed_seconds": round(time.perf_counter() - started, 3)
    }
    _save_manifest(scratch, state)


def _latest_import(db: Path, dataset: str) -> dict[str, Any] | None:
    with get_connection(db) as connection:
        row = connection.execute(
            "SELECT import_id,rows_read,rows_inserted,rows_rejected,source_checksum "
            "FROM data_import_runs WHERE dataset_name=? AND status='COMPLETED' "
            "ORDER BY import_id DESC LIMIT 1",
            (dataset,),
        ).fetchone()
    return dict(row) if row is not None else None


def import_full(scratch: Path, state: dict[str, Any]) -> None:
    if state["phases"].get("audit", {}).get("status") != "PASS":
        raise RuntimeError("Run the source audit phase first.")
    _require_capacity(scratch)
    db = scratch / "certification.db"
    started = time.perf_counter()
    initialize_database(db)
    with get_connection(db) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0]
    if int(version) != CURRENT_SCHEMA_VERSION:
        raise RuntimeError("Disposable database was not migrated to current schema.")
    (scratch / "data").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "data" / "product_master.csv", scratch / "data" / "product_master.csv")
    calls = {
        "customers": lambda p: import_customers(p, database_path=db, replace=True, batch_size=20_000),
        "campaign_sales": lambda p: import_campaign_sales(p, database_path=db, replace=True, batch_size=20_000),
        "demographics": lambda p: import_demographics((p,), database_path=db, replace=True, batch_size=20_000),
    }
    for name, filename, expected in INPUTS:
        existing = _latest_import(db, name)
        with get_connection(db) as connection:
            actual_count = int(connection.execute(
                f"SELECT COUNT(*) FROM {name}"
            ).fetchone()[0])
        expected_checksum = state["inputs"][name]["import_source_checksum"]
        if existing and actual_count == expected and existing["source_checksum"] == expected_checksum:
            _log(f"reusing verified disposable import {name}: {actual_count}")
            continue
        if actual_count:
            raise RuntimeError(f"Partial or mismatched {name} import needs explicit inspection.")
        _log(f"importing {name}: {expected} canonical source rows")
        result = calls[name](ROOT / "data" / filename)
        if result.status != "COMPLETED" or result.rows_inserted != expected or result.rows_rejected:
            raise RuntimeError(f"Disposable {name} import did not match canonical source count.")
        stored = _latest_import(db, name)
        if stored is None or stored["source_checksum"] != expected_checksum:
            raise RuntimeError(f"Disposable {name} import source checksum mismatch.")
        state.setdefault("imports", {})[name] = {
            "import_id": stored["import_id"], "rows_read": result.rows_read,
            "rows_inserted": result.rows_inserted, "rows_rejected": result.rows_rejected,
            "source_checksum": stored["source_checksum"],
            "elapsed_seconds": round(result.duration_seconds, 3),
        }
        _save_manifest(scratch, state)
        _log(f"import complete for {name}: {result.rows_inserted} rows")
    state["schema_version"] = CURRENT_SCHEMA_VERSION
    state["phases"]["import"] = {
        "status": "PASS", "elapsed_seconds": round(time.perf_counter() - started, 3),
        "db_bytes": db.stat().st_size, "resources_after": _resources(scratch),
    }
    _save_manifest(scratch, state)


def profiles(scratch: Path, state: dict[str, Any]) -> None:
    if state["phases"].get("import", {}).get("status") != "PASS":
        raise RuntimeError("Finish the full canonical import first.")
    _require_capacity(scratch)
    db = scratch / "certification.db"
    context = state["recorded_common_context"]
    started = time.perf_counter()
    cohort = build_product_buyer_cohorts(
        db, product_ids=context["product_ids"], window_start=WINDOW_START,
        window_end=WINDOW_END, campaign_types=context["campaign_types"],
        campaign_categories=context["campaign_categories"],
        offer_types=context["offer_types"],
        historical_campaign_channels=context["historical_campaign_channels"],
        demographic_reference_date=WINDOW_END,
        product_catalog_path=scratch / "data" / "product_master.csv",
    )
    support = [asdict(item) for item in cohort.manifest.product_support]
    state["product_support"] = support
    state["common_context_status"] = (
        "READY" if all(item["status"] == "ELIGIBLE" for item in support)
        else "BLOCKED_INSUFFICIENT_SPLIT_SUPPORT"
    )
    state["cohort_lineage"] = {
        "union_buyer_count": cohort.manifest.union_buyer_count,
        "union_fit_count": cohort.manifest.union_fit_count,
        "union_holdout_count": cohort.manifest.union_holdout_count,
        "source_identity": asdict(cohort.manifest.source_identity),
    }
    for item in support:
        if item["status"] != "ELIGIBLE":
            _log(f"{item['product_id']} is blocked: {item['reason_code']}")
            continue
        product = item["product_id"]
        fit_start = time.perf_counter()
        profile = fit_buyer_similarity_profile(cohort, product_id=product)
        published = publish_buyer_similarity_profile(
            db, profile, project_root=scratch,
            execution_owner=f"stage16-{product}", execution_token=secrets.token_hex(32),
            now=_now(),
        )
        state.setdefault("profiles", {})[product] = {
            "profile_id": published.profile_id,
            "fit_publish_seconds": round(time.perf_counter() - fit_start, 3),
        }
        _save_manifest(scratch, state)
        _log(f"published supported exact profile {product}")
    state["phases"]["profiles"] = {
        "status": "PASS_WITH_BLOCKED_COMMON_CONTEXT"
        if state["common_context_status"] != "READY" else "PASS",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "resources_after": _resources(scratch),
    }
    _save_manifest(scratch, state)


def _crash_worker(scratch: Path, profile_id: int) -> None:
    def crash_at_checkpoint(stage: str, processed: int, _total: int, _message: str) -> None:
        if stage == "SCORING_PROSPECTS" and processed >= CHUNK_SIZE:
            os._exit(77)

    run_similarity_generation(
        scratch / "certification.db", profile_id, project_root=scratch,
        execution_owner="stage16-interrupted-worker", execution_token=secrets.token_hex(32),
        chunk_size=CHUNK_SIZE, progress_callback=crash_at_checkpoint,
    )
    raise RuntimeError("Controlled crash checkpoint was not reached.")


def score(scratch: Path, state: dict[str, Any]) -> None:
    if state["phases"].get("profiles", {}).get("status") not in {
        "PASS", "PASS_WITH_BLOCKED_COMMON_CONTEXT"
    }:
        raise RuntimeError("Finish supported profile publication first.")
    _require_capacity(scratch)
    db = scratch / "certification.db"
    eligible = [item["product_id"] for item in state["product_support"] if item["status"] == "ELIGIBLE"]
    for index, product in enumerate(eligible):
        profile_id = int(state["profiles"][product]["profile_id"])
        if product in state.get("scores", {}) and has_current_similarity_attestation(
            db, int(state["scores"][product]["generation_id"]), project_root=scratch
        ):
            _log(f"reusing previously verified full generation for {product}")
            continue
        interrupted_rows = 0
        interrupt_seconds = 0.0
        if index == 0 and "restart" not in state:
            _log(f"starting controlled one-chunk process interruption for {product}")
            start = time.perf_counter()
            child = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--phase", "crash-worker",
                 "--scratch-dir", str(scratch), "--profile-id", str(profile_id)],
                cwd=ROOT, capture_output=True, text=True, timeout=900, check=False,
            )
            interrupt_seconds = time.perf_counter() - start
            if child.returncode != 77:
                raise RuntimeError("Controlled scoring process did not stop at the checkpoint.")
            with get_connection(db) as connection:
                row = connection.execute(
                    "SELECT similarity_generation_id,publication_state FROM buyer_similarity_score_generations "
                    "WHERE profile_id=? ORDER BY similarity_generation_id DESC LIMIT 1",
                    (profile_id,),
                ).fetchone()
                if row is None or row["publication_state"] == "PUBLISHED":
                    raise RuntimeError("Interrupted scoring falsely published a generation.")
                interrupted_rows = int(connection.execute(
                    "SELECT COUNT(*) FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
                    (row["similarity_generation_id"],),
                ).fetchone()[0])
            if interrupted_rows != CHUNK_SIZE:
                raise RuntimeError("Controlled restart checkpoint row count is incorrect.")
            state["restart"] = {
                "product_id": product, "generation_id": row["similarity_generation_id"],
                "checkpoint_rows": interrupted_rows,
                "interrupt_seconds": round(interrupt_seconds, 3),
                "published_before_restart": False,
            }
            _save_manifest(scratch, state)
        start = time.perf_counter()
        last_report = 0

        def progress(stage: str, processed: int, total: int, _message: str) -> None:
            nonlocal last_report
            if stage in {"DEEP_VERIFY", "PUBLISH"} or processed - last_report >= 250_000:
                _log(f"{product} {stage}: {processed}/{total}")
                last_report = processed

        result = run_similarity_generation(
            db, profile_id, project_root=scratch,
            execution_owner=f"stage16-{product}-scorer", execution_token=secrets.token_hex(32),
            chunk_size=CHUNK_SIZE,
            stale_before=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            if index == 0 else None,
            progress_callback=progress,
        )
        elapsed = time.perf_counter() - start
        generation_id = int(result["similarity_generation_id"])
        if not has_current_similarity_attestation(db, generation_id, project_root=scratch):
            raise RuntimeError(f"Full generation for {product} lacks current attestation.")
        if index == 0 and generation_id != state["restart"]["generation_id"]:
            raise RuntimeError("Restart did not retain the exact generation identity.")
        state.setdefault("scores", {})[product] = {
            "generation_id": generation_id,
            "published_person_count": result["published_person_count"],
            "elapsed_seconds": round(elapsed, 3),
            "restarted_from_stale_lease": bool(result.get("restarted_from_stale_lease")),
            "deep_verification_run": bool(result.get("deep_verification_run")),
            "db_bytes": db.stat().st_size,
            "wal_bytes": db.with_name(db.name + "-wal").stat().st_size
            if db.with_name(db.name + "-wal").exists() else 0,
            "resources_after": _resources(scratch),
        }
        _save_manifest(scratch, state)
        _log(f"verified {product} full population: {result['published_person_count']}")
    state["phases"]["score"] = {"status": "PASS", "completed_at": _now()}
    _save_manifest(scratch, state)


def _readonly(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sample_scalar_checks(connection: sqlite3.Connection, scratch: Path,
                          product: str, generation_id: int, profile_id: int) -> dict[str, Any]:
    profile = connection.execute(
        """SELECT p.product_id,a.storage_uri,a.artifact_sha256
           FROM buyer_similarity_profiles p JOIN buyer_similarity_profile_artifacts a
             ON a.profile_id=p.profile_id AND a.artifact_state='PUBLISHED'
           WHERE p.profile_id=?""", (profile_id,),
    ).fetchone()
    if profile is None or profile["product_id"] != product:
        raise RuntimeError("Published profile artifact is missing or misbound.")
    artifact = load_profile_artifact(
        project_root=scratch, storage_uri=profile["storage_uri"],
        expected_artifact_sha256=profile["artifact_sha256"],
        expected_product_id=product,
    )
    positions = [1, 250_000, 500_000, 750_000, 1_000_000, 1_500_000,
                 2_000_000, 2_500_000, 3_000_000, 3_500_000,
                 4_000_000, 4_500_000, 5_000_000]
    checked = 0
    columns = ",".join(ORDERED_FEATURES)
    for position in positions:
        row = connection.execute(
            f"SELECT person_id,{columns} FROM demographics WHERE rowid=?",
            (position,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Deterministic scalar sample is missing a source row.")
        stored = connection.execute(
            """SELECT is_valid,buyer_similarity_score,prototype_key,invalid_reason_code
               FROM buyer_similarity_scores
               WHERE similarity_generation_id=? AND person_id=?""",
            (generation_id, row["person_id"]),
        ).fetchone()
        if stored is None:
            raise RuntimeError("Deterministic scalar sample is missing a score row.")
        calculated = score_buyer_similarity_record(
            {feature: row[feature] for feature in ORDERED_FEATURES}, artifact,
        )
        if bool(stored["is_valid"]) != calculated.is_valid:
            raise RuntimeError("Scalar scorer validity differs from stored score.")
        if calculated.is_valid:
            if not math.isclose(
                float(stored["buyer_similarity_score"]),
                float(calculated.buyer_similarity_score), abs_tol=1e-12,
            ) or stored["prototype_key"] != calculated.prototype_key:
                raise RuntimeError("Scalar scorer differs from stored score/prototype.")
        elif stored["invalid_reason_code"] != calculated.invalid_reason_code:
            raise RuntimeError("Scalar scorer invalidity reason differs from stored score.")
        checked += 1
    return {"positions_checked": checked, "mismatch_count": 0,
            "sample_method": "fixed demographic rowid positions across full imported population"}


def _numeric(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _stream_feature_distributions(connection: sqlite3.Connection) -> dict[str, Any]:
    numeric = {feature: [0.0, 0] for feature in NUMERIC_FEATURES}
    categorical = {feature: Counter() for feature in ORDERED_FEATURES
                   if feature not in NUMERIC_FEATURES}
    columns = ",".join(ORDERED_FEATURES)
    rows = 0
    for row in connection.execute(f"SELECT {columns} FROM demographics ORDER BY person_id"):
        rows += 1
        for feature in NUMERIC_FEATURES:
            value = _numeric(row[feature])
            if value is not None:
                numeric[feature][0] += value
                numeric[feature][1] += 1
        for feature, counts in categorical.items():
            label = str(row[feature]) if row[feature] is not None else "MISSING"
            counts[label] += 1
    return {
        "streamed_rows": rows,
        "numeric": {
            name: {"observed": count, "mean": total / count if count else None}
            for name, (total, count) in numeric.items()
        },
        "categorical": {
            name: {"distinct_values": len(counts), "top_3": counts.most_common(3)}
            for name, counts in categorical.items()
        },
        "interpretation": "descriptive full-prospect features; not purchase-response validation",
    }


def verify(scratch: Path, state: dict[str, Any]) -> None:
    if state["phases"].get("score", {}).get("status") != "PASS":
        raise RuntimeError("Publish all eligible full-population generations first.")
    db = scratch / "certification.db"
    started = time.perf_counter()
    product_results = {}
    with _readonly(db) as connection:
        demographic_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])
        if demographic_count != 5_000_000:
            raise RuntimeError("Disposable demographic population is not five million.")
        for product, score_state in state["scores"].items():
            generation_id = int(score_state["generation_id"])
            profile_id = int(state["profiles"][product]["profile_id"])
            _log(f"independent full-population integrity for {product}")
            began = time.perf_counter()
            generation = connection.execute(
                "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
                (generation_id,),
            ).fetchone()
            attestation = connection.execute(
                "SELECT * FROM buyer_similarity_generation_attestations WHERE similarity_generation_id=?",
                (generation_id,),
            ).fetchone()
            current_import = _latest_import(db, "demographics")
            if (generation is None or attestation is None or
                generation["publication_state"] != "PUBLISHED" or
                attestation["verification_status"] != "VERIFIED" or
                int(generation["expected_person_count"]) != demographic_count or
                int(generation["published_person_count"]) != demographic_count or
                int(attestation["verified_row_count"]) != demographic_count or
                generation["demographic_import_id"] != current_import["import_id"] or
                generation["demographic_source_checksum"] != current_import["source_checksum"]):
                raise RuntimeError(f"{product} publication or current-source lineage is invalid.")
            aggregate = connection.execute(
                """SELECT COUNT(*) row_count,COUNT(DISTINCT person_id) distinct_people,
                          SUM(CASE WHEN is_valid=1 THEN 1 ELSE 0 END) valid_count,
                          SUM(CASE WHEN is_valid=0 THEN 1 ELSE 0 END) invalid_count,
                          SUM(CASE WHEN is_valid=1 AND
                              (buyer_similarity_score<0 OR buyer_similarity_score>1 OR
                               buyer_similarity_score IS NULL OR
                               feature_coverage<0.80 OR feature_coverage>1)
                              THEN 1 ELSE 0 END) invalid_valid_state,
                          MIN(CASE WHEN is_valid=1 THEN buyer_similarity_score END) minimum,
                          MAX(CASE WHEN is_valid=1 THEN buyer_similarity_score END) maximum,
                          SUM(CASE WHEN buyer_similarity_score>=0.50 THEN 1 ELSE 0 END) ge_50,
                          SUM(CASE WHEN buyer_similarity_score>=0.60 THEN 1 ELSE 0 END) ge_60,
                          SUM(CASE WHEN buyer_similarity_score>=0.70 THEN 1 ELSE 0 END) ge_70,
                          SUM(CASE WHEN buyer_similarity_score>=0.80 THEN 1 ELSE 0 END) ge_80,
                          SUM(CASE WHEN buyer_similarity_score>=0.90 THEN 1 ELSE 0 END) ge_90
                   FROM buyer_similarity_scores WHERE similarity_generation_id=?""",
                (generation_id,),
            ).fetchone()
            counts = {key: aggregate[key] for key in aggregate.keys()}
            if (counts["row_count"] != demographic_count or
                counts["distinct_people"] != demographic_count or
                counts["valid_count"] + counts["invalid_count"] != demographic_count or
                counts["invalid_valid_state"] != 0):
                raise RuntimeError(f"{product} score population/state failed independent aggregate.")
            missing = int(connection.execute(
                """SELECT COUNT(*) FROM demographics d WHERE NOT EXISTS
                   (SELECT 1 FROM buyer_similarity_scores s
                    WHERE s.similarity_generation_id=? AND s.person_id=d.person_id)""",
                (generation_id,),
            ).fetchone()[0])
            extra = int(connection.execute(
                """SELECT COUNT(*) FROM buyer_similarity_scores s
                   WHERE s.similarity_generation_id=? AND NOT EXISTS
                   (SELECT 1 FROM demographics d WHERE d.person_id=s.person_id)""",
                (generation_id,),
            ).fetchone()[0])
            if missing or extra:
                raise RuntimeError(f"{product} has missing or extra score identities.")
            tier_rows = connection.execute(
                """SELECT COALESCE(similarity_tier,'INVALID') tier,COUNT(*) total
                   FROM buyer_similarity_scores WHERE similarity_generation_id=?
                   GROUP BY COALESCE(similarity_tier,'INVALID')""",
                (generation_id,),
            ).fetchall()
            valid_count = int(counts["valid_count"])
            quantiles = {}
            for label, fraction in (("p05", .05), ("p25", .25), ("p50", .50),
                                    ("p75", .75), ("p95", .95)):
                if valid_count:
                    offset = min(valid_count - 1, int(fraction * (valid_count - 1)))
                    value = connection.execute(
                        """SELECT buyer_similarity_score FROM buyer_similarity_scores
                           WHERE similarity_generation_id=? AND is_valid=1
                           ORDER BY buyer_similarity_score LIMIT 1 OFFSET ?""",
                        (generation_id, offset),
                    ).fetchone()[0]
                    quantiles[label] = float(value)
                else:
                    quantiles[label] = None
            scalar = _sample_scalar_checks(connection, scratch, product, generation_id, profile_id)
            product_results[product] = {
                "generation_id": generation_id, "profile_id": profile_id,
                "attestation_key_sha256": attestation["attestation_key_sha256"],
                "verified_facts_sha256": attestation["verified_facts_sha256"],
                "population": counts, "missing": missing, "extra": extra,
                "tier_counts": {row["tier"]: row["total"] for row in tier_rows},
                "quantiles": quantiles, "sampled_scalar": scalar,
                "audit_seconds": round(time.perf_counter() - began, 3),
            }
            state["integrity"] = product_results
            _save_manifest(scratch, state)
            _log(f"{product} independent integrity passed")
        state["prospect_features"] = _stream_feature_distributions(connection)
        if state["prospect_features"]["streamed_rows"] != demographic_count:
            raise RuntimeError("Full-prospect feature stream omitted demographic rows.")
        products = sorted(product_results)
        if len(products) == 2:
            first, second = products
            first_id = product_results[first]["generation_id"]
            second_id = product_results[second]["generation_id"]
            composite = connection.execute(
                """SELECT COUNT(*) total,
                          SUM(CASE WHEN a.is_valid=1 OR b.is_valid=1 THEN 1 ELSE 0 END) valid,
                          SUM(CASE WHEN a.is_valid=1 AND
                               (b.is_valid=0 OR a.buyer_similarity_score>=b.buyer_similarity_score)
                               THEN 1 ELSE 0 END) first_wins,
                          SUM(CASE WHEN b.is_valid=1 AND
                               (a.is_valid=0 OR b.buyer_similarity_score>a.buyer_similarity_score)
                               THEN 1 ELSE 0 END) second_wins,
                          SUM(CASE WHEN a.is_valid=1 AND b.is_valid=1 AND
                               a.buyer_similarity_score=b.buyer_similarity_score
                               THEN 1 ELSE 0 END) ties
                   FROM buyer_similarity_scores a
                   JOIN buyer_similarity_scores b ON b.person_id=a.person_id
                   WHERE a.similarity_generation_id=? AND b.similarity_generation_id=?""",
                (first_id, second_id),
            ).fetchone()
            state["supported_subset_composite"] = {
                "products": products, "total": composite["total"],
                "valid": composite["valid"], "winner_counts": {
                    first: composite["first_wins"], second: composite["second_wins"],
                }, "ties_won_by_first_product": composite["ties"],
                "not_the_recorded_three_product_context": True,
            }
            if (composite["total"] != demographic_count or
                composite["first_wins"] + composite["second_wins"] != composite["valid"]):
                raise RuntimeError("Supported-subset composite winner identity is invalid.")
        state["query_plans"] = {
            "score_lookup": [tuple(row) for row in connection.execute(
                """EXPLAIN QUERY PLAN SELECT person_id FROM buyer_similarity_scores
                   WHERE similarity_generation_id=? AND is_valid=1
                     AND buyer_similarity_score>=0.70 ORDER BY person_id""",
                (product_results[products[0]]["generation_id"],),
            )],
            "source_identity_lookup": [tuple(row) for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT person_id FROM demographics WHERE person_id=?",
                ("not-a-real-person",),
            )],
        }
    _log("testing warm generation reuse for each supported profile")
    for product, result in product_results.items():
        start = time.perf_counter()
        reused = run_similarity_generation(
            db, result["profile_id"], project_root=scratch,
            execution_owner=f"stage16-warm-{product}", execution_token=secrets.token_hex(32),
        )
        elapsed = time.perf_counter() - start
        if not reused["reused"] or int(reused["similarity_generation_id"]) != result["generation_id"]:
            raise RuntimeError("Warm reuse rebuilt or switched generation identity.")
        result["warm_reuse_seconds"] = round(elapsed, 3)
        result["warm_reuse_within_declared_budget"] = elapsed <= BUDGETS_SECONDS["warm_generation_reuse"]
    _log("measuring the recorded common-context preflight")
    options_started = time.perf_counter()
    options = submission.search_form_options(db)
    options_elapsed = time.perf_counter() - options_started
    preflight_started = time.perf_counter()
    preflight = exact_similarity_preflight(
        db, context=state["recorded_common_context"], criteria={},
        similarity_minimum=.70, selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=scratch,
    )
    state["recorded_context_preflight"] = {
        "status": preflight.get("status"),
        "readiness": preflight.get("similarity_currentness"),
        "selected_count": preflight.get("selected_count"),
        "options_seconds": round(options_elapsed, 3),
        "preflight_seconds": round(time.perf_counter() - preflight_started, 3),
        "unsupported_product": "PRD001",
    }
    if state["common_context_status"] != "READY" and preflight.get("selected_count") is not None:
        raise RuntimeError("Blocked common context produced a false exact result count.")
    state["phases"]["verify"] = {
        "status": "PASS_SUPPORTED_PRODUCTS_COMMON_CONTEXT_BLOCKED",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "resources_after": _resources(scratch),
    }
    _save_manifest(scratch, state)


def preflight_check(scratch: Path, state: dict[str, Any]) -> None:
    if state.get("phases", {}).get("verify", {}).get("status") != (
        "PASS_SUPPORTED_PRODUCTS_COMMON_CONTEXT_BLOCKED"
    ):
        raise RuntimeError("Complete full-population verification first.")
    db = scratch / "certification.db"
    started = time.perf_counter()
    options = submission.search_form_options(db)
    preflight = exact_similarity_preflight(
        db, context=state["recorded_common_context"], criteria={},
        similarity_minimum=.70, selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=scratch,
    )
    previous = state.get("recorded_context_preflight")
    if previous is not None and "recorded_context_preflight_before_correction" not in state:
        state["recorded_context_preflight_before_correction"] = previous
    state["recorded_context_preflight"] = {
        "readiness": preflight["similarity_currentness"],
        "reason_code": preflight["reason_code"],
        "build_available": preflight["build_available"],
        "selected_count": preflight["selected_count"],
        "preflight_seconds": round(time.perf_counter() - started, 3),
        "recorded_products": list(state["recorded_common_context"]["product_ids"]),
        "unsupported_product": "PRD001",
    }
    if (preflight["reason_code"] != "PROFILE_NOT_ELIGIBLE"
        or preflight["build_available"] is not False
        or preflight["selected_count"] is not None):
        raise RuntimeError("Recorded common context was not safely blocked.")
    state["phases"]["preflight"] = {
        "status": "PASS_EXPECTED_BLOCKED_COMMON_CONTEXT",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "resources_after": _resources(scratch),
    }
    _save_manifest(scratch, state)


def subset_preflight(scratch: Path, state: dict[str, Any]) -> None:
    """Bounded timing probe, explicitly not the recorded common-context gate."""

    if state.get("phases", {}).get("preflight", {}).get("status") != (
        "PASS_EXPECTED_BLOCKED_COMMON_CONTEXT"
    ):
        raise RuntimeError("Complete recorded-context readiness first.")
    started = time.perf_counter()
    try:
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--phase",
             "subset-preflight-worker", "--scratch-dir", str(scratch)],
            cwd=ROOT, capture_output=True, text=True,
            timeout=BUDGETS_SECONDS["exact_preflight"], check=False,
        )
    except subprocess.TimeoutExpired:
        state["supported_subset_preflight"] = {
            "status": "TIMEOUT", "elapsed_seconds": round(time.perf_counter() - started, 3),
            "budget_seconds": BUDGETS_SECONDS["exact_preflight"],
            "not_the_recorded_three_product_context": True,
        }
    else:
        if child.returncode:
            state["supported_subset_preflight"] = {
                "status": "ERROR", "elapsed_seconds": round(time.perf_counter() - started, 3),
                "safe_error_tail": child.stderr[-1000:],
                "not_the_recorded_three_product_context": True,
            }
        else:
            state["supported_subset_preflight"] = json.loads(child.stdout)
            state["supported_subset_preflight"]["status"] = (
                "PASS" if state["supported_subset_preflight"]["readiness"] == "CURRENT"
                else "BLOCKED_EXACT_CONTEXT_IDENTITY"
            )
            state["supported_subset_preflight"]["elapsed_seconds"] = round(
                time.perf_counter() - started, 3
            )
            state["supported_subset_preflight"]["not_the_recorded_three_product_context"] = True
    _save_manifest(scratch, state)


def _subset_preflight_worker(scratch: Path, state: dict[str, Any]) -> None:
    db = scratch / "certification.db"
    options_started = time.perf_counter()
    options = submission.search_form_options(db)
    options_seconds = time.perf_counter() - options_started
    context = {**state["recorded_common_context"], "product_ids": ["PRD003", "PRD004"]}
    count_started = time.perf_counter()
    response = exact_similarity_preflight(
        db, context=context, criteria={}, similarity_minimum=.70,
        selection_mode="ALL_MATCHING", top_n=None,
        catalog_version=options["catalog_version"], project_root=scratch,
    )
    print(json.dumps({
        "products": context["product_ids"], "threshold": .70,
        "options_seconds": round(options_seconds, 3),
        "count_seconds": round(time.perf_counter() - count_started, 3),
        "readiness": response["similarity_currentness"],
        "reason_code": response["reason_code"],
        "selected_count": response["selected_count"],
        "cache_hit": response["cache_hit"],
    }))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("audit", "import", "profiles", "score", "verify", "preflight", "subset-preflight", "subset-preflight-worker", "crash-worker"), required=True)
    parser.add_argument("--scratch-dir", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--profile-id", type=int)
    args = parser.parse_args()
    scratch = args.scratch_dir.resolve()
    allowed = (ROOT / "output").resolve()
    if not scratch.is_relative_to(allowed) or scratch == allowed or scratch == ROOT:
        raise SystemExit("Scratch directory must be a dedicated child of repository output/.")
    scratch.mkdir(parents=True, exist_ok=True)
    if args.phase == "crash-worker":
        if args.profile_id is None:
            raise SystemExit("Controlled worker requires --profile-id.")
        _crash_worker(scratch, args.profile_id)
        return 1
    state = _read_manifest(scratch)
    if args.phase == "subset-preflight-worker":
        _subset_preflight_worker(scratch, state)
        return 0
    phases = {"audit": audit, "import": import_full, "profiles": profiles,
              "score": score, "verify": verify, "preflight": preflight_check,
              "subset-preflight": subset_preflight}
    phases[args.phase](scratch, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
