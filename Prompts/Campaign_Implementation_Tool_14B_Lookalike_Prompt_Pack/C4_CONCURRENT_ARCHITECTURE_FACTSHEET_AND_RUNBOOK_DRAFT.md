# Concurrent prompt C4 — documentation and presentation draft lane

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

Safe wave: after 14B_01 interface freeze. Use a documentation-only isolated namespace. Draft against approved score semantics and frozen interfaces. Final consolidation belongs to Prompt 18 after measured evidence exists.

Explain separate probability and similarity paths, strict audience filters, product ANY/max, learned supported prototypes, the defined 90/100 distance meaning, coverage versus score, missing values and support floors. Describe learning → scoring → filtering → minimum selection → snapshot → export. Explain the retained probability/history capability and the existing predictive-validation limitation.

Create client narrative, factsheet, architecture and runbook drafts. Label examples illustrative. Use NEEDS_MEASUREMENT for latency, score distributions and scenario yield until actual evidence arrives. Exact headphone/mobile products are absent from the present catalog. Catalog 48 versus history 36 is a pinned input observation, not a permanent assumption. Selected analytical members may differ from exportable contacts; campaign sending is not implemented.

Return a documentation patch and unresolved factual questions with required stage evidence. Do not modify shared root README/authority files or assert GO, CI success, or deployment. The controller owns final status. Deliver C4_DOCUMENTATION_DRAFT.md.
