# Guardrails and execution order

## Execution contract — read before acting

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`.
Trusted starting SHA: `336875c30fc32b00323d916ecc45b232016168a1`. Starting code schema: 31.
This pack records Kedar's approved direction: add product-aware buyer similarity for the POC; retain purchase probability and all existing v1/v2 behavior for future use. Do not run 14A. This is a new approved alternative to the older conditional 14B. Preserve old evidence and append a dated decision addendum instead of rewriting its history.

Run `git rev-parse HEAD`, `git status --short`, and check applicable `AGENTS.md`. Accept the trusted SHA or a verified descendant containing completed pack stages; do not silently reset a newer branch. Record the actual starting SHA, preceding stage, and working-tree changes. Read `00_GUARDRAILS_AND_EXECUTION_ORDER.md`, `01_APPROVED_V3_SEMANTICS.md`, and `02_REPOSITORY_REVIEW_AND_INTEGRATION_MAP.md` from this pack before implementation. Paths for proposed new files are suggestions; existing paths are verified at the pinned SHA. Search all callers with `rg` before changing shared symbols.

Preserve unrelated changes, immutable history, existing probability columns/artifacts, default v2 behavior for legacy callers, calibration governance, BROAD → 0.60, explicit v2 0.50 semantics, and the existing 10,000 demo qualification minimum. No thresholds, filters, products, synthetic outcomes, or evidence may be altered to force counts. Existing tests must retain their original assertions. New v3 callers must explicitly request v3. There is no automatic historical conversion.

Use disposable DBs for migration/recovery/full-scale certification. Do not replace canonical inputs or migrate an operator's canonical DB without the existing authorized operational workflow. Routine code edits and test fixtures are within this implementation task. Do not send campaigns or contact people. Do not commit, push, merge, or deploy unless the operator has authorized that action in the session. Do not invent a pending remote CI success.

All worker writes need durable owner/token fencing, bounded messages, transactional publication, current-source checks, and safe cancellation. Contact PII and raw traces must not enter analytical metadata or evidence. Prove each requirement with independent expected outcomes, not an oracle copied from the function under test. Report blocked and skipped checks explicitly.

Completion: starting SHA; candidate SHA or UNCOMMITTED; changed files; requirements proved; preserved v1/v2 behavior; schema/API/data impact; exact commands and results; evidence paths; limitations; stage GO/NO-GO; next stage. Runtime correctness, descriptive-model quality, predictive validation, full-5M readiness, and demo readiness are separate decisions.


## Preserve by behavior, not by copying every old implementation line

Retain the implemented probability feature and its data. Shared plumbing may be extended or narrowly refactored behind compatibility tests. Do not delete mature components, globally change probability constants to similarity constants, rename existing probability fields, or leave a second divergent filter engine. Existing schemas that assume only v1/v2 must gain an explicit v3 path; historical SQL/migrations remain historical.

New UI submissions may default to v3 after certified readiness. Omitted API discriminator fields continue the exact pinned behavior; characterize it first rather than inventing a new default. Existing URLs, response contracts, persisted runs, and exports remain interpretable. The probability mode remains accessible as an explicit advanced/future mode with truthful currentness and empty/blocking explanations.

## Execution dependency table

| Stage | Prerequisites | Owner responsibilities |
|---|---|---|
| 14B_00 | trusted baseline | decision, golden fixtures, current-source inventory |
| 14B_01 | 00 | frozen interfaces, registry, one migration owner |
| 14B_02 | 01 | product-context buyer cohorts |
| 14B_03 | 02 | train and serialize descriptive profiles |
| 14B_04 | 03 | score generations and attestations |
| 14B_05 | 04 | mode-specific readiness, preflight/search/cache |
| 14B_06 | 05 | full UI and safe mode switching |
| 14B_07 | 06 | immutable results, export, feedback identity |
| 14B_08 | 07 | data/model assurance, drift, explanation |
| 14B_09 | 08 | integration closure and feature enablement |
| 15 | 09 | fault/restart/concurrency proof |
| 16 | 15 | full-scale certification on disposable DB |
| 17 | 16 | exact scenario preflight and real runs |
| 18 | 17, including honest blocked outcome | docs and client narrative |
| 19 | applicable prior work | final exact-SHA certification |

Sequential execution is fully supported. Concurrent lanes are optional: C1 after 00 (read-only audit), C2 after 01 (isolated test-only branch), C3 after 01 (new isolated UI component/mock contract), C4 after 01 (documentation-only). Freeze interfaces before these lanes. The controller merges artifacts sequentially, runs affected tests, and owns shared registry/schema/routers/orchestration. No two writers share a DB, checkout, port, output directory, dependency lock, or migration number. Full-scale scoring is one bounded heavy job per context, not several agents each scoring 5M.

## Release classifications

`14B_IMPLEMENTATION_GO`: integrated behavior and v1/v2 regressions pass.
`SIMILARITY_DESCRIPTIVE_GO`: supports a reproducible buyer-profile resemblance claim under its declared metric.
`PREDICTIVE_VALIDATION_UNAVAILABLE`: not a failure of descriptive scoring; blocks response/lift/purchase claims.
`FULL5M_GO`: actual complete population, exact identities, currentness, resource measurements passed.
`DEMO_GO`: every claimed scenario meets existing qualification using real current outputs; otherwise `DEMO_NO_GO`.
`REMOTE_CI_PENDING`: unavailable or unrun remote certification; cannot be called final release GO.

Changing score methodology after contract freeze requires a new score-method version and new generations, never relabeling old scores. Keep stable feature definitions and training-only scales. Do not manufacture 90 scores by min-max stretching or percentiles.
