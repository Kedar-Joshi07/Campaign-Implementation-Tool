# Phase 9 Closure Step 06 Regression Report

Generated: 2026-09-13

Prompt: `06_STEP_06_FULL_REGRESSION_AND_NO_HEAVY_WORK_GATE.md`

## Decision

`PASS` - every Step 06 local regression, compatibility, static, dependency,
repository-hygiene, and LFS gate is green. Exact-SHA CI and the final Phase 9
closure decision remain reserved for Step 07.

## Executed gates

All commands ran sequentially. No later command started before the prior command
exited.

| Gate | Command | Result |
|---|---|---|
| Full pytest | `.venv\Scripts\python.exe -m pytest -q` | PASS - 557 passed in 416.48s |
| Focused Phase 9 interoperability | Seven explicit Step 03 node IDs | PASS - 7 passed in 40.28s |
| Phase 9 planner, preview, and recommendation | `pytest -q tests/test_phase9_campaign_context.py tests/test_phase9_target_group_preview.py tests/test_phase9_match_strength_recommendation.py` | PASS - 24 passed in 44.47s |
| Phase 8 browser harness unit tests | `pytest -q tests/test_system_browser_harness.py` | PASS - 13 passed in 0.22s |
| Clean-room Phase 1-7 | `python scripts/validation/run_cleanroom_phase1_to_phase7.py` | PASS - all five stages and cleanup passed |
| Python compilation | `python -m compileall -q app scripts tests` | PASS |
| Dependency integrity | `python -m pip check` | PASS - no broken requirements |
| Diff hygiene | `git diff --check` | PASS - no whitespace errors; informational CRLF conversion notices only |
| Repository hygiene and LFS pointer syntax | `python scripts/validation/validate_ci_hygiene.py` | PASS |
| Local LFS object integrity | `git lfs fsck` | PASS - `Git LFS fsck OK` |
| Explicit source/link/export contracts | Five selected contract node IDs | PASS - 5 passed in 48.23s |

The clean-room evidence was regenerated at
`docs/evidence/CLEANROOM_PHASE1_TO_PHASE7_REPORT.md` and
`docs/evidence/cleanroom_phase1_to_phase7.json`. It used an isolated runtime,
removed that runtime on completion, and did not modify production source data.

## Explicit compatibility verification

| Required assertion | Result and evidence |
|---|---|
| Historical Analysis unchanged | PASS - no Historical Analysis implementation file is in the closure diff; clean-room Step 3 completed Historical Analysis successfully. |
| Model Training unchanged | PASS - no training implementation, worker, repository, or ML file is in the closure diff; clean-room bounded fixture training completed. |
| Scoring contracts unchanged | PASS - no scoring service, compatibility, worker, repository, rank, or analytics implementation file is in the closure diff; clean-room scoring integrity and provenance passed. |
| Legacy Audience Explorer still works for legacy audiences | PASS - focused legacy reopen test passed, and clean-room Step 4 passed the Audience Explorer filter, pagination, preparation, and saved-audience checks. |
| Phase 9 multi-branch groups no longer reopen incorrectly | PASS - service/API metadata identify multiple branches, the legacy reopen capability is false, the frontend control is disabled, and the defensive handler exits before filter population. The focused multi-branch and frontend tests passed. |
| Saved Target Groups still work | PASS - exact count, canonical branch hash, immutable persisted metadata, currentness, and idempotent behavior passed in the focused interoperability matrix and full suite. |
| Campaign Planner still works | PASS - 24 planner/preview/recommendation tests passed. |
| Campaign Draft links to the correct Saved Target Group | PASS - the explicit save/link contract test passed and asserts `campaign.saved_audience_id == saved_target_group.saved_target_group_id`. |
| Email/Direct Mail export contracts unchanged | PASS - clean-room Step 5 created and exported both channel types; explicit Email and Direct Mail deliverability tests also passed. |
| Multi-branch campaign membership unchanged | PASS - the focused regression resolves the exact expected union, has no duplicates, and matches the stored resolved count. No campaign member/export resolver was changed. |
| No PII leak | PASS - interoperability and save responses recursively reject contact-PII keys; browser recertification remains green; clean-room governed-export checks passed. |
| No latest-scoring fallback | PASS - `test_no_link_is_not_available_and_never_searches_for_latest` passed; targeting-intelligence resolution code is unchanged. |
| Phase 10 handoff unchanged | PASS - no Phase 10 orchestration or handoff implementation was added or changed. The documented handoff remains explicit-source, immutable-target-group, provenance-preserving, fail-closed, and PII-safe. |

## Heavy-work gate

Production model training, 5-million-person rescoring, and rank rebuilding were
`NOT RUN`.

The interoperability correction changes only saved-audience response metadata,
API schema exposure, legacy reopen UI guarding, tests, and closure documentation.
It does not alter model features, training semantics, score computation, scoring
compatibility, targeting semantics, member resolution, ranking semantics, or
source provenance. Therefore there is no invalidation reason and heavy work is
both unnecessary and prohibited by this prompt.

The clean-room runner's bounded 1,200-customer/12,000-person fixture training and
scoring are required isolated regression checks, not production retraining or a
5M rescore.

## Repository state and release boundary

- Branch: `main`
- Pre-Step-07 HEAD and `origin/main`: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- Closure implementation: present in the working tree and intentionally not
  assigned a SHA before commit
- Exact-SHA CI: not run; reserved for Step 07
- Final closure decision: not declared; reserved for Step 07

## Step result

`STEP_06_COMPLETE_STOP`

Step 07 was not started.
