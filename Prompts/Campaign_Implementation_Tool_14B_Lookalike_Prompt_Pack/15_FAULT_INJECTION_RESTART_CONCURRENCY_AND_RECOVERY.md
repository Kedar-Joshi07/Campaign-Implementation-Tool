# Prompt 15 — faults, restart, concurrency, and mixed-mode recovery

> 2026-10-09 alignment addendum: Prompt 15.1 adds
> `SIMILARITY_CUSTOMER_SPLIT_V2`, exact support-aware buyer partitioning,
> atomic partition publication, V2 profile/attestation currentness and its
> restart/fencing tests. The current gate evidence is
> `docs/evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md`.
> Historical Prompt 15 evidence remains readable under its original policy.

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

Prerequisite: 14B_09 implementation GO. This replaces the older Prompt 15 for this branch.

Build and execute a matrix on disposable DBs/temp artifact roots. Include every boundary: profile build, artifact fsync/rename, score stage chunk commit, score verification, generation promotion, attestation creation, queued dependency rejoin, preflight caching, result file publication, registry completion, export, feedback ingestion, import invalidation, startup/shutdown. Inject process crash, exception, source replacement, disk/write failure, corrupted artifact, slow heartbeat and lease takeover. Bound runs; no crash injection on canonical DB.

For each boundary assert durable terminal/resumable state, no false READY/COMPLETED, no half-published downloadable artifact, no lost historical membership, bounded safe message and no leaked traceback/PII. Retry creates/rejoins the appropriate immutable attempt and dependency, does not duplicate heavy work. Nonretryable insufficient buyer history does not loop. Two workers competing for same context/generation cannot publish competing active artifact; stale token writes fail, including progress/lineage/failure/completion.

Concurrency cases: two identical v3 submissions, different thresholds same profiles, different products, v2 and v3 same criteria, long v3 scoring with cheap verified reuse request, import during preflight/materialization, mode switch during fetch, active worker during shutdown. SQLite is single-node; do not claim distributed deployment correctness. Heavy concurrency stays bounded, queue timing truthful, no proportional 5M scan per waiter.

Prove both failure modes and eventual recovery through repository/API production path. Observations include attempt owner transitions privately, safe public projection, immutable old attempts, dependency IDs, actual row counts and file checksums. No raw ownership tokens in deliverable evidence.

Keep old probability promotion/feedback split/fencing coverage intact. Add tests for optional stale probability never corrupting similarity completion. Run focused fault suites plus affected regression once repairs complete. Matrix rows: injection, expected state, observed state, retry behavior, duplicate counts, historical preservation, test evidence.

Evidence: docs/evidence/lookalike_v3/15_FAULT_RECOVERY.{md,json}. GO requires all critical publication/currentness/ownership cases; untested required boundary → NO-GO. Next 16.
