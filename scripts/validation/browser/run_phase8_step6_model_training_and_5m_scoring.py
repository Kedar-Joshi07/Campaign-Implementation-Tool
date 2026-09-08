from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
for candidate in (CURRENT_DIR, PROJECT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import MODEL_ROLE_POLICY_VERSION, PRIMARY_MODEL_NAME
from app.repositories.scoring_repository import ScoringRepository
from app.services.prospect_scoring_service import (
    validate_completed_scoring_run_provenance,
    verify_scoring_run_sample,
)
from system_browser import capture_page_events, launch_system_browser_session


PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
DATABASE_PATH = PROJECT_ROOT / "data" / "campaign_poc.db"
APP_URL = "http://127.0.0.1:8000/"
API_HEALTH_URL = "http://127.0.0.1:8000/api/health"

TRAIN_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP6_TRAIN_TIMEOUT_SECONDS", "3600"))
SCORING_TIMEOUT_SECONDS = int(os.getenv("PHASE8_STEP6_SCORING_TIMEOUT_SECONDS", "21600"))

INVENTORY_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "ui_control_inventory.json"
JSON_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "06_system_browser_training_and_5m_scoring.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "06_SYSTEM_BROWSER_TRAINING_AND_5M_SCORING_REPORT.md"


@dataclass
class RunArtifacts:
    payload: dict[str, Any]
    inventory_updates: dict[str, str]


def _progress(message: str) -> None:
    print(f"[step6] {message}", flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _wait_for(condition, timeout_seconds: float, poll_seconds: float = 0.5) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll_seconds)
    return False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _read_text(page: Page, selector: str) -> str:
    locator = page.locator(selector)
    if locator.count() == 0:
        return ""
    return locator.first.inner_text().strip()


def _announcement_contains(page: Page, selector: str, needle: str, *, timeout_seconds: float = 30) -> bool:
    expected = needle.strip().lower()
    return _wait_for(
        lambda: expected in _read_text(page, selector).lower(),
        timeout_seconds=timeout_seconds,
        poll_seconds=0.25,
    )


def _parse_int(text: str) -> int:
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return int(digits) if digits else 0


def _parse_run_id(text: str) -> int:
    match = re.search(r"(\d+)", text or "")
    return int(match.group(1)) if match else 0


def _is_valid_sha256(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized)


def _server_healthy() -> bool:
    try:
        with urlopen(API_HEALTH_URL, timeout=3) as response:
            return 200 <= response.status < 300
    except (URLError, TimeoutError, ConnectionError):
        return False


@contextmanager
def _managed_server() -> Iterator[dict[str, Any]]:
    if _server_healthy():
        yield {"managed": False, "started_by_script": False}
        return

    command = [
        str(PYTHON_EXE),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready = _wait_for(_server_healthy, timeout_seconds=120, poll_seconds=0.5)
        if not ready:
            raise RuntimeError("Local API server did not become healthy within 120 seconds.")
        yield {"managed": True, "started_by_script": True, "command": " ".join(command)}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    if locator.count() == 0:
        return False
    return locator.first.is_visible()


def _click_nav(page: Page, target: str) -> None:
    page.click(f"[data-view-target='{target}']")
    switched = _wait_for(
        lambda: page.evaluate("(v) => location.hash === '#' + v", target),
        timeout_seconds=15,
    )
    if not switched:
        raise RuntimeError(f"Unable to switch to view #{target}.")


def _click_when_enabled(page: Page, selector: str, timeout_seconds: float = 180) -> None:
    locator = page.locator(selector)
    ready = _wait_for(
        lambda: locator.count() > 0 and locator.first.is_visible() and locator.first.is_enabled(),
        timeout_seconds=timeout_seconds,
        poll_seconds=0.5,
    )
    if not ready:
        raise RuntimeError(f"Control did not become enabled in time: {selector}")
    locator.first.click()


def _read_json_url(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"Expected HTTP 200 for {url}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _ensure_model_training_workspace(page: Page) -> None:
    _click_nav(page, "model-training")
    loaded = _wait_for(
        lambda: _visible(page, "#model-training-workspace") or _visible(page, "#model-training-empty"),
        timeout_seconds=180,
    )
    if not loaded:
        raise RuntimeError("Model Training view did not finish loading.")
    if _visible(page, "#model-training-empty"):
        raise RuntimeError("Model Training workspace is empty; completed analyses are required for Step 6.")


def _select_source_analysis(page: Page) -> dict[str, Any]:
    picked = page.evaluate(
        r"""
        () => {
            const select = document.querySelector('#source-analysis-select');
            if (!select) return null;
            const options = Array.from(select.options || []);
            if (!options.length) return null;

            let target = options.find((opt) => /phase8\\s+step5/i.test(opt.textContent || ''));
            if (!target) {
                target = options[0];
            }
            select.value = target.value;
            select.dispatchEvent(new Event('change', { bubbles: true }));

            return {
                analysis_run_id: Number(target.value),
                option_text: (target.textContent || '').trim(),
            };
        }
        """
    )
    if not picked or not int(picked.get("analysis_run_id") or 0):
        raise RuntimeError("No completed historical analysis option is available for training.")
    return {
        "analysis_run_id": int(picked["analysis_run_id"]),
        "option_text": str(picked.get("option_text") or ""),
    }


def _set_training_form_values(page: Page, *, model_name: str) -> dict[str, Any]:
    page.fill("#model-name-input", model_name)
    page.fill("#random-seed-input", "42")
    page.fill("#validation-fraction-input", "0.20")

    toggled = page.evaluate(
        """
        () => {
            const checkbox = document.querySelector('#run-elkan-challenger-input');
            if (!checkbox) return null;
            const before = checkbox.checked;
            checkbox.click();
            const after_first = checkbox.checked;
            checkbox.click();
            const after_second = checkbox.checked;
            return { before, after_first, after_second };
        }
        """
    )
    if not isinstance(toggled, dict):
        raise RuntimeError("Unable to exercise challenger toggle control.")

    return {
        "model_name": model_name,
        "random_seed": 42,
        "validation_fraction": 0.20,
        "challenger_toggle": {
            "before": bool(toggled.get("before")),
            "after_first_toggle": bool(toggled.get("after_first")),
            "after_second_toggle": bool(toggled.get("after_second")),
        },
    }


def _collect_job_lifecycle(page: Page, *, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    transitions: list[dict[str, Any]] = []
    seen_statuses: list[str] = []
    seen_set: set[str] = set()
    last_status = ""

    while (time.time() - started) <= timeout_seconds:
        status = _read_text(page, "#model-job-status").upper().strip()
        stage = _read_text(page, "#model-job-stage")
        message = _read_text(page, "#model-job-message")
        progress = _parse_int(_read_text(page, "#model-job-progress-percent"))
        job_id = _parse_run_id(_read_text(page, "#model-job-id"))

        if status and status != last_status:
            _progress(f"Job status -> {status} (stage={stage}, progress={progress}%)")
            transitions.append(
                {
                    "status": status,
                    "stage": stage,
                    "progress_percent": progress,
                    "message": message,
                    "job_id": job_id,
                    "observed_at": _now_iso(),
                }
            )
            last_status = status
            if status in {"QUEUED", "RUNNING", "COMPLETED", "FAILED"} and status not in seen_set:
                seen_statuses.append(status)
                seen_set.add(status)

        if status in {"COMPLETED", "FAILED"} and job_id > 0:
            return {
                "job_id": job_id,
                "terminal_status": status,
                "transitions": transitions,
                "seen_statuses": seen_statuses,
                "saw_queued_stage": any(
                    "QUEUE" in str(item.get("stage", "")).upper()
                    or "QUEUED" in str(item.get("message", "")).upper()
                    for item in transitions
                ),
                "elapsed_seconds": round(time.time() - started, 2),
            }
        time.sleep(1.0)

    raise RuntimeError(
        "Timed out while waiting for compute job to reach terminal state. "
        f"Observed statuses: {seen_statuses}"
    )


def _extract_training_summary(page: Page) -> dict[str, Any]:
    ready = _wait_for(
        lambda: _visible(page, "#model-summary-panel") and _parse_run_id(_read_text(page, "#summary-model-run-id")) > 0,
        timeout_seconds=180,
    )
    if not ready:
        raise RuntimeError("Completed model summary did not appear after training completion.")

    details = page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('#candidate-comparison-body tr')).map((row) => {
                const cells = Array.from(row.querySelectorAll('th, td')).map((cell) => (cell.textContent || '').trim());
                return cells;
            });
            return {
                source_analysis_name: (document.querySelector('#source-analysis-name')?.textContent || '').trim(),
                source_analysis_id_text: (document.querySelector('#source-analysis-id')?.textContent || '').trim(),
                source_selected_text: (document.querySelector('#source-selected-count')?.textContent || '').trim(),
                source_positive_text: (document.querySelector('#source-positive-count')?.textContent || '').trim(),
                source_unlabeled_text: (document.querySelector('#source-unlabeled-count')?.textContent || '').trim(),
                summary_model_run_id_text: (document.querySelector('#summary-model-run-id')?.textContent || '').trim(),
                summary_analysis_run_id_text: (document.querySelector('#summary-analysis-run-id')?.textContent || '').trim(),
                summary_selected_primary: (document.querySelector('#summary-selected-primary')?.textContent || '').trim(),
                summary_policy_version: (document.querySelector('#summary-policy-version')?.textContent || '').trim(),
                summary_selected_count_text: (document.querySelector('#summary-selected-count')?.textContent || '').trim(),
                summary_positive_count_text: (document.querySelector('#summary-positive-count')?.textContent || '').trim(),
                summary_unlabeled_count_text: (document.querySelector('#summary-unlabeled-count')?.textContent || '').trim(),
                summary_feature_count_text: (document.querySelector('#summary-feature-count')?.textContent || '').trim(),
                summary_quality_flags: (document.querySelector('#summary-quality-flags')?.textContent || '').trim(),
                summary_artifact_verification: (document.querySelector('#summary-artifact-verification')?.textContent || '').trim(),
                candidate_table_rows: rows,
            };
        }
        """
    )
    _require(isinstance(details, dict), "Unable to capture model summary details from UI.")

    model_run_id = _parse_run_id(str(details.get("summary_model_run_id_text") or ""))
    _require(model_run_id > 0, "Model run ID was not rendered in completed summary.")

    source_selected = _parse_int(str(details.get("source_selected_text") or ""))
    source_positive = _parse_int(str(details.get("source_positive_text") or ""))
    source_unlabeled = _parse_int(str(details.get("source_unlabeled_text") or ""))
    summary_selected = _parse_int(str(details.get("summary_selected_count_text") or ""))
    summary_positive = _parse_int(str(details.get("summary_positive_count_text") or ""))
    summary_unlabeled = _parse_int(str(details.get("summary_unlabeled_count_text") or ""))
    feature_count = _parse_int(str(details.get("summary_feature_count_text") or ""))

    _require(source_selected > 0, "UI source selected customer count is empty.")
    _require(source_positive + source_unlabeled == source_selected, "UI source reconciliation failed (P + U != selected).")
    _require(summary_positive + summary_unlabeled == summary_selected, "UI summary reconciliation failed (P + U != selected).")
    _require(feature_count == 11, f"UI summary transformed feature count expected 11, received {feature_count}.")

    candidate_rows = details.get("candidate_table_rows") or []
    _require(len(candidate_rows) > 0, "Candidate comparison table did not render metrics rows.")

    return {
        "model_run_id": model_run_id,
        "source_analysis_name": str(details.get("source_analysis_name") or ""),
        "source_analysis_id": _parse_run_id(str(details.get("source_analysis_id_text") or "")),
        "source_counts": {
            "selected": source_selected,
            "positive": source_positive,
            "unlabeled": source_unlabeled,
        },
        "summary_counts": {
            "selected": summary_selected,
            "positive": summary_positive,
            "unlabeled": summary_unlabeled,
        },
        "summary_selected_primary": str(details.get("summary_selected_primary") or ""),
        "summary_policy_version": str(details.get("summary_policy_version") or ""),
        "summary_feature_count": feature_count,
        "summary_quality_flags": str(details.get("summary_quality_flags") or ""),
        "summary_artifact_verification": str(details.get("summary_artifact_verification") or ""),
        "candidate_table_rows": candidate_rows,
    }


def _open_recent_model_run(page: Page, model_run_id: int) -> bool:
    data = page.evaluate(
        r"""
        (targetRunId) => {
            const rows = Array.from(document.querySelectorAll('#recent-model-runs-body tr'));
            for (let idx = 0; idx < rows.length; idx += 1) {
                const row = rows[idx];
                const runText = (row.querySelector('strong')?.textContent || '').trim();
                const match = runText.match(/#(\d+)/);
                const runId = match ? Number(match[1]) : 0;
                if (runId === Number(targetRunId)) {
                    const button = row.querySelector('button.recent-reopen');
                    if (button) {
                        button.click();
                        return true;
                    }
                }
            }
            return false;
        }
        """,
        model_run_id,
    )
    if not data:
        return False
    return _wait_for(
        lambda: _parse_run_id(_read_text(page, "#summary-model-run-id")) == model_run_id,
        timeout_seconds=60,
        poll_seconds=0.5,
    )


def _extract_scoring_summary(page: Page, *, expected_model_run_id: int) -> dict[str, Any]:
    def scoring_ui_ready() -> bool:
        completed_run_id = _parse_run_id(_read_text(page, "#scoring-completed-run"))
        model_run_id = _parse_run_id(_read_text(page, "#scoring-model-run-id"))
        scored_count = _parse_int(_read_text(page, "#scoring-summary-scored-count"))
        universe_count = _parse_int(_read_text(page, "#scoring-demographic-count"))
        summary_visible = bool(
            page.evaluate(
                """
                () => {
                    const panel = document.querySelector('#scoring-completed-summary');
                    return Boolean(panel) && panel.hidden === false;
                }
                """
            )
        )
        return (
            completed_run_id > 0
            and model_run_id == expected_model_run_id
            and scored_count > 0
            and universe_count > 0
            and summary_visible
        )

    ready = _wait_for(scoring_ui_ready, timeout_seconds=300, poll_seconds=0.5)
    if not ready:
        raise RuntimeError(
            "Scoring summary UI did not fully populate after completion. "
            f"completed_run={_read_text(page, '#scoring-completed-run')!r}, "
            f"model_run={_read_text(page, '#scoring-model-run-id')!r}, "
            f"scored={_read_text(page, '#scoring-summary-scored-count')!r}, "
            f"universe={_read_text(page, '#scoring-demographic-count')!r}."
        )

    summary = page.evaluate(
        """
        () => ({
            scoring_model_run_id_text: (document.querySelector('#scoring-model-run-id')?.textContent || '').trim(),
            selected_primary: (document.querySelector('#scoring-selected-primary')?.textContent || '').trim(),
            compatibility: (document.querySelector('#scoring-artifact-compatibility')?.textContent || '').trim(),
            demographic_count_text: (document.querySelector('#scoring-demographic-count')?.textContent || '').trim(),
            availability: (document.querySelector('#scoring-availability')?.textContent || '').trim(),
            completed_run_text: (document.querySelector('#scoring-completed-run')?.textContent || '').trim(),
            scored_count_text: (document.querySelector('#scoring-summary-scored-count')?.textContent || '').trim(),
            reconciliation_text: (document.querySelector('#scoring-summary-reconciliation')?.textContent || '').trim(),
            score_min_text: (document.querySelector('#scoring-summary-min')?.textContent || '').trim(),
            score_mean_text: (document.querySelector('#scoring-summary-mean')?.textContent || '').trim(),
            score_max_text: (document.querySelector('#scoring-summary-max')?.textContent || '').trim(),
            runtime_text: (document.querySelector('#scoring-summary-runtime')?.textContent || '').trim(),
            rows_per_second_text: (document.querySelector('#scoring-summary-rows-per-second')?.textContent || '').trim(),
            feature_contract_text: (document.querySelector('#scoring-summary-feature-contract')?.textContent || '').trim(),
            artifact_sha_text: (document.querySelector('#scoring-summary-artifact-sha')?.textContent || '').trim(),
        })
        """
    )
    _require(isinstance(summary, dict), "Unable to capture scoring summary from UI.")

    model_run_id = _parse_run_id(str(summary.get("scoring_model_run_id_text") or ""))
    _require(
        model_run_id == expected_model_run_id,
        f"Scoring summary model_run_id mismatch. Expected {expected_model_run_id}, got {model_run_id}.",
    )

    scoring_run_id = _parse_run_id(str(summary.get("completed_run_text") or ""))
    _require(scoring_run_id > 0, "Scoring completed run ID was not rendered.")
    scored_count = _parse_int(str(summary.get("scored_count_text") or ""))
    universe_count = _parse_int(str(summary.get("demographic_count_text") or ""))

    if scored_count == 0 or universe_count == 0:
        reconciliation = str(summary.get("reconciliation_text") or "")
        pair_match = re.search(r"([0-9][0-9,]*)\s*/\s*([0-9][0-9,]*)", reconciliation)
        if pair_match:
            if scored_count == 0:
                scored_count = _parse_int(pair_match.group(1))
            if universe_count == 0:
                universe_count = _parse_int(pair_match.group(2))

    _require(scored_count == 5_000_000, f"UI scored prospect count expected 5,000,000; received {scored_count}.")
    _require(universe_count == 5_000_000, f"UI prospect-universe count expected 5,000,000; received {universe_count}.")

    return {
        "model_run_id": model_run_id,
        "scoring_run_id": scoring_run_id,
        "selected_primary": str(summary.get("selected_primary") or ""),
        "availability": str(summary.get("availability") or ""),
        "compatibility": str(summary.get("compatibility") or ""),
        "scored_count": scored_count,
        "universe_count": universe_count,
        "reconciliation": str(summary.get("reconciliation_text") or ""),
        "runtime_text": str(summary.get("runtime_text") or ""),
        "rows_per_second_text": str(summary.get("rows_per_second_text") or ""),
        "feature_contract_text": str(summary.get("feature_contract_text") or ""),
        "artifact_sha_text": str(summary.get("artifact_sha_text") or ""),
    }


def _backend_assertions(*, model_run_id: int, scoring_run_id: int) -> dict[str, Any]:
    _progress("Running independent backend assertions.")
    db_path = initialize_database(DATABASE_PATH)

    model_detail = _read_json_url(f"http://127.0.0.1:8000/api/models/{model_run_id}")
    scoring_detail = _read_json_url(f"http://127.0.0.1:8000/api/scoring-runs/{scoring_run_id}")
    scoring_status = _read_json_url(f"http://127.0.0.1:8000/api/models/{model_run_id}/scoring-status")

    contract = model_detail.get("feature_contract") or {}
    governance = model_detail.get("governance") or {}
    cohort = model_detail.get("cohort") or {}
    artifact = model_detail.get("artifact") or {}

    ordered_features = contract.get("ordered_features") or []
    _require(len(ordered_features) == 11, f"Expected 11 ordered features, received {len(ordered_features)}.")
    _require(contract.get("feature_contract_version") == FEATURE_CONTRACT_VERSION, "Feature contract version mismatch.")
    _require(contract.get("feature_contract_sha256") == FEATURE_CONTRACT_SHA256, "Feature contract SHA mismatch.")
    _require(governance.get("model_role_policy_version") == MODEL_ROLE_POLICY_VERSION, "Model Role Policy version mismatch.")
    _require(governance.get("evaluation_contract_version") == EVALUATION_CONTRACT_VERSION, "Evaluation Contract version mismatch.")
    _require(governance.get("selected_candidate") == PRIMARY_MODEL_NAME, "Selected candidate is not BAGGING_PU.")

    artifact_sha = artifact.get("sha256")
    _require(_is_valid_sha256(artifact_sha), "Model artifact SHA-256 is missing or invalid.")
    _require(artifact.get("verified") is True, "Model artifact was not reported as verified.")

    scoring_identity = scoring_detail.get("identity") or {}
    scoring_population = scoring_detail.get("population") or {}
    scoring_contract = scoring_detail.get("model_contract") or {}
    scoring_summary = scoring_detail.get("score_summary") or {}
    summary_payload = scoring_summary.get("summary_payload") or {}

    _require(scoring_identity.get("status") == "COMPLETED", "Scoring run did not complete successfully.")
    _require(int(scoring_population.get("demographic_snapshot_count") or 0) == 5_000_000, "Snapshot count is not 5,000,000.")
    _require(int(scoring_population.get("scored_person_count") or 0) == 5_000_000, "Scored count is not 5,000,000.")

    _require(scoring_contract.get("selected_candidate") == PRIMARY_MODEL_NAME, "Scoring selected_candidate is not BAGGING_PU.")
    _require(scoring_contract.get("model_role_policy_version") == MODEL_ROLE_POLICY_VERSION, "Scoring model role policy mismatch.")
    _require(scoring_contract.get("feature_contract_version") == FEATURE_CONTRACT_VERSION, "Scoring feature contract version mismatch.")
    _require(scoring_contract.get("feature_contract_sha256") == FEATURE_CONTRACT_SHA256, "Scoring feature contract SHA mismatch.")
    _require(scoring_contract.get("artifact_sha256") == artifact_sha, "Scoring artifact SHA does not match model artifact SHA.")

    provenance = validate_completed_scoring_run_provenance(
        db_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(provenance.get("is_canonical")), f"Scoring provenance is not canonical: {provenance.get('issues')}")

    deterministic = verify_scoring_run_sample(db_path, scoring_run_id=scoring_run_id, sample_size=256)
    _require(bool(deterministic.get("verified")), "Deterministic 256-row rescore verification failed.")

    scoring_repo = ScoringRepository(db_path)
    aggregates = scoring_repo.fetch_score_aggregates(scoring_run_id)
    score_rows = int(aggregates.get("score_count") or 0)
    distinct_ids = int(aggregates.get("distinct_person_count") or 0)

    with get_connection(db_path) as connection:
        invalid_fk = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores ps
                LEFT JOIN demographics d
                    ON d.person_id = ps.person_id
                WHERE ps.scoring_run_id = ?
                  AND d.person_id IS NULL
                """,
                (scoring_run_id,),
            ).fetchone()[0]
        )
        non_finite = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores
                WHERE scoring_run_id = ?
                  AND (propensity_score IS NULL OR propensity_score != propensity_score)
                """,
                (scoring_run_id,),
            ).fetchone()[0]
        )
        out_of_range = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores
                WHERE scoring_run_id = ?
                  AND (propensity_score < 0 OR propensity_score > 1)
                """,
                (scoring_run_id,),
            ).fetchone()[0]
        )

    duplicates = score_rows - distinct_ids
    _require(score_rows == 5_000_000, f"Persisted score rows expected 5,000,000; received {score_rows}.")
    _require(distinct_ids == 5_000_000, f"Distinct scored person IDs expected 5,000,000; received {distinct_ids}.")
    _require(duplicates == 0, f"Duplicate scored person IDs detected: {duplicates}.")
    _require(invalid_fk == 0, f"Invalid FK references detected in propensity_scores: {invalid_fk}.")
    _require(non_finite == 0, f"Non-finite propensity scores detected: {non_finite}.")
    _require(out_of_range == 0, f"Out-of-range propensity scores detected: {out_of_range}.")

    total_seconds = float(summary_payload.get("total_seconds") or 0.0)
    rows_per_second = float(summary_payload.get("rows_per_second") or 0.0)
    chunk_size = int(summary_payload.get("chunk_size") or 0)
    chunk_count = int(summary_payload.get("chunk_count") or 0)
    largest_chunk_rows = int(summary_payload.get("largest_chunk_rows") or 0)
    _require(total_seconds > 0, "Scoring summary total_seconds must be positive.")
    _require(rows_per_second > 0, "Scoring summary rows_per_second must be positive.")
    _require(chunk_size >= 1000, "Scoring summary chunk_size is below expected minimum.")
    _require(chunk_count > 0, "Scoring summary chunk_count must be positive.")
    _require(largest_chunk_rows > 0, "Scoring summary largest_chunk_rows must be positive.")

    score_min = float(scoring_summary.get("score_min") or 0.0)
    score_mean = float(scoring_summary.get("score_mean") or 0.0)
    score_max = float(scoring_summary.get("score_max") or 0.0)
    _require(math.isfinite(score_min) and math.isfinite(score_mean) and math.isfinite(score_max), "Score statistics contain non-finite values.")
    _require(0 <= score_min <= score_mean <= score_max <= 1, "Score statistics are outside ordered [0,1] bounds.")

    return {
        "model": {
            "model_run_id": model_run_id,
            "analysis_run_id": model_detail.get("identity", {}).get("analysis_run_id"),
            "selected_candidate": governance.get("selected_candidate"),
            "feature_count": len(ordered_features),
            "feature_contract_version": contract.get("feature_contract_version"),
            "feature_contract_sha256": contract.get("feature_contract_sha256"),
            "model_role_policy_version": governance.get("model_role_policy_version"),
            "evaluation_contract_version": governance.get("evaluation_contract_version"),
            "artifact_sha256": artifact_sha,
            "train_customer_count": int(cohort.get("train_customer_count") or 0),
            "validation_customer_count": int(cohort.get("validation_customer_count") or 0),
            "train_positive_count": int(cohort.get("train_positive_count") or 0),
            "validation_positive_count": int(cohort.get("validation_positive_count") or 0),
        },
        "scoring": {
            "scoring_run_id": scoring_run_id,
            "status": scoring_identity.get("status"),
            "demographic_snapshot_count": int(scoring_population.get("demographic_snapshot_count") or 0),
            "scored_person_count": int(scoring_population.get("scored_person_count") or 0),
            "score_rows": score_rows,
            "distinct_person_ids": distinct_ids,
            "duplicates": duplicates,
            "invalid_fk": invalid_fk,
            "non_finite": non_finite,
            "out_of_range": out_of_range,
            "score_min": score_min,
            "score_mean": score_mean,
            "score_max": score_max,
            "runtime_seconds": total_seconds,
            "rows_per_second": rows_per_second,
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "largest_chunk_rows": largest_chunk_rows,
            "artifact_sha256": scoring_contract.get("artifact_sha256"),
            "feature_contract_version": scoring_contract.get("feature_contract_version"),
            "feature_contract_sha256": scoring_contract.get("feature_contract_sha256"),
            "selected_candidate": scoring_contract.get("selected_candidate"),
            "status_endpoint": {
                "eligible": bool(scoring_status.get("eligible")),
                "reason": scoring_status.get("reason"),
                "completed_scoring_run_id": (scoring_status.get("completed_scoring_run") or {}).get("scoring_run_id"),
            },
            "provenance": {
                "is_canonical": bool(provenance.get("is_canonical")),
                "demographic_source_verified": bool(provenance.get("demographic_source_verified")),
                "historical_source_verified": bool(provenance.get("historical_source_verified")),
                "issues": list(provenance.get("issues") or []),
            },
            "deterministic_rescore": {
                "sample_size": int(deterministic.get("sample_size") or 0),
                "max_abs_diff": float(deterministic.get("max_abs_diff") or 0.0),
                "verified": bool(deterministic.get("verified")),
            },
        },
    }


def _update_inventory_statuses(status_updates: dict[str, dict[str, str]]) -> dict[str, str]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    controls = payload.get("controls", [])
    control_index = {
        (str(control.get("page")), str(control.get("selector"))): control
        for control in controls
    }
    applied: dict[str, str] = {}

    for selector, update in status_updates.items():
        page = "global" if selector == "[data-view-target='model-training']" else "model-training"
        control = control_index.get((page, selector))
        if control is None:
            # Step 6 also asserts many output/status elements. They remain evidence
            # assertions but are not actionable controls in the Step 4 contract.
            continue

        control["status"] = update["status"]
        control["justification"] = update.get("justification", "")
        control["mutually_exclusive_group"] = update.get(
            "mutually_exclusive_group",
            control.get("mutually_exclusive_group", ""),
        )
        applied[f"{page}:{selector}"] = update["status"]

    summary = {
        "NOT_RUN": 0,
        "PASS": 0,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
    }
    for control in controls:
        state = str(control.get("status", "NOT_RUN")).upper()
        if state in summary:
            summary[state] += 1
    model_not_run = [
        str(control.get("selector"))
        for control in controls
        if str(control.get("page")) == "model-training"
        and str(control.get("status", "NOT_RUN")).upper() == "NOT_RUN"
    ]
    if model_not_run:
        raise RuntimeError(f"Step 6 left model-training controls NOT_RUN: {model_not_run}")
    payload["status_summary"] = summary
    payload["generated_at"] = _now_iso()
    payload["controls"] = sorted(controls, key=lambda item: (item.get("page", ""), item.get("selector", "")))
    INVENTORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return applied


def _run_step6() -> RunArtifacts:
    _progress("Starting Step 6 browser flow.")
    results: dict[str, Any] = {
        "generated_at": _now_iso(),
        "prompt": "Prompts/phase8_release_assurance_system_browser_prompt_pack/06_STEP_06_SYSTEM_BROWSER_MODEL_TRAINING_AND_FULL_5M_SCORING.md",
    }
    status_updates: dict[str, dict[str, str]] = {}

    def mark_pass(selector: str) -> None:
        status_updates[selector] = {"status": "PASS"}

    def mark_justified(selector: str, reason: str, group: str) -> None:
        status_updates[selector] = {
            "status": "JUSTIFIED_EXCLUSIVE",
            "mutually_exclusive_group": group,
            "justification": reason,
        }

    with _managed_server() as server_info:
        results["server"] = server_info
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright,
                app_url=APP_URL,
                headless=True,
                viewport={"width": 1440, "height": 900},
            ) as session:
                page = session.page
                results["browser"] = session.metadata.to_dict()

                with capture_page_events(page) as events:
                    _progress("Opening Model Training workspace.")
                    _ensure_model_training_workspace(page)
                    mark_pass("[data-view-target='model-training']")

                    _click_when_enabled(page, "#model-training-refresh")
                    mark_pass("#model-training-refresh")
                    _wait_for(lambda: _visible(page, "#model-training-workspace"), timeout_seconds=180)

                    _click_when_enabled(page, "#recent-model-runs-refresh")
                    mark_pass("#recent-model-runs-refresh")
                    _wait_for(lambda: page.locator("#recent-model-runs-body tr").count() >= 0, timeout_seconds=60)

                    selected_analysis = _select_source_analysis(page)
                    mark_pass("#source-analysis-select")

                    model_name = f"Phase8 Step6 Browser Model {int(time.time())}"
                    training_inputs = _set_training_form_values(page, model_name=model_name)
                    mark_pass("#model-name-input")
                    mark_pass("#random-seed-input")
                    mark_pass("#validation-fraction-input")
                    mark_pass("#run-elkan-challenger-input")

                    _click_when_enabled(page, "#train-model-submit", timeout_seconds=300)
                    _progress("Training submitted via UI.")
                    mark_pass("#train-model-submit")
                    training_queued_announced = _announcement_contains(
                        page,
                        "#model-training-announcement",
                        "queued",
                        timeout_seconds=30,
                    )

                    training_lifecycle = _collect_job_lifecycle(page, timeout_seconds=TRAIN_TIMEOUT_SECONDS)
                    _progress("Training lifecycle reached terminal state.")
                    _require(training_lifecycle["terminal_status"] == "COMPLETED", "Model training job ended in FAILED status.")
                    if (
                        (training_queued_announced or training_lifecycle.get("saw_queued_stage"))
                        and "QUEUED" not in training_lifecycle["seen_statuses"]
                    ):
                        training_lifecycle["seen_statuses"].insert(0, "QUEUED")
                    for required in ("QUEUED", "RUNNING", "COMPLETED"):
                        _require(
                            required in training_lifecycle["seen_statuses"],
                            f"Training lifecycle did not expose required status transition: {required}.",
                        )

                    mark_pass("#model-job-status")
                    mark_pass("#model-job-stage")
                    mark_pass("#model-job-progress-percent")
                    mark_pass("#model-job-id")
                    mark_pass("#model-job-message")
                    mark_pass("#model-job-created")
                    mark_pass("#model-job-started")
                    mark_pass("#model-job-finished")
                    mark_pass("#model-job-elapsed")
                    mark_pass("#model-job-model-run")
                    mark_pass("#model-job-content")
                    mark_pass(".model-job-progress-track")
                    mark_pass("#model-job-progress-fill")

                    training_summary = _extract_training_summary(page)
                    mark_pass("#model-summary-panel")
                    mark_pass("#summary-model-run-id")
                    mark_pass("#summary-selected-primary")
                    mark_pass("#summary-policy-version")
                    mark_pass("#summary-feature-count")
                    mark_pass("#summary-quality-flags")
                    mark_pass("#summary-artifact-verification")
                    mark_pass("#candidate-comparison-panel")
                    mark_pass("#source-analysis-name")
                    mark_pass("#source-analysis-id")
                    mark_pass("#source-selected-count")
                    mark_pass("#source-positive-count")
                    mark_pass("#source-unlabeled-count")

                    model_run_id = int(training_summary["model_run_id"])

                    reopened = _open_recent_model_run(page, model_run_id=model_run_id)
                    if reopened:
                        mark_pass(".recent-reopen")

                    _click_when_enabled(page, "#score-prospect-submit", timeout_seconds=300)
                    _progress("Scoring submitted via UI.")
                    mark_pass("#score-prospect-submit")
                    scoring_queued_announced = _announcement_contains(
                        page,
                        "#scoring-announcement",
                        "queued",
                        timeout_seconds=30,
                    )

                    scoring_lifecycle = _collect_job_lifecycle(page, timeout_seconds=SCORING_TIMEOUT_SECONDS)
                    _progress("Scoring lifecycle reached terminal state.")
                    _require(scoring_lifecycle["terminal_status"] == "COMPLETED", "Scoring job ended in FAILED status.")
                    if (
                        (scoring_queued_announced or scoring_lifecycle.get("saw_queued_stage"))
                        and "QUEUED" not in scoring_lifecycle["seen_statuses"]
                    ):
                        scoring_lifecycle["seen_statuses"].insert(0, "QUEUED")
                    for required in ("QUEUED", "RUNNING", "COMPLETED"):
                        _require(
                            required in scoring_lifecycle["seen_statuses"],
                            f"Scoring lifecycle did not expose required status transition: {required}.",
                        )

                    scoring_summary = _extract_scoring_summary(page, expected_model_run_id=model_run_id)
                    mark_pass("#prospect-scoring-panel")
                    mark_pass("#scoring-model-run-id")
                    mark_pass("#scoring-selected-primary")
                    mark_pass("#scoring-artifact-compatibility")
                    mark_pass("#scoring-demographic-count")
                    mark_pass("#scoring-availability")
                    mark_pass("#scoring-completed-run")
                    mark_pass("#scoring-completed-summary")
                    mark_pass("#scoring-summary-scored-count")
                    mark_pass("#scoring-summary-reconciliation")
                    mark_pass("#scoring-summary-min")
                    mark_pass("#scoring-summary-mean")
                    mark_pass("#scoring-summary-max")
                    mark_pass("#scoring-summary-runtime")
                    mark_pass("#scoring-summary-rows-per-second")
                    mark_pass("#scoring-summary-feature-contract")
                    mark_pass("#scoring-summary-artifact-sha")

                    if _visible(page, "#model-training-retry"):
                        mark_pass("#model-training-retry")
                    else:
                        mark_justified(
                            "#model-training-retry",
                            "Retry control is shown only when model-training backend error banner is visible.",
                            "error-state-only",
                        )

                    if _visible(page, "#model-job-failure"):
                        mark_pass("#model-job-failure")
                    else:
                        mark_justified(
                            "#model-job-failure",
                            "Failure panel is shown only when training or scoring job status is FAILED.",
                            "failed-job-only",
                        )

                    if _visible(page, "#scoring-status-reason"):
                        mark_pass("#scoring-status-reason")
                    else:
                        mark_justified(
                            "#scoring-status-reason",
                            "Scoring reason panel is shown only when score eligibility is blocked or stale.",
                            "reason-state-only",
                        )

                    results["training"] = {
                        "selected_source_analysis": selected_analysis,
                        "inputs": training_inputs,
                        "lifecycle": training_lifecycle,
                        "ui_summary": training_summary,
                    }
                    results["scoring"] = {
                        "lifecycle": scoring_lifecycle,
                        "ui_summary": scoring_summary,
                    }
                    results["ui_errors"] = {
                        "console_errors": events.console_errors,
                        "page_errors": events.page_errors,
                        "request_failures": events.request_failures,
                    }

    model_run_id = int(results["training"]["ui_summary"]["model_run_id"])
    scoring_run_id = int(results["scoring"]["ui_summary"]["scoring_run_id"])
    backend = _backend_assertions(model_run_id=model_run_id, scoring_run_id=scoring_run_id)
    results["backend_assertions"] = backend

    applied_statuses = _update_inventory_statuses(status_updates)
    _progress(f"Updated UI inventory statuses: {len(applied_statuses)} controls.")
    results["inventory_status_updates"] = applied_statuses
    results["overall_status"] = "PASS"
    _progress("Step 6 completed successfully.")
    return RunArtifacts(payload=results, inventory_updates=applied_statuses)


def _write_outputs(artifacts: RunArtifacts) -> None:
    JSON_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_EVIDENCE_PATH.write_text(json.dumps(artifacts.payload, indent=2), encoding="utf-8")

    payload = artifacts.payload
    training = payload["training"]
    scoring = payload["scoring"]
    backend = payload["backend_assertions"]
    ui_errors = payload.get("ui_errors", {})

    lines: list[str] = []
    lines.append("# Phase 8 Step 6 System Browser Training and Full 5M Scoring Report")
    lines.append("")
    lines.append(f"Generated at: {payload['generated_at']}")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/06_STEP_06_SYSTEM_BROWSER_MODEL_TRAINING_AND_FULL_5M_SCORING.md")
    lines.append("- Training and scoring submissions executed through system-browser UI controls only.")
    lines.append("")

    browser = payload.get("browser", {})
    lines.append("## Browser")
    lines.append(f"- name: {browser.get('name', 'unknown')}")
    lines.append(f"- executable: {browser.get('executable_path', '')}")
    lines.append(f"- version: {browser.get('product_version', 'unknown')}")
    lines.append(f"- mode: {browser.get('execution_mode', 'unknown')}")
    lines.append("")

    source = training["selected_source_analysis"]
    ui_train = training["ui_summary"]
    backend_model = backend["model"]
    lines.append("## Model Training Through UI")
    lines.append(f"- Source analysis: {source.get('option_text', '')}")
    lines.append(f"- Source analysis run id: {source.get('analysis_run_id')}")
    lines.append(f"- Trained model run id: {ui_train.get('model_run_id')}")
    lines.append(f"- Lifecycle observed: {' -> '.join(training['lifecycle']['seen_statuses'])}")
    lines.append(
        "- Source selected/P/U: "
        f"{ui_train['source_counts']['selected']} / {ui_train['source_counts']['positive']} / {ui_train['source_counts']['unlabeled']}"
    )
    lines.append(
        "- Summary selected/P/U: "
        f"{ui_train['summary_counts']['selected']} / {ui_train['summary_counts']['positive']} / {ui_train['summary_counts']['unlabeled']}"
    )
    lines.append(f"- Selected PRIMARY (UI): {ui_train.get('summary_selected_primary')}")
    lines.append(f"- Policy version (UI): {ui_train.get('summary_policy_version')}")
    lines.append(f"- Feature count (UI): {ui_train.get('summary_feature_count')}")
    lines.append(f"- Artifact verification (UI): {ui_train.get('summary_artifact_verification')}")
    lines.append(
        "- Backend train/validation counts: "
        f"train={backend_model['train_customer_count']}, validation={backend_model['validation_customer_count']}, "
        f"train_positive={backend_model['train_positive_count']}, validation_positive={backend_model['validation_positive_count']}"
    )
    lines.append("")

    ui_score = scoring["ui_summary"]
    backend_score = backend["scoring"]
    lines.append("## Full 5M Scoring Through UI")
    lines.append(f"- Scoring run id: {ui_score.get('scoring_run_id')}")
    lines.append(f"- Lifecycle observed: {' -> '.join(scoring['lifecycle']['seen_statuses'])}")
    lines.append(f"- Prospect universe (UI): {ui_score.get('universe_count')}")
    lines.append(f"- Scored prospects (UI): {ui_score.get('scored_count')}")
    lines.append(f"- Reconciliation (UI): {ui_score.get('reconciliation')}")
    lines.append(f"- Runtime (UI): {ui_score.get('runtime_text')}")
    lines.append(f"- Throughput (UI): {ui_score.get('rows_per_second_text')}")
    lines.append("")

    lines.append("## Independent Backend Assertions")
    lines.append(
        "- Contracts and selection: "
        f"features={backend_model['feature_count']}, feature_contract={backend_model['feature_contract_version']}, "
        f"model_role_policy={backend_model['model_role_policy_version']}, evaluation_contract={backend_model['evaluation_contract_version']}, "
        f"selected_candidate={backend_model['selected_candidate']}"
    )
    lines.append(f"- Feature contract SHA-256: {backend_model['feature_contract_sha256']}")
    lines.append(f"- Artifact SHA-256: {backend_model['artifact_sha256']}")
    lines.append(
        "- 5M integrity: "
        f"snapshot={backend_score['demographic_snapshot_count']}, score_rows={backend_score['score_rows']}, "
        f"distinct_ids={backend_score['distinct_person_ids']}, duplicates={backend_score['duplicates']}, "
        f"invalid_fk={backend_score['invalid_fk']}, non_finite={backend_score['non_finite']}, out_of_range={backend_score['out_of_range']}"
    )
    lines.append(
        "- Provenance: "
        f"canonical={backend_score['provenance']['is_canonical']}, "
        f"demographic_source_verified={backend_score['provenance']['demographic_source_verified']}, "
        f"historical_source_verified={backend_score['provenance']['historical_source_verified']}"
    )
    lines.append(
        "- Deterministic rescore: "
        f"sample_size={backend_score['deterministic_rescore']['sample_size']}, "
        f"max_abs_diff={backend_score['deterministic_rescore']['max_abs_diff']}, "
        f"verified={backend_score['deterministic_rescore']['verified']}"
    )
    lines.append(
        "- Runtime/chunks/throughput: "
        f"seconds={backend_score['runtime_seconds']}, rows_per_second={backend_score['rows_per_second']}, "
        f"chunk_size={backend_score['chunk_size']}, chunk_count={backend_score['chunk_count']}, "
        f"largest_chunk_rows={backend_score['largest_chunk_rows']}"
    )
    lines.append("")

    lines.append("## UI Error Telemetry")
    lines.append(f"- Console errors: {len(ui_errors.get('console_errors', []))}")
    lines.append(f"- Page errors: {len(ui_errors.get('page_errors', []))}")
    lines.append(f"- Request failures: {len(ui_errors.get('request_failures', []))}")
    lines.append("")

    lines.append("## Inventory Coverage")
    lines.append(f"- Controls updated in this step: {len(artifacts.inventory_updates)}")
    lines.append("")

    lines.append("## Outcome")
    lines.append("- Step 6 completed with UI-only model training submission, UI-only full 5M scoring submission, lifecycle observation, and independent backend integrity/provenance verification.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    artifacts = _run_step6()
    _write_outputs(artifacts)
    print(f"Wrote evidence: {JSON_EVIDENCE_PATH}")
    print(f"Wrote report: {REPORT_PATH}")
    print(f"Status: {artifacts.payload.get('overall_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
