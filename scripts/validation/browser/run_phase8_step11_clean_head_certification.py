from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.validation.browser.check_ui_control_coverage import evaluate_inventory
    from scripts.validation.browser.system_browser import resolve_system_browser
except ModuleNotFoundError:
    from check_ui_control_coverage import evaluate_inventory  # type: ignore[no-redef]
    from system_browser import resolve_system_browser  # type: ignore[no-redef]

PROMPT_PATH = (
    "Prompts/phase8_release_assurance_system_browser_prompt_pack/"
    "11_STEP_11_CLEAN_HEAD_TRUE_BROWSER_PHASE1_TO_PHASE7_CERTIFICATION.md"
)
RESUME_EXISTING_ENV = "PHASE8_STEP11_RESUME_EXISTING"

PHASE8_DIR = PROJECT_ROOT / "docs" / "evidence" / "phase8"
FINAL_DIR = PHASE8_DIR / "final_system_browser"
REPORT_PATH = FINAL_DIR / "PHASE8_SYSTEM_BROWSER_CERTIFICATION_REPORT.md"
COVERAGE_PATH = FINAL_DIR / "ui_control_coverage.json"
MANIFEST_PATH = FINAL_DIR / "phase8_certification_manifest.json"

INVENTORY_PATH = PHASE8_DIR / "ui_control_inventory.json"
DB_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"
SERVER_LOG_PATH = PROJECT_ROOT / "logs" / "phase8_step11_uvicorn.log"

STEP_RUNNERS: list[dict[str, Path]] = [
    {
        "name": "step5_historical",
        "script": PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step5_historical_analysis.py",
        "evidence": PHASE8_DIR / "05_system_browser_historical_analysis.json",
    },
    {
        "name": "step6_training_scoring",
        "script": PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step6_model_training_and_5m_scoring.py",
        "evidence": PHASE8_DIR / "06_system_browser_training_and_5m_scoring.json",
    },
    {
        "name": "step7_audience",
        "script": PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step7_audience_explorer_all_controls.py",
        "evidence": PHASE8_DIR / "07_system_browser_audience_explorer_all_controls.json",
    },
    {
        "name": "step8_campaigns",
        "script": PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step8_campaign_builder_and_exports.py",
        "evidence": PHASE8_DIR / "08_system_browser_campaign_builder_and_exports.json",
    },
    {
        "name": "step9_browser_quality",
        "script": PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step9_browser_quality.py",
        "evidence": PHASE8_DIR / "09_browser_quality_evidence.json",
    },
]

STEP_ARTIFACT_PATHS = [
    PHASE8_DIR / "05_system_browser_historical_analysis.json",
    PHASE8_DIR / "05_SYSTEM_BROWSER_HISTORICAL_ANALYSIS_REPORT.md",
    PHASE8_DIR / "06_system_browser_training_and_5m_scoring.json",
    PHASE8_DIR / "06_SYSTEM_BROWSER_TRAINING_AND_5M_SCORING_REPORT.md",
    PHASE8_DIR / "07_system_browser_audience_explorer_all_controls.json",
    PHASE8_DIR / "07_SYSTEM_BROWSER_AUDIENCE_REPORT.md",
    PHASE8_DIR / "08_system_browser_campaign_builder_and_exports.json",
    PHASE8_DIR / "08_SYSTEM_BROWSER_CAMPAIGN_EXPORT_REPORT.md",
    PHASE8_DIR / "09_browser_quality_evidence.json",
    PHASE8_DIR / "09_BROWSER_QUALITY_REPORT.md",
    INVENTORY_PATH,
]


class Step11ValidationError(RuntimeError):
    """Raised when Step 11 certification validation fails."""


@dataclass(frozen=True)
class GateState:
    branch: str
    candidate_sha: str
    git_status_short: list[str]
    browser_name: str
    browser_executable: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def _log(message: str) -> None:
    print(f"[step11] {message}", flush=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Step11ValidationError(message)


def _git(args: list[str], *, strict: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or "").strip()
    if completed.returncode != 0 and strict:
        stderr = (completed.stderr or "").strip()
        raise Step11ValidationError(
            f"git command failed: git {' '.join(args)}\nstdout={output}\nstderr={stderr}"
        )
    return output


def _run_command(command: list[str], *, env: dict[str, str] | None = None) -> str:
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip("\n")
        print(text, flush=True)
        lines.append(text)

    returncode = process.wait()
    output = "\n".join(lines)
    if returncode != 0:
        tail = "\n".join(lines[-60:])
        raise Step11ValidationError(
            "Subprocess failed with non-zero exit code.\n"
            f"command={' '.join(command)}\n"
            f"exit_code={returncode}\n"
            f"output_tail={tail}"
        )
    return output


def _remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
    return True


def _clear_children(directory: Path, *, preserve_names: set[str] | None = None) -> list[str]:
    removed: list[str] = []
    preserve = preserve_names or set()
    if not directory.is_dir():
        return removed
    for child in directory.iterdir():
        if child.name in preserve:
            continue
        if _remove_path(child):
            removed.append(_portable(child))
    return removed


def _clean_runtime_state() -> dict[str, Any]:
    removed: list[str] = []

    for file_path in [DB_PATH, DB_PATH.with_name(DB_PATH.name + "-wal"), DB_PATH.with_name(DB_PATH.name + "-shm")]:
        if _remove_path(file_path):
            removed.append(_portable(file_path))

    removed.extend(_clear_children(PROJECT_ROOT / "artifacts" / "models", preserve_names={".gitkeep"}))
    removed.extend(_clear_children(PROJECT_ROOT / "logs", preserve_names={".gitkeep"}))

    for folder_name in ["output", "downloads", "traces", "videos", "playwright-report", "test-results"]:
        folder = PROJECT_ROOT / folder_name
        if _remove_path(folder):
            removed.append(_portable(folder))

    # Ensure final output folder is fresh for this certification run.
    if FINAL_DIR.exists():
        for child in FINAL_DIR.iterdir():
            if _remove_path(child):
                removed.append(_portable(child))

    return {
        "removed_items": sorted(removed),
    }


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"Missing required JSON file: {_portable(path)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected JSON object in {_portable(path)}")
    return payload


@contextmanager
def _managed_server(python_exe: Path) -> Iterator[dict[str, Any]]:
    SERVER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SERVER_LOG_PATH.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                str(python_exe),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            _wait_for_backend_ready(timeout_seconds=180)
            yield {
                "pid": process.pid,
                "log_path": _portable(SERVER_LOG_PATH),
                "command": f"{python_exe} -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
            }
        finally:
            if os.name == "nt":
                # Audience preparation runs in a multiprocessing child. Killing
                # only Uvicorn orphans that worker and leaves inherited DB/log
                # handles open, so tear down the complete managed process tree.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            else:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def _wait_for_backend_ready(*, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "unknown"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            last_error = str(exc)
        time.sleep(0.5)

    raise Step11ValidationError(f"Backend did not become ready on 127.0.0.1:8000. Last error: {last_error}")


def _run_official_fresh_init_and_import(python_exe: Path) -> dict[str, Any]:
    commands = [
        [str(python_exe), str(PROJECT_ROOT / "scripts" / "init_db.py")],
        [
            str(python_exe),
            str(PROJECT_ROOT / "scripts" / "import_customers.py"),
            "--file",
            str(PROJECT_ROOT / "data" / "customer_master_125000.csv.gz"),
        ],
        [
            str(python_exe),
            str(PROJECT_ROOT / "scripts" / "import_campaign_sales.py"),
            "--file",
            str(PROJECT_ROOT / "data" / "campaign_sales_570000.csv.gz"),
        ],
        [
            str(python_exe),
            str(PROJECT_ROOT / "scripts" / "import_demographics.py"),
            "--file",
            str(PROJECT_ROOT / "data" / "usa_demographic_synthetic_5000000_rows.csv.gz"),
        ],
    ]

    outputs: list[dict[str, Any]] = []
    for command in commands:
        started = time.perf_counter()
        output = _run_command(command)
        outputs.append(
            {
                "command": " ".join(command),
                "duration_seconds": round(time.perf_counter() - started, 3),
                "output_tail": output.splitlines()[-10:],
            }
        )

    return {"commands": outputs}


def _run_step_runners(python_exe: Path) -> dict[str, Any]:
    step_results: dict[str, Any] = {}

    # Step 11 requires fresh inventory/coverage regeneration.
    _run_command([str(python_exe), str(PROJECT_ROOT / "scripts" / "validation" / "browser" / "build_ui_control_inventory.py")])

    for spec in STEP_RUNNERS:
        name = str(spec["name"])
        script = Path(spec["script"])
        evidence = Path(spec["evidence"])

        _log(f"Executing {name} via system browser runner.")
        started = time.perf_counter()
        _run_command([str(python_exe), str(script)])
        duration = round(time.perf_counter() - started, 3)

        payload = _load_json(evidence)
        status = str(payload.get("overall_status") or "").upper()
        _require(status == "PASS", f"{name} did not pass. overall_status={status!r}")

        step_results[name] = {
            "script": _portable(script),
            "evidence": _portable(evidence),
            "duration_seconds": duration,
            "overall_status": status,
        }

    return step_results


def _load_existing_passed_step_results() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    step_results: dict[str, Any] = {}
    step_payloads: dict[str, dict[str, Any]] = {}
    for spec in STEP_RUNNERS:
        name = str(spec["name"])
        script = Path(spec["script"])
        evidence = Path(spec["evidence"])
        payload = _load_json(evidence)
        status = str(payload.get("overall_status") or "").upper()
        _require(status == "PASS", f"Resume checkpoint {name} did not pass. overall_status={status!r}")
        step_payloads[name] = payload
        step_results[name] = {
            "script": _portable(script),
            "evidence": _portable(evidence),
            "duration_seconds": None,
            "overall_status": status,
            "execution": "reused_completed_checkpoint",
        }
    return step_results, step_payloads


def _build_coverage_payload() -> dict[str, Any]:
    inventory = _load_json(INVENTORY_PATH)
    result = evaluate_inventory(inventory)
    controls = inventory.get("controls", [])

    justified: list[dict[str, Any]] = []
    if isinstance(controls, list):
        for control in controls:
            status = str(control.get("status", "")).upper()
            if status != "JUSTIFIED_EXCLUSIVE":
                continue
            justified.append(
                {
                    "page": control.get("page"),
                    "selector": control.get("selector"),
                    "label": control.get("label"),
                    "mutually_exclusive_group": control.get("mutually_exclusive_group"),
                    "justification": control.get("justification"),
                }
            )

    payload = {
        "generated_at": _now_iso(),
        "inventory_path": _portable(INVENTORY_PATH),
        "counts": result.get("counts", {}),
        "ok": bool(result.get("ok")),
        "errors": result.get("errors", []),
        "generic_exception_count": 0,
        "justified_exclusive_controls": justified,
    }
    return payload


def _single_value(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(sql, params).fetchone()
    return row[0] if row else None


def _collect_integrity_and_ids(step_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _require(DB_PATH.is_file(), f"Expected database file missing: {_portable(DB_PATH)}")

    with sqlite3.connect(DB_PATH) as connection:
        customer_count = int(_single_value(connection, "SELECT COUNT(*) FROM customers") or 0)
        campaign_sales_count = int(_single_value(connection, "SELECT COUNT(*) FROM campaign_sales") or 0)
        demographic_count = int(_single_value(connection, "SELECT COUNT(*) FROM demographics") or 0)

        imports_latest = [
            {
                "dataset_name": row[0],
                "import_id": row[1],
                "status": row[2],
                "rows_inserted": row[3],
                "source_checksum": row[4],
                "completed_at": row[5],
            }
            for row in connection.execute(
                """
                SELECT d.dataset_name, d.import_id, d.status, d.rows_inserted, d.source_checksum, d.completed_at
                FROM data_import_runs d
                JOIN (
                    SELECT dataset_name, MAX(import_id) AS max_import_id
                    FROM data_import_runs
                    GROUP BY dataset_name
                ) latest
                  ON latest.dataset_name = d.dataset_name
                 AND latest.max_import_id = d.import_id
                ORDER BY d.dataset_name
                """
            ).fetchall()
        ]

        completed_analysis_count = int(
            _single_value(connection, "SELECT COUNT(*) FROM historical_analysis_runs WHERE status='COMPLETED'") or 0
        )

        latest_model = connection.execute(
            """
            SELECT model_run_id, status, selected_candidate, feature_contract_json,
                   artifact_sha256
            FROM model_runs
            ORDER BY model_run_id DESC
            LIMIT 1
            """
        ).fetchone()

        latest_scoring = connection.execute(
            """
            SELECT scoring_run_id, model_run_id, status, scored_person_count,
                   demographic_snapshot_count, feature_contract_version,
                   feature_contract_sha256, artifact_sha256, completed_at,
                   model_role_policy_version
            FROM scoring_runs
            ORDER BY scoring_run_id DESC
            LIMIT 1
            """
        ).fetchone()

        latest_scoring_run_id = int(latest_scoring[0]) if latest_scoring else -1

        rank_boundary_count = int(
            _single_value(
                connection,
                "SELECT COUNT(*) FROM audience_rank_boundaries WHERE scoring_run_id=?",
                (latest_scoring_run_id,),
            )
            or 0
        )

        analytics_snapshot_count = int(
            _single_value(
                connection,
                "SELECT COUNT(*) FROM audience_analytics_snapshots WHERE scoring_run_id=?",
                (latest_scoring_run_id,),
            )
            or 0
        )

        saved_audience_count = int(_single_value(connection, "SELECT COUNT(*) FROM saved_audiences") or 0)

        finalized_email_campaigns = int(
            _single_value(
                connection,
                "SELECT COUNT(*) FROM campaigns WHERE status='FINALIZED' AND channel='EMAIL'",
            )
            or 0
        )
        finalized_direct_mail_campaigns = int(
            _single_value(
                connection,
                "SELECT COUNT(*) FROM campaigns WHERE status='FINALIZED' AND channel='DIRECT_MAIL'",
            )
            or 0
        )

        completed_exports = int(
            _single_value(connection, "SELECT COUNT(*) FROM campaign_export_events WHERE status='COMPLETED'") or 0
        )
        started_exports = int(
            _single_value(connection, "SELECT COUNT(*) FROM campaign_export_events WHERE status='STARTED'") or 0
        )

        active_jobs = int(
            _single_value(connection, "SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')") or 0
        )

        integrity_check = str(_single_value(connection, "PRAGMA integrity_check") or "").strip().lower()

    step6_payload = step_payloads.get("step6_training_scoring", {})
    step7_payload = step_payloads.get("step7_audience", {})
    step8_payload = step_payloads.get("step8_campaigns", {})

    deterministic_rescore = (
        step6_payload.get("backend_assertions", {})
        .get("scoring", {})
        .get("deterministic_rescore", {})
    )
    model_feature_contract: dict[str, Any] = {}
    model_feature_contract_sha256: str | None = None
    if latest_model and latest_model[3]:
        try:
            parsed_contract = json.loads(str(latest_model[3]))
            if isinstance(parsed_contract, dict):
                model_feature_contract = parsed_contract
                canonical_contract = json.dumps(
                    parsed_contract,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                model_feature_contract_sha256 = hashlib.sha256(canonical_contract.encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            model_feature_contract = {}

    model_feature_contract_version = model_feature_contract.get("version")
    deterministic_max_abs_diff = deterministic_rescore.get("max_abs_diff")

    run_ids = {
        "historical_analysis_run_ids": {
            "broad": step_payloads.get("step5_historical", {})
            .get("historical_runs", {})
            .get("broad", {})
            .get("run_id"),
            "narrow": step_payloads.get("step5_historical", {})
            .get("historical_runs", {})
            .get("narrow", {})
            .get("run_id"),
        },
        "model_run_id": step6_payload.get("backend_assertions", {}).get("model", {}).get("model_run_id"),
        "scoring_run_id": step6_payload.get("backend_assertions", {}).get("scoring", {}).get("scoring_run_id"),
        "saved_audience_id": step7_payload.get("saved_audience_flow", {}).get("saved_audience_id"),
        "campaign_ids": {
            "email": step8_payload.get("email_flow", {}).get("campaign_id"),
            "direct_mail": step8_payload.get("direct_mail_flow", {}).get("campaign_id"),
        },
        "export_event_ids": {
            "email": step8_payload.get("email_flow", {}).get("ui_export_event", {}).get("event_id"),
            "direct_mail": step8_payload.get("direct_mail_flow", {}).get("ui_export_event", {}).get("event_id"),
        },
        "export_checksums": {
            "email": step8_payload.get("email_flow", {}).get("ui_export_event", {}).get("checksum"),
            "direct_mail": step8_payload.get("direct_mail_flow", {}).get("ui_export_event", {}).get("checksum"),
        },
    }

    checks = {
        "customers_125k": customer_count == 125_000,
        "campaign_sales_570k": campaign_sales_count == 570_000,
        "prospects_5m": demographic_count == 5_000_000,
        "current_imports_completed": bool(imports_latest)
        and all(str(row.get("status") or "").upper() == "COMPLETED" for row in imports_latest),
        "completed_analysis_present": completed_analysis_count > 0,
        "governed_model_present": bool(latest_model)
        and str(latest_model[1]).upper() == "COMPLETED"
        and bool(latest_model[2])
        and bool(model_feature_contract_version)
        and bool(model_feature_contract_sha256)
        and bool(latest_model[4])
        and bool(latest_scoring)
        and latest_model[0] == latest_scoring[1]
        and str(model_feature_contract_version) == str(latest_scoring[5])
        and model_feature_contract_sha256 == latest_scoring[6]
        and latest_model[4] == latest_scoring[7]
        and bool(latest_scoring[9]),
        "scores_5m_completed": bool(latest_scoring)
        and str(latest_scoring[2]).upper() == "COMPLETED"
        and int(latest_scoring[3] or 0) == 5_000_000,
        "deterministic_rescore_sample": bool(deterministic_rescore.get("verified"))
        and deterministic_max_abs_diff is not None
        and float(deterministic_max_abs_diff) == 0.0,
        "rank_boundaries_100": rank_boundary_count == 100,
        "analytics_current": analytics_snapshot_count > 0,
        "saved_audience_present": saved_audience_count > 0,
        "finalized_email_campaign": finalized_email_campaigns > 0,
        "finalized_direct_mail_campaign": finalized_direct_mail_campaigns > 0,
        "completed_exports_present": completed_exports >= 2,
        "no_stale_active_jobs": active_jobs == 0,
        "no_started_exports": started_exports == 0,
        "pragma_integrity_ok": integrity_check == "ok",
    }

    details = {
        "row_counts": {
            "customers": customer_count,
            "campaign_sales": campaign_sales_count,
            "demographics": demographic_count,
        },
        "imports_latest": imports_latest,
        "completed_analysis_count": completed_analysis_count,
        "latest_model": {
            "model_run_id": latest_model[0] if latest_model else None,
            "status": latest_model[1] if latest_model else None,
            "selected_candidate": latest_model[2] if latest_model else None,
            "feature_contract_version": model_feature_contract_version,
            "feature_contract_sha256": model_feature_contract_sha256,
            "model_role_policy_version": latest_scoring[9] if latest_scoring else None,
            "artifact_sha256": latest_model[4] if latest_model else None,
        },
        "latest_scoring": {
            "scoring_run_id": latest_scoring[0] if latest_scoring else None,
            "model_run_id": latest_scoring[1] if latest_scoring else None,
            "status": latest_scoring[2] if latest_scoring else None,
            "scored_person_count": latest_scoring[3] if latest_scoring else None,
            "demographic_snapshot_count": latest_scoring[4] if latest_scoring else None,
            "feature_contract_version": latest_scoring[5] if latest_scoring else None,
            "feature_contract_sha256": latest_scoring[6] if latest_scoring else None,
            "artifact_sha256": latest_scoring[7] if latest_scoring else None,
            "completed_at": latest_scoring[8] if latest_scoring else None,
            "deterministic_rescore": deterministic_rescore,
        },
        "rank_boundary_count": rank_boundary_count,
        "analytics_snapshot_count": analytics_snapshot_count,
        "saved_audience_count": saved_audience_count,
        "finalized_email_campaigns": finalized_email_campaigns,
        "finalized_direct_mail_campaigns": finalized_direct_mail_campaigns,
        "completed_exports": completed_exports,
        "active_jobs": active_jobs,
        "started_exports": started_exports,
        "integrity_check": integrity_check,
    }

    return {
        "checks": checks,
        "details": details,
        "run_ids": run_ids,
    }


def _collect_browser_quality(step9_payload: dict[str, Any]) -> dict[str, Any]:
    summary = step9_payload.get("error_classification", {}).get("summary", {})
    quality = {
        "unexplained_console_total": int(summary.get("unexplained_console_total") or 0),
        "unexplained_js_total": int(summary.get("unexplained_js_total") or 0),
        "unexplained_critical_network_total": int(summary.get("unexplained_critical_network_total") or 0),
    }
    quality["ok"] = (
        quality["unexplained_console_total"] == 0
        and quality["unexplained_js_total"] == 0
        and quality["unexplained_critical_network_total"] == 0
    )
    return quality


def _collect_artifact_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in STEP_ARTIFACT_PATHS:
        if path.is_file():
            hashes[_portable(path)] = _sha256_file(path)
    return hashes


def _write_report(manifest: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Phase 8 System Browser Certification Report")
    lines.append("")
    lines.append(f"Generated at: {manifest.get('generated_at')}")
    lines.append(f"Prompt: {manifest.get('prompt')}")
    lines.append(f"Candidate SHA: {manifest.get('candidate', {}).get('sha')}")
    lines.append(f"Branch: {manifest.get('candidate', {}).get('branch')}")
    lines.append(f"Execution mode: {manifest.get('execution_mode')}")
    if manifest.get("resume_checkpoint"):
        lines.append(
            "Resume disclosure: user-directed reuse of existing completed scoring; "
            "no import, training, or scoring rerun was performed by this aggregation."
        )
    lines.append("")

    clean_gate = manifest.get("clean_start_gate", {})
    lines.append("## Clean-start gate")
    lines.append(f"- Passed: {clean_gate.get('passed')}")
    lines.append(f"- git status --short lines: {clean_gate.get('git_status_short')}")
    lines.append(f"- Browser resolved: {clean_gate.get('browser_name')} @ {clean_gate.get('browser_executable')}")
    lines.append("")

    if manifest.get("step_runs"):
        lines.append("## Browser-driven stages")
        for key, value in manifest.get("step_runs", {}).items():
            lines.append(
                f"- {key}: {value.get('overall_status')} ({value.get('duration_seconds')}s)"
            )
        lines.append("")

    coverage = manifest.get("coverage", {})
    lines.append("## Coverage acceptance")
    lines.append(f"- PASS: {coverage.get('counts', {}).get('PASS')}")
    lines.append(f"- FAIL: {coverage.get('counts', {}).get('FAIL')}")
    lines.append(f"- NOT_RUN: {coverage.get('counts', {}).get('NOT_RUN')}")
    lines.append(
        f"- JUSTIFIED_EXCLUSIVE (with individual docs): {coverage.get('counts', {}).get('JUSTIFIED_EXCLUSIVE')}"
    )
    lines.append(f"- Generic EXCEPTION: {coverage.get('generic_exception_count')}")
    lines.append(f"- Coverage gate status: {coverage.get('ok')}")
    if coverage.get("errors"):
        lines.append(f"- Coverage errors: {coverage.get('errors')}")
    lines.append("")

    integrity = manifest.get("integrity", {})
    lines.append("## Integrity")
    for key, value in integrity.get("checks", {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    quality = manifest.get("browser_quality", {})
    lines.append("## Browser quality")
    lines.append(f"- 0 unexplained console errors: {quality.get('unexplained_console_total') == 0}")
    lines.append(f"- 0 unexplained critical network failures: {quality.get('unexplained_critical_network_total') == 0}")
    lines.append("")

    lines.append("## Run IDs and checksums")
    lines.append(f"- IDs: {manifest.get('run_ids')}")
    lines.append("")

    lines.append("## Artifact SHA-256")
    for path, digest in manifest.get("artifact_sha256", {}).items():
        lines.append(f"- {path}: {digest}")
    lines.append("")

    lines.append("## Decision")
    lines.append(f"- Overall status: {manifest.get('overall_status')}")
    lines.append(f"- Local decision: {manifest.get('local_decision')}")
    lines.append("- Final GO declaration is deferred until Step 12 CI is green.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _run_step11() -> dict[str, Any]:
    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.is_file():
        python_exe = Path(sys.executable)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    resume_existing = os.getenv(RESUME_EXISTING_ENV, "").strip().casefold() in {"1", "true", "yes"}

    manifest: dict[str, Any] = {
        "generated_at": _now_iso(),
        "prompt": PROMPT_PATH,
        "candidate": {},
        "clean_start_gate": {},
        "step_runs": {},
        "coverage": {},
        "integrity": {},
        "browser_quality": {},
        "run_ids": {},
        "artifact_sha256": {},
        "overall_status": "FAIL",
        "local_decision": "NO-GO",
        "execution_mode": "user_directed_resume_existing" if resume_existing else "strict_fresh_single_run",
    }

    coverage_payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "inventory_path": _portable(INVENTORY_PATH) if INVENTORY_PATH.exists() else None,
        "counts": {},
        "ok": False,
        "errors": ["Step 11 did not reach coverage evaluation."],
        "generic_exception_count": 0,
        "justified_exclusive_controls": [],
    }

    try:
        _log("Evaluating clean-start gate.")
        status_short = _git(["status", "--short"]).splitlines()
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        candidate_sha = _git(["rev-parse", "HEAD"])
        browser_target = resolve_system_browser()

        gate = GateState(
            branch=branch,
            candidate_sha=candidate_sha,
            git_status_short=status_short,
            browser_name=browser_target.name,
            browser_executable=str(browser_target.executable_path),
        )

        manifest["candidate"] = {
            "branch": gate.branch,
            "sha": gate.candidate_sha,
        }
        manifest["clean_start_gate"] = {
            "passed": len(gate.git_status_short) == 0,
            "git_status_short": gate.git_status_short,
            "dirty_override": False,
            "browser_name": gate.browser_name,
            "browser_executable": gate.browser_executable,
        }

        _require(
            len(gate.git_status_short) == 0,
            "Clean-start gate failed: git status --short is not empty. Commit Steps 1-10 changes before Step 11.",
        )

        step_payloads: dict[str, dict[str, Any]] = {}
        if resume_existing:
            _log("Resuming from completed Step 5-9 evidence without rerunning import, training, or scoring.")
            _require(DB_PATH.is_file(), "Resume checkpoint database is missing.")
            manifest["step_runs"], step_payloads = _load_existing_passed_step_results()
            manifest["resume_checkpoint"] = {
                "enabled": True,
                "environment_variable": RESUME_EXISTING_ENV,
                "user_directed_no_scoring_rerun": True,
                "database_path": _portable(DB_PATH),
                "evidence_reused": [value["evidence"] for value in manifest["step_runs"].values()],
            }
            manifest["fresh_init_and_import"] = {
                "mode": "reused_existing_fresh_runtime_checkpoint",
                "rerun": False,
            }
        else:
            _log("Performing fresh runtime cleanup.")
            manifest["runtime_cleanup"] = _clean_runtime_state()

            _log("Initializing and importing fresh runtime database via official scripts.")
            manifest["fresh_init_and_import"] = _run_official_fresh_init_and_import(python_exe)

            _log("Starting managed backend and executing browser stages.")
            with _managed_server(python_exe) as server_meta:
                manifest["server"] = {
                    "managed": True,
                    "command": server_meta["command"],
                    "log_path": server_meta["log_path"],
                    "pid": server_meta["pid"],
                }

                manifest["step_runs"] = _run_step_runners(python_exe)

            for spec in STEP_RUNNERS:
                name = str(spec["name"])
                evidence_path = Path(spec["evidence"])
                step_payloads[name] = _load_json(evidence_path)

        coverage_payload = _build_coverage_payload()
        manifest["coverage"] = coverage_payload
        _require(bool(coverage_payload.get("ok")), "Coverage gate failed for Step 11.")
        counts = coverage_payload.get("counts", {})
        _require(int(counts.get("FAIL") or 0) == 0, "Coverage gate failed: FAIL controls present.")
        _require(int(counts.get("NOT_RUN") or 0) == 0, "Coverage gate failed: NOT_RUN controls remain.")
        _require(int(coverage_payload.get("generic_exception_count") or 0) == 0, "Coverage gate failed: generic EXCEPTION found.")

        integrity = _collect_integrity_and_ids(step_payloads)
        manifest["integrity"] = {
            "checks": integrity["checks"],
            "details": integrity["details"],
        }
        manifest["run_ids"] = integrity["run_ids"]
        _require(all(bool(v) for v in integrity["checks"].values()), "Integrity gates failed for Step 11.")

        step9_payload = step_payloads["step9_browser_quality"]
        manifest["browser"] = step9_payload.get("browser", {})
        quality = _collect_browser_quality(step9_payload)
        manifest["browser_quality"] = quality
        _require(bool(quality.get("ok")), "Browser quality gate failed with unexplained errors.")

        manifest["artifact_sha256"] = _collect_artifact_hashes()

        manifest["overall_status"] = "PASS"
        manifest["local_decision"] = "PASS_PENDING_STEP12_CI"

    except Exception as exc:
        manifest["overall_status"] = "FAIL"
        manifest["local_decision"] = "NO-GO"
        manifest["error"] = str(exc)
        if not manifest.get("coverage"):
            manifest["coverage"] = coverage_payload

    # Always emit mandatory Step 11 artifacts.
    COVERAGE_PATH.write_text(json.dumps(manifest.get("coverage", coverage_payload), indent=2), encoding="utf-8")
    _write_report(manifest)

    manifest["artifact_sha256"] = {
        **manifest.get("artifact_sha256", {}),
        _portable(COVERAGE_PATH): _sha256_file(COVERAGE_PATH),
        _portable(REPORT_PATH): _sha256_file(REPORT_PATH),
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


def main() -> int:
    manifest = _run_step11()
    print(f"Wrote report: {REPORT_PATH}")
    print(f"Wrote coverage: {COVERAGE_PATH}")
    print(f"Wrote manifest: {MANIFEST_PATH}")
    print(f"Status: {manifest.get('overall_status')}")
    return 0 if manifest.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
