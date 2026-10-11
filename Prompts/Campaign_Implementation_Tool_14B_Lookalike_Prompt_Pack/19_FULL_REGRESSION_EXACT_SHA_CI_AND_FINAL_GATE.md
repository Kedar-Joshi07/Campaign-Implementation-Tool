# Prompt 19 — final regression, exact-SHA CI, and independent release decisions

> 2026-10-09 alignment addendum for future execution only: include the V2
> split/objective/partition hashes, old-policy compatibility, new fault tests,
> full-scale Prompt 16.1 status and preflight/materialization parity in the
> exact-SHA regression and CI decision. Do not infer final GO from local
> Prompt 15.1 runtime GO or partial Prompt 16 scale correctness.

## Execution contract — read before acting

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`.
Trusted starting SHA: `336875c30fc32b00323d916ecc45b232016168a1`. Starting code schema: 31.
This pack records Kedar's approved direction: add product-aware buyer similarity for the POC; retain purchase probability and all existing v1/v2 behavior for future use. Do not run 14A. This is a new approved alternative to the older conditional 14B. Preserve old evidence and append a dated decision addendum instead of rewriting its history.

Run `git rev-parse HEAD`, `git status --short`, and check applicable `AGENTS.md`. Accept the trusted SHA or a verified descendant containing completed pack stages; do not silently reset a newer branch. Record the actual starting SHA, preceding stage, and working-tree changes. Read `00_GUARDRAILS_AND_EXECUTION_ORDER.md`, `01_APPROVED_V3_SEMANTICS.md`, and `02_REPOSITORY_REVIEW_AND_INTEGRATION_MAP.md` from this pack before implementation. Paths for proposed new files are suggestions; existing paths are verified at the pinned SHA. Search all callers with `rg` before changing shared symbols.

Preserve unrelated changes, immutable history, existing probability columns/artifacts, default v2 behavior for legacy callers, calibration governance, BROAD → 0.60, explicit v2 0.50 semantics, and the existing 10,000 demo qualification minimum. No thresholds, filters, products, synthetic outcomes, or evidence may be altered to force counts. Existing tests must retain their original assertions. New v3 callers must explicitly request v3. There is no automatic historical conversion.

Use disposable DBs for migration/recovery/full-scale certification. Do not replace canonical inputs or migrate an operator's canonical DB without the existing authorized operational workflow. Routine code edits and test fixtures are within this implementation task. Do not send campaigns or contact people. Do not commit, push, merge, or deploy unless the operator has authorized that action in the session. Do not invent a pending remote CI success.

All worker writes need durable owner/token fencing, bounded messages, transactional publication, current-source checks, and safe cancellation. Contact PII and raw traces must not enter analytical metadata or evidence. Prove each requirement with independent expected outcomes, not an oracle copied from the function under test. Report blocked and skipped checks explicitly.

Completion: starting SHA; candidate SHA or UNCOMMITTED; changed files; requirements proved; preserved v1/v2 behavior; schema/API/data impact; exact commands and results; evidence paths; limitations; stage GO/NO-GO; next stage. Runtime correctness, descriptive-model quality, predictive validation, full-5M readiness, and demo readiness are separate decisions.


## Required work and gate

Prerequisites: all applicable 14B–18 stages with actual status evidence. This replaces older Prompt 19. Missing data/tests cannot be turned intoPASS.

Audit all acceptance rows and final diff with a fine comb: omitted API defaults, v1 raw semantics, v2 probability ranges and immutable columns, BROAD=.60, explicit.50, default.70,10K registry, scenario hash/distribution, v3 cumulative score>=threshold, profile formula/support/unknowns, generation/source identity, probability-independent readiness, cache discrimination, lease/fencing/retry, immutable files, consent/contactability/CSV guards, feedback isolation and truthful UI/client narrative.

Run pinned dependency integrity, compileall, diff hygiene, actual JS syntax/lint supported by repo, migration/idempotence on populated 31 → new version, DB integrity/FKs. Run focused v3 tests then repository bounded suites matching CI: pytest -m "not cleanroom and not full5m and not performance and not browser"; frontend/API browser-or-integration; Phase9,10,11 bounded; Phase 1–7 cleanroom; required full-fresh/browser/manual workflow if available. Inspect existing workflow/environment/runner requirements rather than inventing commands for missing scripts. Run full5m/performance separately from bounded CI and reference exact validated candidate, not a previous implementation. Repair failures without deleting or weakening legacy tests.

Exact-SHA CI: once commit/push authorized, record actual candidate SHA, run ID, head_sha, event and conclusions for Repository Hygiene, Python Validation, Tests, Frontend Contract, Clean-Room Phase1-7 and any required new jobs. Existing workflow triggers push main/PR, not arbitrary feature-branch push; use authorized correct trigger, never push main solely to create evidence. Verify final executable state independently; no infinite documentation-commit loop. Uncommitted work or absent remote run isCI_PENDING and final release cannot claimGO.

Recheck branch protection/read-only rules and manual Full Validation result at the actual candidate. Pending admin/manual items must remain labeled and distinguished from runtime blockers according to existing accepted governance policy; don't claim completion. No privileged settings change without authority. Use disposable canonical copy for integrity counts, active orphan jobs, duplicate active ownership, generation publication singleton, invalid current attestations, promoted-calibration singleton, cache/currentness and snapshot/export consistency. No source destructive certification.

Produce19_FINAL_RELEASE_GATE.md/json: starting/candidate SHA, changed files, requirements issue table FIXED/PARTIAL/BLOCKED/ACCEPTED_LIMITATION, commands/outcomes, DB/schema/data/provenance impact, actualCI, manual/governance status, risks and next action.

Independent verdicts: implementation/runtime; descriptive similarity; predictive response/lift validation; full5m; 20-scenario demo; exact-SHA release. Runtime/descriptiveGO does not imply predictiveGO or demoGO. Final releaseGO requires current exact-SHA CI and all mandatory technical gates, with accepted governance limits stated.20-scenario DEMO_GO requires 17 evidence for every promised case. If blocked, name minimal concrete remedy and resume point. No automatic 14A or probability rewrite.
