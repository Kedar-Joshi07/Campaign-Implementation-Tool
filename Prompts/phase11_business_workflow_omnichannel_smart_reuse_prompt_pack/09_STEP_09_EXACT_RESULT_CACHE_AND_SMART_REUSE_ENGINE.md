# Step 9 — Exact Result Cache & Smart Reuse Engine

## Objective
Implement the three-layer reuse decision without duplicating Phase 10 compatibility logic.

Create focused service:
`phase11_search_orchestration_service.py`
(or equivalent).

Workflow:
1. normalize/persist exact Phase9 targeting criteria and filter branches;
2. invoke/inspect Phase10 exact intelligence compatibility;
3. if current READY generation exists, compute exact result cache key;
4. attempt exact current snapshot reuse;
5. if miss, run Audience Engine filtering on READY scoring generation;
6. if no READY generation, invoke Phase10 prepare and durably wait/poll through its state;
7. after READY, calculate cache key/filter/materialize;
8. complete search run.

Exact result-cache hit validation:
- generation remains current for request;
- stored generation ID/key matches;
- criteria SHA matches;
- branch SHA matches;
- selection mode/target count matches;
- result membership contract matches;
- snapshot file exists;
- snapshot checksum verifies;
- stored resolved count matches snapshot.

Never reuse solely because criteria text “looks the same”.

Result source:
EXACT_RESULT_REUSE / INTELLIGENCE_REUSE / NEW_INTELLIGENCE_BUILD.

If exact snapshot cache hit:
do not query/iterate all propensity-score rows merely to re-prove membership.
Perform bounded metadata/currentness/checksum validation.

Add explicit regression:
same Modeling Context + changed delivery profile → no training/no scoring.
same Modeling Context + changed demographic filters → no training/no scoring.
identical exact request twice → second snapshot reused, but second search_run created.
stale generation → exact cache rejected.

No all-permutation precompute.

Evidence:
`docs/evidence/phase11/09_SMART_REUSE_ENGINE.md`

STOP.
