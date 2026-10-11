# Concurrent prompt C1 — independent source and topology audit

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

Safe wave: after 14B_00, concurrent with 14B_01–04. Read-only inputs; write only your isolated report directory. No shared DB migrations, imports, model training, canonical generation or dependency-lock changes.

Audit 125K customers,570K sales and 5M common features with streamed counts/checksums and latest imported metadata where available. Validate exact product master versus observed sales versus distinct attributed buyers; report per-product support with context/window filters. Reproduce catalog 48/observed 36 as an input claim, not assume it forever. Check state/gender/education/marital/employment vocabularies, income units, date/age reference and missingness. Evaluate customer/prospect distribution differences using fit-defined bins; identify limits of sample-only checks. Do not store PII in evidence.

Build historical customer/campaign component counts and explain why existing probability governance remains blocked if the topology remains one component. Distinguish descriptive customer-disjoint holdout from independent campaign response evaluation. Do not change split contracts to make them pass.

Return findings with exact paths/queries/input identities, affected 14B stage, observed severity and fix suggestions. Unknown production DB state remains unknown. Product-support edge cases must inform 02/03. Integrator merges this lane's reports/tests sequentially and resolves discrepancies with actual sources. DeliverC1_DATA_AUDIT.{md,json}.
