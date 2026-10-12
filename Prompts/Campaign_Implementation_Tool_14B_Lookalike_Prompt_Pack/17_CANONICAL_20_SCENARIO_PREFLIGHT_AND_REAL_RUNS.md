# Prompt 17 — unchanged scenarios, explicit v3 translation, real-run qualification

> 2026-10-09 alignment addendum for future execution only: refresh each exact
> scenario preflight against the current support-aware V2 profile/score
> generations, frozen partition, source checksums and unchanged scenario JSON.
> Prompt 16.1's one Scenario 20 snapshot is not a 20-scenario demo gate.

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

Prerequisite: 16 FULL5M_GO for exact current context. This replaces older Prompt 17.

Preserve original 20-scenario JSON byte-for-byte and IDs 1–20. Its historical default minimum 101 must not override the current 10,000 qualification registry; document that legacy metadata remains historical. Use the recorded common-context manifest required by scripts/validation/preflight_demo_readiness_scenarios.py. Do not guess a product/context if that uncommitted manifest is missing; report missing operator input and continue independent validation. If prior recorded context is unsupported under v3 floors, report it; an additional explicitly named context may be evaluated as a new demo set, never substituted into canonical results.

Create an additive versioned v3 translation manifest referencing original JSON hash and exact context/source/catalog/profile/generation identities. Mapping is explicit and separate from v2: VERY_STRONG → minimum .90, STRONG → .80, GOOD → .70, BROAD → .60. Exploratory .50 only for separately named new scenarios; no original scenario maps to .50. Distribution remains 1/2/7/10. Each mapped number now means cumulative similarity minimum; preserve v2 bucket mapping unchanged. This new translation is approved by this pack's declared semantics, not an invisible redefinition of old requests.

For each unchanged demographic scenario, run exact current v3 preflight: eligible, valid/invalid scored, qualified, selected, profile support/currentness, selected threshold, minimum 10K, and expected contact/export availability separately. Do not widen filters, lower thresholds, replace products, copy prospects, fabricate contacts or shrink 10K. Unknown/unprepared isn't valid zero. If not qualifying, record a truthful diagnostic and do not submit it as a qualifying preload. Controlled explicit empty-state tests belong to fixtures/integration evidence, not successful real demo runs.

Submit qualifying cases sequentially/bounded using the actual API/UI worker path. Track exact attempt/dependency/generation IDs, terminal outcome, elapsed/processing time, membership file/count/checksum and immutable reopen/representative governed export. Verify preflight selected=count of analytical membership exactly for unchanged bound source; exportable may be lower and explained. Save screenshots of actual results with safe identifiers and correct mode/labels. Prevent duplicate preload when retrying the script with a checkpoint/idempotency strategy.

A summary must report 20 tested, count eligible/qualifying/completed/blocked/failed, with reason per row. DEMO_GO only if all 20 promised scenarios meet the existing 10K gate and real runs/current outputs prove it. Partial success remains DEMO_NO_GO for the 20-scenario claim; runtime can still be technically correct. Do not promise 20 successful runs before model/data evidence.

Evidence: 17_SCENARIOS.{md,json} and translation/checkpoint. Preserve old scenario evidence. Next 18 can document honest NO-GO without falsifying success.
