# 02 — Repository-Wide Implementation Audit

Audit the entire repository at the required SHA before running the demo scenarios. Do not start by changing code.

## A. Repository and dependency gates

Record:
- exact SHA/branch/worktree state;
- Python and pip versions;
- Git LFS status;
- tracked/untracked/ignored summary;
- dependency lock files and install policy.

Run at minimum:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
.\.venv\Scripts\python.exe scripts\validate_data.py --json
```

Also run the focused Phase 9/10/11 suites and the lifecycle/reuse/recovery/concurrency tests. Repeat the concurrency-focused group enough times to look for the previously observed artifact-root race. Never dismiss a nondeterministic failure merely because one isolated rerun passes.

## B. Database/schema integrity

Verify the canonical DB:
- `PRAGMA integrity_check = ok`;
- `app_metadata.schema_version = 19`;
- all expected Phase 1–11 tables, indexes, triggers and foreign keys exist;
- source row counts/currentness match configured canonical sources;
- no stale RUNNING/STARTED jobs/exports/orchestrations/searches remain without an explicit recovery reason;
- the Phase 11 runtime row exists one-for-one for current search history as intended.

## C. Lifecycle contract audit

Inspect and verify:
- guarded legal transitions;
- immutable runtime identity;
- heartbeat update behavior;
- monotonically increasing `state_version`;
- monotonic `progress_percent` and `processed_count`;
- terminal completion exactly 100%;
- BLOCKED/FAILED requires structured failure code/category/summary/resolution steps;
- retryability is truthful;
- restart recovery cannot duplicate or corrupt snapshots/runs.

## D. Progress and ETA audit

Confirm Phase 10/11 progress is derived from actual work/materialized counts and cannot decrease.

Verify ETA:
- queue time is excluded;
- no ETA is returned before sufficient processing evidence exists;
- completed returns zero remaining;
- estimates are bounded to the documented maximum;
- no NaN/negative/infinite values;
- UI labels confidence honestly;
- ETA behavior does not imply an SLA.

Note separately whether ETA derives from overall stage-weighted progress versus direct record throughput; treat any accuracy limitation as a documented improvement, not hidden certainty.

## E. Business search and smart-reuse audit

Verify production flow:
`POST search -> durable run -> Phase 10 compatibility/reuse/build -> exact filter membership -> atomic snapshot -> COMPLETED result -> history/detail -> governed download`

Check:
- exact result cache validates before reuse;
- different targeting criteria do not unnecessarily rebuild modeling intelligence;
- changed modeling context invalidates only required layers;
- no “latest score” fallback;
- target filters map deterministically to exact audience filters;
- ALL_MATCHING/TOP_N semantics are exact;
- no contact PII in JSON/search snapshot membership;
- download joins only profile-required fields and applies contactability/consent rules.

## F. UI audit

Exercise normal business UI with installed system browser:
- Home;
- Find Potential Customers;
- Results;
- Result Detail;
- manual Refresh Progress;
- automatic polling on Results/Result Detail;
- blocked/failed guidance;
- download gating.

Check status consistency: list/detail/Home must not disagree between base run status and runtime lifecycle status.

Explicitly verify behavior after the current bounded poll window (`5s x 60 = 5 minutes`). If a legitimate long run is still active, ensure the UI makes it clear when automatic polling pauses and manual refresh remains available. Flag silent polling cessation as a UX issue.

## G. Security/privacy/safe-error audit

Search repository and runtime responses for:
- secrets/credentials;
- stack traces/local paths/SQL in public API/UI;
- contact PII in JSON projections/snapshot artifacts;
- unguarded CSV formula injection;
- unsafe DOM HTML sinks;
- stale debug endpoints or test-only runtime injection.

POC limitations (no auth/RBAC/tenant isolation) are allowed only if explicitly documented and not falsely presented as implemented.

## H. Code-quality/static audit

Repository-wide search for:
- TODO/FIXME/HACK/XXX;
- `NotImplementedError` / placeholder `pass`;
- dead duplicate services;
- orphan migrations;
- stale temporary scripts;
- hard-coded absolute local paths;
- outdated schema/SHA/current-baseline docs;
- duplicated contract constants;
- generated/runtime artifacts accidentally tracked;
- oversized historical prompt/evidence surface lacking a current index.

## I. Output

Create:
`docs/evidence/demo_readiness/REPO_AUDIT_AT_F2B98AD.md`

Classify every finding:
- BLOCKER BEFORE DEMO
- MUST FIX BEFORE DEMO
- SHOULD FIX BEFORE DEMO
- POST-DEMO HARDENING
- ACCEPTED POC LIMITATION

Do not make unrelated architectural changes while auditing.
