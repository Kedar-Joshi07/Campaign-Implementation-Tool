# Prompt 14B_08 — Descriptive assurance, distribution comparison, and honest intelligence

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

Measure training customers vs prospect common-feature distributions with fixed training-defined bins and canonical vocabularies: numeric ranges/quantiles/missingness, KS statistic, categorical variation, PSI with recorded epsilon/bins/sample size. Compare at both broad training population and product buyer cohorts; product-buyer differences are expected and not automatically data corruption. No ID match required. Infer drift only from actual measured results; stale sources cannot be evaluated as current. Full5m distributions can be streamed under 16; bounded results labeled bounded.

Evaluate independent descriptive holdout score distributions, invalid coverage, prototype support/convergence, bootstrap fit stability and perturbation sensitivity. Bootstrap only fit buyers; deterministic seeds and sample budgets; no tuning to holdout or >=90/10K yields. Record score changes/membership overlap with uncertainty and poor stability honestly. Product specificity compares relevant profiles and unrelated-product control; learnable buyer patterns should change with buyer evidence. Unlabeled comparison is descriptive, not confirmed-negative classifier evaluation.

Enforce deterministic/profile/source isolation and no feature leakage. The historical graph remains one campaign component; descriptive customer holdout does not solve probability governance. Existing AUC 0.544 is historical nongoverned evidence; do not claim v3 improves it. Similarity may be broad demographic resemblance shared by many nonbuyers. Mark response/lift validation unavailable until independently observed outcomes/suitable design exist.

Build explanations from winning profile distance: actual feature weights, differences, exact per-feature contributions, coverage, selected product/context and support. Aggregate descriptions in business UI; no prototype customer identities/contact data. Do not generate invented percentages per feature or causal claims. If narrative AI exists, ground it only in verified bounded aggregates and distinguish observations from inference; deterministic templates suffice. No external LLM requirement.

Tests: independence from threshold/audience filter changes; sample/source identity; zero-range/missing feature score policy; misleading narrative terms prohibited; all-score-ties and low predictive evidence remain truthful. Evidence08_MODEL_DATA_ASSURANCE.{md,json}; factsheet with descriptive scope and predictive limits.
