# Scoring Job Lifecycle Contract

Job type: `PROSPECT_SCORING`.

```text
QUEUED 0
→ STARTING 2
→ VALIDATING_MODEL 5
→ PREPARING_SCORING_RUN 10
→ SCORING_PROSPECTS 10..90
→ FINALIZING_SCORES 94
→ VERIFYING_COMPLETENESS 98
→ COMPLETED 100
```

Any nonterminal state may fail; terminal states never restart.

Jobs orchestrate; scoring_runs are domain records. Completed job result contains scoring_run_id; scoring_run stores job_id.

At most one active heavy job across MODEL_TRAINING/PROSPECT_SCORING. Startup fails stale active jobs and RUNNING scoring runs. No resume. Partial FAILED score rows are not canonical.
