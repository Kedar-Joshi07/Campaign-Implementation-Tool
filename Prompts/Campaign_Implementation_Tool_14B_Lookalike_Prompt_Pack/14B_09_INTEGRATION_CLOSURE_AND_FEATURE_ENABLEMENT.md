# Prompt 14B_09 — 14B integration closure and controlled enablement

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

Audit requirement matrix and every call path after merging staged/concurrent work. Run actual end-to-end HTTP/UI path from imports → product history → profile training → score generation → verified reuse → preflight → search → snapshot → history → channel export; not just direct service functions. Run v1/v2 paths and saved fixtures unchanged. Confirm probability future mode remains implemented and accessible with honest existing block/empty behavior.

Check mode discriminator consistently through registry/schema/options/API/context fingerprints/queue/retry/health/attestation/preflight/cache/iterator/snapshot/results/export/feedback. Missing v3 readiness must not accidentally use a probability READY generation. No stale currentness, type coercion, cross-mode cache, private-worker shortcut, ignored invalid-score row or unsupported product fallback.

Run meaningful focused v3 suites, then existing bounded main suite, frontend/API, phase9/10/11 and Phase 1–7 cleanroom using pinned dependencies/markers. Collect exact command/results. Enable new UI default only after integration checks pass. Preserve v2 default .70 and unversioned API behavior. Documentation states real schema version/migration and statuses; old evidence untouched.

Publish 14B integration report and JSON, migrations/changed files/regression summary/actual evidence/known limitations. Stage reports need actual current hashes; do not record an evidence-only future SHA before it exists. If no authorized commit yet, UNCOMMITTED is truthful. ImplementationGO does not substitute for 15 fault,16 full5m,17 demo,19 exact-SHA final certification.

GO when integration and compatibility proved, descriptive method reproducible, no architectural blockers remain in v3. If canonical data unavailable or some products unsupported, list separately; don't claim all scenarios qualify. Next action: updated Prompt 15. Evidence: 09_INTEGRATION_CLOSURE.{md,json}.
