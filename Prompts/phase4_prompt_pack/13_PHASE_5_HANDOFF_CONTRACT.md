# Phase 5 Handoff Contract — Prospect Scoring

Authoritative Phase 4 baseline for Phase 5:
`da487443dc61601b9d02fafa784b03bbae52257a`

Phase 5 input is a verified completed `model_run_id` produced by Phase 4 APIs/job lifecycle.

For new role-policy-v2 runs:
```text
PRIMARY = BAGGING_PU
selected_candidate = BAGGING_PU
model_role_policy_version = 2
```

Validated evidence run (Step 5 full-data workflow):

```text
analysis_run_id = 10
job_id = 3
model_run_id = 7
job_status = COMPLETED
selected_candidate = BAGGING_PU
artifact_verified = true
artifact_sha256 = a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210
```

Before scoring:
1. load completed model run;
2. verify artifact path;
3. verify SHA-256;
4. validate payload;
5. confirm feature-contract version/hash;
6. confirm selected estimator;
7. only then scan prospects.

Phase 5 should also reuse Phase 4 hardening semantics:

1. one active scoring/training-class job at a time unless explicitly redesigned;
2. durable queued/running/completed/failed transitions;
3. startup reconciliation for stale active jobs;
4. safe failure envelopes (no traceback/SQL/path leaks in API responses).

Phase 5 may add:
- scoring job using Phase 4 job architecture;
- chunked demographic scoring;
- one score per person_id + model_run_id;
- score bands/percentiles if explicitly frozen;
- scoring status/summary.

Phase 5 must preserve independence:
```text
customer_id != person_id
```
There is no row-level linkage. Only compatible feature semantics are shared.

Prospect raw features remain exactly the frozen 11 features.

Unless separately approved, Phase 5 should still not automatically add Audience Explorer, campaign builder, audience persistence, export, or activation.

Residual risks carried forward intentionally:

- Local SQLite + single-process design is not a distributed production scheduler.
- Job throughput is intentionally bounded (`max_workers=1`) for deterministic safety.
- Observed-label diagnostics are not calibrated probability guarantees.
