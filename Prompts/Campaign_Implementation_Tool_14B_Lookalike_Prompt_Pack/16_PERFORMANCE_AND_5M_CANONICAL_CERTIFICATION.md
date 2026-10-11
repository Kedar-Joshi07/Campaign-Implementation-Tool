# Prompt 16 — performance and full five-million-row certification

> 2026-10-09 alignment addendum: recertify the exact PRD001+PRD003+PRD004
> context with `SIMILARITY_CUSTOMER_SPLIT_V2` and frozen partition identity.
> The versioned isolated runner is
> `scripts/validation/run_14b_15_1_full5m.py`; current measured evidence is
> `docs/evidence/lookalike_v3/16_1_SUPPORT_AWARE_FULL5M.md`.
> Preserve the earlier V1 `16_FULL5M` NO-GO as historical evidence. Separate
> per-product, complete-context and overall performance verdicts.

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

Prerequisite: 15 GO. This replaces older Prompt 16. Full5m is required for FULL5M_GO, never inferred from a 10K sample.

Use the actual canonical gzip demographics (summary declares 5M; count source identities independently),125K customer and 570K sales inputs on a disposable imported/migrated DB. If inputs are LFS pointers, materialize actual verified bytes; do not silently use samples. Record input hashes/import IDs/catalog/current schema, disk/memory/CPU/system/library versions and initial available resources. Existing operator canonical DB remains unchanged; if copying its several-GB state, measure disk headroom and preserve source checksum. Scratch certification outputs must not be committed as huge DBs.

Choose the recorded common product/historical context manifest from prior scenario work, not a new context solely for count yield. Missing manifest stops canonical demo-context certification; independent bounded certification may continue. Unsupported products keep safe blocked status. Build only supported exact profiles, score every demographic person in bounded chunks and deep-verify once. If profile support invalid, report the real blocker rather than regenerate data.

Measure training/cohort/scoring/verification/index/publication/prepare/reuse/preflight/materialization/history/export timings; memory peak, artifact/DB/WAL/disk usage, query plans, chunk size, retries and cache reuse. Quantify per-product costs and potential maximum context fanout. One verified score population can support multiple thresholds; no repeated training/scoring per scenario. No universal latency claim until measured on named hardware. Preserve existing performance limits where present; declare new v3 budgets before evaluating results, no after-the-fact relaxed gates.

Full integrity: source population=valid+invalid for each product; unique/no omissions/extras; score ranges/coverage; composite max and winner checks (full SQL aggregate plus independent sampled scalar scorer); lineage checks; latest-source currentness; snapshot count/hash. Stream common-feature drift and score distributions/min/max/quantiles/tier counts/cumulative>=counts at 50/60/70/80/90. These are empirical results, not expected top-percentile shares.

Perform one controlled restart midway on disposable full-scale work if resources permit, recording resume/replay cost and exact final identity. Test warm fast reuse and multiple sequential scenarios do not rebuild/scans unexpectedly. Independence: promoting v2 calibration does not force a new v3 score generation; replacing source invalidates it.

Use existing full5m/performance gates and add an explicit new versioned runner. Reconcile sample vs full output; no sample screenshots called 5M. If no actual full run, FULL5M_PENDING/NO-GO and record resume command; implementation may remainGO. Evidence: 16_FULL5M.{md,json} with commands/budgets/resources/limitations. Next 17 only after full required context validated.
