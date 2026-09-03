import json
import sqlite3
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dependencies import get_database_path
from app.main import app
from app.services.prospect_scoring_service import (
    validate_completed_scoring_run_provenance,
    verify_scoring_run_sample,
)

DB_PATH = Path("data/campaign_poc.db")
REPORT_PATH = Path("logs/phase5_prephase6_step3_rerun_report.json")


def _fetchone(query: str, params: tuple = ()) -> dict:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(query, params).fetchone()
        return dict(row) if row is not None else {}
    finally:
        con.close()


def _fetch_score_quality(scoring_run_id: int) -> dict:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            SELECT
                COUNT(*) AS score_rows,
                COUNT(DISTINCT person_id) AS distinct_person_ids,
                SUM(CASE WHEN propensity_score != propensity_score THEN 1 ELSE 0 END) AS nonfinite,
                SUM(CASE WHEN propensity_score < 0 THEN 1 ELSE 0 END) AS below_zero,
                SUM(CASE WHEN propensity_score > 1 THEN 1 ELSE 0 END) AS above_one,
                MIN(propensity_score) AS score_min,
                AVG(propensity_score) AS score_mean,
                MAX(propensity_score) AS score_max
            FROM propensity_scores
            WHERE scoring_run_id = ?
            """,
            (scoring_run_id,),
        ).fetchone()
        fk_row = con.execute(
            """
            SELECT COUNT(*) AS invalid_fk
            FROM propensity_scores ps
            LEFT JOIN demographics d ON d.person_id = ps.person_id
            WHERE ps.scoring_run_id = ? AND d.person_id IS NULL
            """,
            (scoring_run_id,),
        ).fetchone()
    finally:
        con.close()

    result = dict(row)
    result["invalid_fk"] = int(fk_row["invalid_fk"])
    result["duplicate_person_ids"] = int(result["score_rows"] - result["distinct_person_ids"])
    return result


def _latest_completed_demographic_import() -> dict:
    return _fetchone(
        """
        SELECT import_id, source_checksum, rows_inserted, status
        FROM data_import_runs
        WHERE dataset_name = 'demographics'
        ORDER BY import_id DESC
        LIMIT 1
        """
    )


def _completed_model_candidates() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT model_run_id, analysis_run_id, selected_candidate, status, artifact_sha256
            FROM model_runs
            WHERE status = 'COMPLETED'
            ORDER BY model_run_id DESC
            """
        ).fetchall()
        candidates: list[dict] = []
        for row in rows:
            completed_scoring_count = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM scoring_runs
                    WHERE model_run_id = ? AND status = 'COMPLETED'
                    """,
                    (int(row["model_run_id"]),),
                ).fetchone()[0]
            )
            candidate = dict(row)
            candidate["completed_scoring_count"] = completed_scoring_count
            candidates.append(candidate)
        return candidates
    finally:
        con.close()


def main() -> int:
    app.dependency_overrides[get_database_path] = lambda: DB_PATH

    db_size_before = DB_PATH.stat().st_size
    latest_import = _latest_completed_demographic_import()
    if not latest_import:
        raise RuntimeError("No demographics import found")

    model_row: dict | None = None
    selected_status_before: dict | None = None
    selected_model_detail: dict | None = None
    model_candidates = _completed_model_candidates()
    if not model_candidates:
        raise RuntimeError("No completed model run found")

    polling: list[dict] = []

    try:
        with TestClient(app) as client:
            for candidate in model_candidates:
                candidate_model_run_id = int(candidate["model_run_id"])
                status_before = client.get(f"/api/models/{candidate_model_run_id}/scoring-status")
                if status_before.status_code != 200:
                    continue
                status_payload = status_before.json()
                if not status_payload.get("artifact_feature_compatible"):
                    continue
                if status_payload.get("feature_contract_version") != "1":
                    continue
                if status_payload.get("selected_candidate") != "BAGGING_PU":
                    continue
                if int(candidate.get("completed_scoring_count", 0)) != 0:
                    continue

                model_detail = client.get(f"/api/models/{candidate_model_run_id}")
                if model_detail.status_code != 200:
                    continue
                model_detail_payload = model_detail.json()
                governance = model_detail_payload.get("governance", {})
                if str(governance.get("model_role_policy_version")) != "2":
                    continue
                if str(governance.get("evaluation_contract_version")) != "2":
                    continue

                if not status_payload.get("eligible"):
                    continue

                model_row = candidate
                selected_status_before = status_payload
                selected_model_detail = model_detail_payload
                break

            if model_row is None or selected_status_before is None or selected_model_detail is None:
                raise RuntimeError("No eligible completed BAGGING_PU model found for canonical rerun")

            model_run_id = int(model_row["model_run_id"])
            analysis_run_id = int(model_row["analysis_run_id"])

            submit = client.post(f"/api/models/{model_run_id}/score")
            if submit.status_code != 202:
                raise RuntimeError(f"Submit failed: {submit.status_code} {submit.text}")
            submit_payload = submit.json()
            job_id = int(submit_payload["job_id"])

            # Active conflict checks while run is in progress.
            second_submit_status = client.post(f"/api/models/{model_run_id}/score").status_code
            train_submit_status = client.post(
                "/api/models/train",
                json={"analysis_run_id": analysis_run_id},
            ).status_code

            deadline = time.time() + 60 * 90
            final_job = None
            while time.time() < deadline:
                job = client.get(f"/api/jobs/{job_id}")
                job.raise_for_status()
                payload = job.json()
                polling.append(
                    {
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "status": payload.get("status"),
                        "progress_percent": payload.get("progress_percent"),
                        "stage": payload.get("stage"),
                    }
                )
                if payload.get("status") in {"COMPLETED", "FAILED"}:
                    final_job = payload
                    break
                time.sleep(5)

            if final_job is None:
                raise RuntimeError("Timed out waiting for scoring job completion")
            if final_job.get("status") != "COMPLETED":
                raise RuntimeError(f"Scoring job failed: {final_job}")

            scoring_run_id = int(final_job["result"]["scoring_run_id"])
            detail = client.get(f"/api/scoring-runs/{scoring_run_id}")
            detail.raise_for_status()
            detail_payload = detail.json()
            status_after = client.get(f"/api/models/{model_run_id}/scoring-status")
            status_after.raise_for_status()
            status_after_payload = status_after.json()

    finally:
        app.dependency_overrides.clear()

    db_size_after = DB_PATH.stat().st_size

    scoring_row = _fetchone(
        """
        SELECT scoring_run_id, job_id, model_run_id, status, demographic_snapshot_count,
               scored_person_count, chunk_size, created_at, completed_at, score_summary_json
        FROM scoring_runs
        WHERE scoring_run_id = ?
        """,
        (scoring_run_id,),
    )
    summary_payload = json.loads(scoring_row["score_summary_json"])
    score_quality = _fetch_score_quality(scoring_run_id)

    sample_verify = verify_scoring_run_sample(
        DB_PATH,
        scoring_run_id=scoring_run_id,
        sample_size=256,
    )
    provenance_validation = validate_completed_scoring_run_provenance(
        DB_PATH,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )

    report = {
        "preflight": {
            "database_path": str(DB_PATH),
            "database_size_before": db_size_before,
            "latest_demographic_import": latest_import,
            "candidate_models": model_candidates,
            "model": model_row,
            "model_detail": {
                "identity": selected_model_detail.get("identity"),
                "governance": selected_model_detail.get("governance"),
                "feature_contract": selected_model_detail.get("feature_contract"),
                "artifact": selected_model_detail.get("artifact"),
            },
            "status_before": selected_status_before,
        },
        "submit": submit_payload,
        "conflict_checks": {
            "second_scoring_submit_status": second_submit_status,
            "training_submit_status": train_submit_status,
        },
        "polling": polling,
        "job_terminal": final_job,
        "scoring_row": {
            "scoring_run_id": scoring_row["scoring_run_id"],
            "job_id": scoring_row["job_id"],
            "model_run_id": scoring_row["model_run_id"],
            "status": scoring_row["status"],
            "demographic_snapshot_count": scoring_row["demographic_snapshot_count"],
            "scored_person_count": scoring_row["scored_person_count"],
            "chunk_size": scoring_row["chunk_size"],
            "created_at": scoring_row["created_at"],
            "completed_at": scoring_row["completed_at"],
        },
        "score_summary": summary_payload,
        "score_quality": score_quality,
        "detail_identity": detail_payload.get("identity"),
        "detail_population": detail_payload.get("population"),
        "detail_model_contract": detail_payload.get("model_contract"),
        "detail_score_summary": detail_payload.get("score_summary"),
        "status_after": status_after_payload,
        "sample_verification": sample_verify,
        "provenance_validation": provenance_validation,
        "postflight": {
            "database_size_after": db_size_after,
            "database_growth_bytes": db_size_after - db_size_before,
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"report_written={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
