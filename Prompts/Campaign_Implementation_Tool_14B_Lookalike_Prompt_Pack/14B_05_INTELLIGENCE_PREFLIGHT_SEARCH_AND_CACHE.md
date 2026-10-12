# Prompt 14B_05 — Mode-specific intelligence, exact preflight, and materialization

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

Integrate v3 through submission, Phase10/11 orchestration, dependency retry, preflight and lifecycle. A v3 request resolves historical buyer profiles and similarity generations without requiring existing PU model/calibration campaign split. Add mode discriminator to compatibility/reuse identities rather than weakening legacy model eligibility. Never route an unknown version into legacy v1 defaults. Build/rejoin/reset handling uses repositories/state machines, not private worker calls.

Make build reachable when no similarity generation exists. Options/preflight identify demographic eligibility and build availability, then explicit prepare/search drives queued profile/scoring dependency. Progress distinguishes preparing buyer patterns, scoring, verifying, selecting/materializing. No field edit triggers heavy scoring. Blocked insufficient history is distinct from transient failed build, stale generation, zero qualifying results and queued work.

Implement one v3 selection predicate/iterator used by exact count and membership emission. Strict AND filters and canonical OR union dedup; score >= minimum on full precision, valid coverage only, same product/generation/source cutoff. No percentile reinterpretation. Preflight returns eligible/valid/invalid/qualified/selected separately. ALL_MATCHING parity; TOP_N explicit ordered cap. Use database snapshot/read-consistency and final source check so counts cannot belong to a different generation from materialization. Changed input requires refresh, not silent fallback.

Full cache identity per03_INTERFACE; prevent cross-mode/cache/profile/product/source/threshold/filter collisions. V1/v2 exact reuse remains stable. Snapshot reuse verifies stored analytical membership contract/hash; probability optional display is governed separately. Imports/method changes invalidate latest-currentness even if callback fails. Approved .90 cumulative doesn't reuse old v2 .90 by numeric coincidence.

Tests: A.96/B.92/C.88/D.73 eligible, E.97 ineligible; .90 → A/B, .80 → A/B/C. Include exact boundaries/nextafter, null/unknown/invalid, overlapping OR, all-equal, empty, TOP_N, stale source, missing calibration with ready similarity, ready probability with absent similarity, prepare → score → preflight → search cycle, queue/heartbeat/retry/fencing, preflight count==immutable membership==reopen count. Evidence: 05_PREFLIGHT_SEARCH.{md,json}.

## Operational health and invalidation proof

Extend runtime health and options coherently: critical worker/database failures degrade the supported workflows, while absent purchase calibration is a probability-specific unavailable state. A ready v3 similarity workflow cannot be globally hidden by a probability-only data limitation. Expose safe mode-specific readiness, without suppressing actual infrastructure failure.

Persist profile/model/generation build lineage and statistical scope in analytical metadata. Currentness is not synonymous with quality: a current profile can have modest descriptive quality; an unsupported profile cannot be promoted just because sources are fresh. Import invalidation callbacks and startup repair must both preserve those distinctions.
