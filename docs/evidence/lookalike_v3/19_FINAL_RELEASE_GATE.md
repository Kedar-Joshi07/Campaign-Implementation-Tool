# Prompt 19 — final regression and release gate

**Current checkpoint (2026-10-12 IST): FINAL RELEASE NO-GO.** The latest
validated executable candidate is `ec0c28920cf64301c3ce75dd27be0d706571cf24`
on draft PR #1. All five exact-SHA PR CI jobs passed. Manual Full Validation
passed 1,308 baseline tests, strict regenerated-source hashes, the fresh
125K/570K/5M import, and reconciliation, then stopped at the governed
probability-model split because the canonical campaign history has fewer than
three independent campaign-connected groups. The dated sections below retain
their original checkpoint wording; the final run IDs and decision are in the
latest addendum at the end of this report.

Recorded 2026-10-11 (IST). Trusted starting and current HEAD:
`336875c30fc32b00323d916ecc45b232016168a1`. Candidate: **UNCOMMITTED**
14B worktree; preceding Stage 18 documentation gate was GO. The worktree
already contained Stages 00–18 when this check began. Prompt 19 removed two
unused imports in `app/services/buyer_similarity_result_service.py` and added
this evidence pair. It did not migrate the operator DB, regenerate input,
retrain, rescore 5M, send contacts, commit, push, or deploy. The detailed
changed-path inventory is reproducible with
`git status --short --untracked-files=all` (183 path entries at report time); it includes the new v3 app/schema,
repositories, services, tests, runners, documentation, Stage 17 screenshots,
and modified API/UI/Phase 11 integration files. The Phase 1–7 runner's old
tracked evidence content was restored after the run (the JSON now has only a
trailing-newline diff); its new result is recorded below, not presented as
the historical 2026-10-05 record.

## Decision

**LOCAL_BOUNDED_TECHNICAL_GO; FINAL_RELEASE_NO_GO / CI_PENDING.** The current
candidate is uncommitted and has no exact-SHA GitHub Actions run. The remote
`main` SHA is still the trusted starting SHA, and its successful CI run
`37282486202` on 2026-10-05 tested that older code, not this worktree.
Neither that run nor the local passes below can satisfy A44. The manual Full
Validation workflow has no recorded run in the 44 repository Actions runs
returned by the read-only API and has not run at a candidate SHA.

| Independent gate | Verdict | Basis / limit |
|---|---|---|
| Implementation and bounded single-node runtime | **GO locally** | 149/149 focused v3, 1,171/1,171 bounded CI selection, Phase 9/10/11 and browser contract gates below; fault/restart evidence in [15.1](15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md). |
| Descriptive similarity integrity | **GO for the declared index**, not predictive quality | Current source/profile/generation lineage, 5M attestations and immutable result hashes checked; [method](03_PROFILE_METHOD.md), [assurance](08_MODEL_DATA_ASSURANCE.md), [factsheet](08_MODEL_FACTSHEET.md). Weak product specificity and bounded bootstrap instability remain disclosed. |
| Predictive response, conversion probability and lift | **NO-GO / unavailable** | No independent campaign-outcome or prospective-response validation for v3. Similarity is not calibrated purchase probability. |
| Full-5M on named hardware | **GO locally, source/context-specific** | [16.1](16_1_SUPPORT_AWARE_FULL5M.md) and [16.2](16_2_FULL5M_MEASUREMENTS.md); existing isolated schema-33 DB rechecked read-only here. No new full scoring run was needed after Stage 18's example-metadata change and the import-only cleanup. Not an exact committed candidate. |
| Unchanged 20-scenario demo | **DEMO_GO locally, source/context-specific** | [17](17_SCENARIOS.md): 20 current exact preflights and completed results, each ≥10,000; 20 screenshot hashes and run/member counts rechecked here. Not predictive efficacy. |
| Exact-SHA CI and release | **NO-GO / CI_PENDING** | No authorized commit/push/PR trigger in this session; no candidate SHA or candidate run ID. Manual Full Validation and governance review remain pending. |

## Acceptance matrix

`PASS` below means actual local test or cited stage evidence, not remote CI.
Historical limitations are not rewritten as green predictive claims.

| ID | Status | Proof or precise limit |
|---|---|---|
| A01 | PASS | [dated approval](00_APPROVED_V3_DECISION_ADDENDUM.md); old policy retained. |
| A02 | PASS | Starting SHA and [golden compatibility](00_BASELINE.md); omitted-version API tests in focused suite. |
| A03 | PASS | v1 raw fixtures/reopen in `test_lookalike_v3_baseline_compatibility.py`. |
| A04 | PASS | Literal v2 discrete boundaries in golden/selection tests. |
| A05 | PASS | BROAD→0.60 in [translation](17_V3_TRANSLATION.json), source hash and tests. |
| A06 | PASS | Explicit v2 0.50 and default 0.70 golden tests. |
| A07 | PASS | Fresh/populated-31 migration, rollback and idempotence in `test_lookalike_v3_contract_migration.py`; schema 33 and isolated DB integrity below. Direct uninterrupted 26→33 migration was not claimed. |
| A08 | PASS | Mixed v2/v3 fields rejected in contract/API tests. |
| A09 | PASS | Exact join/distinct buyer/repeat order tests and [cohort evidence](02_BUYER_COHORTS.md). |
| A10 | PASS | 36 observed sales products versus 48 master; [support manifest](02_PRODUCT_SUPPORT_MANIFEST.json). |
| A11 | PASS | Unsupported/199-buyer context blocks; no alias/fallback, cohort and UI tests. |
| A12 | PASS | Union customer-disjoint [V2 partition](15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md), split tests. |
| A13 | PASS | Fit-only preprocessing and holdout/prospect mutation tests in profile suite. |
| A14 | PASS | Buyer-driven artifact identity tests and [profile evidence](03_PROFILE_METHOD.md). |
| A15 | PASS | Independent scalar 11-feature distance oracles in scoring tests. |
| A16 | PASS | Missing/unknown feature and coverage tests. |
| A17 | PASS | Finite range/invalid-reason tests and five-million-row attestations. |
| A18 | PASS | Cluster support and no singleton-anchor tests; [method evidence](03_PROFILE_METHOD.md). |
| A19 | PASS | Per-product max and product-ID tie tests. |
| A20 | PASS | Independent hard-filter fixture, v3 preflight/search tests. |
| A21 | PASS | Inclusive v3 threshold versus exclusive v2 band boundaries. |
| A22 | PASS | Preflight, immutable membership and reopened count parity; Stage 17 and 20/20 DB recheck. |
| A23 | PASS | Overlapping OR branch dedup tests. |
| A24 | PASS | TOP_N qualified-versus-selected count tests. |
| A25 | PASS | Similarity readiness without calibration, focused/API/browser tests; isolated DB has zero calibration artifacts. |
| A26 | PASS | V2 probability split/calibration remains separate in compatibility tests. |
| A27 | PASS | Missing intelligence→bounded prepare→ready→count browser/integration tests. |
| A28 | PASS | Mode/source/profile/filter/threshold cache discrimination tests. |
| A29 | PASS | Fast verified reuse without retraining/rescoring in [16.2](16_2_FULL5M_MEASUREMENTS.md); measured only on named hardware. |
| A30 | PASS | Stale UI response ignored after mode switch in browser tests. |
| A31 | PASS | Index wording and no probability/percentile claim in browser tests and [client guide](../../BUYER_SIMILARITY_OPERATOR_AND_DEMO.md). |
| A32 | PASS | Membership 1/2/3 readers and export interoperability tests. |
| A33 | PASS | Full-precision membership decision versus display-rounding tests. |
| A34 | PASS | Consent, contactability, dedup and CSV formula guards in snapshot/export tests and representative Stage 17 export. |
| A35 | PASS | V3 feedback lineage isolated from v2 probability calibration tests. |
| A36 | PASS | Source replacement/currentness fault tests; actual three gzip hashes match current isolated DB source identities. |
| A37 | PASS | Old-owner fencing, crash/restart and no partial-ready publication in [15](15_FAULT_RECOVERY.md) and 15.1 tests. |
| A38 | PASS | [16.1](16_1_SUPPORT_AWARE_FULL5M.md): 5M distinct source people per product, valid+invalid=5M, no omissions/extras; 5M valid composite. |
| A39 | PASS with limits | [16.2](16_2_FULL5M_MEASUREMENTS.md): CPU/process journal, observed RSS, DB/WAL/disk and end-to-end timings; 5-second RSS sampling and interrupted PRD004 first-process peak limitation retained. |
| A40 | PASS | Original `scenarios.json` SHA-256 `d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`; explicit v3 translation. |
| A41 | PASS | 10,000 current registry minimum, historical 101 metadata not substituted; 20/20 exact qualifying results. |
| A42 | PASS | [architecture](../../BUYER_SIMILARITY_ARCHITECTURE.md), [guide](../../BUYER_SIMILARITY_OPERATOR_AND_DEMO.md), [factsheet](08_MODEL_FACTSHEET.md) disclose absent products and predictive limits. |
| A43 | PASS locally | Complete bounded repository CI selection and dedicated frontend/Phase 9–11/clean-room commands below. |
| A44 | **BLOCKED** | Uncommitted candidate: no exact-SHA remote run/jobs or candidate manual validation. |
| A45 | PASS | Six independent decisions above; local/demo/full5M GO is not release or predictive GO. |

## Commands and outcomes on this worktree

| Gate | Exact command or equivalent PowerShell file expansion | Result |
|---|---|---|
| Dependency consistency | `python -m pip check`; `.venv/Scripts/python.exe -m pip check`; compare installed distributions with `requirements.lock` | Both `pip check` runs PASS. The existing `.venv` differs from 10 of 40 exact pins (including one absent `cloudpickle`); it is **not** a pinned-environment certification. Exact lock installation and tests remain a remote-CI gate. |
| Python syntax | `python -m compileall -q app scripts tests` | PASS, including after import cleanup. |
| Diff hygiene | `git diff --check` | PASS, only line-ending conversion warnings. |
| Repository hygiene / workflow YAML | `python scripts/validation/validate_ci_hygiene.py`; `python scripts/validation/validate_workflow_syntax.py` | PASS / PASS. |
| Focused v3 | `pytest -q tests/test_lookalike_v3_*.py tests/test_buyer_similarity_*.py tests/test_preflight_materialization_parity.py` (PowerShell expanded file paths) | **149 passed**, 651.85 s, outside restricted Windows sandbox. First sandboxed attempt had 138 passes/11 Playwright setup errors (`WinError 5` named pipe); unsandboxed rerun cleared all 11. |
| CI Tests | `pytest -m "not cleanroom and not full5m and not performance and not browser" -q --tb=short` | **1,171 passed**, 132 deselected, 2,968.11 s. |
| Frontend/API | `pytest -q -m 'browser or integration' tests/test_frontend.py tests/test_*_api.py --tb=short` (PowerShell expanded) | **125 passed**, 467.52 s. |
| Phase 9 | `pytest -q tests/test_phase9_*.py --tb=short` (expanded) | **69 passed**, 515.57 s. |
| Phase 10 | `pytest -q tests/test_phase10_*.py --tb=short` (expanded) | **90 passed**, 609.13 s. |
| Phase 11 | `pytest -q -m 'not cleanroom and not performance and not full5m' tests/test_phase11_*.py --tb=short` (expanded) | **356 passed**, 5 deselected, 1,034.36 s. |
| CI clean-room | `python scripts/validation/run_cleanroom_phase1_to_phase7.py` | PASS, bounded disposable schema-33 generation/import/model/scoring/audience/campaign/export/drift stages. Its prior tracked historical report was restored after execution. |
| Post-cleanup affected tests | `pytest -q tests/test_lookalike_v3_snapshot_export_feedback.py tests/test_lookalike_v3_preflight_search.py --tb=short` | **18 passed**, 127.57 s. |
| Changed production Python lint | `python -m ruff check` over changed/new `app`, `scripts`, `data_generation_scripts` Python paths | PASS after removing two unused imports. Whole-repository Ruff is not configured CI and reports 353 legacy/new-test findings; no broad automatic rewrite was made. |
| JS | No Node binary/package lint script installed on this host/repo. Real Chrome/Playwright frontend/API and v3 UI tests above passed; standalone JS syntax/lint remains NOT_RUN. |

## Read-only isolated full-scale integrity and provenance recheck

The existing disposable database is
`output/lookalike_stage16_2_measurements/certification.db` (8,560,308,224
bytes), opened with SQLite `mode=ro`. `PRAGMA quick_check` returned `ok`,
`PRAGMA foreign_key_check` returned zero violations, and `app_metadata`
records schema 33. Latest imports are 125,000 customers, 570,000 sales, and
5,000,000 demographics. The three current compressed source-file hashes match
[16.1](16_1_SUPPORT_AWARE_FULL5M.json). All five published profiles and
their artifact-file SHA-256 values match, and all five published generations
have VERIFIED attestations of five million rows each. PRD001 generation 3
retains 4,999,849 valid and 151 invalid scores; PRD003/PRD004 generations
4/5 each have 5,000,000 valid. The three-product composite remains 5,000,000
valid, zero invalid per prior full SQL audit; no new composite scan was run.

There are zero active jobs, zero active attempts, no published profile or
generation identity collision, no published generation missing a verified
attestation, and no import-checksum mismatch. All 22 searches/attempts are
COMPLETED. All 20 v3 snapshots and 21 preflight cache rows are CURRENT.
The 20 immutable snapshot files (35,015,710 compressed bytes total) match
their recorded SHA-256; their DB selected counts match the runs. All 20
Stage 17 screenshot files match their JSON SHA-256, and all 20 selected
counts still exceed the 10,000 registry minimum. Both recorded v3 export
events are COMPLETED/CURRENT; `deliverable+undeliverable=selected_count`
and `row_count=deliverable_count`. This recheck did not alter scores, files,
calibration, snapshots or source data.

## Governance, impact, limits and next action

Read-only GitHub branch metadata on 2026-10-11 reports `main` at the old HEAD
and `protected=false`; the rulesets collection is empty. The branch-protection
detail endpoint returned 403 `Resource not accessible by integration`, so no
privileged settings were inferred or changed. Existing CI triggers on push to
`main` or pull request, not arbitrary feature-branch push. The current worktree
must not be pushed to `main` merely to manufacture a run. Manual Full
Validation is a `workflow_dispatch` gate and has not run on this candidate.

Schema impact of Stages 01–18 is additive 31→32→33, with explicit v3
profile/score/search/snapshot/export lineage; v1 raw and v2 probability,
calibration and feedback contracts remain readable and tested. This Prompt
19 pass changes no schema or data. The isolated canonical-copy chain was
previously built through schema 33; an uninterrupted direct migration of the
operator's older schema-26 DB is not newly claimed. Prompt 16.2's memory and
latency claims apply only to its named hardware and source context. Full-fresh
Phase 1–7 at 5M was not rerun after these uncommitted changes; its actual
candidate manual-workflow gate is pending. No customer contact or production
release is authorized by this report.

**Minimal resume:** obtain explicit operator authorization for a reviewed
commit/push/PR workflow. Once a candidate SHA exists, run the CI workflow
through its authorized trigger, verify run ID/head SHA/event and every required
job, run Manual Full Validation at that same SHA, and recheck branch-governance
requirements. Append an exact-SHA addendum to this report; do not rewrite
the local result or promote predictive claims without independent outcomes.

## Exact-SHA addendum — first candidate and manual-gate correction (2026-10-12 IST)

The sections above are the recorded pre-commit local checkpoint. The operator
subsequently authorized a feature branch and PR, not a direct `main` push.
Commit `f480a3ca9e046ed61b3d0358bf0989a5d0d8205f` was pushed to
`feature/14b-lookalike-final-gate` and draft PR #1 was opened. Pull-request CI
run [38168396109](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38168396109)
had `head_sha=f480a3ca9e046ed61b3d0358bf0989a5d0d8205f`, event
`pull_request`, and conclusion `success`. Repository Hygiene, Python
Validation, Tests (1,171 passed, 132 deselected), Frontend Contract (125
frontend/API, 69 Phase 9, 90 Phase 10, 356 Phase 11 passed), and Clean-Room
Phase1-7 all concluded `success`. Locked dependency installation passed in
CI; the local `.venv` pin mismatch remains a local-environment disclosure.

Manual Full Validation run
[38169298180](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38169298180)
on the same SHA failed its baseline step after 1,300 passes and three
`test_system_browser_harness.py` failures. That workflow deliberately sets
`SYSTEM_BROWSER_PATH=/usr/bin/google-chrome`; three pure resolver tests had
implicitly inherited it instead of supplying an empty `environ`. The
full-fresh step was consequently **skipped**, not passed. The tests now supply
`environ={}` for the intended no-override cases. With both workflow browser
variables set locally, all 13 harness tests pass. This test-isolation change
does not alter production browser resolution or weaken the assertions.

This addendum accompanies the corrective commit. Its new SHA and the
subsequent PR CI/manual workflow outcomes must be recorded against the actual
remote runs (for example in PR #1) before final release GO. The predictive
response/lift NO-GO and governance limitations remain unchanged.

## Exact-SHA addendum — source-generation lock correction (2026-10-12 IST)

Corrective commit `5eb4d5ee7caed2810dc99e693e9d7da1d1b2d823` passed
all five jobs in pull-request CI run
[38170580504](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38170580504)
(`head_sha` equals that commit; event `pull_request`). Manual Full Validation
run [38171414135](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38171414135)
on that same SHA passed its baseline step (**1,303 tests passed**) and
entered the full-fresh runner. It then failed at Step 2, after regenerating
125,000 customer, 570,000 sales, and 5,000,000 demographic rows, because at
least one generated canonical source hash differed from the accepted input.
No import, training, or scoring ran in that manual attempt. The old hash gate
did not print the dataset name, so that run alone cannot identify which file
drifted.

A disposable Windows generation probe under the local accepted-source
environment reproduced all five canonical hashes. A second probe under the
project `.venv` (NumPy 2.4.6, pandas 3.0.5, Faker 40.36.0) also reproduced
the complete 125K customer, 570K sales, 5M demographic, campaign-master,
and product-master canonical hashes. CI's lock had NumPy 2.4.6 and pandas
3.0.5 but Faker 40.38.0. **Inference:** the newer Faker pin is the likely
source of CI generation drift; the failed CI artifact does not expose its
per-dataset hashes, so this is not represented as direct proof. The lock is
returned to Faker 40.36.0, the exact accepted-data reproduction environment.
The full-fresh hash gate remains strict; its failure now includes per-dataset
accepted and generated hashes, with unit tests for canonical mismatch,
missing output, and compressed-container-only drift. No canonical input or
historical score was changed.

The next exact-SHA PR CI and manual full-fresh run are **PENDING**. A final
GO cannot be inferred from the earlier green CI, from the local probes, or
from a full-fresh run that stopped at Step 2. Record the actual new SHA and
remote conclusions in PR #1 to avoid an endless evidence-only commit loop.

## Exact-SHA addendum — confirmed cross-platform catalog hashing (2026-10-12 IST)

Commit `2b7b0145f872d2c00a6aaca5e10dc767cbd98b7c` passed all five PR CI
jobs in [38174491203](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38174491203).
Manual run [38175147476](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38175147476)
passed baseline validation and then reached full-fresh Step 2. Its improved
strict hash diagnostic reported **only two** mismatches:

| Plain CSV catalog | GitHub accepted LF SHA-256 | Generated CRLF SHA-256 |
|---|---|---|
| `campaign_master.csv` | `d6f6101f65884f7a4afe87e1c220de144d4ddc0cc99cd9052ecb51eee22da9a5` | `1e453d77ad8dae2bb2c4dc997f53b900b1706117b7a22d095f0b13281b67be84` |
| `product_master.csv` | `82f55d63f3d043d978fc6a136e05c50f9cb25d575d7deb99cab6a08ede853b3c` | `317778cd2f591ad34757413915c33ad9298c7fb70fbbe22605d8078be3b9ba6a` |

`git ls-files --eol` reports the repository blobs as LF and the existing
Windows worktree copies as CRLF. Locally replacing CRLF with LF in those
catalogs yields exactly the GitHub accepted hashes above. The generator uses
`csv.writer`, whose CSV line terminator is CRLF on Linux too. This is a
confirmed serialization mismatch, not a changed catalog row. The earlier
Faker-version hypothesis is **not established as the cause of this remaining
failure**. Faker 40.36.0 remains pinned because the full local 5M probe with
that version reproduced every accepted source; the first run with 40.38.0 did
not expose per-dataset mismatches, so no stronger claim is made about it.

The canonical hash now normalizes CRLF to LF for **plain `.csv` files only**,
while gzip sources retain exact decompressed-payload hashing. Raw stored-byte
hashes remain recorded separately. Tests prove LF/CRLF equivalence, changed
field values still fail, and gzip line endings are not normalized. The two
real Windows catalog files now compute the GitHub accepted LF hashes. This
does not modify canonical sources or weaken customer/sales/demographic
integrity checks. PR CI and manual full-fresh on the next SHA remain pending;
the two prior manual runs are failures, not release evidence.

## Exact-SHA addendum — terminal CI and governed full-fresh outcome (2026-10-12 IST)

Commit `ec0c28920cf64301c3ce75dd27be0d706571cf24` on
`feature/14b-lookalike-final-gate` passed all five jobs in pull-request CI
[38198011573](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38198011573):
Repository Hygiene, Python Validation, Tests, Frontend Contract, and Clean-Room
Phase1-7. The run's `head_sha` equals the candidate and its event is
`pull_request`.

Manual Full Validation
[38198876255](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/38198876255)
was dispatched on the same exact SHA. Its baseline step passed **1,308 tests**.
Full-fresh Step 2 regenerated all canonical sources and passed the strict
canonical-hash gate, including the two plain-CSV catalogs. Step 3 imported
125,000 customers, 570,000 sales, and 5,000,000 demographics into a fresh
schema-33 database and reconciled the sources. Step 4 then failed before
model/scoring certification with
`CampaignGroupSplitError: At least three independent campaign-connected groups are required.`
This is the already documented canonical one-connected-component limitation,
not a hash or import failure. Prompt 13.6 explicitly prohibits random
customer splitting, `MIN(campaign_id)` grouping, or changing canonical
campaign data merely to fabricate disconnected components. None was done.

Independent decisions: bounded implementation and exact-SHA PR CI **GO**;
prior named-hardware 5M buyer-similarity and 20-scenario evidence remain
source/context-specific **GO**; predictive response/lift **NO-GO / unvalidated**;
this candidate's manual full-fresh Phase1-7 model/scoring path **NO-GO**; final
release **NO-GO**. The PR remains draft and unmerged. Read-only branch metadata
reports `main` unprotected with zero rulesets; administrator review is pending.
The terminal evidence is also recorded in
[PR #1 comment](https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/pull/1#issuecomment-6117320412).

Safe resume: obtain genuine independent campaign/outcome groups sufficient for
governed train/calibration/evaluation, or an explicit product/governance decision
about accepting this full-fresh limitation. Do not silently weaken the gate.
Any resulting executable candidate needs its own exact-SHA CI and applicable
manual validation before final release GO.
