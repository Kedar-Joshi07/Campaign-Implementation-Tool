import json
import sqlite3

con = sqlite3.connect("data/campaign_poc.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

job = cur.execute(
    """
    SELECT job_id, status, stage, progress_percent, message, error_message, result_json, model_run_id, created_at, started_at, finished_at
    FROM jobs
    WHERE job_type = 'PROSPECT_SCORING'
    ORDER BY job_id DESC
    LIMIT 1
    """
).fetchone()

if job is None:
    print("No scoring jobs found")
    raise SystemExit(0)

payload = dict(job)
if payload.get("result_json"):
    payload["result_json"] = json.loads(payload["result_json"])

print(json.dumps(payload, indent=2))

row = cur.execute(
    """
    SELECT scoring_run_id, status, scored_person_count, demographic_snapshot_count, score_summary_json, error_message
    FROM scoring_runs
    WHERE job_id = ?
    """,
    (payload["job_id"],),
).fetchone()
if row is not None:
    run = dict(row)
    if run.get("score_summary_json"):
        run["score_summary_json"] = json.loads(run["score_summary_json"])
    print(json.dumps({"scoring_run": run}, indent=2))

con.close()
