import json
import sqlite3

con = sqlite3.connect("data/campaign_poc.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

latest = cur.execute(
    """
    SELECT import_id, dataset_name, status, rows_read, rows_inserted, rows_rejected, source_checksum
    FROM data_import_runs
    WHERE dataset_name = 'demographics'
    ORDER BY import_id DESC
    LIMIT 1
    """
).fetchone()

counts = cur.execute(
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
        MIN(age) AS min_age,
        MAX(age) AS max_age
    FROM demographics
    """
).fetchone()

print(json.dumps({"latest_demographic_import": dict(latest)}, indent=2))
print(json.dumps({"demographics_quality": dict(counts)}, indent=2))
con.close()
