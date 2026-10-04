# Prompt 13.6 — Pre-14 Stabilization, Statistical Integrity, Contract Extensibility, Runtime Ownership and CI Hardening

## Purpose

This is a mandatory stabilization pass after successful Prompt 13.5 and before either Prompt 14A or Prompt 14B.

The purpose is **not** to choose a business-selection policy, improve demo counts, introduce selection contract v3, change probability thresholds, or make the current canonical data produce customers.

The purpose is to remove latent correctness defects, statistical leakage, cross-contract inconsistencies, concurrency weaknesses, CI gaps, and obvious future-change friction that would otherwise create avoidable rework during Prompts 14–19.

Treat this as a release-engineering and architecture-integrity pass over everything implemented from the initial repository/Phase 1 through Phase 11, Phase 11 runtime closure, recovery Prompts 00–13, and Prompt 13.5.

---

# 0. Mandatory starting state

Repository:

`Kedar-Joshi07/Campaign-Implementation-Tool`

Expected starting HEAD:

`58a5852d488aa686ed67ffa7ccecbc50463f4081`

Known exact-SHA CI certification:

`GitHub Actions run 36818012626`

At that SHA all five normal CI jobs were green:

- Repository Hygiene
- Python Validation
- Tests
- Frontend Contract
- Clean-Room Phase1-7

Do not trust this prompt, prior evidence, README statements, commit messages, or test names without checking the repository yourself.

Before modifying anything run:

```text
git rev-parse HEAD
git status --short
git log --oneline --decorate -30
```

If HEAD is not exactly:

```text
58a5852d488aa686ed67ffa7ccecbc50463f4081
```

continue only when HEAD is a documented descendant created specifically for this Prompt 13.6 and compare every intervening commit first.

Do not discard unrelated working-tree changes.

Record the initial state in the evidence.

---

# 1. Absolute guardrails

The following are prohibited in Prompt 13.6:

```text
choosing 14A or 14B
introducing selection contract v3
introducing new probability buckets
lowering the existing 0.50 minimum probability
changing 0.90 / 0.80 / 0.70 / 0.60 / 0.50 v2 semantics
changing the 10,000-customer demo qualification requirement
widening targeting criteria
fabricating potential customers
fabricating feedback
duplicating people to increase counts
rescaling calibrated probabilities
presenting percentiles/ranks as probabilities
falling back from campaign-connected governance to random customer splitting
restoring MIN(campaign_id) grouping
changing canonical campaign data simply to manufacture disconnected components
rewriting historical attempts
rewriting historical snapshots
rewriting historical model/calibration identity
silently changing old API semantics
silently migrating historical v1/v2 runs to a future version
implementing activation/send integrations
claiming true model retraining where only recalibration occurs
claiming multi-node/distributed support unless it is actually implemented and tested
running Prompt 16 full-5M certification
running Prompt 17 20-scenario real qualification
performing the broad Prompt 18 housekeeping sweep
```

The canonical one-campaign-connected-component limitation remains a legitimate known blocker.

Prompt 13.6 must **not** “solve” it by weakening Prompt 11 governance.

---

# 2. Repository-wide audit before editing

Before implementing known fixes, re-audit the current repository.

Inspect at minimum:

```text
README.md
docs/README.md
docs/BRANCH_PROTECTION.md

app/database/
app/repositories/
app/services/
app/jobs/
app/ml/
app/schemas/
app/routers/
frontend/

tests/
scripts/validation/

.github/workflows/ci.yml
.github/workflows/full-validation.yml

docs/evidence/recovery_hardening/00_BASELINE_AND_INVARIANTS.md
docs/evidence/recovery_hardening/01_CI_API_MOBILE.md
docs/evidence/recovery_hardening/02_ATTEMPT_FENCING.md
docs/evidence/recovery_hardening/03_PHASE10_RETRY_REJOIN.md
docs/evidence/recovery_hardening/04_ATTESTATION_CURRENTNESS.md
docs/evidence/recovery_hardening/05_IMPORT_INVALIDATION.md
docs/evidence/recovery_hardening/06_PREFLIGHT_PARITY.md
docs/evidence/recovery_hardening/07_FAST_PATH_AND_TIMING.md
docs/evidence/recovery_hardening/08_PROGRESS_ETA.md
docs/evidence/recovery_hardening/09_V2_SCORE_SEMANTICS.md
docs/evidence/recovery_hardening/10_CATALOG_LIFECYCLE.md
docs/evidence/recovery_hardening/11_CALIBRATION_ISOLATION.md
docs/evidence/recovery_hardening/12_FEEDBACK_LEARNING.md
docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md
docs/evidence/recovery_hardening/13_5_INTEGRATION_CLOSURE.md
```

Also inspect the Phase 1–11 implementation summaries and current authoritative freeze/closure reports.

Search repository-wide for:

```text
TODO
FIXME
HACK
XXX
NotImplementedError

CURRENT_SCHEMA_VERSION
selection_contract_version
propensity_bucket
PROPENSITY_BUCKETS
0.50
0.60
0.70
0.80
0.90
10_000

calibration_currentness
resolve_governed_calibration_eligibility
has_governed_calibration_lineage
split_lineage_json
model_training_group_ids
calibration_fit_group_ids
calibration_evaluation_group_ids

challenger_meets_promotion_gates
feedback-search-run:
campaign_feedback_outcomes
feedback_retraining_decisions

claim_search_attempt
execution_lease_token
lease_owner
lease_heartbeat_at
mark_processing
update_search_progress
heartbeat_search_attempt
bind_current_attempt_lineage
complete_search_run
fail_search_run

status='PROMOTED'
score_calibration_artifacts

workflow_available
/api/health
```

Produce a finding matrix:

```text
finding
affected phase/prompt
production path
current test coverage
severity
reproducible?
fix now / defer
reason
```

Any new P0/P1 defect discovered during this audit is in scope if repairing it does not require choosing Prompt 14 policy.

---

# 3. Workstream A — Repair preflight API/currentness contract mismatch

Known defect:

`resolve_governed_calibration_eligibility()` can return internal states including:

```text
INELIGIBLE
CANDIDATE
REJECTED
```

while:

`PotentialCustomerPreflightResponse.calibration_currentness`

currently accepts only:

```text
CURRENT
NOT_AVAILABLE
STALE
UNVERIFIED
```

and the preflight service can forward the resolver status directly.

Because `/api/potential-customer-search/preflight` declares a FastAPI response model, an otherwise safe fail-closed condition must never become a response validation 500.

## Required design

Separate:

```text
currentness
eligibility
reason
```

instead of overloading one field.

Preserve backward compatibility for existing `calibration_currentness`.

Prefer a stable public currentness vocabulary such as:

```text
CURRENT
NOT_AVAILABLE
STALE
UNVERIFIED
```

and expose an additive bounded eligibility/reason field if necessary.

Internal statuses such as:

```text
INELIGIBLE
CANDIDATE
REJECTED
CALIBRATION_LINEAGE_INVALID
CALIBRATION_GOVERNANCE_INCOMPATIBLE
```

must be mapped intentionally rather than accidentally passed into an incompatible response schema.

Do not expose raw internal exceptions.

## Mandatory tests

Add HTTP-level tests, not service-only tests, covering:

1. no calibration;
2. current eligible calibration;
3. stale calibration;
4. legacy promoted v1 calibration;
5. malformed governed calibration lineage;
6. structurally valid but governance-incompatible calibration;
7. candidate/rejected artifact if reachable;
8. every case returns a bounded documented HTTP response rather than FastAPI response-validation 500.

---

# 4. Workstream B — Prove calibration/model lineage identity, not merely independent validity

Current eligibility validates:

```text
calibration lineage is internally governed
AND
model split lineage is internally governed
AND
model/scoring IDs match
```

but must additionally prove that the calibration was derived from the exact partitions recorded by that model.

Create one shared cross-artifact lineage validator.

At minimum prove exact equality of:

```text
calibration.model_training_group_ids
    ==
model.partitions.model_training.group_ids

calibration.calibration_fit_group_ids
    ==
model.partitions.calibration_fit.group_ids

calibration.calibration_evaluation_group_ids
    ==
model.partitions.calibration_evaluation.group_ids
```

and verify their canonical hashes.

Also prove compatible:

```text
strategy version
seed
validation fraction / partition policy where applicable
model_run_id
scoring_run_id
```

Do not accept two separately valid lineage documents whose identities differ.

Use this validator from the centralized governed-calibration eligibility path.

Where feasible, also validate immediately before publication so corrupted lineage fails earlier.

## Mandatory adversarial tests

Construct:

```text
valid model lineage A
valid calibration lineage B
```

where both are independently well formed but one or more group identities differ.

Eligibility must be false.

Also test:

```text
same groups different order -> accepted
one missing group -> rejected
one extra group -> rejected
hash mismatch -> rejected
partition swapped fit/evaluation -> rejected
```

Historical v1 rows remain readable but cannot become governed v2-consumable.

---

# 5. Workstream C — Eliminate feedback recalibration person leakage

Known statistical defect:

`FeedbackRecalibrationWorker` currently creates recalibration groups from:

```text
feedback-search-run:<search_run_id>
```

but feedback event grain permits the same `person_id` to occur in different search runs.

The current duplicate check prevents duplicate person feedback only inside the same search run.

Therefore the same person/raw score can appear in two different search groups and be assigned to both calibration-fit and calibration-evaluation partitions.

That violates the intended holdout boundary.

## Required design

Preserve immutable feedback event history.

Do **not** silently delete legitimate repeated campaign/search outcome events.

For statistical partitioning, derive a leakage-safe grouping.

Preferred design:

Build deterministic connected components across the bipartite relation:

```text
feedback search run <-> person_id
```

for the fixed:

```text
scoring_run_id
feedback_batch_cutoff
```

Any search runs sharing a person must belong to the same statistical component.

Every person's feedback observations must therefore remain entirely on one side of the calibration/evaluation boundary.

Use stable deterministic group IDs such as a hash of the connected component.

Do not use Python's process-randomized hash.

Do not fall back to row-random or search-random splitting when independent components are insufficient.

If the feedback topology cannot produce safe fit/evaluation partitions containing both outcome classes, fail closed / remain waiting for data with a truthful bounded reason.

Do not mark the recalibration as a generic system failure when it is simply statistically insufficient.

## Gate integration

Audit `_adaptive_gate`.

`COUNT(DISTINCT search_run_id)` is not proof of statistical independence.

If necessary add/persist a bounded fact such as:

```text
independent_feedback_group_count
feedback_grouping_contract_version
feedback_grouping_sha256
```

or equivalent immutable lineage.

Do not overwrite historical feedback batches.

## Mandatory tests

At minimum:

1. same person in two searches -> both searches belong to same statistical component;
2. same person cannot be split fit/evaluation;
3. chained overlap:
   search A shares P1 with B, B shares P2 with C -> A/B/C one component;
4. disjoint searches remain independent;
5. component construction deterministic across ordering;
6. insufficient component count fails closed;
7. class-insufficient components fail closed;
8. repeated-person feedback remains auditable at original event grain;
9. no synthetic duplication is introduced to satisfy minimum counts.

---

# 6. Workstream D — Make challenger vs incumbent recalibration comparison like-for-like

Known defect/risk:

The feedback worker currently compares:

```text
candidate metrics calculated on the new candidate's held-out evaluation set
```

against:

```text
incumbent.metrics_json persisted when the incumbent calibration was originally created
```

Those metrics may have been calculated on different:

```text
rows
feedback windows
outcome observations
selection populations
time periods
```

and therefore are not a statistically valid head-to-head comparison.

## Required correction

For every challenger decision:

1. freeze one immutable evaluation population;
2. fit the candidate using only calibration-fit records;
3. evaluate candidate on the frozen evaluation records;
4. load the incumbent calibration artifact;
5. apply the incumbent calibration transform to the **same raw scores** in the exact same evaluation records;
6. calculate incumbent metrics with the same metric functions;
7. compare candidate vs incumbent only using these like-for-like metrics.

Persist sufficient bounded lineage to prove this.

At minimum record:

```text
evaluation record count
positive count
negative count
evaluation group IDs/hash
evaluation population SHA-256
feedback batch cutoff
candidate metrics
incumbent recomputed metrics
candidate calibration identity
incumbent calibration identity
promotion checks
```

Do not use previously persisted incumbent metrics as the challenger comparison baseline unless they are explicitly proven to describe the same immutable evaluation population.

Historical incumbent metrics remain useful historical evidence but are not the comparison oracle.

## Bootstrap behavior

Audit the current behavior:

```text
challenger_meets_promotion_gates(candidate, None) == True
```

Determine whether an absent incumbent is actually a valid production feedback-recalibration state.

Do not invent policy.

If governed feedback recalibration always requires an existing promoted calibration, fail closed when the incumbent is unexpectedly absent.

If an existing documented bootstrap rule legitimately permits no incumbent, encode and test that rule explicitly.

## Mandatory tests

1. stored incumbent metrics deliberately differ from recomputed same-window metrics -> promotion uses recomputed metrics;
2. candidate and incumbent evaluated over identical record identity/hash;
3. candidate improves old historical metric but not same-window incumbent -> reject;
4. candidate improves same-window incumbent and passes non-regression gates -> promote;
5. evaluation population mutation changes identity/hash and cannot be silently reused;
6. candidate fitting never consumes evaluation records.

---

# 7. Workstream E — Enforce one promoted calibration per scoring run

Current service publication stales previous promoted calibrations before promoting another one, but the database itself does not enforce the invariant.

Add a database-level invariant:

```text
at most one score_calibration_artifacts row with status='PROMOTED'
per scoring_run_id
```

Prefer an additive partial unique index.

If this requires a schema migration, advance `CURRENT_SCHEMA_VERSION` using the normal additive migration framework.

Do not edit old migrations to pretend the invariant historically existed.

Before creating the index, audit existing data for duplicate promoted artifacts.

If historical duplicates exist:

- do not delete artifacts;
- preserve references/history;
- deterministically make only the legitimate current winner PROMOTED;
- stale older promoted rows only if this is consistent with the existing mutable lifecycle contract;
- record exactly what was changed.

Run foreign-key and integrity checks.

## Tests

Test:

```text
second simultaneous/promoted row rejected by DB
normal replacement promotion succeeds
old calibration remains historically readable
preflight cache becomes stale appropriately
historical result snapshots retain identity
migration idempotent
```

---

# 8. Workstream F — Harden same-attempt execution ownership

Prompt 02 correctly prevents Attempt N from mutating Attempt N+1.

However current `claim_search_attempt()` can allow a different live owner to obtain the same active attempt's existing execution token.

The current restart test explicitly reclaims the same token under another owner.

That is safe only if the old process is definitely dead.

It does not fence a same-attempt split-brain condition.

## Required invariant

At any instant, one active attempt must have at most one live execution owner.

Design a minimal owner-aware takeover contract.

Preferred behavior:

```text
same owner + active lease
    -> idempotent reclaim allowed

different owner + fresh heartbeat
    -> reject claim

different owner + stale/expired heartbeat
    -> controlled takeover allowed
```

On controlled takeover, invalidate the old worker's future mutation authority.

This may be implemented by:

```text
rotating execution_lease_token
or
adding a monotonic lease_generation
```

or another equally strong design.

After takeover, the old worker must fail all fenced writes.

Do not claim multi-node scalability merely because this race is fixed.

The application remains a single-node SQLite POC unless separately redesigned and certified.

## Mandatory tests

1. owner A fresh lease; owner B claim -> rejected;
2. owner A reclaim -> idempotent;
3. stale owner A; owner B takeover -> allowed;
4. takeover changes fencing identity;
5. owner A progress after takeover -> rejected;
6. owner A failure after takeover -> rejected;
7. owner A completion after takeover -> rejected;
8. owner A lineage binding after takeover -> rejected;
9. owner B continues normally;
10. restart after genuinely stale process resumes exactly once;
11. Attempt N versus Attempt N+1 Prompt 02 tests still pass.

Audit the feedback recalibration worker for analogous startup double-ownership risk.

Do not redesign it into a distributed task system unless necessary.

At minimum, make any single-process/runtime ownership assumption explicit and ensure concurrent live app starts do not silently create two owners of the same recalibration decision.

---

# 9. Workstream G — Centralize existing selection-contract knowledge before Prompt 14

This is primarily a rework-prevention workstream.

Current v2 policy is duplicated across:

```text
Pydantic Literal declarations
database CHECK constraints
repository validation
preflight service
search orchestration
calibration bucket SQL
submission options
result labels
frontend JavaScript
tests
demo qualification script
```

Create a low-level dependency-free selection-contract module/registry that describes **only already-approved current contracts**.

For example:

```text
contract version
semantic name
allowed bucket keys
lower/upper bounds
upper inclusive flag
display label
default/recommended bucket
legacy compatibility mapping if required
membership contract
demo qualification minimum
```

Current v2 must remain:

```text
0.90 -> [0.90, 1.00]
0.80 -> [0.80, 0.90)
0.70 -> [0.70, 0.80)
0.60 -> [0.60, 0.70)
0.50 -> [0.50, 0.60)
```

Current demo qualification remains:

```text
10,000
```

Do not introduce v3.

Do not introduce lower bands.

Do not make the database accept future versions in advance.

The purpose is to create an extension seam so Prompt 14B, if selected, does not require hunting through unrelated files.

## Architecture rules

The shared contract module must not import:

```text
database
services
routers
FastAPI
frontend
```

Higher layers may import it.

Avoid circular dependencies.

Backend options should return authoritative bucket metadata.

Frontend should render/use metadata supplied by the backend rather than maintaining its own independent bucket semantics whenever practical.

Historical schema migrations retain their historical literal SQL.

Do not rewrite them.

For current/fresh schema definitions, either consume shared constants safely or add invariant tests proving SQL constraints remain aligned with the registry.

## Mandatory consistency tests

A test must fail if any current runtime layer disagrees on:

```text
contract version
bucket names
bucket bounds
default bucket
labels/semantics
10K qualification minimum
```

Test backend option output against the registry.

Test preflight and materialization against the same registry.

Test result labels against the registry.

Test frontend does not independently redefine v2 probability ranges.

---

# 10. Workstream H — Repair and certify Full Validation workflow

Current `.github/workflows/full-validation.yml` has never had a `workflow_dispatch` run in the repository history as of the Prompt 13.5 baseline.

The workflow installs:

```text
requirements.lock
```

but runs:

```text
pytest -m "not full5m"
```

which includes browser-marked tests.

Normal Frontend Contract CI separately installs:

```text
requirements-browser.lock
```

and configures system Chrome.

Align the manual Full Validation workflow with the actual browser-test dependency contract.

At minimum:

- install pinned browser dependencies when browser tests are run;
- configure the supported system-browser environment consistently;
- do not silently skip browser failures;
- preserve LFS checkout where required;
- clearly separate bounded regression from later full-5M Prompt 16 work;
- remove “when available” behavior for committed mandatory scripts;
- fail explicitly if an expected validation runner is missing.

Do not turn this into Prompt 16.

Prompt 13.6 should still avoid the full canonical 5M scoring certification unless a bounded existing runner inherently requires otherwise.

## Certification

After changes are committed/pushed according to operator instructions:

run the manual Full Validation workflow on the exact candidate SHA/branch state and record:

```text
run ID
head SHA
jobs
conclusion
```

If it cannot be dispatched due permissions, report:

```text
MANUAL FULL VALIDATION REMOTE CERTIFICATION PENDING
```

and do not pretend it ran.

---

# 11. Workstream I — Make application health reflect critical runtime composition

Current application startup can catch a Phase 11 runtime-composition failure and continue serving.

`/api/potential-customer-search/options` can correctly report:

```text
workflow_available=false
```

but `/api/health` currently derives overall health almost entirely from database/schema health.

Therefore the system may appear healthy while its primary search workflow is unavailable.

Add bounded runtime component health.

Prefer app/runtime state rather than leaking globals into business responses.

At minimum health should distinguish:

```text
database/schema health
Phase 11 search workflow availability
feedback recalibration worker availability if treated as critical
```

If Phase 11 runtime composition fails, `/api/health` should become degraded/503 or otherwise truthfully report degraded critical functionality.

Do not expose:

```text
tracebacks
paths
tokens
raw exceptions
database secrets
```

## Tests

1. normal lifespan -> health OK and search workflow available;
2. simulated Phase 11 composition failure -> health degraded;
3. `/options` agrees with health workflow state;
4. shutdown resets state;
5. failure response contains only safe bounded diagnostics.

---

# 12. Workstream J — Remove accidental current-schema-number coupling

Current tests contain assertions equivalent to:

```text
CURRENT_SCHEMA_VERSION == 30
```

in general current-schema tests.

Examples include tests around:

```text
Phase 9 schema
Phase 10 registry schema
calibration governance
attempt execution fencing
future-feedback lineage
```

These create false failures when a legitimate later prompt advances the schema.

Replace general-current-schema assertions with:

```text
stored schema version == str(CURRENT_SCHEMA_VERSION)
```

Keep exact numeric version assertions only where the exact historical migration boundary is the subject of the test.

Examples:

```text
v26 -> v27 preservation
v29 -> v30 feedback decision migration
```

may legitimately retain exact historical numbers.

Do not weaken migration coverage.

The existing historical upgrade matrix from schema 15 through current must continue to pass.

---

# 13. Workstream K — Minimal current-authority documentation refresh

Do not perform Prompt 18's full documentation cleanup.

Do only what is required to prevent the next agent from starting from stale authority.

Update current operational references so they point to the post-13.6 baseline rather than presenting old Phase 11 freeze SHAs/test counts as the latest trusted state.

At minimum audit:

```text
README.md
docs/README.md
docs/BRANCH_PROTECTION.md
Prompts/campaign_recovery_prompt_pack_f437efd3/README.md
```

Preserve historical evidence documents as historical evidence.

Do not rewrite their old run IDs or SHAs to pretend they were generated later.

Create new evidence instead.

---

# 14. Workstream L — Repository governance check

Re-read current GitHub branch metadata.

At the Prompt 13.5 baseline, `main` reports:

```text
protected=false
```

and no repository rulesets were returned.

If the execution environment has administrator permission, configure or verify branch protection for `main`.

At minimum require these existing checks:

```text
Repository Hygiene
Python Validation
Tests
Clean-Room Phase1-7
Frontend Contract
```

Recommended:

```text
require status checks
require branch up to date
require PR before merge
prevent bypass where appropriate
```

Do not invent success if GitHub permissions prevent the change.

If branch protection cannot be changed:

record:

```text
BRANCH PROTECTION PENDING — ADMIN ACTION REQUIRED
```

This is a repository-governance item, not a reason to weaken runtime code or tests.

Do not claim repository-governance closure until it is actually enabled and re-read.

---

# 15. Preserve known good Phase 1–13.5 contracts

After changes, specifically re-prove:

## Phase 1/2

```text
authoritative imports and checksums unchanged
synthetic-data contracts unchanged
historical analysis reconstruction unchanged
```

## Phase 3–6

```text
feature contract unchanged unless explicitly required by a proven bug
raw propensity semantics unchanged
legacy model/scoring artifacts readable
rank/analytics contracts unchanged
```

## Phase 7–9

```text
saved audience / target-group identity unchanged
multi-branch OR union remains exact
no contact PII leaks into analytical membership
campaign/export behavior unchanged
```

## Phase 10

```text
exact Modeling Context compatibility
no latest-run-wins fallback
reuse/build layering unchanged
currentness/invalidation remains fail closed
training methodology identity remains policy version 2
```

## Phase 11

```text
durable search history
result snapshot immutability
smart reuse
omnichannel export
result v1/v2 semantic separation
mobile/result-detail responsiveness
retry/rejoin
progress/heartbeat/ETA
catalog lifecycle
feedback audit history
```

## Recovery Prompts 00–13.5

Re-run focused tests proving:

```text
Prompt 02 fencing
Prompt 03 dependency retry/rejoin
Prompt 04 attestation/currentness
Prompt 05 import invalidation
Prompt 06 preflight/materialization parity
Prompt 07 bounded direct reuse
Prompt 08 progress/ETA
Prompt 09 v1/v2 semantics
Prompt 10 catalog lifecycle
Prompt 11 three-way governance
Prompt 12 recalibration semantics
Prompt 13 thresholds unchanged
Prompt 13.5 integration/migration invariants
```

---

# 16. Canonical database safety

Do not migrate the operator's canonical database in place merely to complete this prompt.

For migration certification:

1. copy the canonical database;
2. checksum the source before;
3. migrate the copy through the real `initialize_database()` path;
4. run:
   - `PRAGMA integrity_check`;
   - `PRAGMA foreign_key_check`;
5. verify important row/identity counts;
6. initialize the migrated copy a second time;
7. prove semantic idempotence;
8. checksum the original source again.

The source must remain unchanged unless the operator explicitly authorizes an in-place migration.

---

# 17. Required regression commands

Run the repository's real commands rather than inventing substitutes.

At minimum:

```text
python -m pip check
python -m compileall app scripts tests
git diff --check
```

Main non-heavy suite:

```text
pytest -m "not cleanroom and not full5m and not performance and not browser"
```

Frontend/API gate using installed/pinned browser dependencies:

```text
pytest -m "browser or integration" tests/test_frontend.py tests/test_*_api.py
```

Phase 9:

```text
pytest -q tests/test_phase9_*.py
```

Phase 10:

```text
pytest -q tests/test_phase10_*.py
```

Phase 11 bounded:

```text
pytest -q -m "not cleanroom and not performance and not full5m" tests/test_phase11_*.py
```

Clean-room:

```text
python scripts/validation/run_cleanroom_phase1_to_phase7.py
```

Run every new focused statistical/concurrency/API test separately first so failures are diagnosable.

Do not remove assertions simply to obtain green.

Do not turn exact assertions into broad “one of several statuses” assertions unless the contract itself genuinely permits those statuses and the reason is documented.

---

# 18. Required new evidence

Create:

```text
docs/evidence/recovery_hardening/13_6_PRE14_STABILIZATION.md
docs/evidence/recovery_hardening/13_6_PRE14_STABILIZATION.json
```

The evidence must contain:

```text
starting SHA
ending/candidate SHA
working tree before
baseline exact-SHA CI
full issue inventory
issues confirmed
issues disproved
new issues found during audit
root cause per issue
files changed
schema changes
API changes
contract changes
migration certification
feedback leakage analysis
challenger like-for-like evaluation proof
cross-lineage proof
lease/fencing proof
selection-contract centralization map
manual Full Validation status
branch-protection status
health/runtime availability proof
test commands
test counts
clean-room result
exact-SHA CI result
remaining limitations
GO/NO-GO
```

Do not include contact PII, raw feedback data, lease tokens, machine-specific secrets, or unbounded logs.

---

# 19. Exact-SHA CI gate

If implementation changes are committed and pushed, wait for the CI run associated with the **exact candidate SHA**.

Do not cite a parent SHA's green run.

Required jobs:

```text
Repository Hygiene
Python Validation
Tests
Frontend Contract
Clean-Room Phase1-7
```

all must be successful.

If changes are locally complete but not pushed, final status must say:

```text
LOCAL IMPLEMENTATION PASS
REMOTE EXACT-SHA CI CERTIFICATION PENDING
PROMPT 13.6 = NO-GO UNTIL EXACT CANDIDATE SHA IS GREEN
```

If pushed but CI is still running or red:

```text
PROMPT 13.6 = NO-GO
```

until corrected.

---

# 20. Explicitly accepted limitations after Prompt 13.6

The following are not Prompt 13.6 failures if honestly retained:

```text
canonical campaign history still forms one campaign-connected component
new governed canonical model/calibration therefore remains unavailable under current data
Prompt 13 business selection decision remains unchosen
14A/14B has not been run
full canonical 5M Prompt 16 certification has not been run
20-scenario Prompt 17 qualification has not been run
repository remains a local single-node SQLite POC
authentication/RBAC is not implemented
activation/send provider integration is not implemented
automatic true feature-model retraining is not implemented
```

These limitations must not be disguised as completed functionality.

---

# 21. Prompt 13.6 acceptance gate

Prompt 13.6 is **GO only if all of the following are true**:

1. Preflight cannot produce a response-model 500 from a valid fail-closed calibration state.
2. Public currentness/eligibility semantics are explicit and bounded.
3. Calibration and model split lineage must match exact partition identities.
4. Feedback recalibration cannot split the same person across fit/evaluation partitions.
5. Feedback topology insufficiency fails closed truthfully.
6. Challenger and incumbent are compared on one identical evaluation population.
7. Promotion evidence records the evaluation population identity.
8. One promoted calibration per scoring run is enforced durably.
9. Prompt 02 Attempt N/N+1 fencing remains intact.
10. Two simultaneously live owners cannot both mutate one active attempt.
11. Controlled stale-owner takeover fences the old owner.
12. Existing v1/v2 selection semantics are unchanged.
13. Existing v2 selection policy has a centralized authoritative runtime registry/contract seam.
14. No v3 contract has been introduced.
15. The 0.50+ minimum has not changed.
16. The 10,000 demo qualification rule has not changed.
17. Manual Full Validation is structurally correct and locally/remote certified as far as permissions allow.
18. Health reports critical Phase 11 runtime unavailability truthfully.
19. General tests no longer hard-code current schema `30` where they mean `CURRENT_SCHEMA_VERSION`.
20. Historical migration-boundary tests remain exact.
21. Migration on a disposable canonical copy passes integrity/FK/idempotence checks.
22. Canonical source database remains unchanged unless explicitly authorized.
23. Full non-heavy regression has zero failures/errors.
24. Frontend Contract passes.
25. Phase 9 passes.
26. Phase 10 passes.
27. Phase 11 bounded suite passes.
28. Clean-Room Phase1-7 passes.
29. Repository Hygiene passes.
30. Python Validation passes.
31. Exact candidate SHA GitHub Actions is green if the candidate is pushed.
32. No Prompt 14 business policy was silently chosen.

Any violation of items 1–12 or 21–32 is a NO-GO for proceeding to Prompt 14.

Branch protection may remain an explicitly documented administrator action if permissions prevent configuration, but it must not be falsely marked complete.

---

# 22. Required completion response

Return exactly these sections:

## Starting SHA

## Ending / Candidate SHA

## Working Tree State Before

## Repository-Wide Audit Scope

## Baseline CI Verification

## Confirmed Pre-14 Defects

## Additional Defects Discovered

## Findings Disproved / Not Reproduced

## API Contract Repairs

## Calibration / Model Cross-Lineage Repairs

## Feedback Statistical Isolation Repairs

## Challenger vs Incumbent Comparison Repairs

## Calibration Singleton Invariant

## Attempt Lease / Split-Brain Hardening

## Selection-Contract Centralization

## Runtime Health Repair

## Schema / Migration Future-Proofing

## Full Validation Workflow Certification

## Branch Protection Status

## Files Changed

## Schema Changes

## API / OpenAPI Changes

## Tests Added or Changed

## Commands Run

## Focused Test Results

## Full Regression Results

## Clean-Room Result

## Canonical Copy Migration Certification

## Exact-SHA GitHub CI

## Evidence Artifacts Produced

## Remaining Accepted Limitations

## GO / NO-GO for Prompt 13.6

## Recommended Next Action

The only valid next action after full Prompt 13.6 GO is:

```text
re-present / reconfirm the Prompt 13 business decision
then run exactly one of Prompt 14A or Prompt 14B
```

Do not recommend Prompt 15 directly.

If Prompt 13.6 is NO-GO:

```text
fix the remaining Prompt 13.6 blocker
```

before any Prompt 14 work.

---

# Final principle

A green repository before Prompt 14 must mean more than “the existing tests pass.”

It must mean:

```text
public contracts agree with internal states
statistical holdouts are genuinely isolated
challenger comparisons are like-for-like
model/calibration lineage agrees end-to-end
execution ownership is fenced
current policy has one authoritative definition
migrations can evolve without fake failures
runtime health is truthful
validation workflows are executable
historical behavior remains interpretable
```

Do not make the demo easier.

Make the engineering boundary stronger so whichever Prompt 14 branch is explicitly selected can be implemented once, cleanly, without reopening Prompt 00–13.5 defects.