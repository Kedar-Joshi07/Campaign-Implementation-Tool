# Prompt 18 — documentation, architecture, and client demonstration narrative

> 2026-10-09 alignment addendum for future execution only: describe V2 as an
> exact support-aware, customer-disjoint *descriptive buyer* holdout. Keep the
> old union-hash policy explicit in historical artifacts. Do not present the
> revised holdout as campaign-isolated purchase-probability validation,
> prospective lift evidence or repair of v2 calibration governance.

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

Prerequisites: completed 14B,15,16/17 actual outcomes including honestly blocked/pending statuses. This replaces older Prompt 18. Documentation can draft concurrently earlier, but final facts come from merged tested code/evidence.

Update root/docs/prompt READMEs, current schema/version/migration notes, OpenAPI examples and source-of-truth architecture. Preserve historical evidence and old prompt pack; mark newer 14B decision supersedes older conditional 14B without rewriting v1/v2 descriptions. Keep probability future mode documented as implemented with current known data/governance limitations. Explain calibration-only feedback updates versus actual profile/feature retraining.

Deliver concise architecture: separate probability model/calibration vs descriptive product buyer profiles; shared demographic data/filtering; independent readiness/generation/attestation; mode-specific selection/membership; immutable history; guarded export. Include dependency/invalidation matrix and single-node SQLite deployment boundaries. Show numeric 90 meaning, cumulative thresholds, tiers as labels only, productANY/max policy, unknown features/support, train-only scales, exact filter vs score difference and preserved legacy bands.

Client story: learn relevant historical buyer patterns → score new prospects → apply strict audience criteria → select minimum resemblance → review/export eligible contacts. Avoid guaranteed buyers,90% purchase likelihood,90% accuracy, validated lift, or production readiness. Sales use attributed buyers for this method; example phone/headphone fixture not current catalog. Explain catalog 48 vs observed 36 correction and unsupported products without hiding it.

Provide a practical demonstration script, operator runbook for preparation/currentness/retry/blocked states/mode switching/history/export, model factsheet, monitoring/retention/resource guide, and clear paths for later real outcome validation/stronger probability modeling. Populate all screenshots/counts from actual evidence with date/SHA/source/model identity. No invented metrics or borrowed fixture counts in client slides/doc.

Housekeeping only removes generated scratch via existing retention policy; never deletes old evidence/runs/scores because they don't qualify. Link actual reports and list pending actions: branch protection admin, remote manual workflow, full5m,20-scenario support as applicable. Evidence: 18_DOCUMENTATION.{md,json}. GO when docs agree with code/contracts/evidence and client claims are honest. Next 19.
