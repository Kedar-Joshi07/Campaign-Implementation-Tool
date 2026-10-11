# Prompt 14B_00 — Baseline, approved decision, and frozen compatibility

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

Inspect pinned source, applicable instructions, prior 13/13.5/13.6/13.6.1 evidence and old 14B/15–19. Build a requirements-to-caller map using the verified integration map. Record the current unversioned submission behavior and v1/v2 persisted contracts through characterization tests, not guesses.

Create golden fixtures for legacy raw-score v1; v2 [.50,.60), [.60,.70), [.70,.80), [.80,.90), [.90,1]; BROAD=.60; default=.70; 10K demo gate; options/openapi/currentness; historical results/export readback. Include .49,.50,nextafter(.60,0),.60,.70,.80,.90,1 and invalid values. Pin all 20 scenario JSON hashes and distribution 1 VERY_STRONG/2 STRONG/7 GOOD/10 BROAD. Capture DB 31 identity signatures on a disposable representative database. Record actual canonical DB availability separately.

Append dated approved v3 decision to the existing decision document or new linked addendum, preserving prior evidence. State that this replaces the choice of old percentile 14B with declared profile-distance similarity. Record cumulative >= thresholds and retained purchase probability. The user's direction is already authorization to implement this design; do not re-ask 14A/14B.

Capture imports/feature/category/date conventions and catalog coverage. Stream CSV audit or query verified imports: catalog=48 vs sales observed=36 at the pin. Define reconciliation and record product support, without assuming the summary is authoritative. Baseline tests run before modification; failing legacy tests become tracked blockers.

Output baseline SHA/file/hash manifest, golden fixtures, decision addendum, gap matrix, preservation plan. GO when baseline reproducible and requirements mapped; NO-GO if provenance/version ambiguity remains. Evidence: 00_BASELINE.{md,json}.
