# Prompt 14B_06 — Buyer-similarity UI and preserved probability mode

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

Integrate frozen contracts into business-search-form.js, targeting/status/results/planner and related templates/CSS/options. New campaign UI defaults explicitly to certified v3, not by changing v2 default. Similarity control says minimum 50/60/70/80/90 and above; label index 0–100. Tooltip defines model-relative demographic distance to supported product buyer profiles; not probability/percentile. Preserve explicit advanced Purchase Probability mode and its discrete band labels/currentness/error states. No new purchase/lift claim.

Maintain separate mode state and validation. Switching clears/replaces incompatible score fields and invalidates preflight; late response for old mode/context cannot overwrite current state. Reopening saved v1/v2 uses original mode/version/labels. Show saved original filters/products/model version and immutable membership. Exact v3 product choice drives learned context; target filters drive eligibility only. Option counts/eligibility based on actual buyer support, not all 48 catalog entries assumed ready.

Display eligible prospects, validly scored pool, similarity-qualified, selected and eventual exportable counts distinctly. A missing generation is “Not prepared” with reachable prepare/start action, never “0 buyers”. A valid zero is a clear empty state. Show queued/building/stale/unsupported data/temporary failure/feature coverage separately. Existing retry controls, queue timing, monotonic progress and accessible error summaries remain.

Explain .80 includes .90+ in v3 whereas old v2 band does not. Do not render optional old probability as zero/current. When available show it as a separate metric with its own provenance; unavailable is not a red similarity blocker.

Browser tests against actual API: new/default v3 payload, advanced v2 payload unchanged, switching response races, missing calibration v3 builds, unsupported products, exact lower/upper filter bounds, product IDs, saved histories, refresh/retry, keyboard/labels/tab order and responsive desktop/tablet/mobile. Verify screenshots visibly contain correct score language and counts. Fixture screenshots explicitly labeled fixture, not canonical. Evidence06_UI.{md,json}.
