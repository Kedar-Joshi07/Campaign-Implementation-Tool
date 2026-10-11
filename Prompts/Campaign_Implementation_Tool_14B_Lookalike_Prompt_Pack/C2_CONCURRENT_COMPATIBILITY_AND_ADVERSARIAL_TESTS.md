# Concurrent prompt C2 — independent compatibility and adversarial test lane

## Execution contract — read before acting

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`.
Trusted starting SHA: `336875c30fc32b00323d916ecc45b232016168a1`. Starting code schema: 31.
This pack records Kedar's approved direction: add product-aware buyer similarity for the POC; retain purchase probability and all existing v1/v2 behavior for future use. Do not run 14A. This is a new approved alternative to the older conditional 14B. Preserve old evidence and append a dated decision addendum instead of rewriting its history.

Run `git rev-parse HEAD`, `git status --short`, and check applicable `AGENTS.md`. Accept the trusted SHA or a verified descendant containing completed pack stages; do not silently reset a newer branch. Record the actual starting SHA, preceding stage, and working-tree changes. Read `00_GUARDRAILS_AND_EXECUTION_ORDER.md`, `01_APPROVED_V3_SEMANTICS.md`, and `02_REPOSITORY_REVIEW_AND_INTEGRATION_MAP.md` from this pack before implementation. Paths for proposed new files are suggestions; existing paths are verified at the pinned SHA. Search all callers with `rg` before changing shared symbols.

Preserve unrelated changes, immutable history, existing probability columns/artifacts, default v2 behavior for legacy callers, calibration governance, BROAD → 0.60, explicit v2 0.50 semantics, and the existing 10,000 demo qualification minimum. No thresholds, filters, products, synthetic outcomes, or evidence may be altered to force counts. Existing tests must retain their original assertions. New v3 callers must explicitly request v3. There is no automatic historical conversion.

Use disposable DBs for migration/recovery/full-scale certification. Do not replace canonical inputs or migrate an operator's canonical DB without the existing authorized operational workflow. Routine code edits and test fixtures are within this implementation task. Do not send campaigns or contact people. Do not commit, push, merge, or deploy unless the operator has authorized that action in the session. Do not invent a pending remote CI success.

All worker writes need durable owner/token fencing, bounded messages, transactional publication, current-source checks, and safe cancellation. Contact PII and raw traces must not enter analytical metadata or evidence. Prove each requirement with independent expected outcomes, not an oracle copied from the function under test. Report blocked and skipped checks explicitly.

Completion: starting SHA; candidate SHA or UNCOMMITTED; changed files; requirements proved; preserved v1/v2 behavior; schema/API/data impact; exact commands and results; evidence paths; limitations; stage GO/NO-GO; next stage. Runtime correctness, descriptive-model quality, predictive validation, full-5M readiness, and demo readiness are separate decisions.


## Write ownership and work

Safe wave: after 14B_01 interface freeze. Worktree/branch dedicated to tests only; isolated temp DB/ports/output. You may add new test modules/fixtures under your assigned namespace, but do not change app/frontend/schema/shared conftest/dependency locks or modify old tests. If interfaces are incomplete, emit contract-level failing tests/blocked notes rather than inventing another API.

Build independent expectations for preserved v1/v2 plus v3: exact threshold 90 vs 80; v2 discrete buckets versus v3 cumulative; BROAD=.60; .50 preserved; all-equal; nextafter; invalid/missing/unknown features; supported multimodal profiles; training-only scale/k fit; fit/holdout no person overlap across products; product max winner/dedup; hard filter excludes highest score; changing audience does not rescore; unsupported product no fallback.

Add API/schema strictness, cache collisions across modes/products/profile/source/threshold/selection mode, missing probability but ready similarity, opposite case, buildup preparation reachability, stale partial scores, full precision and preflight/materialization parity. Prepare snapshot/export/history/feedback readback tests using frozen membership 3, preserving 1/2.

Test suggestions not yet runnable must be labeled pending, not pass. Report exact oracle construction and any suspected ambiguity to controller. Existing broad regressions run by integrator after merges. Deliver isolated test patch and C2_QA.{md,json}. No parallel writes into integrator checkout.
