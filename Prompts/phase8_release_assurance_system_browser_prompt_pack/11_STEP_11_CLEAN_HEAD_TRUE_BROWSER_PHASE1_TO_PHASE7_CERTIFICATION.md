# Step 11 — Clean-HEAD True System-Browser Phase 1→7 Certification

This is the decisive local Phase 8 acceptance run.

## Clean-start gate
Before run:
- all Steps 1–10 implementation/test/doc changes committed
- `git status --short` empty
- no dirty_override
- intended candidate SHA recorded
- system Chrome/Edge available

## Fresh runtime state
Use a fresh runtime DB, artifact directory, browser profile, download directory and logs.

Do not reuse old:
- DB
- model
- scores
- rank state
- saved audiences
- campaigns
- export events

Use accepted current canonical synthetic source files. Full source regeneration is required only if Step 10 intentionally changed canonical deterministic output.

## Browser-driven flow
Using installed Chrome or Edge:

1. initialize/import fresh DB using official mechanisms;
2. open app;
3. exercise Overview controls;
4. exercise Data Status controls;
5. create Historical Analysis via browser;
6. create PU model via browser;
7. observe training to completion;
8. click full 5M scoring via browser;
9. observe scoring to completion;
10. prepare Audience Explorer;
11. exercise every Audience control;
12. save audience;
13. use saved audience in Campaign Builder;
14. exercise every Campaign control;
15. create/finalize/export EMAIL campaign;
16. create/finalize/export DIRECT_MAIL campaign;
17. verify export history;
18. verify finalized immutability.

No direct service/DB write may create browser-workflow state. Backend reads are assertions only.

## Coverage acceptance
Regenerate final control inventory/coverage.

Required:
- FAIL = 0
- NOT_RUN = 0
- generic EXCEPTION = 0
- every JUSTIFIED_EXCLUSIVE individually documented

## Integrity
Verify:
- 125K customers
- 570K campaign rows
- 5M prospects
- current imports
- completed analysis
- governed model
- 5M scores
- deterministic rescore sample
- 100 rank boundaries
- current analytics
- saved audience
- finalized Email and Direct Mail campaigns
- completed exports
- no stale active jobs
- no stuck STARTED exports
- PRAGMA integrity_check = ok

## Browser quality
0 unexplained console errors.
0 unexplained critical network failures.

Create:
`docs/evidence/phase8/final_system_browser/PHASE8_SYSTEM_BROWSER_CERTIFICATION_REPORT.md`
`docs/evidence/phase8/final_system_browser/ui_control_coverage.json`
`docs/evidence/phase8/final_system_browser/phase8_certification_manifest.json`

Record browser/version, candidate SHA, run IDs, counts, artifact SHA, scoring summary, audience/campaign/export IDs/checksums, control coverage, timings and local decision.

Do not declare final GO until Step 12 CI is green.

STOP.
