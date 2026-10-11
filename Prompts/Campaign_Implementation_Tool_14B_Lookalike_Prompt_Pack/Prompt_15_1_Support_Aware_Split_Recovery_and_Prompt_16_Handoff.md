# Prompt 15.1 — Support-aware similarity split recovery, Prompt 15 closure, and automatic Prompt 16 execution

You are working on `Kedar-Joshi07/Campaign-Implementation-Tool`.

Complete the authorized implementation and validation below. Establish Prompt 15 GO through actual evidence, then automatically execute the updated Prompt 16. Do not stop at a plan, a diagnosis, or “ready to run 16.” Do not force a GO if a required check fails.

## 1. Current situation and scope

The implemented POC uses additive v3 product-aware buyer similarity. Purchase-probability functionality and historical v1/v2 behavior remain retained.

The recorded canonical search requires all three products:

- PRD001
- PRD003
- PRD004

The reported Prompt 16 outcome is:

- PRD001 has 200 distinct attributed buyers.
- Its original joint customer split produces 158 fit buyers and 42 holdout buyers.
- Required descriptive support is at least 200 total buyers, 160 fit buyers, and 40 holdout buyers per product.
- PRD003 and PRD004 have reportedly been scored and verified over the five-million-person universe.
- The exact three-product context remains NO-GO because PRD001 fails its fit-support minimum.

These are reported observations: reproduce them from current authoritative inputs and persisted evidence. Do not assume them verified merely because this prompt contains them.

The operator approves a focused refinement: introduce a deterministic, support-aware, customer-disjoint similarity split policy that preserves these support floors and the recorded context. Preserve the existing split as historical policy, create new lineage for the revised split, and recertify affected work.

This authorization covers necessary code, tests, contracts, migration changes if actually needed, documentation, and bounded/full-scale execution on isolated certification databases and artifact roots. Do not alter or replace the operator's canonical source files/database. No campaign sending, external activation, or probability-policy changes are authorized here. Honor any existing session authorization for commits/push; otherwise leave changes reviewable and report UNCOMMITTED. Commit/push is not a prerequisite for the local Prompt 15 stage gate; exact-SHA final release certification remains Prompt 19's responsibility.

## 2. Establish the actual baseline

Before editing:

1. Run `git rev-parse HEAD` and `git status --short`. Record the actual current HEAD and preserve unrelated changes. The earlier pack's trusted SHA was `336875c30fc32b00323d916ecc45b232016168a1`; do not reset the implemented branch to that older SHA. Verify its relationship to the earlier work and read applicable `AGENTS.md`.
2. Locate the installed updated look-alike prompt pack. Read its approved semantics, interface contract, Prompt 15, Prompt 16, and the actual 14B implementation/evidence. Use the updated v3 pack, not the older probability-oriented recovery prompts.
3. Discover the real similarity split, cohort/profile builder, fingerprint, artifact, generation, attestation, search, retry, snapshot, export and feedback modules with `rg`. Do not invent existing module names. Follow callers and consumers, including schema/API/UI readiness projections.
4. Read the current recorded common-context manifest and prior Prompt 15/16 evidence. Preserve exact products, historical window, conversion definition, context filters, prospect filters, thresholds and selection mode. Do not guess missing context fields. Missing context stops only context-dependent certification; continue independent implementation/tests.
5. Reproduce the original split counts on a disposable database or a read-only authoritative-input path. Capture private membership hashes and bounded public counts. Explain the original result, particularly why 200 total buyers does not guarantee the required per-product split.
6. Check whether Prompt 15 already has valid evidence. Distinguish existing passes from missing cases; rerun checks affected by this change and any unproved required critical cases. Never claim old evidence certifies changed code.

Keep the original Prompt 16 NO-GO evidence immutable. Append a dated superseding recovery report rather than rewriting historical test results or assignments.

## 3. Preserve the approved business and score contracts

Keep unchanged:

- All three selected products and the recorded search context.
- At least 200 distinct attributed buyers, 160 fit buyers and 40 holdout buyers per product.
- A single fit/holdout assignment for each customer across every product in this composite modeling context.
- V3 product matching: ANY-selected-product/max score over eligible separate product profiles; every requested product must first be eligible. Do not silently drop unsupported products.
- V3 similarity score mathematics, supported prototypes, training-only preprocessing, missing/unknown penalties and feature-coverage rules.
- V3 cumulative similarity minima 0.50/0.60/0.70/0.80/0.90, strict audience filters, and existing 10,000 demo qualification gate.
- V1 raw-score behavior; v2 calibrated purchase-probability bands; BROAD→0.60; explicit v2 0.50; default v2 0.70; calibration isolation and promotion rules.
- Original canonical scenario JSON, immutable history, snapshots, feedback and prior artifacts.

Do not lower a floor to 158, try random seeds until the search passes, duplicate customers, fabricate sales, broaden buyer definitions, regenerate canonical data, or remove PRD001. Do not use similarity outputs, model metrics or demo yields to choose the partition.

## 4. Implement a new deterministic support-aware split policy

Use a distinct version identifier, for example `SIMILARITY_CUSTOMER_SPLIT_V2`, after checking actual version allocation. Preserve the original policy for interpreting historical artifacts. This changes similarity training/split policy identity; it does not require changing selection contract v3 or the score's mathematical meaning.

### Hard constraints

Build the union of distinct eligible buyer customer IDs across the selected products after the exact historical/context filters.

For each customer i, define one binary assignment h_i:

- h_i = 1 means holdout.
- h_i = 0 means fit.

For product p with buyer set B_p and count n_p:

- `sum(h_i for i in B_p) >= 40`
- `sum(h_i for i in B_p) <= n_p - 160`
- `n_p >= 200`

For PRD001 with exactly 200 buyers, these constraints imply exactly 40 holdout and 160 fit buyers. Determine whether this is jointly feasible with the other products. Do not promise feasibility without solving and verifying the actual membership problem.

Each customer has one assignment across the entire composite. Repeated sales do not add votes. A shared buyer cannot be fit for one product and holdout for another.

### Target ratio and deterministic objectives

Treat 80/20 as a target, not a hard global equality that might unnecessarily conflict with the per-product support floors. Freeze an explicit deterministic objective before fitting or evaluating models:

1. Meet all hard support/isolation constraints.
2. Minimize per-product deviation from the declared integer 20% holdout target; define rounding exactly, such as `floor(0.20*n_p + 0.5)`.
3. Among equivalent solutions, minimize the union's deviation from its integer 20% holdout target.
4. Among equivalent solutions, minimize assignment changes from the original deterministic baseline for the same exact sources/context, if that baseline is available and verified.
5. Resolve remaining ties with a declared stable identity-hash ordering and deterministic final assignment ordering.

Publish the actual objective order, seed/hash rule, rounding, feasibility status and resulting counts. Keep seed 20261005 where compatible with the approved implementation; seed must be fixed policy, not a searched performance parameter. Product list order, input row order and process restart must not alter the result.

### Efficient implementation

For the three-product case, group customers by their product-membership signature. There are at most seven nonempty signatures. Solve how many holdout customers belong to each signature, subject to the per-product constraints, then select their actual identities deterministically.

Use a suitable exact bounded integer approach or an already available pinned solver. If introducing a dependency is genuinely necessary, justify it, pin it through repository policy and validate determinism. Do not solve over five million prospects: only historical distinct buyer memberships belong in this problem.

When minimizing changes to the prior baseline, account explicitly for baseline fit/holdout counts within each signature; use further grouping if needed. Do not let an arbitrary choice within a signature undo the stated objective.

Do not rely on a generic stratified splitter to guarantee the hard constraints. Do not claim a heuristic failure proves mathematical infeasibility. Distinguish:

- FEASIBLE, independently verified against actual customer memberships;
- INFEASIBLE, proved by the selected exact method;
- UNRESOLVED/TIMEOUT, not a proved infeasible population.

Return bounded safe reason codes and counts for blocked/unresolved cases, without logging customer identifiers, solver internals containing PII, or raw exceptions into public business metadata.

### Isolation and fit discipline

Create and freeze the new complete partition manifest before training. Fit preprocessing and profiles only on its fit customers. Validate only against the designated holdout customers. Do not move two previously evaluated buyers into training and retain old validation metrics.

The partition may use identities and product-membership labels to enforce support. It must not use demographic feature values, similarity scores, metric outcomes or campaign yield for optimization. New validation remains descriptive customer-disjoint evidence; it is not governed campaign-isolated purchase probability, prospective lift validation, or a claim that the holdout has never been previously observed.

## 5. Version lineage, currentness, caches and affected artifacts

Propagate the new split-policy version, exact source/context identity, partition manifest hash and fit/holdout membership hashes through all similarity artifacts that depend on the split:

- cohort and profile/model manifests;
- training eligibility and profile compatibility;
- generation/scoring dependencies and attestations;
- composite context compatibility;
- preflight and result cache identity;
- snapshot provenance, result currentness and export eligibility;
- retry/resume ownership and build deduplication;
- relevant public readiness/reason projections and diagnostics.

Follow the actual implementation's canonical fingerprint helpers. Do not maintain a second partially equivalent hash convention.

Preserve old immutable profiles, scores, attestations and snapshots. New policy selects compatible current artifacts; old policy artifacts must not silently qualify as new-policy outputs. An old artifact remains historically readable with its original semantics.

Evaluate PRD003 and PRD004 reuse individually. Reuse only when actual fit/holdout assignments, profile parameters, source identities, and full required policy/manifest compatibility legitimately remain unchanged under the new contract. Same numeric scores or the same source checksum alone are insufficient. Otherwise rebuild affected profiles, reevaluate and rescore through the governed production path. Do not unnecessarily repeat unaffected heavy work, but correctness takes precedence over avoiding a scan.

The existing purchase-probability calibration and its artifacts do not change. A similarity split-policy change must not pretend to repair its campaign-connected split limitation.

If persistence changes are needed, use the next correctly allocated additive migration. Verify fresh/current/legacy-populated databases, repeat initialization, rollback on failure, keys/counts/references, integrity and foreign keys on disposable copies. Do not modify historical migrations or force an operator canonical migration.

Append alignment addenda to the current authority for Prompts 15–19: new split-policy identity and tests in 15; actual compatible generations in 16; refreshed preflight in 17; truthful policy description in 18; version/regression checks in 19. Preserve old evidence. Do not execute 17–19 in this run.

## 6. Required split and compatibility tests

Add independent expected results, including:

1. The actual original PRD001 158/42 result is reproduced and remains correctly rejected under the old policy.
2. A controlled 200-buyer product yields exactly 160 fit/40 holdout under a feasible new joint assignment.
3. Three overlapping product cohorts have no cross-product fit/holdout identity overlap and all hard floors are checked against actual sets.
4. Reordered input rows/products and process restart produce the same manifest and membership hashes.
5. A below-200 cohort remains insufficient; no relaxation or product dropping.
6. An independently constructed incompatible overlap/constraint fixture remains blocked. A small parameterized solver fixture may prove infeasibility; nominal 200/160/40 checks also need representative tests.
7. A timeout/unresolved solver case is not mislabeled mathematically infeasible or READY.
8. No demographic features, scores or held-out metrics influence assignments; modifying those while identities/memberships stay fixed cannot change the partition.
9. Training-only preprocessing and profile fitting remain isolated from the new holdout set.
10. Old-policy and new-policy cache/artifact identities cannot collide or be silently reused.
11. V1/v2 requests/history/calibration/export/feedback remain unchanged.
12. A ready v3 workflow still works without probability calibration; v2 governance is not bypassed.

Do not weaken existing assertions to make these pass. If an existing test covers historical split behavior, keep it and add policy-specific coverage for the new behavior.

## 7. Complete and prove the entire applicable Prompt 15 fault matrix

Run the updated Prompt 15, including the revised split/profile stages. Use disposable databases, artifact roots, ports and output paths. Never inject crashes into the canonical operator database.

Required boundaries:

- partition computation and manifest publication;
- profile build and artifact fsync/rename;
- scoring stage chunk commit and resume;
- score verification, generation publication and attestation creation;
- queued dependency creation/rejoin/retry;
- preflight/cache read and source replacement;
- result file publication and registry completion;
- export and feedback ingestion;
- import invalidation;
- startup/shutdown and stale lease takeover.

Inject representative process crashes, exceptions, source changes, corrupt files, failed writes, expired heartbeats and stale workers. At each boundary prove:

- no false READY/COMPLETED or downloadable partial artifact;
- no lost/rewritten historical membership;
- fenced state changes and bounded safe messages;
- idempotent recovery or explicit terminal blocking;
- no duplicate active build/publication;
- correct currentness and retry eligibility.

Concurrency cases must include identical v3 submissions, different thresholds sharing intelligence, different products, mixed v2/v3 requests, cheap current reuse while a heavy job runs, source changes during preflight/materialization, UI mode-switch response races, and active worker shutdown. Preserve queue-versus-processing timing and actual-row progress accounting. Keep single-node SQLite limits explicit.

New-policy cases must include crash during split publication, restart reusing the exact frozen manifest, competing builders with the same partition identity, stale owner unable to publish a new-policy profile, and incomplete manifest/profile unable to report READY.

Insufficient history or proven infeasible support is a legitimate nonretryable data-policy result, not a fault-test failure when the expected behavior is correctly proven. An unresolved solver computation has its own reason and governed retry classification; never spin indefinitely.

Run focused split/fault tests, affected regression modules and the repository's applicable bounded integration/compatibility gates. Preserve existing probability promotion, feedback isolation, lease fencing, snapshot, export and API coverage. Record actual commands and counts. Every required critical boundary needs a concrete test or controlled production-path experiment; don't mark it complete because code exists.

## 8. Prompt 15 evidence and GO gate

Create append-only/current-authority recovery reports, using an available versioned path such as:

- `docs/evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md`
- `docs/evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.json`

Include starting SHA, actual current schema/contracts, exact tree/diff identity if uncommitted, reproduced original defect, new policy/objectives, feasibility proof, per-product old/new fit/holdout counts, private partition hashes, affected/reused artifacts, tests/fault matrix, commands/results, regression evidence, and remaining limitations. Public evidence must exclude customer IDs, contact PII and execution tokens.

Link the new report as current Prompt 15 authority without erasing the original report. Only record Prompt 15 GO if:

- the revised split implementation is correct, deterministic and isolated;
- all applicable critical Prompt 15 fault/restart/concurrency cases are proven;
- affected regressions pass;
- versioning, currentness, fencing, publication and retained probability behavior have no unresolved correctness blocker.

A true data-feasibility blocker can coexist with Prompt 15 runtime GO if the application correctly handles it and all runtime tests pass. It must remain explicitly Prompt 16 context NO-GO. Do not conflate these statuses.

If Prompt 15 is NO-GO, fix authorized repairable defects and rerun affected checks. If an unresolvable dependency/resource/input prevents a required check, report the exact blocker and resume point; do not start dependent Prompt 16 execution.

## 9. Automatically execute the updated Prompt 16 after Prompt 15 GO

Once Prompt 15 GO is established, continue in this same task. No further confirmation is needed to start the already requested isolated certification.

Read and execute `16_PERFORMANCE_AND_5M_CANONICAL_CERTIFICATION.md` from the updated look-alike pack, with the new split-policy addendum. Do not run the older recovery pack's Prompt 16.

First verify the exact recorded PRD001 + PRD003 + PRD004 context and current new-policy eligibility. If the new joint partition is feasible and all profiles qualify, run full-scale certification on an isolated database and artifact root using actual verified canonical bytes. Materialize genuine LFS data when needed; samples cannot substitute for five million prospects.

Execute the complete Prompt 16 requirements: actual source/population identities, training/evaluation and score integrity, per-product valid+invalid accounting, unique/no omissions/no extras, correct composite max/winner, source-current attestations, measured resources and timings, cumulative threshold counts, fast reuse, preflight/materialization checks, and required bounded restart/performance checks. Reuse only fully compatible verified artifacts and explain each reuse decision.

Record separately:

- per-product full-population scoring/integrity;
- complete three-product context readiness;
- overall Prompt 16 certification;
- demo scenario readiness, which belongs to Prompt 17.

If actual memberships are proved infeasible, preserve the exact products/context and document the genuine data-policy block. Continue independent permitted diagnostics, but do not certify a two-product search as the original search. Do not force a GO, manufacture buyers or automatically start Prompt 17.

If resources or missing canonical/context inputs block full-scale execution, retain checkpoints, exact resume commands and pending status. Do not launch an untracked background process and report completion. Persist until the authorized Prompt 16 execution finishes or a concrete blocker prevents further progress.

## 10. Required final response

Return:

- Starting SHA and candidate SHA or UNCOMMITTED, with local tree/diff identity.
- Original behavior reproduced and root cause.
- Old versus new split-policy versions and frozen deterministic objectives.
- Per-product total/fit/holdout counts, feasibility outcome and customer isolation proof.
- Files changed and schema/API/data impact.
- Profile/score artifacts reused versus rebuilt, with compatibility justification.
- Prompt 15 fault matrix, commands, pass/fail/blocked counts and evidence paths.
- Retained v1/v2 purchase-probability regression results.
- **PROMPT 15 = GO or NO-GO**, with a precise reason.
- **PROMPT 16 = STARTED / GO / NO-GO / BLOCKED**, with actual execution details. STARTED is only a live status if execution genuinely remains in progress; prefer completing the authorized run before returning.
- Separate per-product versus complete-context full-5M verdicts.
- Remaining limitations and exact next action.

Do not claim Prompt 17/20-scenario demo GO or final exact-SHA release GO from these results alone.
