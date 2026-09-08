# Step 1 — Baseline & Failure Reconciliation

Required starting baseline: `47a93d0a44c4df8ab12ff58157fbc204ec43a51d`

Record branch, local/remote HEAD, git status, Python, dependency lock, schema/app version, pytest count, workflow names, latest CI conclusions, system Chrome/Edge availability.

Reproduce the current Tests-job failure and document exactly why validation/browser scripts are collected and why Playwright is missing in that environment.

Read current browser evidence. Reclassify every previous control result:
A. genuine mutually-exclusive/disabled-by-design
B. reachable but simply not tested

Every B item becomes mandatory in Phase 8.

Confirm all open issues:
- CI red
- browser control gap
- Historical Analysis not truly initiated via browser
- training not truly initiated via browser
- 5M scoring not truly initiated via browser
- unexplained browser 404/error
- stale source-hash docs
- absolute machine paths in generated summaries/evidence
- raw GZIP hash drift with stable content
- dirty_override used previously
- branch protection state

Create:
`docs/evidence/phase8/01_phase8_gap_register.json`
`docs/evidence/phase8/01_PHASE8_BASELINE_REPORT.md`

No functional code changes. STOP.
