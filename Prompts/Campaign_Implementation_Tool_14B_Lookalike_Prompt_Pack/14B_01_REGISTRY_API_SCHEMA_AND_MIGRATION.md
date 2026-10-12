# Prompt 14B_01 — V3 contract registry, mode-discriminated API, and migration

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

Read and freeze 01_SEMANTICS and 03_INTERFACE. Extend dependency-free app/selection_contracts.py additively without changing legacy definitions or __all__ compatibility. Add separate v3 constants/types/predicate semantics/labels. Avoid ambiguous generic propensity constants shared between modes. Freeze proposed score/membership versions after checking existing allocation.

Inspect all CHECK constraints and migrations in app/database/schema.py, search_recovery_schema.py, phase11_schema.py and result registry repositories. Allocate next additive migration from schema 31 once. Add similarity profiles/artifacts/generations/stage/published scores or justified equivalent, plus discriminator-consistent run/snapshot/cache metadata. A v3 run needs similarity threshold/identity and null probability bucket; v2 preserves its valid combination. Rebuild constrained SQLite tables where necessary through the established migration framework, preserving keys, FKs, indexes, rows, triggers and artifact references. New/legacy paths must agree. Never edit old migration SQL to pretend older schemas had v3.

Add schemas/validators/router/options metadata for explicit v3 and existing response compatibility. Distinguish similarity readiness and optional probability readiness. Strictly reject mixed fields, unsupported version, bool/NaN/infinity, out-of-set threshold, and unknown enums; do not silently coerce 90 to .90 unless documented UI conversion owns it. Resolve absent intelligence through a reachable bounded prepare/build path, not a preflight catch-22. New frontend sends v3 explicitly; unversioned behavior remains pinned.

Migration proofs: fresh DB, schema 31 fixture with populated v1/v2 history, actual canonical copy when available, repeated initialize idempotence, failed-step rollback, PRAGMA integrity/FK checks, semantic counts and IDs unchanged. Invalid direct SQL inserts fail constraints. One active published profile per exact immutable identity (or explicitly versioned pointer) and publication races handled durably. Schema versions in code/README/docs must match real allocation.

Expose frozen JSON interfaces for optional C2/C3/C4 lanes. GO only if actual database/API enforce v3 alongside unchanged v1/v2. Evidence 01_CONTRACT_MIGRATION.{md,json}.

## Migration rollback and version ownership

Use forward migration and safe backups; never downgrade the operator's current database by removing v3 columns/tables. Certification proves failure rollback on disposable copies and preserves old behavior, rather than promising that old binaries can write a newer schema. Document the supported application rollback boundary. All simultaneous lanes consume one allocated schema/method/interface manifest; no lane reserves its own migration number.
