# Repository Audit at `f2b98ad`

Audit date: 2026-09-24
Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`
Required and observed starting SHA: `f2b98adfcf1a01f23f1c201aa2cf5a2df1521a2d`
Branch: `main`

## Verdict

**PASS WITH PRE-DEMO CORRECTIONS.** No source-data, SQLite-integrity,
schema, lifecycle, privacy, test, or Git LFS blocker prevents the real
20-scenario preload. Three presentation/documentation issues must be corrected
before the final demo verdict: the current-version README line, explicit notice
when bounded polling pauses, and consistent durable-lifecycle badges.

The prompt-pack directory was the only untracked worktree content at the start
of the audit. It was preserved. No unrelated user changes were overwritten.

## Gate results

| Gate | Result |
|---|---|
| Python / pip | Python 3.12.0; pip 23.2.1 |
| Dependency integrity | `pip check`: PASS |
| Compilation | `compileall -q app scripts tests`: PASS |
| Complete repository suite | 995 passed in 3296.40 seconds |
| Focused Phase 9 | 69 passed in 529.05 seconds |
| Focused Phase 10 | 88 passed in 524.46 seconds |
| Focused Phase 11 | 294 passed in 1404.10 seconds |
| Repeated submission concurrency | 5 sequential iterations; 15/15 passed |
| Canonical data validation | PASS: 125,000 customers; 570,000 campaign events; 5,000,000 demographics |
| SQLite integrity | `PRAGMA integrity_check`: `ok` in 1890.532 seconds |
| Schema | Version 19; no expected table missing |
| Phase 9-11 foreign-key checks | No violations |
| Runtime one-to-one relationship | 28 searches / 28 runtime rows; zero missing/orphan rows |
| Runtime invariants | No completed-under-100%, count, structured-issue, or base/runtime mismatch violation |
| CI hygiene | PASS |
| Git LFS | `git lfs fsck`: PASS; all three canonical large data objects valid |
| Git whitespace | `git diff --check`: PASS |

Canonical validation reported zero invalid customer references, zero underage
campaign contacts, zero demographic structural violations, and no missing
contactability identifier for an enabled channel.

## Lifecycle, progress, ETA, and recovery

- Schema triggers guard runtime identity, deletion, and legal lifecycle
  transitions.
- Repository updates enforce non-decreasing active percentage and processed
  count.
- Terminal completion requires 100 percent; BLOCKED/FAILED runtime rows require
  structured code, category, summary, and at least one resolution step.
- ETA excludes queue time by using `processing_started_at`, returns no estimate
  before measurable processing, clamps invalid/unbounded values, returns zero
  for completion, and is capped at 24 hours.
- ETA is a bounded stage-progress approximation, not an SLA or a direct
  per-stage throughput forecast.
- Startup found one recoverable Phase 10 path associated with targeting context
  33. The normal application recovery path completed orchestration 19 to READY,
  attached scoring run 6, and published CURRENT generation 3. No manual table
  update was used.
- Search 28 (`ABC`) is a pre-preload failed historical event and is not part of
  the 20-run batch. It remains preserved as required.

## Production-flow and privacy audit

The implemented path remains:

`POST search -> durable run -> Phase 10 compatibility/reuse/build -> exact
filter membership -> atomic immutable snapshot -> completed history/detail ->
governed download`.

Tests and code inspection confirm exact-cache validation, explicit generation
lineage, deterministic targeting normalization, exact ALL_MATCHING/TOP_N
semantics, atomic snapshot publication, no contact PII in JSON/snapshot
membership, profile-specific contact joins only during authorized export, and
CSV formula neutralization. No unsafe DOM HTML/eval sink or credential pattern
was found in production surfaces. Internal traceback diagnostics remain
server-side; public projections use allowlisted safe messages.

## Real installed-Chrome audit

Installed system Chrome 153.0.8010.53 loaded the normal application at
`http://127.0.0.1:8000` using the production database and runtime:

- Home loaded five recent searches and business metrics.
- Normal navigation exposed Home, Find Potential Customers, and Results.
- The complete business form loaded backend-owned context, targeting, and
  AVAILABLE delivery profiles.
- Results loaded 20 newest history items.
- Result Detail reopened Search 28, rendered all six detail panels and one
  progress bar, and manual Refresh Progress succeeded.
- No console error, page error, or failed network request was captured.
- The first cold options load took approximately 45 seconds after database-heavy
  audit activity; a concurrent initial browser attempt exceeded 60 seconds.

No contact-data download was performed.

## Findings

### BLOCKER BEFORE DEMO

None after normal startup recovery completed orchestration 19.

### MUST FIX BEFORE DEMO

1. `README.md` currently states schema version 18 in the "Current versions and
   frozen contracts" list even though code, migration, and canonical DB are
   version 19.
2. Results and Result Detail stop automatic polling after 60 five-second cycles
   but do not visibly announce that automatic refresh paused. Results can still
   claim that refresh occurs every five seconds after scheduling has stopped.
3. Result Detail and Home use base run status for their badge instead of
   consistently preferring `progress.lifecycle_status`, unlike the Results
   list. This can mislabel future PAUSED/STOPPED/requested states.

### SHOULD FIX BEFORE DEMO

1. Warm or cache the production options projection before a live demo. The cold
   5M-backed options request is correct but can take 45-120 seconds when other
   large read workloads overlap.
2. Record the audit-time appearance/recovery of Search 28 and exclude it from
   the exact 20 intended preload event count.

### POST-DEMO HARDENING

1. Refine ETA with observed stage/record throughput and per-stage history while
   retaining bounded, qualified output.
2. Continue repeated Windows concurrency stress in CI. The previously observed
   artifact-root failure did not reproduce in the full suite, focused Phase 11
   suite, or five repeated concurrency runs. Current tests already use per-test
   temporary roots and production publication keeps one governed result root.
3. Consider indexing/archiving the large historical prompt/evidence surface;
   do not mass-delete it immediately before the demo.

### ACCEPTED POC LIMITATIONS

- No authentication, authorization, RBAC, or tenant isolation.
- Single-node SQLite and bounded single-worker compute posture.
- Local artifact storage.
- No live activation/send provider integration.
- No automated provider feedback, outcome-labeling, or retraining loop.
- Historical evidence contains machine-local paths because it records the
  environment in which that historical certification ran; those records are
  not current runtime configuration.

## Preload gate

The audit permits the sequential 20-scenario preload after a SQLite-safe backup
and a fresh baseline capture. The three MUST FIX items remain mandatory before
the final demo-ready verdict and will be addressed during the ordered
housekeeping step.
