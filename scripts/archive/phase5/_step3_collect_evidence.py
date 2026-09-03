import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.prospect_scoring_service import verify_scoring_run_sample

DB_PATH = Path("data/campaign_poc.db")
REPORT_PATH = Path("logs/phase5_prephase6_step3_rerun_report.json")


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    job = cur.execute(
        """
        SELECT job_id, status, model_run_id, created_at, started_at, finished_at, result_json
        FROM jobs
        WHERE job_id = 18
        """
    ).fetchone()
    if job is None:
        raise RuntimeError("Expected job_id=18 not found")
    job_payload = dict(job)
    job_result = json.loads(job_payload["result_json"]) if job_payload.get("result_json") else None

    scoring_run_id = int(job_result["scoring_run_id"])

    run_row = cur.execute(
        """
        SELECT scoring_run_id, job_id, model_run_id, status, demographic_snapshot_count,
               scored_person_count, chunk_size, created_at, completed_at, score_summary_json
        FROM scoring_runs
        WHERE scoring_run_id = ?
        """,
        (scoring_run_id,),
    ).fetchone()
    run_payload = dict(run_row)
    run_summary = json.loads(run_payload["score_summary_json"]) if run_payload.get("score_summary_json") else {}

    import_row = cur.execute(
        """
        SELECT import_id, status, rows_read, rows_inserted, rows_rejected, source_checksum
        FROM data_import_runs
        WHERE dataset_name = 'demographics'
        ORDER BY import_id DESC
        LIMIT 1
        """
    ).fetchone()

    demo_quality = cur.execute(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT person_id) AS distinct_person_id,
            SUM(CASE WHEN age < 18 THEN 1 ELSE 0 END) AS age_lt_18,
            SUM(CASE WHEN age > 100 THEN 1 ELSE 0 END) AS age_gt_100,
            SUM(CASE WHEN employment_status = 'Minor / not in labor force' THEN 1 ELSE 0 END) AS minor_employment,
            SUM(CASE WHEN education IN ('Not yet in school','Primary/Middle school') THEN 1 ELSE 0 END) AS child_education,
            SUM(CASE WHEN individual_yearly_income < 0 THEN 1 ELSE 0 END) AS negative_income,
            SUM(CASE WHEN family_member_count < 1 THEN 1 ELSE 0 END) AS invalid_family_count,
            MIN(person_id) AS min_person_id,
            MAX(person_id) AS max_person_id,
            MIN(age) AS min_age,
            MAX(age) AS max_age
        FROM demographics
        """
    ).fetchone()

    score_quality = cur.execute(
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

    invalid_fk = cur.execute(
        """
        SELECT COUNT(*)
        FROM propensity_scores ps
        LEFT JOIN demographics d ON d.person_id = ps.person_id
        WHERE ps.scoring_run_id = ? AND d.person_id IS NULL
        """,
        (scoring_run_id,),
    ).fetchone()[0]

    summary_import_id = run_summary.get("demographic_import_id")
    summary_checksum = run_summary.get("demographic_source_checksum")
    summary_snapshot = run_summary.get("demographic_snapshot_count")
    summary_min_person = run_summary.get("demographic_min_person_id")
    summary_max_person = run_summary.get("demographic_max_person_id")

    provenance_issues: list[str] = []
    if int(import_row["import_id"]) != int(summary_import_id):
        provenance_issues.append("summary demographic_import_id does not match latest completed demographics import")
    if str(import_row["source_checksum"]).strip().lower() != str(summary_checksum).strip().lower():
        provenance_issues.append("summary demographic_source_checksum does not match latest completed demographics checksum")
    if int(demo_quality["total_rows"]) != int(summary_snapshot):
        provenance_issues.append("summary demographic_snapshot_count does not match current demographics count")
    if run_summary.get("model_run_id") != int(run_payload["model_run_id"]):
        provenance_issues.append("summary model_run_id does not match scoring_runs.model_run_id")
    if str(run_summary.get("artifact_sha256", "")).strip() != str(job_result.get("artifact_sha256", "")).strip():
        provenance_issues.append("summary artifact_sha256 does not match scoring job result")
    if str(run_summary.get("feature_contract_version", "")).strip() != str(job_result.get("feature_contract_version", "")).strip():
        provenance_issues.append("summary feature_contract_version does not match scoring job result")
    if str(run_summary.get("feature_contract_sha256", "")).strip() != str(job_result.get("feature_contract_sha256", "")).strip():
        provenance_issues.append("summary feature_contract_sha256 does not match scoring job result")

    # Current person-id envelope in demographics must match the completed run summary.
    current_min_person = demo_quality["min_person_id"]
    current_max_person = demo_quality["max_person_id"]
    if summary_min_person != current_min_person:
        provenance_issues.append("summary demographic_min_person_id does not match current demographics")
    if summary_max_person != current_max_person:
        provenance_issues.append("summary demographic_max_person_id does not match current demographics")

    con.close()

    sample = verify_scoring_run_sample(DB_PATH, scoring_run_id=scoring_run_id, sample_size=256)

    report = {
        "demographic_import": dict(import_row),
        "demographic_quality": dict(demo_quality),
        "job": {
            "job_id": job_payload["job_id"],
            "status": job_payload["status"],
            "model_run_id": job_payload["model_run_id"],
            "created_at": job_payload["created_at"],
            "started_at": job_payload["started_at"],
            "finished_at": job_payload["finished_at"],
            "result": job_result,
        },
        "scoring_run": {
            "scoring_run_id": run_payload["scoring_run_id"],
            "job_id": run_payload["job_id"],
            "model_run_id": run_payload["model_run_id"],
            "status": run_payload["status"],
            "demographic_snapshot_count": run_payload["demographic_snapshot_count"],
            "scored_person_count": run_payload["scored_person_count"],
            "chunk_size": run_payload["chunk_size"],
            "created_at": run_payload["created_at"],
            "completed_at": run_payload["completed_at"],
            "score_summary_json": run_summary,
        },
        "score_quality": {
            **dict(score_quality),
            "duplicate_person_ids": int(score_quality["score_rows"] - score_quality["distinct_person_ids"]),
            "invalid_fk": int(invalid_fk),
        },
        "conflict_checks_during_active_run": {
            "second_scoring_submit_status": 409,
            "training_submit_status": 409,
            "evidence_source": "copilot-terminal-output-c1c0638b-3b73-4046-96d0-84fac78f23ad.txt",
        },
        "sample_verification": sample,
        "provenance_validation": {
            "scoring_run_id": scoring_run_id,
            "demographic_source_verified": len(provenance_issues) == 0,
            "is_canonical": len(provenance_issues) == 0,
            "issues": provenance_issues,
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report_written": str(REPORT_PATH),
                "job_id": job_payload["job_id"],
                "scoring_run_id": scoring_run_id,
                "model_run_id": run_payload["model_run_id"],
                "deterministic_verified": sample.get("verified"),
                "provenance_verified": len(provenance_issues) == 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
