from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.validation.browser.check_ui_control_coverage import evaluate_inventory
except ModuleNotFoundError:
    from check_ui_control_coverage import evaluate_inventory  # type: ignore[no-redef]

PROMPT_PATH = (
    "Prompts/phase8_release_assurance_system_browser_prompt_pack/"
    "12_STEP_12_CI_GREEN_BRANCH_PROTECTION_AND_PHASE8_FREEZE.md"
)

PHASE8_DIR = PROJECT_ROOT / "docs" / "evidence" / "phase8"
OUTPUT_JSON = PHASE8_DIR / "12_ci_green_branch_protection_and_phase8_freeze.json"
FINAL_ACCEPTANCE_PATH = PHASE8_DIR / "PHASE8_FINAL_ACCEPTANCE.md"
CHECKLIST_JSON = PHASE8_DIR / "12_master_acceptance_checklist_run.json"
CHECKLIST_MD = PHASE8_DIR / "12_MASTER_ACCEPTANCE_CHECKLIST_RUN.md"

STEP11_MANIFEST = PHASE8_DIR / "final_system_browser" / "phase8_certification_manifest.json"
STEP10_EVIDENCE = PHASE8_DIR / "10_reproducibility_and_lfs_evidence.json"
STEP6_EVIDENCE = PHASE8_DIR / "06_system_browser_training_and_5m_scoring.json"
STEP5_EVIDENCE = PHASE8_DIR / "05_system_browser_historical_analysis.json"
STEP7_EVIDENCE = PHASE8_DIR / "07_system_browser_audience_explorer_all_controls.json"
STEP8_EVIDENCE = PHASE8_DIR / "08_system_browser_campaign_builder_and_exports.json"
STEP9_EVIDENCE = PHASE8_DIR / "09_browser_quality_evidence.json"
INVENTORY_PATH = PHASE8_DIR / "ui_control_inventory.json"
BRANCH_PROTECTION_DOC = PROJECT_ROOT / "docs" / "BRANCH_PROTECTION.md"
PROGRESS_TRACKER = (
    PROJECT_ROOT
    / "Prompts"
    / "phase8_release_assurance_system_browser_prompt_pack"
    / "02_PROGRESS_TRACKER.md"
)

DB_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"
LOCAL_RUNTIME_DIR = PROJECT_ROOT / "artifacts" / "phase8_step12_checks"

GITHUB_OWNER = "Kedar-Joshi07"
GITHUB_REPO = "Campaign-Implementation-Tool"
GITHUB_BRANCH = "main"
REQUIRED_CHECKS = [
    "Repository Hygiene",
    "Python Validation",
    "Tests",
    "Clean-Room Phase1-7",
    "Frontend Contract",
]


class Step12ValidationError(RuntimeError):
    """Raised when Step 12 automation encounters an unrecoverable issue."""


@dataclass(frozen=True)
class CommandSpec:
    key: str
    command: list[str]
    required_for_go: bool = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _portable(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _log(message: str) -> None:
    print(f"[step12] {message}", flush=True)


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
        raise Step12ValidationError(
            f"git {' '.join(args)} failed. stderr={(completed.stderr or '').strip()}"
        )
    return output


def _git_last_commit_for_path(path: Path) -> str | None:
    value = _git(["log", "-1", "--format=%H", "--", _portable(path)], strict=False)
    return value or None


def _phase8_starting_sha() -> str | None:
    if not PROGRESS_TRACKER.is_file():
        return None
    tracker = PROGRESS_TRACKER.read_text(encoding="utf-8")
    match = re.search(r"Starting SHA:\s*`([0-9a-f]{40})`", tracker, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _run_command(command: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
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
    duration = round(time.perf_counter() - started, 3)

    return {
        "command": " ".join(command),
        "returncode": returncode,
        "duration_seconds": duration,
        "passed": returncode == 0,
        "output_tail": lines[-40:],
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Step12ValidationError(f"Expected JSON object in {_portable(path)}")
    return payload


def _run_with_hard_timeout(func: Any, timeout_seconds: float, fallback: Any) -> Any:
    result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put((True, func()))
        except Exception as exc:  # pragma: no cover - defensive fallback path
            result_queue.put((False, exc))

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive() or result_queue.empty():
        return fallback

    ok, value = result_queue.get_nowait()
    return value if ok else fallback


def _try_get_json(url: str) -> dict[str, Any] | None:
    def _fetch() -> dict[str, Any] | None:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "phase8-step12-runner",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status != 200:
                    return None
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    return _run_with_hard_timeout(_fetch, timeout_seconds=25.0, fallback=None)


def _query_ci_status(candidate_sha: str, required_checks: list[str]) -> dict[str, Any]:
    workflow_runs_url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/ci.yml/runs"
        f"?branch={GITHUB_BRANCH}&per_page=20"
    )
    runs_payload = _try_get_json(workflow_runs_url)
    if not runs_payload:
        return {
            "available": False,
            "reason": "Unable to read GitHub Actions workflow runs API response.",
            "required_checks": {},
        }

    runs = runs_payload.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return {
            "available": False,
            "reason": "No CI workflow runs found for branch.",
            "required_checks": {},
        }

    matching_runs = [run for run in runs if str(run.get("head_sha") or "").lower() == candidate_sha.lower()]
    if not matching_runs:
        return {
            "available": True,
            "reason": "No CI workflow run found for the exact candidate SHA.",
            "candidate_sha": candidate_sha,
            "observed_head_shas": [run.get("head_sha") for run in runs],
            "required_checks": {
                name: {"found": False, "status": "UNKNOWN", "green": False}
                for name in required_checks
            },
            "required_all_green": False,
            "candidate_matches": False,
        }

    latest = matching_runs[0]
    run_id = latest.get("id")
    jobs_url = latest.get("jobs_url")

    checks: dict[str, Any] = {
        name: {"found": False, "status": "UNKNOWN", "green": False}
        for name in required_checks
    }

    jobs: list[dict[str, Any]] = []
    if isinstance(jobs_url, str) and jobs_url:
        jobs_payload = _try_get_json(jobs_url)
        if jobs_payload and isinstance(jobs_payload.get("jobs"), list):
            jobs = [item for item in jobs_payload["jobs"] if isinstance(item, dict)]

    for job in jobs:
        name = str(job.get("name") or "")
        if name not in checks:
            continue
        conclusion = str(job.get("conclusion") or "").upper() or "UNKNOWN"
        status = str(job.get("status") or "").upper() or "UNKNOWN"
        green = conclusion == "SUCCESS"
        checks[name] = {
            "found": True,
            "status": status,
            "conclusion": conclusion,
            "green": green,
            "html_url": job.get("html_url"),
        }

    candidate_matches = str(latest.get("head_sha") or "").lower() == candidate_sha.lower()
    required_all_green = (
        candidate_matches
        and str(latest.get("status") or "").upper() == "COMPLETED"
        and str(latest.get("conclusion") or "").upper() == "SUCCESS"
        and all(bool(info.get("green")) for info in checks.values())
    )

    return {
        "available": True,
        "workflow": "CI",
        "run_id": run_id,
        "run_number": latest.get("run_number"),
        "run_attempt": latest.get("run_attempt"),
        "status": latest.get("status"),
        "conclusion": latest.get("conclusion"),
        "head_sha": latest.get("head_sha"),
        "candidate_sha": candidate_sha,
        "candidate_matches": candidate_matches,
        "html_url": latest.get("html_url"),
        "required_checks": checks,
        "required_all_green": required_all_green,
    }


def _branch_protection_doc_complete() -> bool:
    if not BRANCH_PROTECTION_DOC.is_file():
        return False
    content = BRANCH_PROTECTION_DOC.read_text(encoding="utf-8")
    required_phrases = [
        "Require a pull request before merging",
        "Require status checks to pass before merging",
        "Require branches to be up to date before merging",
        "Do not allow bypassing the above settings",
        *REQUIRED_CHECKS,
    ]
    return all(phrase.casefold() in content.casefold() for phrase in required_phrases)


def _evaluate_branch_protection(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    required_status = (
        response.get("required_status_checks")
        if isinstance(response.get("required_status_checks"), dict)
        else {}
    )
    contexts = required_status.get("contexts") if isinstance(required_status.get("contexts"), list) else []
    checks = required_status.get("checks") if isinstance(required_status.get("checks"), list) else []
    configured_checks = {str(value) for value in contexts}
    configured_checks.update(
        str(value.get("context"))
        for value in checks
        if isinstance(value, dict) and value.get("context")
    )
    reviews = response.get("required_pull_request_reviews")
    enforce_admins = response.get("enforce_admins") if isinstance(response.get("enforce_admins"), dict) else {}
    api_settings_complete = bool(payload.get("available")) and all(
        (
            required_status,
            required_status.get("strict") is True,
            set(REQUIRED_CHECKS).issubset(configured_checks),
            isinstance(reviews, dict),
            enforce_admins.get("enabled") is True,
        )
    )
    documented_complete = _branch_protection_doc_complete()
    return {
        "api_settings_complete": api_settings_complete,
        "documented_complete": documented_complete,
        "acceptable": api_settings_complete or documented_complete,
        "configured_required_checks": sorted(configured_checks),
    }


def _query_branch_protection_status() -> dict[str, Any]:
    def _fetch() -> dict[str, Any]:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/branches/{GITHUB_BRANCH}/protection"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "phase8-step12-runner",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return {
                    "available": True,
                    "status_code": response.status,
                    "response": payload,
                    "used_fallback_doc": False,
                }
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "available": False,
                "status_code": exc.code,
                "error": body or str(exc),
                "used_fallback_doc": True,
                "fallback_doc": _portable(BRANCH_PROTECTION_DOC),
            }
        except Exception as exc:
            return {
                "available": False,
                "status_code": None,
                "error": str(exc),
                "used_fallback_doc": True,
                "fallback_doc": _portable(BRANCH_PROTECTION_DOC),
            }

    return _run_with_hard_timeout(
        _fetch,
        timeout_seconds=25.0,
        fallback={
            "available": False,
            "status_code": None,
            "error": "Timed out querying branch protection API.",
            "used_fallback_doc": True,
            "fallback_doc": _portable(BRANCH_PROTECTION_DOC),
        },
    )


def _parse_pytest_summary(output_tail: list[str]) -> dict[str, Any]:
    text = "\n".join(output_tail)
    match = re.search(r"(?P<passed>\d+)\s+passed(?:,\s+(?P<failed>\d+)\s+failed)?", text)
    if not match:
        return {"parsed": False}
    return {
        "parsed": True,
        "passed": int(match.group("passed") or 0),
        "failed": int(match.group("failed") or 0),
    }


def _collect_control_summary() -> dict[str, Any]:
    inventory = _read_json(INVENTORY_PATH)
    controls = inventory.get("controls", []) if isinstance(inventory.get("controls"), list) else []
    coverage_eval = evaluate_inventory(inventory)

    status_counts = {
        "PASS": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
        "FAIL": 0,
        "NOT_RUN": 0,
        "OTHER": 0,
    }
    justified_entries: list[dict[str, Any]] = []
    for control in controls:
        status = str(control.get("status") or "").upper()
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["OTHER"] += 1

        if status == "JUSTIFIED_EXCLUSIVE":
            justified_entries.append(
                {
                    "page": control.get("page"),
                    "selector": control.get("selector"),
                    "label": control.get("label"),
                    "mutually_exclusive_group": control.get("mutually_exclusive_group"),
                    "justification": control.get("justification"),
                }
            )

    return {
        "controls_discovered": len(controls),
        "status_counts": status_counts,
        "coverage_ok": bool(coverage_eval.get("ok")),
        "coverage_errors": coverage_eval.get("errors", []),
        "justified_entries": justified_entries,
    }


def _collect_db_integrity() -> dict[str, Any]:
    if not DB_PATH.is_file():
        return {"available": False, "reason": "Database file missing."}

    with sqlite3.connect(DB_PATH) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0]).strip().lower()
        counts = {
            "customers": int(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]),
            "campaign_sales": int(connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0]),
            "demographics": int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0]),
        }
        active_jobs = int(connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0])
        started_exports = int(
            connection.execute("SELECT COUNT(*) FROM campaign_export_events WHERE status='STARTED'").fetchone()[0]
        )

    return {
        "available": True,
        "pragma_integrity_check": integrity,
        "counts": counts,
        "active_jobs": active_jobs,
        "started_exports": started_exports,
        "integrity_ok": integrity == "ok",
    }


def _status_summary_complete(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return False
    return (
        int(summary.get("FAIL", -1)) == 0
        and int(summary.get("NOT_RUN", -1)) == 0
        and int(summary.get("PASS", 0)) + int(summary.get("JUSTIFIED_EXCLUSIVE", 0)) > 0
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _collect_phase8_references() -> dict[str, Any]:
    step5 = _read_json(STEP5_EVIDENCE) if STEP5_EVIDENCE.is_file() else {}
    step6 = _read_json(STEP6_EVIDENCE) if STEP6_EVIDENCE.is_file() else {}
    step7 = _read_json(STEP7_EVIDENCE) if STEP7_EVIDENCE.is_file() else {}
    step8 = _read_json(STEP8_EVIDENCE) if STEP8_EVIDENCE.is_file() else {}
    step9 = _read_json(STEP9_EVIDENCE) if STEP9_EVIDENCE.is_file() else {}
    step10 = _read_json(STEP10_EVIDENCE) if STEP10_EVIDENCE.is_file() else {}
    step11 = _read_json(STEP11_MANIFEST) if STEP11_MANIFEST.is_file() else {}

    quality_summary = step9.get("error_classification", {}).get("summary", {})
    quality_gate = step9.get("quality_gate", {})
    quality_failures = quality_gate.get("failures", {}) if isinstance(quality_gate, dict) else {}
    state_coverage = step9.get("state_coverage", {})
    export_states = state_coverage.get("export_state_coverage", {})
    job_states = state_coverage.get("job_state_coverage", {})
    scoring_lifecycle = step6.get("scoring", {}).get("lifecycle", {})

    audience_summary = step7.get("audience_inventory_status_summary", {})
    campaign_summary = step8.get("campaign_inventory_status_summary", {})
    accessibility_pass = (
        str(quality_gate.get("status") or "").upper() == "PASS"
        and quality_failures.get("accessibility") == []
    )
    responsive_pass = (
        str(quality_gate.get("status") or "").upper() == "PASS"
        and quality_failures.get("responsive") == []
        and bool(step9.get("responsive", {}).get("viewports"))
    )
    trackability_pass = (
        quality_failures.get("state_coverage") == []
        and all(bool(export_states.get(key)) for key in ("started_seen", "failed_and_aborted_seen", "completed_seen"))
        and all(bool(job_states.get(key)) for key in ("running_seen", "failed_seen"))
        and "RUNNING" in scoring_lifecycle.get("seen_statuses", [])
        and "COMPLETED" in scoring_lifecycle.get("seen_statuses", [])
        and float(scoring_lifecycle.get("elapsed_seconds") or 0.0) > 120.0
    )

    return {
        "step5_historical": {
            "run_id": step5.get("historical_runs", {}).get("narrow", {}).get("run_id"),
            "status": step5.get("overall_status"),
        },
        "step6_model": {
            "model_run_id": step6.get("backend_assertions", {}).get("model", {}).get("model_run_id"),
            "status": step6.get("overall_status"),
        },
        "step6_scoring": {
            "scoring_run_id": step6.get("backend_assertions", {}).get("scoring", {}).get("scoring_run_id"),
            "status": step6.get("overall_status"),
            "scored_person_count": step6.get("backend_assertions", {}).get("scoring", {}).get("scored_person_count"),
        },
        "step7_saved_audience": {
            "saved_audience_id": step7.get("saved_audience_flow", {}).get("saved_audience_id"),
            "saved_audience_name": step7.get("saved_audience_flow", {}).get("saved_audience_name"),
            "status": step7.get("overall_status"),
            "inventory_status_summary": audience_summary,
            "all_controls_complete": _status_summary_complete(audience_summary),
        },
        "step8_exports": {
            "email_checksum": step8.get("email_flow", {}).get("ui_export_event", {}).get("checksum"),
            "direct_mail_checksum": step8.get("direct_mail_flow", {}).get("ui_export_event", {}).get("checksum"),
            "email_campaign_id": step8.get("email_flow", {}).get("campaign_id"),
            "direct_mail_campaign_id": step8.get("direct_mail_flow", {}).get("campaign_id"),
            "status": step8.get("overall_status"),
            "inventory_status_summary": campaign_summary,
            "all_controls_complete": _status_summary_complete(campaign_summary),
        },
        "step9_browser_quality": {
            "browser": step9.get("browser", {}),
            "unexplained_console_total": _optional_int(quality_summary.get("unexplained_console_total")),
            "unexplained_critical_network_total": _optional_int(
                quality_summary.get("unexplained_critical_network_total")
            ),
            "quality_gate": quality_gate,
            "accessibility_pass": accessibility_pass,
            "responsive_pass": responsive_pass,
            "trackability_pass": trackability_pass,
            "state_coverage": state_coverage,
            "status": step9.get("overall_status"),
        },
        "step10_deterministic": {
            "status": step10.get("overall_status"),
            "non_lfs_large_files": len(step10.get("large_file_scan", {}).get("non_lfs_large_files", [])),
            "duplicate_nested_full_datasets": len(
                step10.get("large_file_scan", {}).get("duplicate_nested_full_datasets", [])
            ),
        },
        "step11_certification": {
            "status": step11.get("overall_status"),
            "clean_start_passed": step11.get("clean_start_gate", {}).get("passed"),
            "candidate_sha": step11.get("candidate", {}).get("sha"),
            "no_dirty_override": not bool(step11.get("clean_start_gate", {}).get("dirty_override")),
        },
    }


def _build_checklist_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    local = payload.get("local_regression", {})
    step_refs = payload.get("phase8_references", {})
    control = payload.get("control_coverage", {})
    ci = payload.get("github_ci", {})
    branch = payload.get("branch_protection", {})

    command_status = {item.get("key"): bool(item.get("passed")) for item in local.get("checks", [])}
    browser = step_refs.get("step9_browser_quality", {}).get("browser", {})
    browser_name = str(browser.get("name") or "").casefold()
    browser_executable = str(browser.get("executable_path") or "").casefold()
    is_system_browser = browser_name in {"chrome", "edge", "system_chrome", "system_edge"}
    is_not_embedded = is_system_browser and "code.exe" not in browser_executable and "vscode" not in browser_executable

    items: list[dict[str, Any]] = []

    def add(item_id: int, text: str, status: str, evidence: str, reason: str | None = None) -> None:
        entry: dict[str, Any] = {
            "id": item_id,
            "item": text,
            "status": status,
            "evidence": evidence,
        }
        if reason:
            entry["reason"] = reason
        items.append(entry)

    def pass_fail(condition: bool) -> str:
        return "PASS" if condition else "FAIL"

    add(1, "CI collection/dependency issue fixed", pass_fail(command_status.get("full_pytest", False)), _portable(OUTPUT_JSON))
    add(2, "Normal pytest collects only intended tests", pass_fail(command_status.get("full_pytest", False)), _portable(OUTPUT_JSON))
    add(
        3,
        "System Chrome or Edge used",
        pass_fail(is_system_browser),
        _portable(STEP9_EVIDENCE),
    )
    add(
        4,
        "No VS Code embedded browser used",
        pass_fail(is_not_embedded),
        _portable(STEP9_EVIDENCE),
    )
    add(
        5,
        "Browser product/version recorded",
        pass_fail(bool(step_refs.get("step9_browser_quality", {}).get("browser", {}).get("product_version"))),
        _portable(STEP9_EVIDENCE),
    )
    add(
        6,
        "Every reachable actionable control inventoried",
        pass_fail(bool(control.get("coverage_ok")) and control.get("controls_discovered", 0) > 0),
        _portable(INVENTORY_PATH),
    )
    add(
        7,
        "No generic reachable but not tested exception remains",
        pass_fail(
            bool(control.get("coverage_ok"))
            and control.get("status_counts", {}).get("NOT_RUN", -1) == 0
            and control.get("status_counts", {}).get("FAIL", -1) == 0
            and control.get("status_counts", {}).get("OTHER", -1) == 0
            and not control.get("coverage_errors")
        ),
        _portable(INVENTORY_PATH),
    )
    add(
        8,
        "Historical Analysis actually submitted through browser",
        pass_fail(str(step_refs.get("step5_historical", {}).get("status") or "").upper() == "PASS"),
        _portable(STEP5_EVIDENCE),
    )
    add(
        9,
        "Model Training actually submitted through browser",
        pass_fail(str(step_refs.get("step6_model", {}).get("status") or "").upper() == "PASS"),
        _portable(STEP6_EVIDENCE),
    )
    add(
        10,
        "Full 5M scoring actually submitted through browser",
        pass_fail(
            str(step_refs.get("step6_scoring", {}).get("status") or "").upper() == "PASS"
            and int(step_refs.get("step6_scoring", {}).get("scored_person_count") or 0) == 5_000_000
        ),
        _portable(STEP6_EVIDENCE),
    )
    add(
        11,
        "All Audience Explorer controls tested",
        pass_fail(
            str(step_refs.get("step7_saved_audience", {}).get("status") or "").upper() == "PASS"
            and bool(step_refs.get("step7_saved_audience", {}).get("all_controls_complete"))
        ),
        _portable(STEP7_EVIDENCE),
    )
    add(
        12,
        "All Campaign Builder controls tested",
        pass_fail(
            str(step_refs.get("step8_exports", {}).get("status") or "").upper() == "PASS"
            and bool(step_refs.get("step8_exports", {}).get("all_controls_complete"))
        ),
        _portable(STEP8_EVIDENCE),
    )
    add(13, "Email browser export tested", pass_fail(bool(step_refs.get("step8_exports", {}).get("email_checksum"))), _portable(STEP8_EVIDENCE))
    add(14, "Direct Mail browser export tested", pass_fail(bool(step_refs.get("step8_exports", {}).get("direct_mail_checksum"))), _portable(STEP8_EVIDENCE))
    console_total = step_refs.get("step9_browser_quality", {}).get("unexplained_console_total")
    network_total = step_refs.get("step9_browser_quality", {}).get("unexplained_critical_network_total")
    add(15, "Zero unexplained console errors", pass_fail(console_total is not None and console_total == 0), _portable(STEP9_EVIDENCE))
    add(16, "Zero unexplained critical network failures", pass_fail(network_total is not None and network_total == 0), _portable(STEP9_EVIDENCE))
    add(17, "Accessibility smoke passes", pass_fail(bool(step_refs.get("step9_browser_quality", {}).get("accessibility_pass"))), _portable(STEP9_EVIDENCE))
    add(18, "Responsive layouts pass", pass_fail(bool(step_refs.get("step9_browser_quality", {}).get("responsive_pass"))), _portable(STEP9_EVIDENCE))
    add(19, "Long-running jobs/exports remain trackable", pass_fail(bool(step_refs.get("step9_browser_quality", {}).get("trackability_pass"))), _portable(STEP9_EVIDENCE))
    add(20, "GZIP reproducibility addressed", pass_fail(str(step_refs.get("step10_deterministic", {}).get("status") or "").upper() == "PASS"), _portable(STEP10_EVIDENCE))
    add(21, "Absolute machine paths removed from canonical summaries", pass_fail(str(step_refs.get("step10_deterministic", {}).get("status") or "").upper() == "PASS"), _portable(STEP10_EVIDENCE))
    add(22, "LFS/hash docs current", pass_fail(command_status.get("deterministic_generation_hash_checks", False)), _portable(OUTPUT_JSON))
    add(23, "Final certification begins from clean HEAD", pass_fail(bool(step_refs.get("step11_certification", {}).get("clean_start_passed"))), _portable(STEP11_MANIFEST))
    add(24, "Full pytest passes", pass_fail(command_status.get("full_pytest", False)), _portable(OUTPUT_JSON))
    add(25, "Clean-room passes", pass_fail(command_status.get("clean_room_phase1_to_phase7", False)), _portable(OUTPUT_JSON))

    ci_green = bool(ci.get("required_all_green"))
    add(
        26,
        "Required GitHub CI checks all green",
        pass_fail(ci_green),
        str(ci.get("html_url") or "GitHub CI unavailable"),
        None if ci_green else str(ci.get("reason") or "Required checks are not all green."),
    )

    branch_ok = bool(branch.get("evaluation", {}).get("acceptable"))
    add(
        27,
        "Branch protection enabled or fully documented",
        pass_fail(branch_ok),
        _portable(BRANCH_PROTECTION_DOC),
        None if branch_ok else "Unable to verify protection and fallback doc missing.",
    )

    final_go = all(item["status"] == "PASS" for item in items)
    add(28, "Final Phase 8 decision GO", "PASS" if final_go else "FAIL", _portable(FINAL_ACCEPTANCE_PATH), None if final_go else "One or more required gates failed.")

    return items


def _write_checklist_artifacts(items: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "pass": sum(1 for item in items if item["status"] == "PASS"),
        "fail": sum(1 for item in items if item["status"] == "FAIL"),
        "pending": sum(1 for item in items if item["status"] == "PENDING"),
    }
    decision = "GO" if totals["fail"] == 0 and totals["pending"] == 0 else "NO_GO"

    checklist_json = {
        "generated_at": _now_iso(),
        "source_checklist": "Prompts/phase8_release_assurance_system_browser_prompt_pack/01_MASTER_ACCEPTANCE_CHECKLIST.md",
        "decision": decision,
        "totals": totals,
        "items": items,
    }
    CHECKLIST_JSON.write_text(json.dumps(checklist_json, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Phase 8 Master Acceptance Checklist Run (Step 12)")
    lines.append("")
    lines.append(f"Generated at: {checklist_json['generated_at']}")
    lines.append(f"Decision: {decision}")
    lines.append("")
    lines.append("## Item Results")
    lines.append("")
    for item in items:
        lines.append(f"{item['id']}. {item['item']}: {item['status']}")
        lines.append(f"Evidence: {item['evidence']}")
        if item.get("reason"):
            lines.append(f"Reason: {item['reason']}")
        lines.append("")

    lines.append("## Totals")
    lines.append(f"- PASS: {totals['pass']}")
    lines.append(f"- FAIL: {totals['fail']}")
    lines.append(f"- PENDING: {totals['pending']}")

    CHECKLIST_MD.write_text("\n".join(lines), encoding="utf-8")
    return checklist_json


def _write_final_acceptance(payload: dict[str, Any], checklist: dict[str, Any]) -> None:
    local = payload.get("local_regression", {})
    refs = payload.get("phase8_references", {})
    control = payload.get("control_coverage", {})
    ci = payload.get("github_ci", {})
    db = payload.get("db_integrity", {})

    step9_browser = refs.get("step9_browser_quality", {}).get("browser", {})

    lines: list[str] = []
    lines.append("# Phase 8 Final Acceptance")
    lines.append("")
    lines.append(f"Generated at: {payload.get('generated_at')}")
    lines.append(f"Prompt: {PROMPT_PATH}")
    lines.append("")
    lines.append("## Final Report")
    lines.append("")

    report_items = [
        (1, "starting SHA", payload.get("sha_chain", {}).get("starting_sha")),
        (2, "CI-fix SHA", payload.get("sha_chain", {}).get("ci_fix_sha")),
        (3, "browser-harness SHA", payload.get("sha_chain", {}).get("browser_harness_sha")),
        (4, "certification candidate SHA", payload.get("sha_chain", {}).get("certification_candidate_sha")),
        (5, "final implementation SHA", payload.get("sha_chain", {}).get("final_implementation_sha")),
        (6, "optional closure SHA", payload.get("sha_chain", {}).get("optional_closure_sha")),
        (7, "browser product/version", f"{step9_browser.get('name')} / {step9_browser.get('product_version')}"),
        (8, "controls discovered", control.get("controls_discovered")),
        (9, "PASS", control.get("status_counts", {}).get("PASS")),
        (10, "JUSTIFIED_EXCLUSIVE", control.get("status_counts", {}).get("JUSTIFIED_EXCLUSIVE")),
        (11, "FAIL", control.get("status_counts", {}).get("FAIL")),
        (12, "Historical Analysis browser run", refs.get("step5_historical")),
        (13, "Model browser run", refs.get("step6_model")),
        (14, "5M scoring browser run", refs.get("step6_scoring")),
        (15, "saved audience", refs.get("step7_saved_audience")),
        (16, "Email export checksum", refs.get("step8_exports", {}).get("email_checksum")),
        (17, "Direct Mail export checksum", refs.get("step8_exports", {}).get("direct_mail_checksum")),
        (
            18,
            "console/network result",
            {
                "unexplained_console_total": refs.get("step9_browser_quality", {}).get("unexplained_console_total"),
                "unexplained_critical_network_total": refs.get("step9_browser_quality", {}).get(
                    "unexplained_critical_network_total"
                ),
            },
        ),
        (19, "DB integrity", db),
        (20, "pytest count", local.get("pytest_summary")),
        (
            21,
            "clean-room result",
            next((item for item in local.get("checks", []) if item.get("key") == "clean_room_phase1_to_phase7"), None),
        ),
        (22, "CI checks", ci),
        (23, "branch protection", payload.get("branch_protection")),
        (24, "deterministic GZIP result", refs.get("step10_deterministic")),
        (
            25,
            "LFS result",
            next((item for item in local.get("checks", []) if item.get("key") == "deterministic_generation_hash_checks"), None),
        ),
        (26, "no dirty override", refs.get("step11_certification", {}).get("no_dirty_override")),
        (27, "FINAL DECISION", payload.get("final_decision")),
    ]

    for index, label, value in report_items:
        lines.append(f"{index}. {label}: {value}")
    lines.append("")

    lines.append("## Local Regression Checks")
    lines.append("")
    for check in local.get("checks", []):
        lines.append(
            f"- {check.get('key')}: {'PASS' if check.get('passed') else 'FAIL'} "
            f"(returncode={check.get('returncode')}, duration={check.get('duration_seconds')}s)"
        )
    lines.append("")

    lines.append("## Acceptance Checklist")
    lines.append("")
    lines.append(f"- Decision: {checklist.get('decision')}")
    lines.append(f"- PASS: {checklist.get('totals', {}).get('pass')}")
    lines.append(f"- FAIL: {checklist.get('totals', {}).get('fail')}")
    lines.append(f"- PENDING: {checklist.get('totals', {}).get('pending')}")

    FINAL_ACCEPTANCE_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_step12() -> dict[str, Any]:
    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.is_file():
        python_exe = Path(sys.executable)

    sha_now = _git(["rev-parse", "HEAD"])
    git_status = _git(["status", "--short"]).splitlines()

    sha_chain = {
        "starting_sha": _phase8_starting_sha(),
        "ci_fix_sha": _git_last_commit_for_path(PHASE8_DIR / "02_CI_DISCOVERY_FIX_REPORT.md"),
        "browser_harness_sha": _git_last_commit_for_path(PHASE8_DIR / "03_SYSTEM_BROWSER_HARNESS_REPORT.md"),
        "certification_candidate_sha": None,
        "final_implementation_sha": sha_now,
        "optional_closure_sha": None,
    }

    if STEP11_MANIFEST.is_file():
        try:
            step11 = _read_json(STEP11_MANIFEST)
            sha_chain["certification_candidate_sha"] = step11.get("candidate", {}).get("sha")
        except Exception:
            pass

    commands = [
        CommandSpec("full_pytest", [str(python_exe), "-m", "pytest", "-vv"]),
        CommandSpec(
            "clean_room_phase1_to_phase7",
            [
                str(python_exe),
                str(PROJECT_ROOT / "scripts" / "validation" / "run_cleanroom_phase1_to_phase7.py"),
                "--report-path",
                str(LOCAL_RUNTIME_DIR / "CLEANROOM_PHASE1_TO_PHASE7_REPORT.md"),
                "--json-path",
                str(LOCAL_RUNTIME_DIR / "cleanroom_phase1_to_phase7.json"),
            ],
        ),
        CommandSpec(
            "system_browser_harness_unit_tests",
            [
                str(python_exe),
                "-m",
                "pytest",
                "-q",
                "tests/test_system_browser_harness.py",
                "tests/test_ui_control_coverage_contract.py",
            ],
        ),
        CommandSpec(
            "control_coverage_checker",
            [
                str(python_exe),
                str(PROJECT_ROOT / "scripts" / "validation" / "browser" / "check_ui_control_coverage.py"),
                "--inventory",
                str(INVENTORY_PATH),
            ],
        ),
        CommandSpec("compileall", [str(python_exe), "-m", "compileall", "-q", "app", "scripts", "tests"]),
        CommandSpec("pip_check", [str(python_exe), "-m", "pip", "check"]),
        CommandSpec("git_diff_check", ["git", "diff", "--check"]),
        CommandSpec("repository_hygiene", [str(python_exe), str(PROJECT_ROOT / "scripts" / "validation" / "validate_ci_hygiene.py")]),
        CommandSpec("current_data_validation", [str(python_exe), str(PROJECT_ROOT / "scripts" / "validate_data.py"), "--json"]),
        CommandSpec(
            "deterministic_generation_hash_checks",
            [str(python_exe), str(PROJECT_ROOT / "scripts" / "validation" / "browser" / "run_phase8_step10_reproducibility_and_lfs.py")],
        ),
    ]

    checks: list[dict[str, Any]] = []
    for spec in commands:
        _log(f"Running local check: {spec.key}")
        result = _run_command(spec.command)
        result["key"] = spec.key
        result["required_for_go"] = spec.required_for_go
        checks.append(result)

    full_pytest = next((item for item in checks if item.get("key") == "full_pytest"), {})
    pytest_summary = _parse_pytest_summary(full_pytest.get("output_tail", []))

    _log("Collecting control coverage summary.")
    control_summary = _collect_control_summary()
    _log("Collecting database integrity summary.")
    db_integrity = _collect_db_integrity()
    _log("Querying branch protection status.")
    branch_protection = _query_branch_protection_status()
    branch_protection["evaluation"] = _evaluate_branch_protection(branch_protection)
    required_ci_checks = sorted(
        set(REQUIRED_CHECKS)
        | set(branch_protection["evaluation"].get("configured_required_checks", []))
    )
    _log("Querying GitHub CI status for the exact candidate SHA.")
    ci_status = _query_ci_status(sha_now, required_ci_checks)
    _log("Collecting Phase 8 step reference evidence.")
    phase8_refs = _collect_phase8_references()

    required_local_pass = all(bool(item.get("passed")) for item in checks if item.get("required_for_go"))
    step11_pass = str(phase8_refs.get("step11_certification", {}).get("status") or "").upper() == "PASS"
    ci_green = bool(ci_status.get("required_all_green")) and bool(ci_status.get("candidate_matches"))
    coverage_good = bool(control_summary.get("coverage_ok"))

    final_go = required_local_pass and step11_pass and ci_green and coverage_good

    payload = {
        "generated_at": _now_iso(),
        "prompt": PROMPT_PATH,
        "sha_chain": sha_chain,
        "git": {
            "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "head_sha": sha_now,
            "status_short": git_status,
            "clean_head": len(git_status) == 0,
        },
        "execution_policy": {
            "full_5m_scoring_rerun": False,
            "step6_runner_invoked": False,
            "note": "Step 12 consumes the completed Step 6/11 evidence and does not rerun full 5M scoring.",
        },
        "local_regression": {
            "checks": checks,
            "required_local_pass": required_local_pass,
            "pytest_summary": pytest_summary,
        },
        "control_coverage": control_summary,
        "db_integrity": db_integrity,
        "github_ci": ci_status,
        "branch_protection": branch_protection,
        "phase8_references": phase8_refs,
        "final_decision": "GO" if final_go else "NO_GO",
        "go_conditions": {
            "local_regression_green": required_local_pass,
            "step11_certification_pass": step11_pass,
            "required_ci_green": ci_green,
            "control_coverage_green": coverage_good,
        },
    }

    items = _build_checklist_items(payload)
    checklist = _write_checklist_artifacts(items)
    _write_final_acceptance(payload, checklist)

    payload["artifacts"] = {
        "final_acceptance": _portable(FINAL_ACCEPTANCE_PATH),
        "checklist_json": _portable(CHECKLIST_JSON),
        "checklist_md": _portable(CHECKLIST_MD),
    }
    payload["artifact_sha256"] = {
        _portable(FINAL_ACCEPTANCE_PATH): _sha256_file(FINAL_ACCEPTANCE_PATH),
        _portable(CHECKLIST_JSON): _sha256_file(CHECKLIST_JSON),
        _portable(CHECKLIST_MD): _sha256_file(CHECKLIST_MD),
    }

    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return payload


def main() -> int:
    PHASE8_DIR.mkdir(parents=True, exist_ok=True)
    payload = run_step12()
    print(f"Wrote Step 12 JSON: {OUTPUT_JSON}")
    print(f"Wrote final acceptance: {FINAL_ACCEPTANCE_PATH}")
    print(f"Wrote checklist JSON: {CHECKLIST_JSON}")
    print(f"Wrote checklist report: {CHECKLIST_MD}")
    print(f"Final decision: {payload.get('final_decision')}")
    return 0 if payload.get("final_decision") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
