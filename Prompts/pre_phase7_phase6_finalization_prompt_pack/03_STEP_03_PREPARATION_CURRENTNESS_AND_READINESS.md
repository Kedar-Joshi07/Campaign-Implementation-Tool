# Step 3 — Preparation Currentness and Readiness

Use HEAD from Step 2.

## Semantics

Preserve:

`prepared = 100 valid boundary rows exist for the requested rank contract`

Add:

```text
is_canonical
source_verified
ready_for_current_audience_actions
currentness_issues
```

Recommended:

```text
ready_for_current_audience_actions =
    prepared
    AND is_canonical
    AND source_verified
```

`source_verified` must reflect both historical and demographic currentness.

## APIs

Update:

```text
GET /api/audience/runs
GET /api/audience/runs/{scoring_run_id}/preparation-status
```

Historical stale runs must remain visible, but clearly not ready.

Do not expose raw paths/checksums/SQL/tracebacks.

## UI

Audience Explorer should auto-use only a run where:

`ready_for_current_audience_actions = true`

A prepared-but-stale run may be shown as historical/read-only context only.

Existing options/search/profile/save canonical gates must remain intact.

## Tests

1. prepared + current => ready true.
2. prepared + demographic stale => prepared true, ready false.
3. prepared + historical stale => ready false.
4. unprepared + current => ready false.
5. stale runs remain listed.
6. UI prefers current-ready run over newer stale run.
7. currentness issues bounded/safe.
8. no PII leakage.
9. regressions pass.

STOP.
