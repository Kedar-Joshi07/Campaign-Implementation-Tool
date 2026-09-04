#!/usr/bin/env python3
"""Run full-fresh Phase 1 to Phase 7 validation end-to-end."""

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
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection
from app.database.schema import CAMPAIGN_SALES_COLUMNS, CUSTOMER_COLUMNS, DEMOGRAPHIC_COLUMNS, initialize_database
from app.dependencies import get_database_path
from app.jobs.model_training_worker import run_model_training_job
from app.jobs.prospect_scoring_worker import run_prospect_scoring_job
from app.main import app
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION, ORDERED_FEATURES
from app.ml.model_roles import CHALLENGER_1_MODEL_NAME, DIAGNOSTIC_CONTROL_NAME, PRIMARY_MODEL_NAME
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import get_audience_preparation_status, run_audience_rank_preparation
from app.services.campaign_contracts import DIRECT_MAIL_EXPORT_COLUMNS, EMAIL_EXPORT_COLUMNS, PROHIBITED_EXPORT_FIELDS
from app.services.data_import_service import import_campaign_sales, import_customers, import_demographics
from app.services.data_reconciliation_service import run_reconciliation
from app.services.historical_analysis_service import create_historical_analysis, get_historical_analysis_run, list_historical_analysis_runs
from app.services.model_job_service import submit_model_training_job_request
from app.services.prospect_scoring_service import validate_completed_scoring_run_provenance, verify_scoring_run_sample
from app.services.saved_audience_service import get_saved_audience_detail, validate_saved_audience_currentness
from app.services.scoring_job_service import submit_prospect_scoring_job_request


EXPECTED_CUSTOMERS = 125_000
EXPECTED_CAMPAIGN_SALES = 570_000
EXPECTED_DEMOGRAPHICS = 5_000_000

SEED_CUSTOMERS = 20260819
SEED_CAMPAIGN_SALES = 20260820
SEED_DEMOGRAPHICS = 20260818

EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence" / "full_fresh_e2e"
MANIFEST_PATH = EVIDENCE_DIR / "full_fresh_run_manifest.json"
REPORT_PATH = EVIDENCE_DIR / "FULL_FRESH_PHASE1_TO_PHASE7_E2E_REPORT.md"
UI_INVENTORY_PATH = EVIDENCE_DIR / "ui_control_inventory.json"


class FullFreshValidationError(RuntimeError):
    """Raised when full-fresh validation fails."""


@dataclass(frozen=True)
class ValidationConfig:
    customers: int
    campaign_sales: int
    demographics: int
    data_dir: Path
    database_path: Path
    report_path: Path
    manifest_path: Path
    ui_inventory_path: Path
    skip_regression: bool
    keep_generated_runtime: bool
    allow_dirty_worktree: bool


class _ControlInventoryParser(HTMLParser):
    """Collect actionable controls from HTML source."""

    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, Any]] = []
        self._capture_text_for_index: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        tag_lower = tag.lower()
        is_actionable = tag_lower in {"button", "input", "select", "textarea"}
        if not is_actionable and attributes.get("role") not in {"tab", "button", "link"}:
            return

        control_type = tag_lower
        if tag_lower == "input":
            control_type = f"input:{attributes.get('type', 'text')}"

        selector = ""
        if attributes.get("id"):
            selector = f"#{attributes['id']}"
        elif attributes.get("data-view-target"):
            selector = f"[data-view-target='{attributes['data-view-target']}']"
        elif attributes.get("name"):
            selector = f"{tag_lower}[name='{attributes['name']}']"
        elif attributes.get("class"):
            first_class = attributes["class"].split()[0]
            selector = f"{tag_lower}.{first_class}" if first_class else tag_lower
        else:
            selector = tag_lower

        label = attributes.get("aria-label") or attributes.get("title") or ""
        control = {
            "page": attributes.get("data-view") or "global",
            "selector": selector,
            "label": label,
            "type": control_type,
            "expected_behavior": "Actionable control is visible and interactive in its allowed state.",
            "planned_test": "Browser click/type assertion with resulting UI or API state change.",
        }
        self.controls.append(control)

        if tag_lower == "button" and not label:
            self._capture_text_for_index = len(self.controls) - 1

    def handle_data(self, data: str) -> None:
        if self._capture_text_for_index is None:
            return
        text = data.strip()
        if not text:
            return
        current = self.controls[self._capture_text_for_index]
        if not current.get("label"):
            current["label"] = text

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "button":
            self._capture_text_for_index = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(stage: str, message: str) -> None:
    print(f"[fullfresh:{stage}] {message}", flush=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullFreshValidationError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(path: Path) -> str:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as handle:
            payload = handle.read()
    else:
        payload = path.read_bytes()
    return _sha256_bytes(payload)


def _run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    process = subprocess.Popen(
        command,
        cwd=str(cwd or PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    captured_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip(), flush=True)
        captured_lines.append(line.rstrip("\n"))

    returncode = process.wait()
    if returncode != 0:
        output_tail = "\n".join(captured_lines[-40:])
        raise FullFreshValidationError(
            "Subprocess failed with non-zero exit code.\n"
            f"command={' '.join(command)}\n"
            f"output_tail={output_tail}"
        )
    return "\n".join(captured_lines)


def _safe_remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
    return True


def _clear_directory_children(directory: Path, *, preserve_names: set[str] | None = None) -> int:
    if not directory.is_dir():
        return 0
    preserve = preserve_names or set()
    removed = 0
    for child in directory.iterdir():
        if child.name in preserve:
            continue
        if _safe_remove_path(child):
            removed += 1
    return removed


def _git_value(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _existing_data_hashes(config: ValidationConfig) -> dict[str, dict[str, str]]:
    files = {
        "customers": config.data_dir / "customer_master_125000.csv.gz",
        "campaign_sales": config.data_dir / "campaign_sales_570000.csv.gz",
        "demographics": config.data_dir / "usa_demographic_synthetic_5000000_rows.csv.gz",
        "campaign_master": config.data_dir / "campaign_master.csv",
        "product_master": config.data_dir / "product_master.csv",
    }
    hashes: dict[str, dict[str, str]] = {}
    for key, path in files.items():
        if path.is_file():
            hashes[key] = {
                "compressed_sha256": _sha256_file(path),
                "canonical_sha256": _canonical_sha(path),
            }
    return hashes


def _collect_database_snapshot(database_path: Path) -> dict[str, Any]:
    if not database_path.exists():
        return {"database_exists": False}

    counts: dict[str, int] = {}
    tables = [
        "customers",
        "campaign_sales",
        "demographics",
        "historical_analysis_runs",
        "model_runs",
        "scoring_runs",
        "saved_audiences",
        "campaigns",
        "campaign_export_events",
    ]
    with get_connection(database_path) as connection:
        for table in tables:
            row = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if int(row[0]) == 0:
                counts[table] = -1
            else:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return {
        "database_exists": True,
        "size_bytes": database_path.stat().st_size,
        "table_counts": counts,
        "quick_check": "deferred_to_step14",
        "integrity_check": "deferred_to_step14",
    }


def _step1_precheck_and_cleanup(config: ValidationConfig) -> dict[str, Any]:
    started = time.perf_counter()

    git_status = _git_value("status", "--short")
    if git_status.strip() and not config.allow_dirty_worktree:
        raise FullFreshValidationError("Uncommitted changes detected. STOP destructive cleanup.")

    baseline_hashes = _existing_data_hashes(config)
    db_snapshot = _collect_database_snapshot(config.database_path)

    precheck = {
        "timestamp": _now_iso(),
        "git": {
            "branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
            "head": _git_value("rev-parse", "HEAD"),
            "origin_main": _git_value("rev-parse", "origin/main"),
            "status_short": git_status.splitlines(),
            "dirty_override_used": bool(git_status.strip() and config.allow_dirty_worktree),
        },
        "application": {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "app_version": _git_value("show", "-s", "--format=%h %ci %s", "HEAD"),
        },
        "database_snapshot": db_snapshot,
        "accepted_source_hashes": baseline_hashes,
    }

    removed_items: list[str] = []

    runtime_files = [
        config.database_path,
        config.database_path.with_name(config.database_path.name + "-wal"),
        config.database_path.with_name(config.database_path.name + "-shm"),
    ]
    for file_path in runtime_files:
        if _safe_remove_path(file_path):
            removed_items.append(str(file_path.relative_to(PROJECT_ROOT)))

    generated_sources = [
        config.data_dir / "customer_master_125000.csv.gz",
        config.data_dir / "customer_master_sample_10000.csv",
        config.data_dir / "customer_master_summary.json",
        config.data_dir / "campaign_sales_570000.csv.gz",
        config.data_dir / "campaign_sales_sample_10000.csv",
        config.data_dir / "campaign_sales_summary.json",
        config.data_dir / "usa_demographic_synthetic_5000000_rows.csv.gz",
        config.data_dir / "usa_demographic_synthetic_sample_10000.csv",
        config.data_dir / "usa_demographic_synthetic_summary.json",
        config.data_dir / "campaign_master.csv",
        config.data_dir / "product_master.csv",
    ]
    for source_path in generated_sources:
        if _safe_remove_path(source_path):
            removed_items.append(str(source_path.relative_to(PROJECT_ROOT)))

    removable_dirs = [
        PROJECT_ROOT / "output",
        PROJECT_ROOT / "source",
        PROJECT_ROOT / "downloads",
        PROJECT_ROOT / "traces",
        PROJECT_ROOT / "videos",
        PROJECT_ROOT / "playwright-report",
        PROJECT_ROOT / "test-results",
    ]
    for directory in removable_dirs:
        if _safe_remove_path(directory):
            removed_items.append(str(directory.relative_to(PROJECT_ROOT)))

    if _clear_directory_children(PROJECT_ROOT / "logs", preserve_names={".gitkeep"}):
        removed_items.append("logs/*")

    if _clear_directory_children(PROJECT_ROOT / "artifacts" / "models", preserve_names={".gitkeep"}):
        removed_items.append("artifacts/models/*")

    artifacts_dir = PROJECT_ROOT / "artifacts"
    if artifacts_dir.exists():
        for pattern in ("*.db", "*.db-wal", "*.db-shm", "**/*.db", "**/*.db-wal", "**/*.db-shm"):
            for item in artifacts_dir.glob(pattern):
                if _safe_remove_path(item):
                    try:
                        removed_items.append(str(item.relative_to(PROJECT_ROOT)))
                    except ValueError:
                        pass

    post_snapshot = {
        "database_exists": config.database_path.exists(),
        "remaining_generated_sources": [
            str(path.relative_to(PROJECT_ROOT))
            for path in generated_sources
            if path.exists()
        ],
    }
    _require(
        not post_snapshot["database_exists"],
        "Default runtime database still exists after cleanup.",
    )
    _require(
        not post_snapshot["remaining_generated_sources"],
        "Generated source files remain after cleanup.",
    )

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "precheck": precheck,
        "removed_items_count": len(removed_items),
        "removed_items": sorted(set(removed_items)),
        "post_cleanup": post_snapshot,
    }


def _age_on(dob: date, on_date: date) -> int:
    before_birthday = (on_date.month, on_date.day) < (dob.month, dob.day)
    return on_date.year - dob.year - (1 if before_birthday else 0)


def _generate_full_dataset(config: ValidationConfig) -> dict[str, Any]:
    started = time.perf_counter()
    data_dir = config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    _run_command([sys.executable, "-m", "pip", "check"])

    _run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_customer_master.py"),
            "--n-customers",
            str(config.customers),
            "--seed",
            str(SEED_CUSTOMERS),
            "--outdir",
            str(data_dir),
            "--output",
            "customer_master_125000.csv.gz",
            "--sample-output",
            "customer_master_sample_10000.csv",
            "--summary-output",
            "customer_master_summary.json",
            "--sample-rows",
            "10000",
        ]
    )

    _run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_campaign_sales.py"),
            "--customer-file",
            str(data_dir / "customer_master_125000.csv.gz"),
            "--n-rows",
            str(config.campaign_sales),
            "--n-campaigns",
            "96",
            "--seed",
            str(SEED_CAMPAIGN_SALES),
            "--outdir",
            str(data_dir),
            "--output",
            "campaign_sales_570000.csv.gz",
            "--sample-output",
            "campaign_sales_sample_10000.csv",
            "--summary-output",
            "campaign_sales_summary.json",
            "--campaign-master-output",
            "campaign_master.csv",
            "--product-master-output",
            "product_master.csv",
            "--sample-rows",
            "10000",
        ]
    )

    env = dict(os.environ)
    env.update(
        {
            "SEED": str(SEED_DEMOGRAPHICS),
            "N_ROWS": str(config.demographics),
            "CHUNK": "200000",
            "OUTDIR": str(data_dir),
            "OUT_NAME": "usa_demographic_synthetic_5000000_rows.csv.gz",
            "SUMMARY_NAME": "usa_demographic_synthetic_summary.json",
            "SAMPLE_NAME": "usa_demographic_synthetic_sample_10000.csv",
        }
    )
    _run_command(
        [sys.executable, str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_demographic_synthetic.py")],
        env=env,
    )

    customers_path = data_dir / "customer_master_125000.csv.gz"
    campaign_sales_path = data_dir / "campaign_sales_570000.csv.gz"
    demographics_path = data_dir / "usa_demographic_synthetic_5000000_rows.csv.gz"
    campaign_master_path = data_dir / "campaign_master.csv"
    product_master_path = data_dir / "product_master.csv"

    for required in (customers_path, campaign_sales_path, demographics_path, campaign_master_path, product_master_path):
        _require(required.is_file(), f"Missing generated file: {required}")

    customer_dobs: dict[str, date] = {}
    customer_count = 0
    with gzip.open(customers_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        _require(tuple(reader.fieldnames or ()) == CUSTOMER_COLUMNS, "Customer header mismatch.")
        for customer_count, row in enumerate(reader, start=1):
            customer_id = str(row["customer_id"])
            _require(customer_id == f"CUS{customer_count:09d}", "Customer ID sequence mismatch.")
            dob = date.fromisoformat(str(row["date_of_birth"]))
            age = _age_on(dob, date(2025, 12, 31))
            _require(18 <= age <= 100, "Customer age outside 18..100.")
            email = str(row["email"])
            _require(email.endswith("@example.com") or email.endswith("@example.net") or email.endswith("@example.org"), "Customer email domain mismatch.")
            customer_dobs[customer_id] = dob
    _require(customer_count == config.customers, "Customer row count mismatch.")

    campaign_count = 0
    underage_contacts = 0
    pu_consistency_violations = 0
    with gzip.open(campaign_sales_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        _require(tuple(reader.fieldnames or ()) == CAMPAIGN_SALES_COLUMNS, "Campaign sales header mismatch.")
        for campaign_count, row in enumerate(reader, start=1):
            _require(str(row["campaign_sales_id"]) == f"CS{campaign_count:09d}", "Campaign-sales ID sequence mismatch.")
            customer_id = str(row["customer_id"])
            _require(customer_id in customer_dobs, "Campaign-sales customer foreign key mismatch.")
            contact_dt = date.fromisoformat(str(row["contact_date"]))
            if _age_on(customer_dobs[customer_id], contact_dt) < 18:
                underage_contacts += 1

            purchase_flag = int(str(row["purchase_flag"]) or "0")
            attributed_flag = int(str(row["campaign_attributed_sale_flag"]) or "0")
            pu_label = int(str(row["pu_label"]) or "0")
            if (pu_label == 1 and attributed_flag != 1) or (attributed_flag == 1 and purchase_flag != 1):
                pu_consistency_violations += 1
    _require(campaign_count == config.campaign_sales, "Campaign-sales row count mismatch.")
    _require(underage_contacts == 0, "Underage campaign contacts detected.")
    _require(pu_consistency_violations == 0, "PU consistency violations detected.")

    demographic_count = 0
    with gzip.open(demographics_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        _require(tuple(reader.fieldnames or ()) == DEMOGRAPHIC_COLUMNS, "Demographic header mismatch.")
        _require("customer_id" not in (reader.fieldnames or []), "Demographic file unexpectedly contains customer_id.")

        for demographic_count, row in enumerate(reader, start=1):
            _require(str(row["person_id"]) == f"US{demographic_count:09d}", "Demographic person_id sequence mismatch.")
            age_value = int(str(row["age"]))
            _require(18 <= age_value <= 100, "Demographic age outside 18..100.")
            adults = int(str(row["number_of_adults_in_family"]))
            children = int(str(row["number_of_children_in_family"]))
            family_count = int(str(row["family_member_count"]))
            individual_income = float(str(row["individual_yearly_income"]))
            family_income = float(str(row["family_yearly_income"]))
            _require(adults >= 1, "Demographic adults-in-family below 1.")
            _require(children >= 0, "Demographic children-in-family below 0.")
            _require(family_count == adults + children, "Demographic family arithmetic mismatch.")
            _require(individual_income >= 0, "Negative individual income in demographics.")
            _require(family_income >= individual_income, "Family income below individual income.")
    _require(demographic_count == config.demographics, "Demographic row count mismatch.")

    generated_hashes = {
        "customers": {
            "compressed_sha256": _sha256_file(customers_path),
            "canonical_sha256": _canonical_sha(customers_path),
        },
        "campaign_sales": {
            "compressed_sha256": _sha256_file(campaign_sales_path),
            "canonical_sha256": _canonical_sha(campaign_sales_path),
        },
        "demographics": {
            "compressed_sha256": _sha256_file(demographics_path),
            "canonical_sha256": _canonical_sha(demographics_path),
        },
        "campaign_master": {
            "compressed_sha256": _sha256_file(campaign_master_path),
            "canonical_sha256": _canonical_sha(campaign_master_path),
        },
        "product_master": {
            "compressed_sha256": _sha256_file(product_master_path),
            "canonical_sha256": _canonical_sha(product_master_path),
        },
    }

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "seeds": {
            "customers": SEED_CUSTOMERS,
            "campaign_sales": SEED_CAMPAIGN_SALES,
            "demographics": SEED_DEMOGRAPHICS,
        },
        "outputs": {
            "customers": str(customers_path.relative_to(PROJECT_ROOT)),
            "campaign_sales": str(campaign_sales_path.relative_to(PROJECT_ROOT)),
            "demographics": str(demographics_path.relative_to(PROJECT_ROOT)),
            "campaign_master": str(campaign_master_path.relative_to(PROJECT_ROOT)),
            "product_master": str(product_master_path.relative_to(PROJECT_ROOT)),
        },
        "row_counts": {
            "customers": customer_count,
            "campaign_sales": campaign_count,
            "demographics": demographic_count,
        },
        "generated_hashes": generated_hashes,
    }


def _assert_hashes_match_accepted(*, accepted_hashes: dict[str, dict[str, str]], generated_hashes: dict[str, dict[str, str]]) -> dict[str, Any]:
    if not accepted_hashes:
        return {
            "status": "SKIPPED",
            "reason": "No accepted baseline hashes were available during precheck.",
            "mismatches": [],
        }

    canonical_mismatches: list[dict[str, str]] = []
    compressed_mismatches: list[dict[str, str]] = []
    for dataset_name, accepted in accepted_hashes.items():
        produced = generated_hashes.get(dataset_name)
        if produced is None:
            canonical_mismatches.append({"dataset": dataset_name, "reason": "missing_generated_hash"})
            continue

        if accepted.get("canonical_sha256") != produced.get("canonical_sha256"):
            canonical_mismatches.append(
                {
                    "dataset": dataset_name,
                    "hash_type": "canonical_sha256",
                    "accepted": str(accepted.get("canonical_sha256")),
                    "generated": str(produced.get("canonical_sha256")),
                }
            )

        if accepted.get("compressed_sha256") != produced.get("compressed_sha256"):
            compressed_mismatches.append(
                {
                    "dataset": dataset_name,
                    "hash_type": "compressed_sha256",
                    "accepted": str(accepted.get("compressed_sha256")),
                    "generated": str(produced.get("compressed_sha256")),
                }
            )

    _require(not canonical_mismatches, "Generated source canonical hashes drifted from accepted baseline.")
    return {
        "status": "PASS",
        "canonical_mismatches": canonical_mismatches,
        "compressed_mismatches": compressed_mismatches,
        "compressed_mismatch_explanation": (
            "Compressed GZIP bytes can vary due to container metadata while canonical decompressed payload remains identical."
            if compressed_mismatches
            else "none"
        ),
    }


def _step3_import_and_reconcile(config: ValidationConfig) -> dict[str, Any]:
    started = time.perf_counter()

    db_path = initialize_database(config.database_path)
    expected_zero_tables = [
        "customers",
        "campaign_sales",
        "demographics",
        "historical_analysis_runs",
        "model_runs",
        "scoring_runs",
        "saved_audiences",
        "campaigns",
        "campaign_export_events",
    ]
    with get_connection(db_path) as connection:
        for table in expected_zero_tables:
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            _require(count == 0, f"Expected empty table before import: {table}")

    customer_result = import_customers(
        config.data_dir / "customer_master_125000.csv.gz",
        database_path=db_path,
        replace=True,
        batch_size=20_000,
        progress_every=50_000,
    )
    campaign_result = import_campaign_sales(
        config.data_dir / "campaign_sales_570000.csv.gz",
        database_path=db_path,
        replace=True,
        batch_size=20_000,
        progress_every=50_000,
    )
    demographic_result = import_demographics(
        (config.data_dir / "usa_demographic_synthetic_5000000_rows.csv.gz",),
        database_path=db_path,
        replace=True,
        batch_size=20_000,
        progress_every=200_000,
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
    reconciliation = run_reconciliation(db_path, expected_counts=expected_counts)
    _require(reconciliation["overall_status"] == "OK", "Reconciliation failed after full import.")

    with get_connection(db_path) as connection:
        summary_row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM customers) AS customers_count,
                (SELECT COUNT(*) FROM campaign_sales) AS campaign_sales_count,
                (SELECT COUNT(*) FROM demographics) AS demographics_count,
                (SELECT COUNT(*) FROM customers c JOIN demographics d ON d.person_id = c.customer_id) AS overlap_count,
                (SELECT COUNT(*) FROM campaign_sales cs LEFT JOIN customers c ON c.customer_id = cs.customer_id WHERE c.customer_id IS NULL) AS orphan_fk_count,
                (SELECT COUNT(*) FROM demographics WHERE age < 18 OR age > 100) AS invalid_age_count,
                (SELECT COUNT(*) FROM demographics WHERE number_of_adults_in_family < 1) AS invalid_adults_count,
                (SELECT COUNT(*) FROM demographics WHERE family_member_count <> number_of_children_in_family + number_of_adults_in_family) AS family_violation_count,
                (SELECT COUNT(*) FROM demographics WHERE family_yearly_income < individual_yearly_income) AS income_violation_count,
                (
                    SELECT COUNT(*)
                    FROM campaign_sales cs
                    JOIN customers c ON c.customer_id = cs.customer_id
                    WHERE (
                        CAST(strftime('%Y', cs.contact_date) AS INTEGER)
                        - CAST(strftime('%Y', c.date_of_birth) AS INTEGER)
                        - CASE WHEN strftime('%m-%d', cs.contact_date) < strftime('%m-%d', c.date_of_birth) THEN 1 ELSE 0 END
                    ) < 18
                ) AS underage_contacts
            """
        ).fetchone()

        import_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT import_id, dataset_name, status, rows_read, rows_inserted, rows_rejected, source_checksum
                FROM data_import_runs
                ORDER BY import_id ASC
                """
            ).fetchall()
        ]

    _require(int(summary_row["customers_count"]) == config.customers, "Customer count mismatch after import.")
    _require(int(summary_row["campaign_sales_count"]) == config.campaign_sales, "Campaign-sales count mismatch after import.")
    _require(int(summary_row["demographics_count"]) == config.demographics, "Demographic count mismatch after import.")
    _require(int(summary_row["overlap_count"]) == 0, "customer_id/person_id overlap detected.")
    _require(int(summary_row["orphan_fk_count"]) == 0, "Campaign-sales orphan customer FK detected.")
    _require(int(summary_row["invalid_age_count"]) == 0, "Invalid demographic ages detected.")
    _require(int(summary_row["invalid_adults_count"]) == 0, "Invalid adult-count rows detected.")
    _require(int(summary_row["family_violation_count"]) == 0, "Family arithmetic violations detected.")
    _require(int(summary_row["income_violation_count"]) == 0, "Income rule violations detected.")
    _require(int(summary_row["underage_contacts"]) == 0, "Underage historical contacts detected.")

    for row in import_rows:
        _require(row["status"] == "COMPLETED", f"Import status is not COMPLETED: {row['dataset_name']}")
        checksum = str(row["source_checksum"] or "")
        _require(len(checksum) == 64, f"Invalid source checksum for dataset {row['dataset_name']}")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "imports": {
            "customers": {
                "import_id": customer_result.import_id,
                "rows_read": customer_result.rows_read,
                "rows_inserted": customer_result.rows_inserted,
                "rows_rejected": customer_result.rows_rejected,
            },
            "campaign_sales": {
                "import_id": campaign_result.import_id,
                "rows_read": campaign_result.rows_read,
                "rows_inserted": campaign_result.rows_inserted,
                "rows_rejected": campaign_result.rows_rejected,
            },
            "demographics": {
                "import_id": demographic_result.import_id,
                "rows_read": demographic_result.rows_read,
                "rows_inserted": demographic_result.rows_inserted,
                "rows_rejected": demographic_result.rows_rejected,
            },
        },
        "reconciliation": reconciliation,
        "post_import_snapshot": dict(summary_row),
        "import_runs": import_rows,
    }


def _poll_job_until_terminal(database_path: Path, *, job_id: int, timeout_seconds: float) -> tuple[list[str], dict[str, Any]]:
    repository = JobRepository(database_path)
    started = time.perf_counter()
    seen_statuses: list[str] = []

    while True:
        row = repository.fetch_job(job_id)
        _require(row is not None, f"Job disappeared during polling: {job_id}")
        status = str(row["status"])
        if not seen_statuses or seen_statuses[-1] != status:
            seen_statuses.append(status)
        if status in {"COMPLETED", "FAILED"}:
            return seen_statuses, row
        if (time.perf_counter() - started) > timeout_seconds:
            raise FullFreshValidationError(f"Timed out waiting for job {job_id} completion.")
        time.sleep(1.0)


def _launch_worker_thread(worker, *, database_path: Path, job_id: int, worker_cwd: Path) -> threading.Thread:
    def _target() -> None:
        original_cwd = Path.cwd()
        try:
            os.chdir(worker_cwd)
            worker(database_path, job_id)
        finally:
            os.chdir(original_cwd)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    return thread


def _step4_analysis_train_score(config: ValidationConfig) -> dict[str, Any]:
    started = time.perf_counter()
    database_path = config.database_path

    analysis = create_historical_analysis(database_path, {})
    analysis_run_id = int(analysis["analysis_run_id"])
    _require(analysis["status"] == "COMPLETED", "Historical analysis did not complete.")

    summary = analysis["summary"]
    _require(
        int(summary["positive_customer_count"]) + int(summary["unlabeled_customer_count"]) == int(summary["selected_customer_count"]),
        "Historical P+U reconciliation failed.",
    )

    reopened = get_historical_analysis_run(database_path, analysis_run_id)
    _require(int(reopened["analysis_run_id"]) == analysis_run_id, "Reopen analysis mismatch.")
    listed = list_historical_analysis_runs(database_path, limit=1, offset=0)
    _require(bool(listed) and int(listed[0]["analysis_run_id"]) == analysis_run_id, "Recent analysis listing mismatch.")

    model_thread_holder: dict[str, threading.Thread] = {}

    def _model_submitter(path: str | Path, job_id: int) -> None:
        model_thread_holder["thread"] = _launch_worker_thread(
            run_model_training_job,
            database_path=Path(path),
            job_id=job_id,
            worker_cwd=PROJECT_ROOT,
        )

    queued_model = submit_model_training_job_request(
        database_path,
        {
            "analysis_run_id": analysis_run_id,
            "model_name": "Full-fresh governed model",
            "random_seed": 42,
            "validation_fraction": 0.2,
            "run_elkan_challenger": True,
        },
        submitter=_model_submitter,
    )
    model_job_id = int(queued_model["job_id"])
    model_statuses, model_terminal = _poll_job_until_terminal(database_path, job_id=model_job_id, timeout_seconds=3600)
    model_thread = model_thread_holder.get("thread")
    if model_thread is not None:
        model_thread.join()

    _require(model_terminal["status"] == "COMPLETED", "Model training job failed.")
    _require("QUEUED" in model_statuses and "RUNNING" in model_statuses, "Model job status lifecycle missing states.")

    model_run_id = int(model_terminal["model_run_id"])
    model_row = ModelRunRepository(database_path).fetch_run(model_run_id)
    _require(model_row is not None, "Missing completed model run row.")
    _require(str(model_row["status"]) == "COMPLETED", "model_runs status is not COMPLETED.")
    _require(str(model_row["selected_candidate"]) == PRIMARY_MODEL_NAME, "Primary candidate selection mismatch.")

    feature_contract_json = str(model_row["feature_contract_json"])
    feature_contract = json.loads(feature_contract_json)
    _require(feature_contract.get("version") == FEATURE_CONTRACT_VERSION, "Feature contract version mismatch.")
    _require(tuple(feature_contract.get("ordered_features") or []) == ORDERED_FEATURES, "Feature contract order mismatch.")
    _require(len(tuple(feature_contract.get("ordered_features") or [])) == 11, "Expected exactly 11 ordered features.")
    feature_contract_sha = hashlib.sha256(feature_contract_json.encode("utf-8")).hexdigest()
    _require(feature_contract_sha == FEATURE_CONTRACT_SHA256, "Feature contract SHA mismatch.")

    model_metrics = json.loads(str(model_row["metrics_json"]))
    _require(model_metrics.get("primary_candidate") == PRIMARY_MODEL_NAME, "Primary candidate metadata mismatch.")
    _require(model_metrics.get("challenger_candidates") == [CHALLENGER_1_MODEL_NAME], "Challenger metadata mismatch.")
    _require(model_metrics.get("diagnostic_controls") == [DIAGNOSTIC_CONTROL_NAME], "Diagnostic metadata mismatch.")

    artifact_path = PROJECT_ROOT / str(model_row["artifact_path"])
    _require(artifact_path.is_file(), "Model artifact file missing.")
    _require(_sha256_file(artifact_path) == str(model_row["artifact_sha256"]), "Model artifact SHA mismatch.")

    scoring_thread_holder: dict[str, threading.Thread] = {}

    def _scoring_submitter(path: str | Path, job_id: int) -> None:
        scoring_thread_holder["thread"] = _launch_worker_thread(
            run_prospect_scoring_job,
            database_path=Path(path),
            job_id=job_id,
            worker_cwd=PROJECT_ROOT,
        )

    queued_scoring = submit_prospect_scoring_job_request(
        database_path,
        {"model_run_id": model_run_id},
        submitter=_scoring_submitter,
    )
    scoring_job_id = int(queued_scoring["job_id"])
    scoring_statuses, scoring_terminal = _poll_job_until_terminal(database_path, job_id=scoring_job_id, timeout_seconds=7200)
    scoring_thread = scoring_thread_holder.get("thread")
    if scoring_thread is not None:
        scoring_thread.join()

    _require(scoring_terminal["status"] == "COMPLETED", "Prospect scoring job failed.")
    _require("QUEUED" in scoring_statuses and "RUNNING" in scoring_statuses, "Scoring job status lifecycle missing states.")

    scoring_result = json.loads(str(scoring_terminal["result_json"]))
    scoring_run_id = int(scoring_result["scoring_run_id"])

    with get_connection(database_path) as connection:
        aggregate = connection.execute(
            """
            SELECT
                COUNT(*) AS score_count,
                COUNT(DISTINCT person_id) AS distinct_person_count,
                MIN(propensity_score) AS score_min,
                AVG(propensity_score) AS score_mean,
                MAX(propensity_score) AS score_max,
                SUM(CASE WHEN propensity_score < 0 OR propensity_score > 1 THEN 1 ELSE 0 END) AS out_of_range_count,
                SUM(CASE WHEN propensity_score != propensity_score THEN 1 ELSE 0 END) AS nonfinite_count
            FROM propensity_scores
            WHERE scoring_run_id = ?
            """,
            (scoring_run_id,),
        ).fetchone()
        invalid_fk = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores ps
                LEFT JOIN demographics d ON d.person_id = ps.person_id
                WHERE ps.scoring_run_id = ? AND d.person_id IS NULL
                """,
                (scoring_run_id,),
            ).fetchone()[0]
        )
        demographics_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])

    _require(int(aggregate["score_count"]) == config.demographics, "Scored row count is not 5,000,000.")
    _require(int(aggregate["score_count"]) == demographics_count, "Score count mismatch vs demographics snapshot.")
    _require(int(aggregate["distinct_person_count"]) == int(aggregate["score_count"]), "Duplicate scored person IDs detected.")
    _require(int(aggregate["out_of_range_count"]) == 0, "Scores outside [0,1] detected.")
    _require(int(aggregate["nonfinite_count"]) == 0, "Non-finite scores detected.")
    _require(invalid_fk == 0, "Scoring rows contain invalid demographic FK.")

    provenance = validate_completed_scoring_run_provenance(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(provenance["is_canonical"]), "Completed scoring run is not canonical/current.")

    sample = verify_scoring_run_sample(
        database_path,
        scoring_run_id=scoring_run_id,
        sample_size=256,
        project_root=PROJECT_ROOT,
    )
    _require(bool(sample["verified"]), "Deterministic sample re-score verification failed.")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
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
            "feature_count": len(tuple(feature_contract.get("ordered_features") or [])),
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
            "invalid_fk_count": invalid_fk,
            "score_min": float(aggregate["score_min"]),
            "score_mean": float(aggregate["score_mean"]),
            "score_max": float(aggregate["score_max"]),
            "provenance": provenance,
            "deterministic_sample": sample,
        },
    }


def _json_response(response) -> dict[str, Any] | list[Any]:
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover
        raise FullFreshValidationError("Expected JSON response payload.") from exc


def _assert_status(response, expected: int, context: str) -> None:
    if response.status_code != expected:
        raise FullFreshValidationError(
            f"{context} returned status {response.status_code}, expected {expected}. body={response.text[:600]}"
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
    response = client.get(f"/api/campaigns/{campaign_id}/exports", params={"limit": 50})
    _assert_status(response, 200, "List campaign export events")
    payload = _json_response(response)
    _require(isinstance(payload, list) and bool(payload), "Missing export event payload.")
    latest = payload[0]
    _require(isinstance(latest, dict), "Invalid export event payload.")
    return latest


def _step5_audience_and_campaign_api(config: ValidationConfig, *, scoring_run_id: int) -> dict[str, Any]:
    started = time.perf_counter()
    database_path = config.database_path

    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    prep_status = get_audience_preparation_status(database_path, scoring_run_id=scoring_run_id)
    _require(bool(prep_status["prepared"]) and bool(prep_status["analytics_prepared"]), "Audience preparation did not complete.")
    _require(int(prep_status["boundary_count"]) == 100, "Expected 100 audience percentile boundaries.")

    scenarios: dict[str, Any] = {}
    saved_audience_ids: dict[str, int] = {}

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            options_response = client.get("/api/audience/options", params={"scoring_run_id": scoring_run_id})
            _assert_status(options_response, 200, "Audience options")
            options_payload = _json_response(options_response)
            _require(isinstance(options_payload, dict), "Invalid audience options payload.")

            estimate_payloads = {
                "all_matching": {
                    "filters": {},
                    "selection": {"mode": "ALL_MATCHING"},
                    "expected_selected": config.demographics,
                },
                "top_1_percent": {
                    "filters": {"top_percentile_max": 1},
                    "selection": {"mode": "ALL_MATCHING"},
                    "expected_selected": 50_000,
                },
                "top_decile": {
                    "filters": {"deciles": [1]},
                    "selection": {"mode": "ALL_MATCHING"},
                    "expected_selected": 500_000,
                },
                "demographic_filter": {
                    "filters": {"state": ["California"], "age_min": 25, "age_max": 65},
                    "selection": {"mode": "ALL_MATCHING"},
                    "expected_selected": None,
                },
                "rank_plus_demographic": {
                    "filters": {"rank_bands": ["HIGH", "MEDIUM"], "resident_type": ["Urban core"]},
                    "selection": {"mode": "ALL_MATCHING"},
                    "expected_selected": None,
                },
                "top_n_50k": {
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": 50_000},
                    "expected_selected": 50_000,
                },
            }

            for name, scenario in estimate_payloads.items():
                estimate_response = client.post(
                    "/api/audience/estimate",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": scenario["filters"],
                        "selection": scenario["selection"],
                    },
                )
                _assert_status(estimate_response, 200, f"Audience estimate: {name}")
                estimate_payload = _json_response(estimate_response)
                _require(isinstance(estimate_payload, dict), "Invalid estimate payload.")
                selected_count = int(estimate_payload["selected_count"])
                if scenario["expected_selected"] is not None:
                    _require(
                        selected_count == int(scenario["expected_selected"]),
                        f"Scenario selected_count mismatch for {name}.",
                    )
                scenarios[name] = {
                    "matching_count": int(estimate_payload["matching_count"]),
                    "selected_count": selected_count,
                    "score_min": estimate_payload["score_min"],
                    "score_max": estimate_payload["score_max"],
                    "score_mean": estimate_payload["score_mean"],
                }

            invalid_bounds = client.post(
                "/api/audience/estimate",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {"age_min": 70, "age_max": 50},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            _require(invalid_bounds.status_code == 422, "Expected 422 for invalid age bounds.")

            invalid_topn = client.post(
                "/api/audience/estimate",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": 0},
                },
            )
            _require(invalid_topn.status_code == 422, "Expected 422 for invalid TOP_N target_count.")

            first_page = client.post(
                "/api/audience/search",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "page_size": 100,
                },
            )
            _assert_status(first_page, 200, "Audience search first page")
            first_payload = _json_response(first_page)
            _require(isinstance(first_payload, dict), "Invalid search payload.")
            first_rows = list(first_payload.get("rows") or [])
            _require(bool(first_rows), "Search returned empty first page unexpectedly.")
            prohibited_fields = {
                "email",
                "phone_number",
                "address_line_1",
                "address_line_2",
                "postal_code",
                "ethnicity",
                "religion",
                "occupation_industry",
                "family_yearly_income",
            }
            for row in first_rows:
                _require(prohibited_fields.isdisjoint(set(row.keys())), "Prohibited fields leaked in search rows.")

            seen_person_ids = {str(row["person_id"]) for row in first_rows}
            cursor = first_payload.get("next_cursor")
            pages_checked = 1
            while cursor and pages_checked < 5:
                next_page = client.post(
                    "/api/audience/search",
                    json={
                        "scoring_run_id": scoring_run_id,
                        "filters": {},
                        "page_size": 100,
                        "cursor": cursor,
                    },
                )
                _assert_status(next_page, 200, f"Audience search page {pages_checked + 1}")
                next_payload = _json_response(next_page)
                _require(isinstance(next_payload, dict), "Invalid paged search payload.")
                page_rows = list(next_payload.get("rows") or [])
                for row in page_rows:
                    person_id = str(row["person_id"])
                    _require(person_id not in seen_person_ids, "Duplicate person_id across keyset pages.")
                    seen_person_ids.add(person_id)
                cursor = next_payload.get("next_cursor")
                pages_checked += 1

            profile_response = client.post(
                "/api/audience/profile",
                json={
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            )
            _assert_status(profile_response, 200, "Audience profile")
            profile_payload = _json_response(profile_response)
            _require(isinstance(profile_payload, dict), "Invalid audience profile payload.")
            summary = profile_payload.get("summary") or {}
            selected = summary.get("selected") or {}
            _require(int(selected.get("count") or 0) == config.demographics, "Audience profile selected count mismatch.")

            save_payloads = {
                "email": {
                    "audience_name": "Full-fresh EMAIL TopN50K",
                    "filters": {},
                    "selection": {"mode": "TOP_N", "target_count": 50_000},
                },
                "direct_mail": {
                    "audience_name": "Full-fresh DirectMail Top Decile",
                    "filters": {"deciles": [1]},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            }
            for key, request_payload in save_payloads.items():
                save_response = client.post(
                    "/api/audiences",
                    json={
                        **request_payload,
                        "description": "Full-fresh validation fixture",
                        "scoring_run_id": scoring_run_id,
                        "include_profile_snapshot": True,
                    },
                )
                _assert_status(save_response, 201, f"Save audience {key}")
                saved = _json_response(save_response)
                _require(isinstance(saved, dict), "Invalid saved audience payload.")
                audience_id = int(saved["audience_id"])
                saved_audience_ids[key] = audience_id
                detail = get_saved_audience_detail(database_path, audience_id=audience_id)
                _require(int(detail["audience_id"]) == audience_id, "Saved audience reopen mismatch.")
                currentness = validate_saved_audience_currentness(database_path, audience_id=audience_id)
                _require(bool(currentness["is_current"]), "Saved audience unexpectedly stale.")

            campaign_results: dict[str, Any] = {}
            for channel, audience_key, expected_headers in (
                ("EMAIL", "email", list(EMAIL_EXPORT_COLUMNS)),
                ("DIRECT_MAIL", "direct_mail", list(DIRECT_MAIL_EXPORT_COLUMNS)),
            ):
                create_response = client.post(
                    "/api/campaigns",
                    json={
                        "campaign_name": f"Full-fresh {channel} campaign",
                        "description": "Full-fresh e2e campaign",
                        "channel": channel,
                        "planned_launch_date": "2026-12-01",
                        "saved_audience_id": saved_audience_ids[audience_key],
                    },
                )
                _assert_status(create_response, 201, f"Create {channel} campaign")
                created = _json_response(create_response)
                _require(isinstance(created, dict), "Invalid campaign create payload.")
                campaign_id = int(created["campaign_id"])

                currentness_response = client.get(f"/api/campaigns/{campaign_id}/currentness")
                _assert_status(currentness_response, 200, f"Currentness {channel}")
                currentness_payload = _json_response(currentness_response)
                _require(isinstance(currentness_payload, dict), "Invalid currentness payload.")
                _require(bool(currentness_payload["is_current"]), "Campaign currentness unexpectedly stale.")

                finalize_response = client.post(f"/api/campaigns/{campaign_id}/finalize")
                _assert_status(finalize_response, 200, f"Finalize {channel}")

                export_response = client.get(
                    f"/api/campaigns/{campaign_id}/export.csv",
                    params={"acknowledge_pii": "true"},
                )
                _assert_status(export_response, 200, f"Export {channel}")

                csv_summary = _csv_stats(export_response.content)
                _require(csv_summary["headers"] == expected_headers, f"{channel} export header mismatch.")
                forbidden = sorted(set(csv_summary["headers"]) & set(PROHIBITED_EXPORT_FIELDS))
                _require(not forbidden, f"Forbidden fields present in {channel} export: {forbidden}")

                if channel == "EMAIL":
                    _require(all(str(row.get("email") or "") for row in csv_summary["rows"]), "EMAIL export contains blank email row.")
                else:
                    for row in csv_summary["rows"]:
                        _require(bool(str(row.get("address_line_1") or "").strip()), "DIRECT_MAIL export missing address_line_1.")
                        _require(bool(str(row.get("city") or "").strip()), "DIRECT_MAIL export missing city.")
                        _require(bool(str(row.get("state") or "").strip()), "DIRECT_MAIL export missing state.")
                        _require(bool(str(row.get("postal_code") or "").strip()), "DIRECT_MAIL export missing postal_code.")

                latest_event = _latest_export_event(client, campaign_id)
                _require(str(latest_event["status"]) == "COMPLETED", "Export event did not reach COMPLETED.")
                _require(
                    int(latest_event["selected_count"]) == int(latest_event["deliverable_count"]) + int(latest_event["undeliverable_count"]),
                    "Export event selected reconciliation mismatch.",
                )
                _require(int(latest_event["row_count"]) == int(latest_event["deliverable_count"]), "Export row_count mismatch deliverable_count.")
                _require(int(latest_event["row_count"]) == int(csv_summary["row_count"]), "Export CSV row_count mismatch event row_count.")
                _require(str(latest_event["csv_sha256"]) == str(csv_summary["csv_sha256"]), "CSV checksum mismatch vs export event.")

                campaign_results[channel] = {
                    "campaign_id": campaign_id,
                    "saved_audience_id": saved_audience_ids[audience_key],
                    "selected_count": int(latest_event["selected_count"]),
                    "deliverable_count": int(latest_event["deliverable_count"]),
                    "undeliverable_count": int(latest_event["undeliverable_count"]),
                    "row_count": int(latest_event["row_count"]),
                    "csv_sha256": str(latest_event["csv_sha256"]),
                    "export_profile": str(latest_event["export_profile"]),
                }

    finally:
        app.dependency_overrides.clear()

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "preparation": prep_status,
        "scenarios": scenarios,
        "saved_audience_ids": saved_audience_ids,
        "campaign_results": campaign_results,
    }


def _collect_ui_control_inventory(config: ValidationConfig) -> dict[str, Any]:
    started = time.perf_counter()
    index_path = PROJECT_ROOT / "frontend" / "index.html"
    html_text = index_path.read_text(encoding="utf-8")
    parser = _ControlInventoryParser()
    parser.feed(html_text)

    controls: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for control in parser.controls:
        key = (str(control.get("selector")), str(control.get("type")), str(control.get("label")))
        if key in seen:
            continue
        seen.add(key)
        controls.append(control)

    payload = {
        "generated_at": _now_iso(),
        "source": "frontend/index.html",
        "controls_total": len(controls),
        "controls": controls,
    }
    config.ui_inventory_path.parent.mkdir(parents=True, exist_ok=True)
    config.ui_inventory_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "ui_control_inventory_path": str(config.ui_inventory_path.relative_to(PROJECT_ROOT)),
        "controls_total": len(controls),
    }


def _run_gate_command(name: str, command: list[str], *, allow_empty_stdout: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    passed = completed.returncode == 0
    if not allow_empty_stdout and not stdout_text.strip():
        passed = False
    return {
        "name": name,
        "command": " ".join(command),
        "returncode": completed.returncode,
        "passed": passed,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": "\n".join(stdout_text.splitlines()[-30:]),
        "stderr_tail": "\n".join(stderr_text.splitlines()[-30:]),
    }


def _step6_regression_gates(config: ValidationConfig, *, scoring_run_id: int) -> dict[str, Any]:
    if config.skip_regression:
        return {
            "status": "SKIPPED",
            "reason": "Regression gates skipped by flag.",
            "gates": [],
        }

    started = time.perf_counter()
    gates = [
        _run_gate_command("pytest_full", [sys.executable, "-m", "pytest", "-q"]),
        _run_gate_command(
            "cleanroom_bounded",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "validation" / "run_cleanroom_phase1_to_phase7.py"),
                "--customers",
                "1200",
                "--campaign-sales",
                "9000",
                "--demographics",
                "12000",
            ],
        ),
        _run_gate_command("compileall", [sys.executable, "-m", "compileall", "-q", "app", "scripts", "tests"]),
        _run_gate_command("pip_check", [sys.executable, "-m", "pip", "check"]),
        _run_gate_command("git_diff_check", ["git", "diff", "--check"]),
        _run_gate_command(
            "repository_hygiene",
            [sys.executable, str(PROJECT_ROOT / "scripts" / "validation" / "validate_ci_hygiene.py")],
        ),
        _run_gate_command("validate_data_json", [sys.executable, str(PROJECT_ROOT / "scripts" / "validate_data.py"), "--json"]),
        _run_gate_command(
            "workflow_syntax_validation",
            [sys.executable, str(PROJECT_ROOT / "scripts" / "validation" / "validate_workflow_syntax.py")],
        ),
        _run_gate_command(
            "campaign_export_contract_tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_campaign_api.py",
                "tests/test_campaign_export_hardening.py",
            ],
        ),
    ]

    deterministic_gate = {
        "name": "deterministic_scoring_sample_validation",
        "passed": True,
        "details": {
            "scoring_run_id": scoring_run_id,
            "sample_size": 256,
        },
    }

    overall_pass = all(bool(gate.get("passed")) for gate in gates) and bool(deterministic_gate["passed"])
    _require(overall_pass, "One or more final regression gates failed.")

    return {
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "gates": gates,
        "deterministic_scoring_sample": deterministic_gate,
    }


def _cleanup_runtime(config: ValidationConfig) -> dict[str, Any]:
    if config.keep_generated_runtime:
        return {"status": "PASS", "runtime_cleanup_performed": False}

    removed = 0
    for directory in (
        PROJECT_ROOT / "downloads",
        PROJECT_ROOT / "traces",
        PROJECT_ROOT / "videos",
        PROJECT_ROOT / "playwright-report",
        PROJECT_ROOT / "test-results",
    ):
        if _safe_remove_path(directory):
            removed += 1
    if _clear_directory_children(PROJECT_ROOT / "logs", preserve_names={".gitkeep"}):
        removed += 1

    db_wal = config.database_path.with_name(config.database_path.name + "-wal")
    db_shm = config.database_path.with_name(config.database_path.name + "-shm")
    if _safe_remove_path(db_wal):
        removed += 1
    if _safe_remove_path(db_shm):
        removed += 1

    return {
        "status": "PASS",
        "runtime_cleanup_performed": True,
        "removed_artifact_count": removed,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _build_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Full Fresh Phase 1 to Phase 7 E2E Report")
    lines.append("")
    lines.append(f"Status: {payload.get('overall_status')}")
    lines.append(f"Generated at: {payload.get('generated_at')}")
    lines.append(f"Completed at: {payload.get('completed_at')}")
    lines.append("")

    stages = payload.get("stages") or {}
    for stage_name in ("step1", "step2", "step3", "step4", "step5", "step6", "step13", "step14"):
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            continue
        lines.append(f"## {stage_name.upper()}")
        lines.append(f"- status: {stage.get('status', 'UNKNOWN')}")
        if "duration_seconds" in stage:
            lines.append(f"- duration_seconds: {stage['duration_seconds']}")
        if stage_name == "step2":
            row_counts = stage.get("row_counts") or {}
            lines.append(
                f"- generated_rows: customers={row_counts.get('customers')}, campaign_sales={row_counts.get('campaign_sales')}, demographics={row_counts.get('demographics')}"
            )
        if stage_name == "step4":
            scoring = stage.get("scoring_integrity") or {}
            lines.append(
                f"- scoring_rows={scoring.get('score_count')} distinct={scoring.get('distinct_person_count')} min={scoring.get('score_min')} mean={scoring.get('score_mean')} max={scoring.get('score_max')}"
            )
        if stage_name == "step5":
            campaigns = stage.get("campaign_results") or {}
            for channel in ("EMAIL", "DIRECT_MAIL"):
                channel_payload = campaigns.get(channel) or {}
                if channel_payload:
                    lines.append(
                        f"- {channel.lower()}: campaign_id={channel_payload.get('campaign_id')} selected={channel_payload.get('selected_count')} deliverable={channel_payload.get('deliverable_count')} rows={channel_payload.get('row_count')}"
                    )
        if stage_name == "step13":
            lines.append(f"- ui_controls_total: {stage.get('controls_total')}")
        lines.append("")

    if payload.get("overall_status") != "PASS":
        lines.append("## Failure")
        lines.append(f"- message: {payload.get('failure_message', 'Unknown failure')}")
        lines.append("")

    final_decision = payload.get("final_decision") or {}
    lines.append("## Decision")
    lines.append(f"- status: {final_decision.get('status', 'NO-GO')}")
    lines.append(f"- reason: {final_decision.get('reason', 'Validation failed or incomplete')}" )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_build_report(payload), encoding="utf-8")


def run_full_fresh_validation(config: ValidationConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "overall_status": "RUNNING",
        "stages": {},
    }

    try:
        _log("step1", "Running destructive precheck and generated-state removal.")
        step1 = _step1_precheck_and_cleanup(config)
        payload["stages"]["step1"] = step1

        _log("step2", "Regenerating full synthetic sources and validating file contracts.")
        step2 = _generate_full_dataset(config)
        payload["stages"]["step2"] = step2

        _log("step2", "Validating generated source hashes against accepted baseline.")
        hash_gate = _assert_hashes_match_accepted(
            accepted_hashes=step1["precheck"].get("accepted_source_hashes", {}),
            generated_hashes=step2["generated_hashes"],
        )
        payload["stages"]["step2"]["accepted_manifest_hash_check"] = hash_gate

        _log("step3", "Importing regenerated files into a fresh schema and reconciling.")
        payload["stages"]["step3"] = _step3_import_and_reconcile(config)

        _log("step4", "Running historical analysis, model training, and full 5M scoring checks.")
        step4 = _step4_analysis_train_score(config)
        payload["stages"]["step4"] = step4
        scoring_run_id = int(step4["scoring_job"]["scoring_run_id"])

        _log("step5", "Running audience scenarios and campaign export contract checks.")
        payload["stages"]["step5"] = _step5_audience_and_campaign_api(config, scoring_run_id=scoring_run_id)

        _log("step13", "Capturing full UI control inventory from frontend source.")
        payload["stages"]["step13"] = _collect_ui_control_inventory(config)

        _log("step6", "Running final regression gates for Step 15.")
        payload["stages"]["step6"] = _step6_regression_gates(config, scoring_run_id=scoring_run_id)

        _log("step14", "Cleaning runtime artifacts and verifying final DB integrity.")
        cleanup = _cleanup_runtime(config)
        with get_connection(config.database_path) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
        _require(str(integrity[0]) == "ok", "PRAGMA integrity_check did not return ok.")
        cleanup["pragma_integrity_check"] = str(integrity[0])
        payload["stages"]["step14"] = cleanup

        payload["overall_status"] = "PASS"
    except Exception as exc:
        payload["overall_status"] = "FAIL"
        payload["failure_message"] = str(exc)

    payload["completed_at"] = _now_iso()
    payload["environment"] = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "dependency_versions": {
            name: _safe_package_version(name)
            for name in ("fastapi", "uvicorn", "numpy", "pandas", "scikit-learn", "pulearn", "pytest")
        },
    }
    payload["git"] = {
        "branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
    }

    if payload["overall_status"] == "PASS":
        payload["final_decision"] = {
            "status": "GO",
            "reason": "All full-fresh generation/import/scoring/audience/campaign/export and regression gates passed.",
        }
    else:
        payload["final_decision"] = {
            "status": "NO-GO",
            "reason": str(payload.get("failure_message") or "A required gate failed."),
        }

    _write_json(config.manifest_path, payload)
    _write_report(config.report_path, payload)
    return payload


def _safe_package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full-fresh Phase 1-7 validation.")
    parser.add_argument("--customers", type=int, default=EXPECTED_CUSTOMERS)
    parser.add_argument("--campaign-sales", type=int, default=EXPECTED_CAMPAIGN_SALES)
    parser.add_argument("--demographics", type=int, default=EXPECTED_DEMOGRAPHICS)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Directory where generated source files are created.",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "campaign_poc.db",
        help="Runtime SQLite database path.",
    )
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    parser.add_argument("--ui-inventory-path", type=Path, default=UI_INVENTORY_PATH)
    parser.add_argument("--skip-regression", action="store_true")
    parser.add_argument("--keep-generated-runtime", action="store_true")
    parser.add_argument("--allow-dirty-worktree", action="store_true")
    return parser.parse_args(argv)


def _validated_positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FullFreshValidationError(f"{field_name} must be a positive integer.")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = ValidationConfig(
            customers=_validated_positive_int(args.customers, field_name="customers"),
            campaign_sales=_validated_positive_int(args.campaign_sales, field_name="campaign_sales"),
            demographics=_validated_positive_int(args.demographics, field_name="demographics"),
            data_dir=args.data_dir.resolve(),
            database_path=args.database_path.resolve(),
            report_path=args.report_path.resolve(),
            manifest_path=args.manifest_path.resolve(),
            ui_inventory_path=args.ui_inventory_path.resolve(),
            skip_regression=bool(args.skip_regression),
            keep_generated_runtime=bool(args.keep_generated_runtime),
            allow_dirty_worktree=bool(args.allow_dirty_worktree),
        )
        payload = run_full_fresh_validation(config)
        if payload.get("overall_status") != "PASS":
            _log("fail", str(payload.get("failure_message") or "Full-fresh validation failed."))
            return 1

        _log("pass", "Full-fresh Phase 1-7 validation completed successfully.")
        _log("pass", f"Manifest: {config.manifest_path}")
        _log("pass", f"Report: {config.report_path}")
        _log("pass", f"UI inventory: {config.ui_inventory_path}")
        return 0
    except Exception as exc:
        _log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())