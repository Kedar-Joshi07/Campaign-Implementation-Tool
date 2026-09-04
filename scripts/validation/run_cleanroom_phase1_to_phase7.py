#!/usr/bin/env python3
"""Run bounded clean-room Phase 1 to Phase 7 validation end-to-end."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.jobs.model_training_worker import run_model_training_job
from app.jobs.prospect_scoring_worker import run_prospect_scoring_job
from app.main import app
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION, ORDERED_FEATURES
from app.ml.model_roles import CHALLENGER_1_MODEL_NAME, DIAGNOSTIC_CONTROL_NAME, PRIMARY_MODEL_NAME
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.job_repository import JOB_STAGE_STARTING, JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import get_audience_preparation_status, run_audience_rank_preparation
from app.services.campaign_contracts import DIRECT_MAIL_EXPORT_COLUMNS, EMAIL_EXPORT_COLUMNS, PROHIBITED_EXPORT_FIELDS
from app.services.historical_analysis_service import create_historical_analysis, get_historical_analysis_run, list_historical_analysis_runs
from app.services.model_job_service import STALE_JOB_INTERRUPTION_MESSAGE, reconcile_stale_model_training_jobs, submit_model_training_job_request
from app.services.prospect_scoring_service import (
    verify_scoring_run_sample,
    validate_completed_scoring_run_provenance,
)
from app.services.scoring_job_service import (
    submit_prospect_scoring_job_request,
)
from app.services.saved_audience_service import get_saved_audience_detail, validate_saved_audience_currentness
from app.services.data_import_service import import_campaign_sales, import_customers, import_demographics
from app.services.data_reconciliation_service import run_reconciliation


DEFAULT_CUSTOMERS = 1200
DEFAULT_CAMPAIGN_SALES = 9000
DEFAULT_DEMOGRAPHICS = 12000
DEFAULT_SEED_BASE = 20260902


class CleanRoomValidationError(RuntimeError):
    """Raised when clean-room validation fails."""


@dataclass(frozen=True)
class ValidationConfig:
    customers: int
    campaign_sales: int
    demographics: int
    seed_base: int
    runtime_root: Path
    report_path: Path
    json_path: Path
    keep_runtime: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(stage: str, message: str) -> None:
    print(f"[cleanroom:{stage}] {message}", flush=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CleanRoomValidationError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text_payload(path: Path) -> str:
    lower_name = path.name.lower()
    if lower_name.endswith(".gz"):
        with gzip.open(path, "rb") as handle:
            payload = handle.read()
    else:
        payload = path.read_bytes()
    return _sha256_bytes(payload)


def _run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr_tail = "\n".join((completed.stderr or "").splitlines()[-20:])
        stdout_tail = "\n".join((completed.stdout or "").splitlines()[-20:])
        raise CleanRoomValidationError(
            "Subprocess failed with non-zero exit code.\n"
            f"command={' '.join(command)}\n"
            f"stdout_tail={stdout_tail}\n"
            f"stderr_tail={stderr_tail}"
        )


def _generator_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "customers": run_dir / "customers.csv.gz",
        "customers_summary": run_dir / "customers_summary.json",
        "campaign_sales": run_dir / "campaign_sales.csv.gz",
        "campaign_sales_summary": run_dir / "campaign_sales_summary.json",
        "campaign_master": run_dir / "campaign_master.csv",
        "product_master": run_dir / "product_master.csv",
        "demographics": run_dir / "demographics.csv.gz",
        "demographics_summary": run_dir / "demographics_summary.json",
    }


def _generate_bounded_dataset(*, run_dir: Path, config: ValidationConfig, run_label: str) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)

    customer_seed = config.seed_base + 1
    campaign_seed = config.seed_base + 2
    demographic_seed = config.seed_base + 3

    _log("step1", f"Generating bounded synthetic data ({run_label}).")

    _run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_customer_master.py"),
            "--n-customers",
            str(config.customers),
            "--seed",
            str(customer_seed),
            "--outdir",
            str(run_dir),
            "--output",
            "customers.csv.gz",
            "--sample-output",
            "customers_sample_10000.csv",
            "--summary-output",
            "customers_summary.json",
            "--sample-rows",
            "1000",
        ]
    )

    _run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_campaign_sales.py"),
            "--customer-file",
            str(run_dir / "customers.csv.gz"),
            "--n-rows",
            str(config.campaign_sales),
            "--n-campaigns",
            "24",
            "--seed",
            str(campaign_seed),
            "--outdir",
            str(run_dir),
            "--output",
            "campaign_sales.csv.gz",
            "--sample-output",
            "campaign_sales_sample_10000.csv",
            "--summary-output",
            "campaign_sales_summary.json",
            "--campaign-master-output",
            "campaign_master.csv",
            "--product-master-output",
            "product_master.csv",
            "--sample-rows",
            "1000",
        ]
    )

    env = dict(os.environ)
    env.update(
        {
            "SEED": str(demographic_seed),
            "N_ROWS": str(config.demographics),
            "CHUNK": str(max(1000, min(config.demographics, 4000))),
            "OUTDIR": str(run_dir),
            "OUT_NAME": "demographics.csv.gz",
            "SUMMARY_NAME": "demographics_summary.json",
            "SAMPLE_NAME": "demographics_sample_10000.csv",
        }
    )
    _run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_demographic_synthetic.py"),
        ],
        env=env,
    )

    paths = _generator_paths(run_dir)
    for key in ("customers", "campaign_sales", "demographics", "campaign_master", "product_master"):
        _require(paths[key].is_file(), f"Missing generated file: {paths[key]}")

    content_hashes = {
        "customers": _sha256_text_payload(paths["customers"]),
        "campaign_sales": _sha256_text_payload(paths["campaign_sales"]),
        "demographics": _sha256_text_payload(paths["demographics"]),
        "campaign_master": _sha256_file(paths["campaign_master"]),
        "product_master": _sha256_file(paths["product_master"]),
    }

    return {
        "paths": {key: str(value) for key, value in paths.items()},
        "hashes": content_hashes,
        "seeds": {
            "customers": customer_seed,
            "campaign_sales": campaign_seed,
            "demographics": demographic_seed,
        },
    }


def _dependency_versions() -> dict[str, str | None]:
    package_names = (
        "fastapi",
        "numpy",
        "pandas",
        "scikit-learn",
        "pulearn",
        "joblib",
        "pytest",
    )
    versions: dict[str, str | None] = {}
    for package in package_names:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _stage_step1_environment(config: ValidationConfig) -> dict[str, Any]:
    stage_started = time.perf_counter()
    run_a_dir = config.runtime_root / "generated" / "run_a"
    run_b_dir = config.runtime_root / "generated" / "run_b"

    generated_a = _generate_bounded_dataset(run_dir=run_a_dir, config=config, run_label="run_a")
    generated_b = _generate_bounded_dataset(run_dir=run_b_dir, config=config, run_label="run_b")

    deterministic_checks: dict[str, bool] = {}
    for key, run_a_hash in generated_a["hashes"].items():
        run_b_hash = generated_b["hashes"].get(key)
        deterministic_checks[key] = run_a_hash == run_b_hash

    failed = sorted(key for key, value in deterministic_checks.items() if not value)
    _require(not failed, f"Determinism check failed for files: {', '.join(failed)}")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - stage_started, 3),
        "counts": {
            "customers": config.customers,
            "campaign_sales": config.campaign_sales,
            "demographics": config.demographics,
        },
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "dependency_versions": _dependency_versions(),
        "deterministic_hashes": {
            key: {
                "run_a": generated_a["hashes"][key],
                "run_b": generated_b["hashes"][key],
                "match": deterministic_checks[key],
            }
            for key in sorted(generated_a["hashes"])
        },
        "seeds": generated_a["seeds"],
        "selected_input_files": {
            "customers": generated_a["paths"]["customers"],
            "campaign_sales": generated_a["paths"]["campaign_sales"],
            "demographics": generated_a["paths"]["demographics"],
        },
    }


def _stage_step2_import_reconcile(config: ValidationConfig, stage1: dict[str, Any], database_path: Path) -> dict[str, Any]:
    stage_started = time.perf_counter()

    customer_path = Path(stage1["selected_input_files"]["customers"])
    campaign_path = Path(stage1["selected_input_files"]["campaign_sales"])
    demographic_path = Path(stage1["selected_input_files"]["demographics"])

    initialize_database(database_path)

    customer_result = import_customers(
        customer_path,
        database_path=database_path,
        replace=True,
        batch_size=2000,
        progress_every=0,
    )
    campaign_result = import_campaign_sales(
        campaign_path,
        database_path=database_path,
        replace=True,
        batch_size=2000,
        progress_every=0,
    )
    demographic_result = import_demographics(
        (demographic_path,),
        database_path=database_path,
        replace=True,
        batch_size=2000,
        progress_every=0,
    )

    expected_counts = {
        "customers": {
            "expected_count": config.customers,
            "exact_match_required": True,
            "count_tolerance_percent": None,
        },
        "campaign_sales": {
            "expected_count": config.campaign_sales,
            "exact_match_required": True,
            "count_tolerance_percent": None,
        },
        "demographics": {
            "expected_count": config.demographics,
            "exact_match_required": True,
            "count_tolerance_percent": None,
        },
    }

    reconciliation = run_reconciliation(database_path, expected_counts=expected_counts)
    _require(reconciliation["overall_status"] == "OK", "Reconciliation status is not OK in clean-room run.")

    with get_connection(database_path) as connection:
        overlap_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM customers c
                INNER JOIN demographics d ON d.person_id = c.customer_id
                """
            ).fetchone()[0]
        )
        _require(overlap_count == 0, "customer_id/person_id identity overlap detected.")

        import_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT dataset_name, status, rows_inserted, source_checksum
                FROM data_import_runs
                WHERE status = 'COMPLETED'
                ORDER BY import_id ASC
                """
            ).fetchall()
        ]

    _require(len(import_rows) == 3, "Expected exactly three completed import runs.")

    for row in import_rows:
        checksum = str(row["source_checksum"] or "")
        _require(len(checksum) == 64, f"Invalid source checksum for dataset {row['dataset_name']}.")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - stage_started, 3),
        "imports": {
            "customers": {
                "import_id": customer_result.import_id,
                "rows_inserted": customer_result.rows_inserted,
                "rows_rejected": customer_result.rows_rejected,
            },
            "campaign_sales": {
                "import_id": campaign_result.import_id,
                "rows_inserted": campaign_result.rows_inserted,
                "rows_rejected": campaign_result.rows_rejected,
            },
            "demographics": {
                "import_id": demographic_result.import_id,
                "rows_inserted": demographic_result.rows_inserted,
                "rows_rejected": demographic_result.rows_rejected,
            },
        },
        "identity_isolation": {
            "customer_person_id_overlap_count": overlap_count,
        },
        "reconciliation": reconciliation,
    }


def _poll_job_until_terminal(database_path: Path, *, job_id: int, timeout_seconds: float) -> tuple[list[str], dict[str, Any]]:
    repository = JobRepository(database_path)
    started = time.perf_counter()
    seen_statuses: list[str] = []

    while True:
        row = repository.fetch_job(job_id)
        _require(row is not None, f"Job disappeared during polling: job_id={job_id}")
        status = str(row["status"])
        if not seen_statuses or seen_statuses[-1] != status:
            seen_statuses.append(status)
        if status in {"COMPLETED", "FAILED"}:
            return seen_statuses, row
        if (time.perf_counter() - started) > timeout_seconds:
            raise CleanRoomValidationError(f"Timed out waiting for job {job_id} to complete.")
        time.sleep(0.05)


def _launch_worker_thread(
    worker,
    *,
    database_path: Path,
    job_id: int,
    delay_seconds: float = 0.05,
    worker_cwd: Path | None = None,
) -> threading.Thread:
    def _target() -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        original_cwd = Path.cwd()
        try:
            if worker_cwd is not None:
                os.chdir(worker_cwd)
            worker(database_path, job_id)
        finally:
            os.chdir(original_cwd)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    return thread


def _stage_step3_analysis_train_score(config: ValidationConfig, database_path: Path) -> dict[str, Any]:
    stage_started = time.perf_counter()

    analysis = create_historical_analysis(database_path, {})
    analysis_run_id = int(analysis["analysis_run_id"])
    _require(analysis["status"] == "COMPLETED", "Historical analysis did not complete.")

    summary = analysis["summary"]
    _require(
        int(summary["positive_customer_count"]) + int(summary["unlabeled_customer_count"])
        == int(summary["selected_customer_count"]),
        "Historical analysis P+U consistency failed.",
    )

    reopened = get_historical_analysis_run(database_path, analysis_run_id)
    _require(int(reopened["analysis_run_id"]) == analysis_run_id, "Reopened historical run mismatch.")

    listed = list_historical_analysis_runs(database_path, limit=1, offset=0)
    _require(bool(listed) and int(listed[0]["analysis_run_id"]) == analysis_run_id, "Historical list/reopen mismatch.")

    model_payload = {
        "analysis_run_id": analysis_run_id,
        "model_name": "Clean-room governed model",
        "random_seed": config.seed_base + 10,
        "validation_fraction": 0.25,
        "run_elkan_challenger": True,
    }

    model_thread_holder: dict[str, threading.Thread] = {}

    def _model_submitter(path: str | Path, job_id: int) -> None:
        model_thread_holder["thread"] = _launch_worker_thread(
            run_model_training_job,
            database_path=Path(path),
            job_id=job_id,
            delay_seconds=0.05,
            worker_cwd=config.runtime_root,
        )

    queued_model_job = submit_model_training_job_request(
        database_path,
        model_payload,
        submitter=_model_submitter,
    )
    model_job_id = int(queued_model_job["job_id"])

    model_statuses, model_terminal = _poll_job_until_terminal(
        database_path,
        job_id=model_job_id,
        timeout_seconds=600,
    )
    model_thread = model_thread_holder.get("thread")
    if model_thread is not None:
        model_thread.join()

    _require(model_terminal["status"] == "COMPLETED", "Model training job failed.")
    _require("QUEUED" in model_statuses, "Model job did not enter QUEUED status.")
    _require("RUNNING" in model_statuses, "Model job did not enter RUNNING status.")

    model_run_id = int(model_terminal["model_run_id"])
    model_row = ModelRunRepository(database_path).fetch_run(model_run_id)
    _require(model_row is not None, "Completed model_run row is missing.")
    _require(model_row["status"] == "COMPLETED", "model_runs status is not COMPLETED.")
    _require(model_row["selected_candidate"] == PRIMARY_MODEL_NAME, "Primary governed candidate was not selected.")
    feature_contract_json = str(model_row["feature_contract_json"])
    feature_contract = json.loads(feature_contract_json)
    _require(feature_contract.get("version") == FEATURE_CONTRACT_VERSION, "Feature contract version mismatch.")
    _require(tuple(feature_contract.get("ordered_features") or []) == ORDERED_FEATURES, "Feature contract feature-order mismatch.")
    feature_contract_sha = hashlib.sha256(feature_contract_json.encode("utf-8")).hexdigest()

    model_metrics = json.loads(model_row["metrics_json"])
    _require(model_metrics.get("primary_candidate") == PRIMARY_MODEL_NAME, "Model metrics primary candidate mismatch.")
    _require(model_metrics.get("challenger_candidates") == [CHALLENGER_1_MODEL_NAME], "Missing Elkan challenger metadata.")
    _require(model_metrics.get("diagnostic_controls") == [DIAGNOSTIC_CONTROL_NAME], "Missing Naive diagnostic metadata.")
    candidate_results = model_metrics.get("candidate_results") or {}
    _require(PRIMARY_MODEL_NAME in candidate_results, "Missing Bagging candidate result.")
    _require(CHALLENGER_1_MODEL_NAME in candidate_results, "Missing Elkan candidate result.")
    _require(DIAGNOSTIC_CONTROL_NAME in candidate_results, "Missing Naive diagnostic result.")

    _require(feature_contract_sha == FEATURE_CONTRACT_SHA256, "Feature contract SHA mismatch.")

    artifact_path = config.runtime_root / str(model_row["artifact_path"])
    _require(artifact_path.is_file(), "Model artifact file is missing.")
    _require(_sha256_file(artifact_path) == str(model_row["artifact_sha256"]), "Model artifact SHA mismatch.")

    scoring_thread_holder: dict[str, threading.Thread] = {}

    def _scoring_submitter(path: str | Path, job_id: int) -> None:
        scoring_thread_holder["thread"] = _launch_worker_thread(
            run_prospect_scoring_job,
            database_path=Path(path),
            job_id=job_id,
            delay_seconds=0.05,
            worker_cwd=config.runtime_root,
        )

    original_cwd = Path.cwd()
    try:
        os.chdir(config.runtime_root)
        queued_scoring_job = submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": model_run_id},
            submitter=_scoring_submitter,
        )
        scoring_job_id = int(queued_scoring_job["job_id"])

        scoring_statuses, scoring_terminal = _poll_job_until_terminal(
            database_path,
            job_id=scoring_job_id,
            timeout_seconds=600,
        )
        scoring_thread = scoring_thread_holder.get("thread")
        if scoring_thread is not None:
            scoring_thread.join()
    finally:
        os.chdir(original_cwd)

    _require(scoring_terminal["status"] == "COMPLETED", "Prospect scoring job failed.")
    _require("QUEUED" in scoring_statuses, "Scoring job did not enter QUEUED status.")
    _require("RUNNING" in scoring_statuses, "Scoring job did not enter RUNNING status.")

    scoring_result_payload = json.loads(scoring_terminal["result_json"])
    scoring_run_id = int(scoring_result_payload["scoring_run_id"])

    with get_connection(database_path) as connection:
        aggregate = connection.execute(
            """
            SELECT
                COUNT(*) AS score_count,
                COUNT(DISTINCT person_id) AS distinct_person_count,
                MIN(propensity_score) AS score_min,
                MAX(propensity_score) AS score_max,
                SUM(CASE WHEN propensity_score < 0 OR propensity_score > 1 THEN 1 ELSE 0 END) AS out_of_range_count
            FROM propensity_scores
            WHERE scoring_run_id = ?
            """,
            (scoring_run_id,),
        ).fetchone()
        scored_person_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])

    _require(int(aggregate["score_count"]) == scored_person_count, "Scored row count mismatch vs demographics count.")
    _require(int(aggregate["distinct_person_count"]) == int(aggregate["score_count"]), "Duplicate scores detected for person_id.")
    _require(int(aggregate["out_of_range_count"]) == 0, "Found scores outside [0,1].")

    provenance = validate_completed_scoring_run_provenance(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(provenance["is_canonical"]), "Completed scoring provenance is not canonical.")

    sample_size = max(32, min(128, scored_person_count))
    verification = verify_scoring_run_sample(
        database_path,
        scoring_run_id=scoring_run_id,
        sample_size=sample_size,
        project_root=config.runtime_root,
    )
    _require(bool(verification["verified"]), "Deterministic sample re-score verification failed.")

    stale_job_repository = JobRepository(database_path)
    stale_job_id = stale_job_repository.create_scoring_job(
        created_at=_now_iso(),
        request_payload={"model_run_id": model_run_id},
    )
    stale_job_repository.mark_running(
        job_id=stale_job_id,
        started_at=_now_iso(),
        stage=JOB_STAGE_STARTING,
        progress_percent=2,
        message="stale-fixture",
    )

    with get_connection(database_path) as connection:
        person_bounds = connection.execute(
            "SELECT MIN(person_id), MAX(person_id), COUNT(*) FROM demographics"
        ).fetchone()

    stale_scoring_run_id = ScoringRepository(database_path).create_scoring_run(
        job_id=stale_job_id,
        model_run_id=model_run_id,
        created_at=_now_iso(),
        demographic_snapshot_count=int(person_bounds[2]),
        demographic_min_person_id=str(person_bounds[0]),
        demographic_max_person_id=str(person_bounds[1]),
        chunk_size=1000,
        selected_candidate=str(model_row["selected_candidate"]),
        model_role_policy_version=str(model_metrics.get("model_role_policy_version") or "2"),
        feature_contract_version=str(feature_contract.get("version") or FEATURE_CONTRACT_VERSION),
        feature_contract_sha256=feature_contract_sha,
        artifact_sha256=str(model_row["artifact_sha256"]),
    )

    stale_failed_count = reconcile_stale_model_training_jobs(database_path)
    stale_job_row = stale_job_repository.fetch_job(stale_job_id)
    _require(stale_job_row is not None, "Stale job disappeared after reconciliation.")
    _require(stale_job_row["status"] == "FAILED", "Stale job was not failed by reconciliation.")
    _require(str(stale_job_row.get("error_message") or "") == STALE_JOB_INTERRUPTION_MESSAGE, "Stale job message mismatch.")

    stale_scoring_row = ScoringRepository(database_path).fetch_scoring_run(stale_scoring_run_id)
    _require(stale_scoring_row is not None, "Stale scoring run disappeared after reconciliation.")
    _require(stale_scoring_row["status"] == "FAILED", "Running scoring row was not failed by reconciliation.")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - stage_started, 3),
        "analysis_run_id": analysis_run_id,
        "model_job": {
            "job_id": model_job_id,
            "status_sequence": model_statuses,
            "model_run_id": model_run_id,
        },
        "model_contract": {
            "selected_candidate": str(model_row["selected_candidate"]),
            "feature_contract_version": str(feature_contract.get("version")),
            "feature_contract_sha256": feature_contract_sha,
            "artifact_sha256": str(model_row["artifact_sha256"]),
        },
        "scoring_job": {
            "job_id": scoring_job_id,
            "status_sequence": scoring_statuses,
            "scoring_run_id": scoring_run_id,
        },
        "scoring_integrity": {
            "score_count": int(aggregate["score_count"]),
            "distinct_person_count": int(aggregate["distinct_person_count"]),
            "score_min": float(aggregate["score_min"]),
            "score_max": float(aggregate["score_max"]),
            "provenance": provenance,
            "deterministic_sample": verification,
        },
        "stale_recovery": {
            "stale_jobs_failed_count": stale_failed_count,
            "stale_job_id": stale_job_id,
            "stale_scoring_run_id": stale_scoring_run_id,
        },
    }


def _json_response(response) -> dict[str, Any] | list[Any]:
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover
        raise CleanRoomValidationError("Expected JSON response payload.") from exc


def _assert_status(response, expected: int, context: str) -> None:
    if response.status_code != expected:
        raise CleanRoomValidationError(
            f"{context} returned status {response.status_code}, expected {expected}. body={response.text[:500]}"
        )


def _pick_option(options_payload: dict[str, Any], field_name: str) -> str | None:
    values = options_payload.get("categorical_options", {}).get(field_name) or []
    for item in values:
        if isinstance(item, dict) and int(item.get("count") or 0) > 0:
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value
    return None


def _top_person_ids(database_path: Path, *, scoring_run_id: int, limit: int = 20) -> list[str]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT person_id
            FROM propensity_scores
            WHERE scoring_run_id = ?
            ORDER BY propensity_score DESC, person_id ASC
            LIMIT ?
            """,
            (scoring_run_id, limit),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _assert_sorted(rows: list[dict[str, Any]]) -> None:
    previous: tuple[float, str] | None = None
    for row in rows:
        current = (float(row["propensity_score"]), str(row["person_id"]))
        if previous is not None:
            _require(current[0] <= previous[0], "Search ordering violated: score is not DESC.")
            if current[0] == previous[0]:
                _require(current[1] > previous[1], "Search ordering violated: person_id tie-break is not ASC.")
        previous = current


def _stage_step4_audience_validation(database_path: Path, scoring_run_id: int) -> tuple[dict[str, Any], int]:
    stage_started = time.perf_counter()

    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    prep_status = get_audience_preparation_status(database_path, scoring_run_id=scoring_run_id)

    _require(bool(prep_status["prepared"]), "Audience rank boundaries are not prepared.")
    _require(bool(prep_status["analytics_prepared"]), "Audience analytics snapshot is not prepared.")
    _require(int(prep_status["boundary_count"]) == 100, "Boundary count must equal 100.")
    _require(bool(prep_status["ready_for_current_audience_actions"]), "Audience is not ready for current actions.")

    boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    _require(len(boundaries) == 100, "Expected 100 boundaries.")
    total_population = int(prep_status["total_population"])
    _require(int(boundaries[-1]["boundary_rank"]) == total_population, "Boundary rank at 100th percentile mismatch.")

    family_checks: dict[str, int] = {}
    invalid_cases: dict[str, int] = {}
    unknown_other_case: dict[str, Any] = {}

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            options_response = client.get("/api/audience/options", params={"scoring_run_id": scoring_run_id})
            _assert_status(options_response, 200, "Audience filter options")
            options_payload = _json_response(options_response)
            assert isinstance(options_payload, dict)

            numeric_ranges = options_payload.get("numeric_ranges") or {}
            score_summary = options_payload.get("score_summary") or {}

            gender_value = _pick_option(options_payload, "gender")
            state_value = _pick_option(options_payload, "state")
            marital_value = _pick_option(options_payload, "marital_status")
            education_value = _pick_option(options_payload, "education")
            employment_value = _pick_option(options_payload, "employment_status")
            resident_status_value = _pick_option(options_payload, "resident_status")
            resident_type_value = _pick_option(options_payload, "resident_type")
            employment_type_value = _pick_option(options_payload, "type_of_employment")

            valid_family_payloads = {
                "score": {"score_min": float(score_summary["score_min"]), "score_max": float(score_summary["score_max"])},
                "age": {"age_min": max(18, int(numeric_ranges["age"]["min"])), "age_max": int(numeric_ranges["age"]["max"])},
                "income": {
                    "individual_yearly_income_min": float(numeric_ranges["individual_yearly_income"]["min"]),
                    "individual_yearly_income_max": float(numeric_ranges["individual_yearly_income"]["max"]),
                },
                "family": {
                    "family_member_count_min": max(1, int(numeric_ranges["family_member_count"]["min"])),
                    "family_member_count_max": int(numeric_ranges["family_member_count"]["max"]),
                },
                "percentile": {"top_percentile_max": 10},
                "decile": {"deciles": [1, 2]},
                "band": {"rank_bands": ["ELITE", "HIGH"]},
                "gender": {"gender": [gender_value]} if gender_value else {},
                "state": {"state": [state_value]} if state_value else {},
                "marital": {"marital_status": [marital_value]} if marital_value else {},
                "education": {"education": [education_value]} if education_value else {},
                "employment": {"employment_status": [employment_value]} if employment_value else {},
                "resident_status": {"resident_status": [resident_status_value]} if resident_status_value else {},
                "resident_type": {"resident_type": [resident_type_value]} if resident_type_value else {},
                "employment_type": {"type_of_employment": [employment_type_value]} if employment_type_value else {},
            }

            for family_name, filters in valid_family_payloads.items():
                if not filters:
                    continue
                response = client.post(
                    "/api/audience/estimate",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": filters,
                        "selection": {"mode": "ALL_MATCHING"},
                    },
                )
                _assert_status(response, 200, f"Audience estimate valid filter family {family_name}")
                payload = _json_response(response)
                assert isinstance(payload, dict)
                family_checks[family_name] = int(payload["matching_count"])

            min_gt_max = client.post(
                "/api/audience/estimate",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {"age_min": 70, "age_max": 50},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            invalid_cases["age_min_gt_max"] = min_gt_max.status_code
            _require(min_gt_max.status_code == 422, "Expected 422 for age_min > age_max.")

            invalid_categorical = client.post(
                "/api/audience/estimate",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {"state": ["__INVALID_STATE__"]},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            invalid_cases["unsupported_state"] = invalid_categorical.status_code
            _require(invalid_categorical.status_code == 422, "Expected 422 for unsupported categorical value.")

            invalid_decile = client.post(
                "/api/audience/estimate",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {"deciles": [11]},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            invalid_cases["invalid_decile"] = invalid_decile.status_code
            _require(invalid_decile.status_code == 422, "Expected 422 for invalid decile value.")

            unknown_available_field: str | None = None
            for candidate in (
                "gender",
                "state",
                "marital_status",
                "education",
                "employment_status",
                "resident_status",
                "resident_type",
                "type_of_employment",
            ):
                values = options_payload.get("categorical_options", {}).get(candidate) or []
                if any((item.get("value") == "Unknown/Other") for item in values if isinstance(item, dict)):
                    unknown_available_field = candidate
                    break

            if unknown_available_field is not None:
                unknown_response = client.post(
                    "/api/audience/estimate",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": {unknown_available_field: ["Unknown/Other"]},
                        "selection": {"mode": "ALL_MATCHING"},
                    },
                )
                _assert_status(unknown_response, 200, "Unknown/Other filter case")
                unknown_payload = _json_response(unknown_response)
                assert isinstance(unknown_payload, dict)
                unknown_other_case = {
                    "field": unknown_available_field,
                    "mode": "supported_value",
                    "status_code": unknown_response.status_code,
                    "matching_count": int(unknown_payload["matching_count"]),
                }
            else:
                unknown_response = client.post(
                    "/api/audience/estimate",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": {"state": ["Unknown/Other"]},
                        "selection": {"mode": "ALL_MATCHING"},
                    },
                )
                unknown_other_case = {
                    "field": "state",
                    "mode": "unsupported_value",
                    "status_code": unknown_response.status_code,
                }
                _require(unknown_response.status_code == 422, "Expected 422 for unsupported Unknown/Other state value.")

            first_page = client.post(
                "/api/audience/search",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "page_size": 40,
                },
            )
            _assert_status(first_page, 200, "Audience search page 1")
            first_payload = _json_response(first_page)
            assert isinstance(first_payload, dict)
            rows = list(first_payload["rows"])
            _assert_sorted(rows)

            seen_ids: set[str] = {str(row["person_id"]) for row in rows}
            page_count = 1
            cursor = first_payload.get("next_cursor")
            has_more = bool(first_payload.get("has_more"))

            while has_more and cursor and page_count < 5:
                next_response = client.post(
                    "/api/audience/search",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": {},
                        "page_size": 40,
                        "cursor": cursor,
                    },
                )
                _assert_status(next_response, 200, f"Audience search page {page_count + 1}")
                next_payload = _json_response(next_response)
                assert isinstance(next_payload, dict)
                page_rows = list(next_payload["rows"])
                _assert_sorted(page_rows)
                for row in page_rows:
                    person_id = str(row["person_id"])
                    _require(person_id not in seen_ids, "Duplicate person_id detected across keyset pages.")
                    seen_ids.add(person_id)
                cursor = next_payload.get("next_cursor")
                has_more = bool(next_payload.get("has_more"))
                page_count += 1

            if first_payload.get("next_cursor"):
                mismatch = client.post(
                    "/api/audience/search",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": {"top_percentile_max": 10},
                        "page_size": 40,
                        "cursor": first_payload["next_cursor"],
                    },
                )
                _require(mismatch.status_code == 409, "Expected cursor mismatch to return 409.")

            profile_all = client.post(
                "/api/audience/profile",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            _assert_status(profile_all, 200, "Audience profile ALL_MATCHING")
            profile_all_payload = _json_response(profile_all)
            assert isinstance(profile_all_payload, dict)

            profile_topn = client.post(
                "/api/audience/profile",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": min(250, total_population)},
                },
            )
            _assert_status(profile_topn, 200, "Audience profile TOP_N")
            profile_topn_payload = _json_response(profile_topn)
            assert isinstance(profile_topn_payload, dict)

            _require("historical_positives" in profile_all_payload["summary"], "Profile missing historical_positives comparison group.")
            _require(
                int(profile_topn_payload["summary"]["selected"]["count"]) == min(250, total_population),
                "TOP_N profile selected count mismatch.",
            )

            for forbidden in (
                "first_name",
                "last_name",
                "email",
                "address_line_1",
                "address_line_2",
                "postal_code",
                "customer_id",
            ):
                _require(forbidden not in profile_all.text, f"PII field leaked in audience profile payload: {forbidden}")

            save_response = client.post(
                "/api/audiences",
                json={
                    "audience_name": "Clean-room Audience",
                    "description": "Step 4 immutable audience",
                    "scoring_run_id": scoring_run_id,
                    "filters": {"top_percentile_max": 20},
                    "selection": {"mode": "TOP_N", "target_count": min(300, total_population)},
                    "include_profile_snapshot": True,
                },
            )
            _assert_status(save_response, 201, "Save audience")
            saved = _json_response(save_response)
            assert isinstance(saved, dict)
            saved_audience_id = int(saved["audience_id"])

            detail = get_saved_audience_detail(database_path, audience_id=saved_audience_id)
            _require(int(detail["audience_id"]) == saved_audience_id, "Saved audience reopen mismatch.")
            currentness = validate_saved_audience_currentness(database_path, audience_id=saved_audience_id)
            _require(bool(currentness["is_current"]), "Saved audience is unexpectedly stale.")
    finally:
        app.dependency_overrides.clear()

    return (
        {
            "status": "PASS",
            "duration_seconds": round(time.perf_counter() - stage_started, 3),
            "preparation_status": prep_status,
            "filter_family_checks": family_checks,
            "invalid_cases": invalid_cases,
            "unknown_other_case": unknown_other_case,
            "keyset_pagination": {
                "checked_pages": page_count,
                "unique_person_count_seen": len(seen_ids),
            },
            "saved_audience_id": saved_audience_id,
        },
        saved_audience_id,
    )


def _csv_stats(csv_bytes: bytes) -> dict[str, Any]:
    csv_text = csv_bytes.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text, newline="")))
    ordered_ids = [str(row.get("person_id") or "") for row in rows]
    order_hash = hashlib.sha256("\n".join(ordered_ids).encode("utf-8")).hexdigest()
    return {
        "row_count": len(rows),
        "headers": list(rows[0].keys()) if rows else [],
        "order_hash": order_hash,
        "rows": rows,
        "csv_sha256": _sha256_bytes(csv_bytes),
    }


def _latest_export_event(client: TestClient, campaign_id: int) -> dict[str, Any]:
    response = client.get(f"/api/campaigns/{campaign_id}/exports", params={"limit": 20})
    _assert_status(response, 200, "List campaign export events")
    payload = _json_response(response)
    _require(isinstance(payload, list) and bool(payload), "Missing export event payload.")
    latest = payload[0]
    _require(isinstance(latest, dict), "Invalid export event item.")
    return latest


def _stage_step5_campaign_export(
    config: ValidationConfig,
    database_path: Path,
    *,
    scoring_run_id: int,
    step4_saved_audience_id: int,
) -> dict[str, Any]:
    stage_started = time.perf_counter()

    top_ids = _top_person_ids(database_path, scoring_run_id=scoring_run_id, limit=16)
    _require(len(top_ids) >= 12, "Expected at least 12 scored IDs for export hardening checks.")

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE demographics SET first_name = '=Alice' WHERE person_id = ?",
            (top_ids[0],),
        )
        connection.execute(
            "UPDATE demographics SET first_name = '+Bob' WHERE person_id = ?",
            (top_ids[1],),
        )
        connection.execute(
            "UPDATE demographics SET first_name = '-Carla' WHERE person_id = ?",
            (top_ids[2],),
        )
        connection.execute(
            "UPDATE demographics SET first_name = '@Dina' WHERE person_id = ?",
            (top_ids[3],),
        )
        connection.execute(
            "UPDATE demographics SET email = '' WHERE person_id = ?",
            (top_ids[4],),
        )
        connection.execute(
            "UPDATE demographics SET email = 'not-an-email' WHERE person_id = ?",
            (top_ids[5],),
        )
        connection.execute(
            "UPDATE demographics SET address_line_1 = '' WHERE person_id = ?",
            (top_ids[6],),
        )
        connection.execute(
            "UPDATE demographics SET city = '' WHERE person_id = ?",
            (top_ids[7],),
        )
        connection.execute(
            "UPDATE demographics SET postal_code = '' WHERE person_id = ?",
            (top_ids[8],),
        )
        connection.execute(
            "UPDATE demographics SET first_name = 'Comma,Name' WHERE person_id = ?",
            (top_ids[9],),
        )
        connection.execute(
            'UPDATE demographics SET last_name = "Quote ""Name""" WHERE person_id = ?',
            (top_ids[10],),
        )
        connection.execute(
            "UPDATE demographics SET first_name = 'Line\nBreak' WHERE person_id = ?",
            (top_ids[11],),
        )
        if len(top_ids) >= 13:
            connection.execute(
                "UPDATE demographics SET first_name = 'Unicode Ångstrom' WHERE person_id = ?",
                (top_ids[12],),
            )

    campaign_results: dict[str, Any] = {}

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            save_email = client.post(
                "/api/audiences",
                json={
                    "audience_name": "Clean-room Email Audience",
                    "description": "Step 5 email audience",
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": 60},
                    "include_profile_snapshot": True,
                },
            )
            _assert_status(save_email, 201, "Save email audience")
            email_audience = _json_response(save_email)
            assert isinstance(email_audience, dict)

            save_mail = client.post(
                "/api/audiences",
                json={
                    "audience_name": "Clean-room Direct Mail Audience",
                    "description": "Step 5 direct-mail audience",
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": 60},
                    "include_profile_snapshot": True,
                },
            )
            _assert_status(save_mail, 201, "Save direct-mail audience")
            direct_mail_audience = _json_response(save_mail)
            assert isinstance(direct_mail_audience, dict)

            for channel, expected_headers, audience_id in (
                ("EMAIL", list(EMAIL_EXPORT_COLUMNS), int(email_audience["audience_id"])),
                ("DIRECT_MAIL", list(DIRECT_MAIL_EXPORT_COLUMNS), int(direct_mail_audience["audience_id"])),
            ):
                create = client.post(
                    "/api/campaigns",
                    json={
                        "campaign_name": f"Clean-room {channel} campaign",
                        "description": "Phase 7 clean-room campaign",
                        "channel": channel,
                        "planned_launch_date": "2026-12-01",
                        "saved_audience_id": audience_id,
                    },
                )
                _assert_status(create, 201, f"Create campaign {channel}")
                created = _json_response(create)
                assert isinstance(created, dict)
                campaign_id = int(created["campaign_id"])

                patch = client.patch(
                    f"/api/campaigns/{campaign_id}",
                    json={"description": f"Updated {channel} draft"},
                )
                _assert_status(patch, 200, f"Patch campaign {channel} while DRAFT")

                finalize = client.post(f"/api/campaigns/{campaign_id}/finalize")
                _assert_status(finalize, 200, f"Finalize campaign {channel}")
                finalize_again = client.post(f"/api/campaigns/{campaign_id}/finalize")
                _require(finalize_again.status_code == 409, "Expected 409 when finalizing an already FINALIZED campaign.")

                patch_after_finalize = client.patch(
                    f"/api/campaigns/{campaign_id}",
                    json={"description": "Should fail"},
                )
                _require(patch_after_finalize.status_code == 409, "Expected FINALIZED campaign immutability on PATCH.")

                currentness = client.get(f"/api/campaigns/{campaign_id}/currentness")
                _assert_status(currentness, 200, f"Campaign currentness {channel}")
                currentness_payload = _json_response(currentness)
                assert isinstance(currentness_payload, dict)
                _require(bool(currentness_payload["is_current"]), "Campaign currentness unexpectedly stale.")

                no_ack = client.get(f"/api/campaigns/{campaign_id}/export.csv")
                _require(no_ack.status_code == 422, "Expected 422 export rejection without acknowledge_pii=true.")

                export_run_payloads: list[dict[str, Any]] = []
                for run_index in (1, 2):
                    response = client.get(
                        f"/api/campaigns/{campaign_id}/export.csv",
                        params={"acknowledge_pii": "true"},
                    )
                    _assert_status(response, 200, f"Export campaign {channel} run {run_index}")
                    csv_stats = _csv_stats(response.content)
                    _require(csv_stats["headers"] == expected_headers, f"Header mismatch for {channel} export.")

                    forbidden = sorted(set(csv_stats["headers"]) & set(PROHIBITED_EXPORT_FIELDS))
                    _require(not forbidden, f"Forbidden fields in {channel} export: {forbidden}")

                    event = _latest_export_event(client, campaign_id)
                    _require(event["status"] == "COMPLETED", "Export event status is not COMPLETED.")
                    _require(
                        int(event["selected_count"]) == int(event["deliverable_count"]) + int(event["undeliverable_count"]),
                        "selected_count reconciliation failed for export event.",
                    )
                    _require(
                        int(event["row_count"]) == int(event["deliverable_count"]),
                        "row_count must equal deliverable_count.",
                    )
                    _require(int(event["row_count"]) == int(csv_stats["row_count"]), "CSV row count mismatch vs event row_count.")

                    for row in csv_stats["rows"]:
                        _require(not str(row.get("person_id") or "").startswith("CUS"), "customer_id style identifier leaked in export.")

                    export_run_payloads.append(
                        {
                            "run": run_index,
                            "event": event,
                            "csv": {
                                "row_count": csv_stats["row_count"],
                                "order_hash": csv_stats["order_hash"],
                                "csv_sha256": csv_stats["csv_sha256"],
                            },
                            "rows": csv_stats["rows"],
                        }
                    )

                run1 = export_run_payloads[0]
                run2 = export_run_payloads[1]
                _require(run1["csv"]["order_hash"] == run2["csv"]["order_hash"], "Deterministic member order mismatch across repeated exports.")
                _require(run1["csv"]["csv_sha256"] == run2["csv"]["csv_sha256"], "Deterministic CSV checksum mismatch across repeated exports.")

                all_rows = run1["rows"]
                dangerous_prefix_hits = {
                    "equals": any(str(row.get("first_name") or "").startswith("'=") for row in all_rows),
                    "plus": any(str(row.get("first_name") or "").startswith("'+") for row in all_rows),
                    "minus": any(str(row.get("first_name") or "").startswith("'-") for row in all_rows),
                    "at": any(str(row.get("first_name") or "").startswith("'@") for row in all_rows),
                }
                _require(all(dangerous_prefix_hits.values()), f"CSV formula hardening failed for one or more prefixes in {channel} export.")

                special_char_checks = {
                    "contains_comma": any("," in str(row.get("first_name") or "") or "," in str(row.get("last_name") or "") for row in all_rows),
                    "contains_quote": any('"' in str(row.get("first_name") or "") or '"' in str(row.get("last_name") or "") for row in all_rows),
                    "contains_newline": any("\n" in str(row.get("first_name") or "") or "\n" in str(row.get("last_name") or "") for row in all_rows),
                    "contains_unicode": any("̊" in str(row.get("first_name") or "") for row in all_rows),
                }
                _require(all(special_char_checks.values()), f"Special-character CSV cases were not preserved for {channel} export.")

                campaign_results[channel] = {
                    "campaign_id": campaign_id,
                    "saved_audience_id": audience_id,
                    "runs": [
                        {
                            "run": item["run"],
                            "selected_count": int(item["event"]["selected_count"]),
                            "deliverable_count": int(item["event"]["deliverable_count"]),
                            "undeliverable_count": int(item["event"]["undeliverable_count"]),
                            "row_count": int(item["event"]["row_count"]),
                            "csv_sha256": str(item["event"]["csv_sha256"]),
                            "order_hash": str(item["csv"]["order_hash"]),
                        }
                        for item in export_run_payloads
                    ],
                    "dangerous_prefix_hits": dangerous_prefix_hits,
                    "special_char_checks": special_char_checks,
                }

            drift_db = config.runtime_root / "drift_copy.db"
            shutil.copy2(database_path, drift_db)
            initialize_database(drift_db)
            with get_connection(drift_db, write=True) as drift_connection:
                drift_connection.execute(
                    """
                    INSERT INTO data_import_runs (
                        dataset_name,
                        source_path,
                        started_at,
                        completed_at,
                        status,
                        rows_read,
                        rows_inserted,
                        rows_rejected,
                        source_checksum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "demographics",
                        "cleanroom_drift_demographics.csv.gz",
                        _now_iso(),
                        _now_iso(),
                        "COMPLETED",
                        config.demographics,
                        config.demographics,
                        0,
                        "f" * 64,
                    ),
                )

            app.dependency_overrides[get_database_path] = lambda: drift_db
            with TestClient(app) as drift_client:
                email_campaign_id = int(campaign_results["EMAIL"]["campaign_id"])
                drift_currentness = drift_client.get(f"/api/campaigns/{email_campaign_id}/currentness")
                _assert_status(drift_currentness, 200, "Currentness after source drift")
                currentness_payload = _json_response(drift_currentness)
                assert isinstance(currentness_payload, dict)
                _require(not bool(currentness_payload["is_current"]), "Expected stale currentness after simulated source drift.")

                blocked_export = drift_client.get(
                    f"/api/campaigns/{email_campaign_id}/export.csv",
                    params={"acknowledge_pii": "true"},
                )
                _require(blocked_export.status_code == 409, "Expected export block (409) after simulated source drift.")
                source_drift = {
                    "campaign_id": email_campaign_id,
                    "currentness_after_drift": currentness_payload,
                    "blocked_export_status": blocked_export.status_code,
                    "blocked_export_detail": blocked_export.json().get("detail"),
                }
    finally:
        app.dependency_overrides.clear()

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - stage_started, 3),
        "step4_saved_audience_id": step4_saved_audience_id,
        "campaigns": campaign_results,
        "source_drift": source_drift,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _build_markdown_report(payload: dict[str, Any]) -> str:
    status = str(payload.get("overall_status"))
    generated_at = str(payload.get("generated_at"))
    runtime_root = str(payload.get("runtime_root"))
    stages = payload.get("stages", {})

    lines: list[str] = []
    lines.append("# Clean-Room Phase 1 to Phase 7 Report")
    lines.append("")
    lines.append(f"Status: {status}")
    lines.append(f"Generated at: {generated_at}")
    lines.append(f"Runtime root: {runtime_root}")
    lines.append("")

    for key in ("step1", "step2", "step3", "step4", "step5", "cleanup"):
        stage_payload = stages.get(key)
        if not isinstance(stage_payload, dict):
            continue
        lines.append(f"## {key.upper()}")
        lines.append(f"- status: {stage_payload.get('status', 'UNKNOWN')}")
        if "duration_seconds" in stage_payload:
            lines.append(f"- duration_seconds: {stage_payload['duration_seconds']}")
        if key == "step1":
            counts = stage_payload.get("counts", {})
            lines.append(
                f"- bounded_counts: customers={counts.get('customers')}, campaign_sales={counts.get('campaign_sales')}, demographics={counts.get('demographics')}"
            )
        if key == "step3":
            model_job = stage_payload.get("model_job", {})
            scoring_job = stage_payload.get("scoring_job", {})
            lines.append(
                f"- model_job: id={model_job.get('job_id')} statuses={model_job.get('status_sequence')}"
            )
            lines.append(
                f"- scoring_job: id={scoring_job.get('job_id')} statuses={scoring_job.get('status_sequence')}"
            )
        if key == "step4":
            lines.append(f"- saved_audience_id: {stage_payload.get('saved_audience_id')}")
        if key == "step5":
            campaigns = stage_payload.get("campaigns", {})
            for channel in ("EMAIL", "DIRECT_MAIL"):
                channel_payload = campaigns.get(channel)
                if isinstance(channel_payload, dict):
                    run = channel_payload.get("runs", [{}])[0]
                    lines.append(
                        f"- {channel.lower()}_campaign_id={channel_payload.get('campaign_id')} selected={run.get('selected_count')} deliverable={run.get('deliverable_count')} undeliverable={run.get('undeliverable_count')}"
                    )
        if key == "cleanup":
            lines.append(f"- runtime_removed: {stage_payload.get('runtime_removed')}")
        lines.append("")

    if status != "PASS":
        lines.append("## Failure")
        lines.append(f"- message: {payload.get('failure_message', 'Unknown failure')}")

    return "\n".join(lines).rstrip() + "\n"


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_build_markdown_report(payload), encoding="utf-8")


def run_cleanroom_validation(config: ValidationConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "overall_status": "RUNNING",
        "runtime_root": str(config.runtime_root),
        "stages": {},
    }

    database_path = config.runtime_root / "cleanroom.db"
    config.runtime_root.mkdir(parents=True, exist_ok=True)

    try:
        _log("step1", "Starting isolated environment and deterministic generation checks.")
        payload["stages"]["step1"] = _stage_step1_environment(config)

        _log("step2", "Importing generated data through official importers and running reconciliation.")
        payload["stages"]["step2"] = _stage_step2_import_reconcile(
            config,
            payload["stages"]["step1"],
            database_path,
        )

        _log("step3", "Running historical analysis, model training, scoring, and stale-job recovery checks.")
        step3 = _stage_step3_analysis_train_score(config, database_path)
        payload["stages"]["step3"] = step3
        scoring_run_id = int(step3["scoring_job"]["scoring_run_id"])

        _log("step4", "Validating audience explorer contracts, filters, keyset pagination, and saved audience currentness.")
        step4, saved_audience_id = _stage_step4_audience_validation(database_path, scoring_run_id)
        payload["stages"]["step4"] = step4

        _log("step5", "Validating campaign workflow, deterministic exports, CSV safety, and source-drift behavior.")
        payload["stages"]["step5"] = _stage_step5_campaign_export(
            config,
            database_path,
            scoring_run_id=scoring_run_id,
            step4_saved_audience_id=saved_audience_id,
        )

        payload["overall_status"] = "PASS"
    except Exception as exc:
        payload["overall_status"] = "FAIL"
        payload["failure_message"] = str(exc)

    cleanup_stage: dict[str, Any] = {"status": "SKIPPED", "runtime_removed": False}
    if payload["overall_status"] == "PASS" and not config.keep_runtime:
        shutil.rmtree(config.runtime_root, ignore_errors=True)
        cleanup_stage = {"status": "PASS", "runtime_removed": True}
    elif payload["overall_status"] == "PASS":
        cleanup_stage = {"status": "PASS", "runtime_removed": False}
    else:
        cleanup_stage = {"status": "SKIPPED", "runtime_removed": False}

    payload["stages"]["cleanup"] = cleanup_stage
    payload["completed_at"] = _now_iso()

    _write_json(config.json_path, payload)
    _write_markdown(config.report_path, payload)
    return payload


def _default_runtime_root() -> Path:
    root = PROJECT_ROOT / "artifacts" / "cleanroom-runtime"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="phase1-7-", dir=str(root)))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded clean-room Phase 1-7 validation.")
    parser.add_argument("--customers", type=int, default=DEFAULT_CUSTOMERS)
    parser.add_argument("--campaign-sales", type=int, default=DEFAULT_CAMPAIGN_SALES)
    parser.add_argument("--demographics", type=int, default=DEFAULT_DEMOGRAPHICS)
    parser.add_argument("--seed-base", type=int, default=DEFAULT_SEED_BASE)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help="Optional runtime root directory. Defaults to a temporary folder under artifacts/cleanroom-runtime/.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evidence" / "CLEANROOM_PHASE1_TO_PHASE7_REPORT.md",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evidence" / "cleanroom_phase1_to_phase7.json",
    )
    parser.add_argument("--keep-runtime", action="store_true")
    return parser.parse_args(argv)


def _validated_positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CleanRoomValidationError(f"{field_name} must be a positive integer.")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        customers = _validated_positive_int(args.customers, field_name="customers")
        campaign_sales = _validated_positive_int(args.campaign_sales, field_name="campaign_sales")
        demographics = _validated_positive_int(args.demographics, field_name="demographics")
        seed_base = int(args.seed_base)
        runtime_root = args.runtime_root.resolve() if args.runtime_root else _default_runtime_root()

        config = ValidationConfig(
            customers=customers,
            campaign_sales=campaign_sales,
            demographics=demographics,
            seed_base=seed_base,
            runtime_root=runtime_root,
            report_path=args.report_path.resolve(),
            json_path=args.json_path.resolve(),
            keep_runtime=bool(args.keep_runtime),
        )

        payload = run_cleanroom_validation(config)
        if payload["overall_status"] != "PASS":
            _log("fail", str(payload.get("failure_message") or "Clean-room validation failed."))
            return 1

        _log("pass", "Clean-room Phase 1 to Phase 7 validation completed successfully.")
        _log("pass", f"Report written to: {config.report_path}")
        _log("pass", f"JSON evidence written to: {config.json_path}")
        return 0
    except Exception as exc:
        _log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
