# Step 6 — Current-State Documentation and Schema Cleanup

Use the HEAD from successful Step 5.

Do not begin Phase 6.

## Current documentation drift to correct

README currently contains stale current-state statements.

Update at minimum:

1. repository overview to state Phases 1–5 are implemented/frozen;
2. current schema version to the actual post-correction version;
3. Phase 4 Model Training and Phase 5 Prospect Scoring capability descriptions;
4. current import replacement semantics;
5. current source-provenance semantics;
6. current Phase 6 handoff rule;
7. current test count/evidence after this pass.

## LFS manifest

Read actual Git LFS pointers at final HEAD and update sizes/SHA values exactly.

At the audited starting SHA:
- customer pointer matched README;
- campaign pointer matched README;
- demographic pointer did NOT match README because demographics were regenerated during Phase 5 finalization.

Do not copy the old demographic hash.

## Index naming

The index currently named:

`idx_scoring_runs_completed_model_unique`

is no longer unique after schema v6.

Rename it to a truthful name such as:

`idx_scoring_runs_completed_model_newest`

using the next migration or safe idempotent index cleanup.

Do not change its intended lookup ordering.

## Application description

Update FastAPI application description/current comments that still describe only Phase 1/2.

Do not rewrite historical phase evidence as if it never happened.

Prefer adding current-state/post-correction notes to historical phase summaries where necessary.

## Dependency sanity

Verify fresh requirements installation assumptions.

Do not revert `httpx2` merely because older docs mention `httpx`; verify current Starlette/FastAPI TestClient expectations in the actual environment.

Run full regression.

STOP and report.
