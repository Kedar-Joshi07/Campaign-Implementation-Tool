# Prompt 14B_02 — Product-aware buyer evidence and source alignment

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

Reuse existing exact customer_id sales joins, attributed purchase definition, completed-age reference date, normalization and provenance. Implement a separate descriptive buyer-cohort service without changing PU training behavior. Product/context/window selection precedes customer-grain deduplication. One distinct customer per product; repeated orders do not reweight. Customers may belong to several product cohorts with a consistent union-level train/holdout assignment. Record demographic reference date and explain historical age vs prospect age; no dynamic wall-clock score drift.

Keep historical analytical context separate from prospect hard filters and delivery channel. Exact selected products only; no fuzzy headphones → earbuds or phone → tablet mapping. Enforce ANY_SELECTED_PRODUCT_MAX_V1, per-product floor 200 then realized 160/40 split. Unsupported/no history/insufficient/unknown products produce bounded reasons, no category/global fallback. Existing category model future policy may be documented but not silently enabled.

Audit customer PK uniqueness, sales FK coverage, attributable flag/date validity, missing values, shared vocabularies, state canonicalization, currency/income units and age conventions. Prove 125K customer and 5M prospect IDs are independent and need no identity mapping. Fix observed-product reporting in generator/validation summaries while preserving raw canonical files and previous historical evidence; publish explicit correction, not an invented 48-product training population.

Create customer-disjoint descriptive split manifest and hashes; training/holdout never overlap across products. Sales purchase label is only for buyer membership. Do not treat pu_label=0 as a verified nonbuyer. Non-attributed comparison cohort must be labeled unlabeled unless independent outcome data supports a stronger claim.

Tests: wrong customer join; repeat purchase; same customer two products; context/filter independence; no future window; unsupported products; support floors exactly 199/200; missing demographics; unordered products normalize; unknown source checksum changes. Evidence 02_BUYER_COHORTS.{md,json}, product support manifest. GO when cohort exactly reproducible from current inputs.
