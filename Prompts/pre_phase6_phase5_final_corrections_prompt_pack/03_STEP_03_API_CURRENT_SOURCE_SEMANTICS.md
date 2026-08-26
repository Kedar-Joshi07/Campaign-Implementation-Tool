# Step 3 — API Current-Source Verification Semantics

Use the HEAD produced by Step 2. Do NOT begin Phase 6.

## Objective

Ensure every API/UI readiness indicator evaluates CURRENT demographic source matching correctly.

## Required behavior

### GET /api/models/{model_run_id}/scoring-status

Current canonical run exists:

```text
eligible = false
demographic_source_verified = true
```

Only stale historical run exists:

```text
eligible = true (unless another blocker exists)
demographic_source_verified = false
```

The stale historical run must not disable rescoring.

### GET /api/scoring-runs/{scoring_run_id}

Historical runs stay accessible, but `demographic_source_verified` must reflect CURRENT source match:

```text
stale historical run => false
current canonical run => true
```

### GET /api/scoring-runs

No need for expensive N+1 provenance evaluation. Add only bounded metadata if efficient.

## UI

Prospect Scoring UI must:
- not show stale historical scores as “Scoring Complete” for the current source;
- not disable the Score CTA because of stale history;
- disable duplicate scoring only for a current canonical run.

No Phase 6 UI.

## Privacy

Do not expose source absolute paths, DB paths, PII, individual scores, SQL, or tracebacks.

## Tests

Add service/API/UI tests for current=true, source-changed=false, stale history becoming eligible, successful resubmission after source change, current canonical blocking, historical detail accessibility, no path leakage, no individual-score exposure, and unchanged 404/409/422/500 behavior.

Run full tests/compile/pip/diff.

## Report

Report scoring-status semantics, detail semantics, stale/current UI behavior, privacy checks, tests, and unresolved issues.

STOP.
