# Prompt 13.6 Pre-14 Stabilization Evidence

## Certification state

- Starting SHA: `58a5852d488aa686ed67ffa7ccecbc50463f4081`.
- Ending/candidate SHA: `PENDING_COMMIT`.
- Baseline exact-SHA CI: GitHub Actions run `36818012626`; Repository Hygiene, Python Validation, Tests, Frontend Contract, and Clean-Room Phase1-7 were successful.
- Local status: implementation and required local validation passed.
- Remote status: exact-candidate-SHA CI and manual Full Validation dispatch are pending until the changes are committed and pushed.
- Prompt 13.6 status at this evidence revision: **NO-GO until exact candidate SHA is green**.

## Working tree before

The repository started on the required SHA with `main` and `origin/main` aligned. The only initial working-tree item was the untracked operator-supplied prompt:

`Prompts/campaign_recovery_prompt_pack_f437efd3/Prompt_13_6_Pre-14_Stabilization_Statistical_Integrity_Contract_Extensibility_Runtime_Ownership_and_CI_Hardening.md`

It was preserved. No unrelated tracked edits were discarded.

## Repository-wide audit scope

The audit covered the root and prompt-pack READMEs, operational and branch-protection documentation, application database/repository/service/job/ML/schema/router code, frontend code, tests, validation scripts, both GitHub Actions workflows, Phase 1-11 closure evidence, and recovery evidence 00-13.5. Repository-wide searches covered schema-version coupling, selection semantics, calibration lineage/currentness, feedback decisions, execution leases, runtime health, promoted calibrations, and unfinished-code markers.

## Finding matrix

| Finding | Area | Coverage before | Severity | Reproduced | Disposition and reason |
|---|---|---:|---:|---:|---|
| Internal calibration state could violate the preflight response model | Recovery/preflight API | Service coverage only | P1 | Yes | Fixed now; a safe fail-closed result must not become HTTP 500. |
| Model and calibration lineages could each validate while referring to different partitions | Calibration governance | Internal validity only | P1 | Yes | Fixed now with one cross-artifact identity validator. |
| A person repeated across searches could cross fit/evaluation boundaries | Feedback recalibration | Search-run grouping only | P1 | Yes | Fixed now with deterministic connected components. |
| Challenger used a current window while incumbent comparison used historical metrics | Feedback promotion | Partial | P1 | Yes | Fixed now; both transforms are evaluated on one frozen population. |
| Multiple promoted calibrations were prevented only by service ordering | Schema/calibration | Service tests | P1 | Yes | Fixed with a partial unique index. |
| A second live owner could reuse an active attempt token | Phase 11 runtime | Attempt-number fencing | P1 | Yes | Fixed with owner-aware claim/takeover semantics and token rotation. |
| Graceful shutdown/rejoin did not explicitly surrender the active claim | Phase 11 runtime | Not covered | P1 | Yes, during broad regression | Fixed with fenced claim release before handoff/shutdown. |
| Feedback decision ownership had analogous live-owner ambiguity | Feedback worker | Not covered | P1 | Yes | Fixed with owner/token columns, stale takeover, and an active-decision invariant. |
| Existing v2 selection policy was duplicated across layers | Selection contract | Fragmented | P2 | Yes | Centralized without changing policy. |
| Manual workflow ran browser tests without installing/configuring the browser contract | CI | Never dispatched | P1 | Yes | Workflow repaired; remote dispatch remains permission-bound. |
| Health could remain green when Phase 11 composition failed | Runtime health | DB health only | P1 | Yes | Fixed with bounded component state and degraded HTTP 503. |
| General tests coupled current schema to literal version 30 | Migration tests | Broad but brittle | P2 | Yes | Replaced only general-current assertions; historical boundaries remain exact. |
| Statistical grouping helper under `app/ml` violated the established Phase 3 module boundary | Architecture | Detected by broad regression | P1 | Yes | Moved to `app/services`; boundary test remains strict. |
| Existing canonical data contained duplicate promoted calibrations | Canonical data | Migration audit | P1 | No | Disproved: two calibration rows were one PROMOTED and one STALE. |
| Prompt 13.6 required a new selection contract or lower bucket | Business policy | N/A | Prohibited | No | Disproved/not done: v2 and the 0.50 minimum remain unchanged. |
| TODO/FIXME/HACK/XXX/NotImplementedError represented a new in-scope P0/P1 production defect | Repository audit | Search | P1 | No | No additional actionable P0/P1 item was established. |
| `main` is protected by GitHub branch rules | Governance | Public metadata | P1 | No | `protected=false`; admin action remains required. |

## Repairs and proofs

### API contract

`calibration_currentness` retains the public values `CURRENT`, `NOT_AVAILABLE`, `STALE`, and `UNVERIFIED`. Additive fields `calibration_eligibility` (`ELIGIBLE`/`NOT_ELIGIBLE`) and bounded `calibration_reason_code` expose eligibility without forwarding internal states. Eight HTTP-level cases cover absent, current, stale, legacy, malformed, governance-incompatible, candidate, and rejected calibration states. All return documented responses instead of response-validation errors.

### Calibration/model cross-lineage

`validate_calibration_model_lineage_identity` compares canonical group sets and hashes for model training, calibration fit, and calibration evaluation; strategy, seed, validation fraction, model run, and scoring run must also agree. Group order is intentionally irrelevant. Missing/extra groups, swapped partitions, hash mismatches, a missing seed, and a wrong fraction fail closed. Eligibility and publication both use the validator.

### Feedback statistical isolation

For a fixed scoring run and feedback cutoff, search-run/person relationships are reduced to deterministic bipartite connected components. Overlapping and transitively overlapping searches therefore stay in one statistical group. Original feedback events remain immutable and auditable. The adaptive gate records independent component count, grouping contract version, and grouping SHA-256. Insufficient components or class coverage remains `WAITING_FOR_DATA`, not a generic system failure.

### Like-for-like challenger comparison

The candidate is fitted only on fit records. Candidate and incumbent transforms are applied to the same immutable held-out raw-score records, then scored by the same metric functions. Decision evidence records record/class counts, evaluation group IDs/hash, evaluation-population SHA-256, feedback cutoff, both calibration identities and metrics, and promotion checks. Historical incumbent metrics are retained as evidence but are not the comparison oracle. An absent incumbent fails closed.

### Calibration singleton

Schema 31 adds a partial unique index permitting at most one `PROMOTED` calibration per scoring run. Migration deterministically stales older duplicates if encountered while preserving rows and references. Repository publication retains the normal replacement flow. The canonical copy needed no duplicate repair.

### Attempt and feedback ownership

A same-owner claim is idempotent. A different owner cannot claim a fresh lease. A stale takeover rotates the execution token, so the prior owner's progress, lineage, failure, and completion writes fail fencing. Graceful shutdown and dependency handoff use a fenced release that rotates and clears ownership before another coordinator can claim. Feedback decisions use the same bounded single-node ownership principle. This does not claim distributed or multi-node support.

### Selection-contract centralization

`app/selection_contracts.py` is dependency-free and owns current v2 version, names, bounds, labels, default `.70` bucket, membership contract, legacy mappings, and the `10,000` demo qualification minimum. Backend options, schemas, repositories, preflight, submission, orchestration, calibration SQL, snapshots/results, currentness, frontend rendering, and the demo preflight script consume or are checked against that registry. Historical migrations retain their historical SQL. No v3, lower bucket, threshold change, or demo-minimum change was introduced.

### Runtime health

`app/runtime_health.py` records bounded database/schema, Phase 11 workflow, and feedback-worker component state. `/api/health` returns degraded/503 when critical Phase 11 composition fails, `/options` agrees with workflow availability, shutdown clears state, and diagnostics expose only safe issue codes/messages.

### Full Validation workflow

The manual workflow retains LFS checkout, installs both pinned dependency locks, supplies the supported system Chrome variables to browser-inclusive tests, runs `pytest -m "not full5m"`, and directly invokes the required committed full-fresh runner. Missing mandatory runners now fail. The workflow remains bounded and does not execute Prompt 16 full-5M certification.

Remote manual dispatch status: **MANUAL FULL VALIDATION REMOTE CERTIFICATION PENDING**. GitHub CLI and authenticated Actions dispatch credentials are unavailable in this environment. Local component suites and the committed workflow structure are certified; no remote run is claimed.

### Branch protection

Public GitHub metadata was re-read on 2026-10-04. `main` at the starting SHA reported `protected=false`; the protection-detail endpoint returned HTTP 401 and no authenticated repository-ruleset detail was available. No governance change is claimed.

**BRANCH PROTECTION PENDING - ADMIN ACTION REQUIRED.**

## Schema, API, and contract changes

- Schema advanced additively from 30 to 31.
- Added database-enforced promoted-calibration singleton.
- Added feedback-decision owner/token/heartbeat and immutable comparison/grouping evidence columns plus one-active-decision enforcement.
- Preflight response gained additive eligibility/reason fields while retaining currentness vocabulary.
- Health payload gained bounded runtime component status; critical workflow failure produces HTTP 503.
- Attempt-claim behavior is stricter for competing owners; graceful release is explicit and fenced.
- Existing v1/v2 stored runs, snapshots, and result semantics remain readable and unchanged.

## Canonical-copy migration certification

- Contract: `PHASE13_6_CANONICAL_COPY_MIGRATION_V1`.
- Canonical database size: `7,574,577,152` bytes.
- Canonical SHA-256 before and after: `43b6d31ed6c4f33574f2450f3bf1e2ece0ab56d77fd9213e76de9e8e07ef4d77`.
- Canonical source unchanged: yes.
- Disposable copy migrated through `initialize_database()` from schema 26 to 31.
- Second initialization remained at schema 31.
- Semantic signatures after first and second initialization: `9d044b76d04441cc8b5cb43a99679ec55c5fcd706d6fdb3c04e26c2efbd399b1` (equal).
- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: zero violations.
- Preserved identity counts included 4 imports, 7 analyses, 5 model runs, 6 scoring runs, 3 generations, 24 orchestrations, 1 attestation, 2 calibrations, 33 searches, 39 attempts, 33 runtime rows, 56 progress events, 10 snapshots, 24 exports, 21 preflight-cache rows, and 1 targeting catalog.
- The disposable database copy was removed after certification; the bounded JSON report remained in the process temp directory during evidence preparation.

## Tests and commands

| Gate | Result |
|---|---|
| New/focused statistical, concurrency, API, registry, health, and regression tests | 108 passed in 318.84 s |
| Follow-up tests for broad-suite defects and graceful handoff | 7 passed in 48.26 s |
| Full affected modules | 69 passed in 182.07 s |
| Main non-heavy suite | 1,035 passed, 121 deselected in 3,511.31 s |
| Frontend/API browser-or-integration gate | 125 passed in 621.98 s |
| Phase 9 | 69 passed in 665.14 s |
| Phase 10 | 90 passed in 706.96 s |
| Phase 11 bounded | 354 passed, 5 deselected in 735.87 s |
| Clean-Room Phase1-7 | PASS; completed 2026-10-04T10:16:52Z |
| `python -m pip check` | PASS, no broken requirements |
| `python -m compileall app scripts tests` | PASS |
| `git diff --check` | PASS before evidence generation; rerun at closure |

The exact commands were the prompt-prescribed commands. The clean-room report and JSON were regenerated at `docs/evidence/CLEANROOM_PHASE1_TO_PHASE7_REPORT.md` and `docs/evidence/cleanroom_phase1_to_phase7.json`.

An initial broad non-heavy run found six genuine integration defects (claim handoff/test ownership and module-boundary placement): 1,028 passed, 6 failed, and 121 were deselected. Those failures were repaired rather than weakened; the complete corrected rerun is the 1,035-pass result above.

## Files changed

- Runtime/schema: `app/database/schema.py`, `app/database/search_recovery_schema.py`, `app/repositories/campaign_result_registry_repository.py`, `app/jobs/phase11_search_coordinator.py`, `app/jobs/feedback_retraining_worker.py`, `app/main.py`, `app/runtime_health.py`.
- Statistical/contracts/services: `app/selection_contracts.py`, `app/ml/campaign_group_split.py`, `app/services/feedback_grouping.py`, calibration/currentness/preflight/submission/orchestration/result/snapshot/feedback services.
- Public contracts/UI: relevant schema/router files and `frontend/js/business-search-form.js`.
- Validation/CI: `.github/workflows/full-validation.yml`, migration/demo validation scripts, focused and regression tests.
- Authority/evidence: root, docs, branch-protection and prompt-pack READMEs; clean-room evidence; this report and its JSON companion.

## Remaining accepted limitations

- Canonical history remains one campaign-connected component; governed canonical model/calibration creation remains blocked by the existing leakage-safe policy.
- Prompt 13's business selection decision remains unchosen; neither 14A nor 14B was run.
- Prompt 16 full-5M certification, Prompt 17 20-scenario qualification, and Prompt 18 housekeeping were not run.
- The application remains a local single-node SQLite POC.
- Authentication/RBAC, activation/send integration, and automatic true feature-model retraining are not implemented.
- Remote manual Full Validation is pending due unavailable authenticated dispatch tooling.
- Branch protection remains an administrator action.

## Exact-SHA CI and GO/NO-GO

Exact candidate SHA: `PENDING_COMMIT`.

Exact-SHA GitHub Actions run: `PENDING`.

Current decision: **LOCAL IMPLEMENTATION PASS / REMOTE EXACT-SHA CI CERTIFICATION PENDING / PROMPT 13.6 = NO-GO UNTIL EXACT CANDIDATE SHA IS GREEN.**

After exact-SHA CI is green, the only valid next action is to re-present/reconfirm the Prompt 13 business decision and then run exactly one of Prompt 14A or Prompt 14B.
