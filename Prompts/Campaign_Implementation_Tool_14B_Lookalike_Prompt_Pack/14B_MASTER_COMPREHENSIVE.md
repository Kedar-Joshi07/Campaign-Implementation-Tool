# Prompt 14B — product-aware buyer similarity with retained purchase probability

## Execution contract — read before acting

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`.
Trusted starting SHA: `336875c30fc32b00323d916ecc45b232016168a1`. Starting code schema: 31.
This pack records Kedar's approved direction: add product-aware buyer similarity for the POC; retain purchase probability and all existing v1/v2 behavior for future use. Do not run 14A. This is a new approved alternative to the older conditional 14B. Preserve old evidence and append a dated decision addendum instead of rewriting its history.

Run `git rev-parse HEAD`, `git status --short`, and check applicable `AGENTS.md`. Accept the trusted SHA or a verified descendant containing completed pack stages; do not silently reset a newer branch. Record the actual starting SHA, preceding stage, and working-tree changes. Read `00_GUARDRAILS_AND_EXECUTION_ORDER.md`, `01_APPROVED_V3_SEMANTICS.md`, and `02_REPOSITORY_REVIEW_AND_INTEGRATION_MAP.md` from this pack before implementation. Paths for proposed new files are suggestions; existing paths are verified at the pinned SHA. Search all callers with `rg` before changing shared symbols.

Preserve unrelated changes, immutable history, existing probability columns/artifacts, default v2 behavior for legacy callers, calibration governance, BROAD → 0.60, explicit v2 0.50 semantics, and the existing 10,000 demo qualification minimum. No thresholds, filters, products, synthetic outcomes, or evidence may be altered to force counts. Existing tests must retain their original assertions. New v3 callers must explicitly request v3. There is no automatic historical conversion.

Use disposable DBs for migration/recovery/full-scale certification. Do not replace canonical inputs or migrate an operator's canonical DB without the existing authorized operational workflow. Routine code edits and test fixtures are within this implementation task. Do not send campaigns or contact people. Do not commit, push, merge, or deploy unless the operator has authorized that action in the session. Do not invent a pending remote CI success.

All worker writes need durable owner/token fencing, bounded messages, transactional publication, current-source checks, and safe cancellation. Contact PII and raw traces must not enter analytical metadata or evidence. Prove each requirement with independent expected outcomes, not an oracle copied from the function under test. Report blocked and skipped checks explicitly.

Completion: starting SHA; candidate SHA or UNCOMMITTED; changed files; requirements proved; preserved v1/v2 behavior; schema/API/data impact; exact commands and results; evidence paths; limitations; stage GO/NO-GO; next stage. Runtime correctness, descriptive-model quality, predictive validation, full-5M readiness, and demo readiness are separate decisions.


## Your job

Implement the user's original look-alike POC as a fully integrated additive v3 workflow. Do not stop at renaming the current purchase-probability dropdown. Implement contracts, learning, input assurance, profile artifacts, full-universe scoring, intelligence orchestration, UI, exact counts, immutable membership, safe export and feedback lineage. Preserve the existing mature probability feature, including historical reads and future supported execution.

This controller's detailed normative requirements are `01_APPROVED_V3_SEMANTICS.md` and `03_INTERFACE_AND_DATA_CONTRACT.md`. Execute the ten 14B stage prompts in order; use them as the detailed work plan and acceptance checklist. Never mark the master complete after only a policy document. When resources/data genuinely block a later gate, report precisely what is implemented, what is unvalidated, and which step resumes; continue all independent authorized work.

## Business example and actual input constraints

A request might ask for Male, age 30–40, Texas/California, income 80K–100K, Bachelor+ education, Married or Unmarried, and headphones/mobile phones. Filters are exact, inclusive on bounds, validated against canonical vocabularies; synonyms require an explicit approved map, not fuzzy assumptions. The actual catalog lacks those exact products. A dedicated fixture must demonstrate the example; real runs use exact existing catalog products. Never rename a historical product or claim that fixture results are canonical.

Expected selection example independent of the model: eligible A=.96, B=.92, C=.88, D=.73; ineligible E=.97. Minimum .90 selects A/B. Minimum .80 selects A/B/C. This is cumulative. Existing v2 .80 still means [.80,.90), not >=.80.

## Architecture target

Historical customer+sale linkage produces distinct relevant attributed buyers per selected product/context. The v3 profile builder learns supported mixed-feature prototypes using the declared training-only preprocessing. A deterministic customer-disjoint holdout checks descriptive similarity without claiming campaign-independent predictive validation. Score the independent prospects from the shared feature vocabulary; exact identity overlap is unnecessary. User filters determine eligibility; a shared predicate selects valid scores >=minimum. Publish an immutable result and export through existing channel-specific consent/contactability gates.

Maintain separate resolvers/readiness for purchase prediction versus similarity profiles. Similarity must not require promotion of a purchase calibration or probability's three-way campaign-connected split. V2's governed split must not be weakened. Current probability can optionally accompany a v3 result only when independently valid and lineage-compatible.

Use the existing single-node SQLite/worker application. Extend seams rather than replacing the application framework, adding a distributed platform, or rewriting the 5M data pipeline. Mode-aware contracts and selective extensions are the goal. Automatic feature-model learning/retraining beyond existing governance remains future work unless explicitly scoped here; feedback ingestion gets truthful v3 identity now.

## Required deliverables

1. Baseline golden compatibility and append-only approved decision.
2. Typed v3 registry/request/options/readiness/results/membership contracts and real migration from schema 31; consistent README/OpenAPI/schema code. One owner allocates next migration(s), validates all checks/FKs/indexes, and certifies old DB identity preservation.
3. Product-context buyer cohort service, per-product support manifest, source alignment/drift report, corrected observed-product coverage reporting. No canonical data regeneration.
4. Profile model + artifact persistence/integrity + descriptive holdout and stability evidence. Learned profiles must visibly depend on relevant historical buyers; unrelated products/filter edits cannot redefine the same score.
5. Chunked resumable v3 scoring, generation publication, source-current attestation, integrity and invalid-row accounting over all prospects; reusable by threshold/channel edits.
6. Separate v3 intelligence prepare/reuse state machine; exact preflight and search/materialization share normalization/predicates; full cache identity; startup/retry/cancellation/fencing preserved.
7. Business UI defaults to the certified new similarity mode, with 50/60/70/80/90 minimums, truthful index labels and clear advanced probability option. Saved history uses stored versions. Model-unavailable/building/stale/unsupported/zero states are differentiated.
8. Immutable v3 membership, history/details/reuse/currentness, deterministic analytical output, contact-profile exports and feedback origin identity. No relabeling legacy files.
9. Model/data/quality assurance and bounded client explanations with distinct probability and predictive-validation limitations.
10. Integration tests and completion evidence; 15–19 then certify faults, canonical size, scenarios, documentation, and release.

## Non-negotiable regression obligations

Freeze BROAD=.60, explicit .50 v2 range, v2 default .70, legacy aliases, all canonical scenario JSON values and current API compatibility. Preserve probability promotion singleton, feedback fit/evaluation separation, public currentness vocabulary, owner rotation, exact reuse, ETA timing, safe errors, import atomicity and export safeguards. New schema defaults cannot reinterpret old rows as v3. No new v3 request can be accidentally sent to a v1 fallback.

## Quality and truthful presentation

Similarity explains demographic resemblance under a declared metric. It does not guarantee conversion, uniqueness of buyer behavior, high lift, or product demand. A near-random purchase model cannot be transformed into a strong predictor by percentile normalization. V3 learns a separate descriptive profile, not a relabeled PU score. Produce exact numeric examples and per-feature contributions from the actual winning prototype, plus aggregate evidence without revealing real buyer identities.

The reference 0–100 score is not arbitrary min-max scaling. High similarity may still be rare, or equally common among nonbuyers. Quantify those limitations. Zero results at .90 is legitimate. Demo minimums are qualification policy, not model training objectives.

## Execution and completion

Follow the dependency table. Optional lanes must obey ownership and interface freeze. Sequential is equally valid. Run focused checks while implementing, then the bounded full regressions once integration is complete. Do not run large scoring repeatedly for every UI choice. Do not silently substitute sample evidence for full5m.

Create evidence under `docs/evidence/lookalike_v3/` with stage-specific Markdown and JSON, schema/contract identity, actual commands, timings, source identities, test outcomes and unresolved gates. Final 14B status is implementation/descriptive status only, not premature final/demo GO. After 14B_09 pass, run updated 15,16,17,18,19. Do not run the old 14B or 14A.
