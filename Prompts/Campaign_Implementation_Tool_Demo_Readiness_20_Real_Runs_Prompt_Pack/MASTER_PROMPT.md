# MASTER PROMPT — Audit, Preload 20 Real Demo Runs, and Housekeep

Work in `C:\POCs\Campaign Implementation Tool` at exact SHA:
`f2b98adfcf1a01f23f1c201aa2cf5a2df1521a2d`.

Execute this prompt pack in order:

1. `01_MASTER_GUARDRAILS.md`
2. `02_REPO_WIDE_IMPLEMENTATION_AUDIT.md`
3. `03_REAL_20_SCENARIO_PRELOAD.md` using exact `scenarios.json`
4. `04_VERIFY_DEMO_DATA_AND_UI.md`
5. `05_HOUSEKEEPING_AND_CURRENT_BASELINE.md`
6. `06_FINAL_ACCEPTANCE_REPORT.md`

These 20 scenario runs are real canonical POC application runs, not tests. Use the production FastAPI/application orchestration path and canonical SQLite database. They must persist in normal Results history and be reopenable for the demo.

Do not ask for confirmation between steps. Stop only for a genuine safety/data-integrity blocker. Never silently alter the scenario criteria, source data, model governance, or currentness rules to manufacture a successful result.

Return a concise final summary with:
- exact SHA;
- audit verdict;
- tests/gates;
- 20 run IDs + counts/statuses;
- reuse/build summary;
- demo-ready count;
- housekeeping changes;
- remaining risks.
