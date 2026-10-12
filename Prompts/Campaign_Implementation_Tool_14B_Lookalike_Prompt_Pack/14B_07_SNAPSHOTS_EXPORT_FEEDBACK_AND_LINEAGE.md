# Prompt 14B_07 — Immutable membership, exports, and feedback boundaries

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

Extend result_membership_contract_for_selection, readers/writers/results/history/schema validation for membership 3. Store full score precision, similarity tier display, winning product, feature coverage, profile/generation/method/source identity; metadata and file hash certify selection. Keep v1/v2 columns/aliases intact. Opening/reusing/download must not reinterpret old raw/probability scores. Optional probability payload provenance is separately immutable or explicitly omitted.

Snapshot publication: staged files, hash/count/identity verification, atomic final publish, transactional registry completion, owner fencing, crash reconciliation and retention. A failed file/DB publication cannot produce completed downloadable partial output. Currentness driven by latest sources; preserve old snapshot for history when stale, prohibit invalid current export according to existing policy.

Extend phase11 exports by membership version while retaining profile contactability, opt-in, do-not-call, missing identifier, dedup, CSV formula mitigation, row limits and path guards. Analytical selected!=channel-exportable; show reconciled excluded counts. No campaign sending or external activation. Contact PII remains in governed channel output only, not analytics/evidence.

Feedback: record original selection 3 and similarity/profile/product/method identity plus immutable search/person linkage. Never pass buyer_similarity_score into probability recalibration as raw purchase score. If an independently valid raw probability lineage exists, use only an explicitly tested mapping and existing isolated decision process; otherwise retain feedback and return a truthful learning-not-available reason. Do not claim automatic profile learning or feature retraining has occurred. Existing v1/v2 recalibration tests remain unchanged.

Tests: write/read/reopen/export all three versions; full precision; unknown membership fail closed; exact reuse and provenance hash; crash before/after publish; stale winner score; source invalidation; contact-channel filtering; feedback duplicate/transitive group lineage and mode isolation; similarity changing without altering v2; optional probability absent. Evidence07_MEMBERSHIP_EXPORT_FEEDBACK.{md,json}.

## Existing export bridge requires an explicit extension

At the pinned SHA, phase11_export_service._membership_chunks supports only membership 1/2 and always builds legacy rank/propensity fields. Omnichannel BASE_EXPORT_COLUMNS also includes propensity_score. Do not shoehorn v3 into those fields or invent percentile/decile/rank values to satisfy the writer.

Add a new export/profile version or explicit versioned analytical projection for v3, with buyer_similarity_score and matched_product_id plus the declared semantics/method metadata. Reuse consent, identifier, hashing and contactability logic behind version-aware adapters. Preserve legacy profile versions and headers exactly. Allocate and advertise the new profile version in options/request validation/cache/export registry, and test contact-only versus analytical fields intentionally. If a destination requires a legacy-only schema, report that schema unsupported for v3 rather than silently populating probability/rank columns with similarity.
