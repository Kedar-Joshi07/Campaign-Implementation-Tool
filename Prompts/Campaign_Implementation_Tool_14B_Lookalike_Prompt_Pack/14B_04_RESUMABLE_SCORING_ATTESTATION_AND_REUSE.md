# Prompt 14B_04 — Chunked prospect scoring and generation verification

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

Implement a distinct v3 scoring resolver/storage path, possibly reusing proven chunk/job infrastructure. Profile identity+demographic source+method define a generation; threshold/filter/export edits do not retrain/rescore. A composite product set reuses verified per-product scores; max aggregation and deterministic winner/dedup are authoritative. Check disk/CPU cost before scoring many products; operator sees actual work and resource requirements. Current 50-product API limits do not imply 50 full score tables must be rebuilt per search.

Stream demographics by stable key in bounded chunks. Stage valid/invalid scores with exact one person per product/generation and immutable input version. Progress reflects actual processed rows, queue time separate, heartbeat through each chunk. Cancellation, lease loss, source replacement and process restart must not publish partial READY. Resume/checkpoint semantics must be validated; if restarting a stage is cheaper, explain and prove idempotence. Never score IDs/PII as features.

Deep-verification once per publication: expected and actual person population, distinct/no duplicates/no extras/no omissions, valid+invalid=source population, finite bounds, coverage and invalid reason consistency, model/source/checksum identities, product set/winner policy. Invalid feature rows cannot masquerade as valid zero scores. Attestations compare latest authoritative imports on every reuse, not merely stored old checksums; ordinary reuse avoids redoing full deep scans.

Publication is transactional after verified file/stage durability. Durable unique active work prevents duplicate builders across retries/coordinators; old execution token cannot publish or mutate. Existing v2 calibration singleton/attestation behavior remains unchanged. New score field is buyer_similarity_score, not calibrated_probability or raw_propensity_score.

Tests on bounded fixtures: duplicate/missing/extra person, corrupt artifact, source replaced mid-score, staged crash, stale lease writer, concurrent same context, chunk-size independence, 2 products max/dedup/winner tie, failed verification no READY, fast reuse skips validator, v2 calibration promotion doesn't stale independent v3. Evidence 04_SCORING_ATTESTATION.{md,json}. Full5m proof belongs to 16.
