# 19.0 current baseline and reconciliation

Status: GO to 19.1 and 19.2, sequentially. This is a scoped baseline gate, not a browser, predictive, legacy-probability, or release GO.

## Repository and evidence authority

- Starting HEAD and `origin/main`: `9bea771940f930504ee8635c7b14fc988a37568c` on `main`. At start, only the user-supplied `Prompts/Next_Actions_Native_Browser_Prompt_Pack/` was untracked. This 19.0 work adds only `docs/evidence/post14b_closure/`; no source, schema, scenario, or canonical data changed.
- Current schema version: 33. V3 method: `BUYER_PROFILE_DISTANCE_V1`; split: `SIMILARITY_CUSTOMER_SPLIT_V2`. The repaired minimum support is 200 total / 160 fit / 40 holdout. The recorded canonical product supports are PRD001 200/160/40, PRD003 251/201/50, PRD004 1461/1169/292; union 1,892. The 12 support-aware regression tests passed locally.
- Original 20-scenario JSON SHA-256: `D168DECCF2F7CF9723B5BC08A4B99BF0DC49325309C1A402CD59BA4BEABB2B77`. Current `frontend/index.html` SHA-256: `A86D40B076EF3D0EFD996729E34B410DE893ECB423375765F864820431241B68`, matching the pack seed.
- Earlier `15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md`, `16_2_FULL5M_MEASUREMENTS.md`, and `17_SCENARIOS.md` retain their historical scope: support recovery, recorded canonical 5M measurements, and 20/20 current scenarios above the 10,000 demo threshold. They were **not rerun** for this browser pack. `18_DOCUMENTATION.md` and `19_FINAL_RELEASE_GATE.md` contain dated/historical checkpoints and must not be interpreted as current all-scope release approval.
- GitHub current main is protected and PR #1 is merged at this SHA. Push CI run `38217341713` passed all five jobs. The prior manual Full Validation run `38208450604` on feature head `0f013f98...` failed the separate legacy full-fresh probability model gate because fewer than three independent campaign-connected groups exist. No probability model/scoring success is inferred from green merge CI or v3 evidence. Detailed branch-protection settings were read through authenticated admin access in the preceding session; the connector's details endpoint returned 403. No setting was changed here.

## Local isolated checks

- Created ignored `output/post14b_closure/venv` with Python 3.12.0. Installed exact `requirements.lock` and `requirements-browser.lock` there; `pip check` passed. Pip is 26.2.1. Global Python was not modified.
- `output/post14b_closure/venv/Scripts/python.exe -m compileall -q app scripts tests`: PASS.
- `output/post14b_closure/venv/Scripts/python.exe scripts/validation/validate_ci_hygiene.py`: PASS.
- `output/post14b_closure/venv/Scripts/python.exe scripts/validation/validate_workflow_syntax.py`: PASS.
- `output/post14b_closure/venv/Scripts/python.exe -m pytest -q tests/test_buyer_similarity_support_aware_split.py --maxfail=1 --tb=short`: 12 passed (96.33 s).
- `app.openapi()` has 69 paths and 79 operations, equal to the pack's method catalog. The catalog's seven router byte hashes matched directly. `campaigns.py` and `models.py` differ only by checkout CRLF; normalized LF hashes match. This is not a route drift claim.
- Installed system Chrome resolves to `C:\Program Files\Google\Chrome\Application\chrome.exe`. Headed native browser execution: NOT_RUN at 19.0. Standalone Node is unavailable locally; browser-delivered JS checks remain for 19.3, while prior CI frontend checks remain historical.

## UI, routes, and workers

`frontend/js/view-contract.js` exposes Home, Find Potential Customers, and Results in business navigation, with Result Detail as a visible destination. Saved Target Groups, Campaigns, Insights, Historical Analysis, Audience Explorer, Data Status, and Model Training are retained but intentionally hidden from that navigation; hiding is not authorization. The dated static seed has 211 broad interactive/container entries. The regenerated selector inventory has 197 selector controls (191 DOM, six JS-created), reflecting a different parser scope; neither is exhaustive runtime coverage. See `19_0_STATIC_CONTROL_INVENTORY.json` and `19_0_CONTROL_MAP.md`. Runtime-inserted, state-dependent, keyboard, upload and download controls need 19.3 inspection.

`app.main` lifespan installs the real Phase 11 search coordinator, feedback recalibration worker, and Phase 10 reconciliation/recovery. The old `phase11_step19_server.py` replaces the production search executor with a controlled inline executor; its setup/browser utilities are reusable, but its completion cannot prove real background work. The primary browser runner must use the actual app lifespan, coordinator and jobs on a disposable DB/artifact tree. Direct and indirect compute triggers, including model train/score, audience prepare, targeting intelligence prepare, v3/v2 search/retry, and feedback recalibration, require the 19.2 fail-closed guard before browser use.

## Boundaries and next dependency

Only synthetic, bounded fixture populations may be used. 19.1 establishes a fresh-v3 bounded training/scoring/search/export proof; 19.2 establishes isolated roots, row limits and guard coverage before 19.3 native browser runs. No 5M import/scoring, operator database, real campaign send, contact upload, deployment, commit, push, PR, workflow dispatch or branch setting mutation is authorized by this pack. P01–P19 are reconciled in `19_0_PENDING_REGISTER.md`. Fresh exact-candidate CI and governance remain later remote gates, not current evidence.
