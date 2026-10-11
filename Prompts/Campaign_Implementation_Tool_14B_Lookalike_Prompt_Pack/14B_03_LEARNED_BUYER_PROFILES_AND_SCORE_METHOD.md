# Prompt 14B_03 — Learn, serialize, and verify descriptive buyer profiles

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

Implement BUYER_PROFILE_DISTANCE_V1 exactly as 01_SEMANTICS. Use 11 validated shared fields, training-only q05/q95 scales, categorical normalization, equal declared weights, missing penalties and coverage. Learn supported multiple prototypes with deterministic bounded mixed-type clustering, numeric median/categorical mode updates, declared initialization/k selection/ties/iteration budget. Do not import a purchase estimator and normalize its output. No all-pairs matrices or unbounded model selection. Artifact records every parameter, convergence, support, source/context/split identity and library/method version.

Persist prototype values/support without internal customer identifiers or PII. Integrity-checked artifact loading refuses corrupted, incompatible, stale-source or partial files. Score distance and per-feature contributions use a single scorer function. Serialize safely through existing governed artifact storage, checksum and path rules; no arbitrary user-uploaded pickle execution. Read/write parity and same chunk-size scores must be deterministic.

Holdout is descriptive customer-disjoint validation, explicitly not campaign-independent prediction. Preprocessing/cluster selection cannot use holdout or prospect distributions. Numeric ranges are inferred only from fit buyers, with declared zero-range fallback; inference differences saturate distance at 1 without imputing/clipping to match a center. Unknowns earn no credit; coverage<.80 invalid. Explain how categorical mismatch weighs 1/11, and why 90 is a method-specific distance threshold rather than empirical accuracy.

Independent fixture: set one known prototype with fixed scales/weights; exact known match=1, one categorical mismatch=10/11, several numeric deviations produce a manually calculated sum. Missing all features → invalid, not 1. Check monotonic distance with fixed prototype, ties, multimodal buyer groups, singleton cluster rejection, same historical buyers with reordered rows, unrelated-product changes, and changed relevant buyers causing profile/score change. Score 1 exists only for an exact fully observed prototype match.

No generic AUC/lift pass needed for descriptive fit, but weak buyer specificity must be reported by later assurance. GO requires declared scorer mathematics, deterministic fit, support, valid artifact and leakage boundary. Evidence 03_PROFILE_METHOD.{md,json}.

## Primitive and initialization consistency

Numeric medians minimize the declared absolute-distance term; categorical modes minimize the mismatch term. Use the same missing/unknown penalties in fitting, support assignment and inference. A modal tie uses canonical lexical order; a nearest-prototype tie uses frozen prototype order. Seed selection and farthest-first selection only inspect fit customers; remove identity columns before serialization. For a prototype coordinate with no observed fit values, mark it unknown and apply the same distance penalty. Do not falsely impute a known value and award match credit.
