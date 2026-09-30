# Prompt 13.5 Integration Closure

Generated: 2026-09-30T14:17:29Z

## 1. Baseline

- Starting SHA: `6c7c76164a62f14c15e7d4699cf46922dd632ef0`
- Branch: `main`
- Candidate SHA: not yet created; the candidate is an uncommitted working tree based on the starting SHA.
- Working tree at start: the operator-supplied Prompt 13.5 file was untracked; implementation work was otherwise based on the recorded starting SHA.
- Python: `3.12.0`
- Application version: `0.1.0`
- Code schema version before and after: `30`
- Canonical database schema version: `26` (left unchanged in place).
- `requirements.lock` SHA-256: `350439d9acb3afc8ed9e1adc48dfaa8455ed81c53d3deaa5248e36ceeb2401f1`
- `requirements-browser.lock` SHA-256: `a8ef32bd35a0280ac1324075c14c02bd16dd0702f7fc796ecc2d08309b956a03`
- Baseline GitHub Actions run: `36668701656`, SHA `6c7c76164a62f14c15e7d4699cf46922dd632ef0`, conclusion `failure`.
- Baseline jobs: Repository Hygiene `PASS`, Python Validation `PASS`, Tests `FAIL`, Frontend Contract `FAIL`, Clean-Room Phase1-7 `FAIL`.
- Baseline Tests summary: `945 passed, 9 failed, 38 errors, 121 deselected`.

GitHub's public API confirmed the run, SHA, jobs, and conclusions. Raw job-log download requires repository-admin credentials and returned HTTP 403 in this environment. The failure inventory below therefore combines the authoritative aggregate with locally reproduced failure families and the affected tests; no missing names were invented.

## 2. Failure inventory

| Original test/job | Count | Classification | Root cause | Fix | Final result |
|---|---:|---|---|---|---|
| Tests setup/API/browser groups | 38 errors | `REAL_APPLICATION_DEFECT` | Application lifespan startup used the canonical `DATABASE_PATH` even when FastAPI's `get_database_path` dependency was overridden. Test applications therefore initialized and reconciled the wrong database. | Resolve the runtime database path from the dependency override and use it for schema initialization and every startup reconciliation path. | Full non-heavy test job: `1011 passed, 121 deselected`; browser rerun outside the Windows sandbox passed. |
| Phase 10/11 governed success fixtures | 7 failures | `OUTDATED_SUCCESS_FIXTURE` | Success fixtures created one campaign-connected component and could not satisfy `CAMPAIGN_CONNECTED_THREE_WAY_V1`. | Create deterministic fixtures with at least three independent campaign-connected components while retaining explicit one-component fail-closed tests. | Focused model/fencing tests `20 passed`; Phase 10 `90 passed`; Phase 11 `351 passed, 5 deselected`; clean-room `PASS`. |
| `test_schema_version_16_migration_preserves_version_15_rows` | 1 failure | `INVALID_LEGACY_MIGRATION_FIXTURE` | The hand-built v15 database omitted dependencies required by later migrations and was not an authentic v15 state. | Build the authentic historical boundary, assert v15-to-v16 there, then use the real migration chain. | Migration focused suite `18 passed, 46 deselected`. |
| `test_schema_27_preserves_referenced_v1_snapshot_without_rewriting_identity` | 1 failure | `INVALID_LEGACY_MIGRATION_FIXTURE` | The test jumped across the wrong boundary instead of applying migration 27 to an exact v26 fixture. | Apply migration 27 at its real boundary, verify byte-for-field v1 identity preservation, then upgrade to current v30. | Migration focused suite `18 passed, 46 deselected`; historical identity preserved. |
| Frontend Contract job | job failure | `REAL_APPLICATION_DEFECT` plus environment-sensitive browser IPC | The lifespan path defect affected real-app fixtures. Separately, local sandboxed Playwright could not create Windows named pipes (`WinError 5`). | Fix runtime database isolation; rerun unchanged browser tests outside the restricted sandbox against installed Chrome. | `125 passed` in the combined frontend/API gate; Phase 9 `69 passed`; Phase 11 browser-capable gate `351 passed, 5 deselected`. |
| Clean-Room Phase1-7 job | job failure | `OUTDATED_SUCCESS_FIXTURE` | Synthetic campaign/customer topology was a single connected component, so governed training correctly failed closed. | The clean-room-only generator now supports deterministic component assignment; the official runner uses three components. | Official runner `PASS`, including deterministic generation, import, governed model/scoring, audiences, export, and drift blocking. |

The 7 governed-fixture failures plus 2 migration failures account for the baseline 9 failures; the lifespan isolation defect accounts for the baseline 38 setup errors. A later local broad browser run produced 9 `WinError 5` errors only inside the restricted sandbox; rerunning the unchanged affected browser file with host browser permission produced `14 passed`.

## 3. Training governance reconciliation

- Legacy split semantics: `CUSTOMER_STRATIFIED_V1`.
- Governed split semantics: `CAMPAIGN_CONNECTED_THREE_WAY_V1`.
- Automated training policy version advanced from `1` to `2`.
- The split-strategy version is bound into the model compatibility fingerprint.
- Reuse validation requires persisted governed split lineage and validates its train/calibration/test isolation.
- A legacy model remains readable as historical evidence but is not compatibility-equivalent and cannot satisfy a new governed build request.
- If only an incompatible legacy model exists, Phase 10 chooses `BUILD`; it does not silently `REUSE` or rewrite the old model.

## 4. Calibration consumption governance

- Calibration contract v1 artifacts remain immutable and readable as historical evidence.
- New v2 propensity consumption uses one centralized eligibility resolver.
- Eligibility requires exact generation, scoring run, and model lineage; promoted v2 status; authoritative source currentness; a valid deep-verification attestation; valid governed model split lineage; and valid calibration three-way lineage.
- Preflight and Phase 11 search orchestration both call this resolver.
- A promoted legacy v1 calibration is not eligible for a new v2 preflight or search and is never rewritten to pretend it is v2.
- Malformed or stale lineage fails closed with a governed unavailability result rather than an apparently current zero-customer result.

## 5. Clean-room topology

The clean-room campaign-sales generator accepts an optional component count and defaults to the historical single-component behavior for compatibility. The official Phase1-7 certification explicitly requests three components across 96 campaigns. Customer assignment is deterministic and confined within components, so the campaign graph contains independently splittable connected groups without weakening production governance.

The successful clean-room run used 1,200 customers, 9,000 campaign-sales rows, and 12,000 demographic rows. It reached model `COMPLETED`, scoring `COMPLETED`, validated 12,000 distinct scored people, exercised audience filters and deterministic exports, and proved that source drift blocks export with HTTP 409. The disposable runtime directory was removed by the runner.

A dedicated one-connected-component test remains and proves governed training fails closed without random-split fallback or artifact promotion.

## 6. Migration certification

The canonical `data/campaign_poc.db` was not changed. A byte-for-byte disposable copy was created and migrated through the exact production `initialize_database()` path.

- Canonical source size: `7,574,577,152` bytes.
- Canonical source SHA-256 before/after: `43b6d31ed6c4f33574f2450f3bf1e2ece0ab56d77fd9213e76de9e8e07ef4d77`.
- Copy schema: `26 -> 30`.
- Pre/post `PRAGMA integrity_check`: `ok`.
- Pre/post foreign-key violations: `0`.
- Second initialization semantic signature: unchanged (`dc418b578ddc2fffead338f9fc2f1a480dac5021f2fd2e9935bf73e410dd8c45`).
- Second initialization: semantically idempotent.
- Source size, modified time, and checksum: unchanged.

Sanitized identity/count preservation after migration included: 4 import runs, 7 historical-analysis runs, 5 model runs, 6 scoring runs, 3 intelligence generations, 24 orchestrations, 1 verification attestation, 2 calibration artifacts, 33 search runs, 39 attempts, 56 progress events, 10 result snapshots, 24 export events, 21 preflight cache entries, and 1 targeting catalog. All recorded ordered identity digests were identical after the first and second initialization.

## 7. Prompt 00-13 regression audit

| Prompt | Status | Evidence |
|---|---|---|
| 00 | `PASS` | Guardrails retained; no raw-score rewrite, PII evidence, policy substitution, or canonical in-place migration. |
| 01 | `PASS` | CI/API/mobile evidence retained; API compatibility gates pass. |
| 02 | `FIXED IN 13.5` | Current browser/clean-room worker entry points now claim attempts and pass mandatory execution fences. |
| 03 | `FIXED IN 13.5` | Retry/rejoin succeeds on valid governed multi-component fixtures. |
| 04 | `FIXED IN 13.5` | Calibration eligibility now requires exact deep attestation and current source lineage. |
| 05 | `FIXED IN 13.5` | Replacement invalidation tests run on governed fixtures and preserve stale/ineligible behavior. |
| 06 | `FIXED IN 13.5` | Preflight/materialization parity uses the centralized governed eligibility rule; `19 passed`. |
| 07 | `PASS` | Reuse/heavy-gate/time accounting remains covered by the full and Phase 11 gates. |
| 08 | `PASS` | Progress/heartbeat/ETA behavior remains covered by the full and Phase 11 gates. |
| 09 | `PASS` | V2 score semantics and historical v1 readability remain intact. |
| 10 | `PASS` | Catalog lifecycle/currentness tests remain green. |
| 11 | `FIXED IN 13.5` | Policy v2, split identity, persisted lineage validation, and calibration consumption are reconciled. |
| 12 | `PASS` | Feedback/recalibration governance remains green; no search completion is treated as learning feedback. |
| 13 | `PASS WITH ACCEPTED LIMITATION` | No selection-policy branch was chosen. Canonical one-component topology is recorded honestly. |

## 8. Worker/fencing audit

Production coordination already claimed attempts and passed an `AttemptExecutionFence`. Three executable validation/browser entry points were corrected: `run_phase11_bounded_cleanroom.py`, `phase11_step19_server.py`, and `phase11_step20_server.py`. Each now claims the attempt and supplies the fence to orchestration/failure mutation. No optional/default fence bypass was introduced.

## 9. Tests and commands

Key commands and results:

```text
.venv\Scripts\python.exe -m pytest -m "not cleanroom and not full5m and not performance and not browser"
1011 passed, 121 deselected in 2254.23s

.venv\Scripts\python.exe scripts/validation/run_cleanroom_phase1_to_phase7.py
PASS

.venv\Scripts\python.exe -m pytest -m "browser or integration" tests/test_frontend.py <explicit test_*_api.py files>
125 passed in 384.27s

.venv\Scripts\python.exe -m pytest -q <explicit test_phase9_*.py files>
69 passed in 438.20s

.venv\Scripts\python.exe -m pytest -q <explicit test_phase10_*.py files>
90 passed in 445.61s

SYSTEM_BROWSER=chrome; SYSTEM_BROWSER_PATH=<installed Chrome>; pytest -q -m "not cleanroom and not performance and not full5m" <explicit test_phase11_*.py files>
351 passed, 5 deselected in 781.48s
```

Focused results:

- Model resolution and attempt fencing: `20 passed in 108.70s`.
- Migration boundaries/matrix: `18 passed, 46 deselected`.
- Preflight/materialization parity: `19 passed in 98.50s`.
- Generator compatibility: `3 passed in 25.88s`.
- Restricted-sandbox broad matrix: `278 passed, 9 environment-only Playwright named-pipe errors`; unchanged browser file rerun outside sandbox: `14 passed in 109.09s`.
- `pip check`: no broken requirements.
- `compileall`: passed.
- CI hygiene validator: passed.

## 10. Files and contracts changed

- Training/split identity and validation: `app/schemas/phase10_intelligence.py`, `app/ml/campaign_group_split.py`, Phase 10 context/model resolution services.
- Governed calibration consumption: calibration, source-currentness, preflight, and Phase 11 search services.
- Runtime isolation: `app/main.py`.
- Clean-room topology: generator and Phase1-7 runner/evidence.
- Fencing: bounded clean-room and Step 19/20 browser entry points.
- Migration/governance regression tests and two read-only certification scripts.
- Root and recovery-pack documentation/manifest.

No schema-version change.

No new HTTP endpoint or response field was added. The behavioral contract change is that new v2 preflight/search consumption fails closed unless the recorded calibration satisfies the governed eligibility boundary. Legacy rows and API detail remain readable.

## 11. Canonical data status

- Technical/runtime readiness: locally green across the non-heavy repository suite, frontend/API gate, Phase 9/10/11 gates, clean-room, migration copy, and hygiene checks.
- Governed model/calibration readiness: `BLOCKED_ONE_CONNECTED_COMPONENT`. Read-only canonical audit found 96 campaigns, 119,909 distinct customers, 570,000 distinct customer/campaign pairs, 108,330 multi-campaign customers, a maximum of 23 campaigns/customer, and exactly 1 campaign-connected component. A governed three-way split is unavailable and the application fails closed.
- Business-selection readiness: awaiting the explicit Prompt 13 decision; this prompt does not choose 14A or 14B.
- Demo readiness: not certified. Canonical governed calibration is unavailable and no 10K+ scenario qualification has been rerun under a selected policy.

## 12. CI certification and remaining limitations

- Exact candidate SHA: not available because commit/push was not authorized in this execution.
- Exact-SHA GitHub Actions run: not started.
- Exact-SHA CI status: `PENDING_COMMIT_AND_PUSH_AUTHORIZATION`.
- Prompt 13.5 status: `NO-GO` until the candidate is committed, pushed, and the required GitHub Actions jobs are green on that exact SHA.

Accepted limitations:

- Historical v1 models/calibrations remain readable but are intentionally ineligible for new governed v2 consumption.
- The canonical campaign topology cannot currently support the governed three-way split. This is a data/business-policy limitation, not an unresolved fallback opportunity.
- Prompt 14A/14B remains an explicit future business decision.
- Full canonical performance and 20-scenario demo qualification remain future work after policy selection.

The only valid next action is to obtain authorization to create/push the candidate commit, run exact-SHA GitHub CI, and fix any remaining Prompt 13.5 blocker. Prompt 14 must not begin until Prompt 13.5 is fully green.
