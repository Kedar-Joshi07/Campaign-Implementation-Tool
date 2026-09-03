# Step 15 — Full Regression, Evidence, Final Decision & Commit

Run:
- full pytest
- bounded clean-room Phase1→7 runner
- compileall
- pip check
- git diff --check
- repository hygiene gate
- current data validation
- source manifest validation
- deterministic scoring sample validation
- campaign/export contract tests

Create:
`docs/evidence/full_fresh_e2e/FULL_FRESH_PHASE1_TO_PHASE7_E2E_REPORT.md`
`docs/evidence/full_fresh_e2e/full_fresh_run_manifest.json`

Report environment, Git SHAs, generator versions/seeds, data row counts/hashes, import IDs,
analysis/model/artifact/scoring IDs and checksums, score count, audience prep/saved audience,
campaign/export IDs and SHAs, UI controls total/tested/failed, browser errors, real timings,
DB integrity, test counts and cleanup status.

NO-GO if any major generation/import/PU/artifact/5M scoring/ranking/analytics/audience/campaign/export/UI-control/browser/integrity assertion fails.

Do not change product semantics merely to make tests pass. If an upstream semantic fix is required, restart validation from the earliest affected phase.

Final commit only after GO:
`test: validate complete fresh phase1-7 browser-driven 5m workflow`

Do not commit runtime DB/WAL/SHM, local model artifact, browser cache or unnecessary downloads/traces.

Report exact final SHA and GO/NO-GO. STOP.
