# Phase 11 Step 10 — Atomic Segment Optimization

## Final decision

**NO ADDITIONAL ATOMIC STRUCTURE.**

The required read-only benchmark has now completed against the current Phase 11
canonical 5M generation. The measured path is exact and stable, and the existing
schema already has atomic single-dimension indexes for the supported demographic
filters plus the canonical scoring-run/score/person index.

No Cartesian combination table, bitmap artifact, materialized segment membership,
or new database index was added. Exact-result reuse remains the zero-rescan path
for repeated business requests; Phase 10 intelligence reuse remains the path for
new demographic criteria.

## Current-generation benchmark

Command:

```text
python scripts/validation/phase11/phase11_step10_benchmark.py --repetitions 3
```

Result: `COMPLETED`.

| Fact | Value |
|---|---:|
| schema version | 18 |
| demographic rows | 5,000,000 |
| propensity-score rows | 15,000,000 |
| active jobs/orchestrations | 0 / 0 |
| selected generation | 1 (`READY`, `CURRENT`) |
| selected scoring run | 3 (`COMPLETED`) |
| scored people | 5,000,000 |

Each query ran three times through the production `estimate_audience` service.
Counts and selection results were identical across repetitions.

| Representative query | p50-like median (s) | Matching | Selected |
|---|---:|---:|---:|
| score threshold, no demographics | 1.612901 | 28 | 28 |
| one state | 2.886989 | 136,250 | 136,250 |
| five states | 9.580604 | 1,526,425 | 1,526,425 |
| age + income bucket | 10.889234 | 144,297 | 144,297 |
| multi-age/income + five states | 8.817770 | 328,920 | 328,920 |
| advanced demographics | 2.000935 | 805 | 805 |
| TOP_N 100 across five states | 10.484398 | 1,526,425 | 100 |

Machine-readable evidence:
`docs/evidence/phase11/10_atomic_segment_benchmark.json`.

## Decision rationale

The measurements are local POC observations, not an invented SLA. Some broad
new-filter estimates take several seconds because they aggregate hundreds of
thousands to more than 1.5 million exact members. That cost is bounded and occurs
only when a new exact result must be computed. Step 20 separately proved that an
identical request uses `EXACT_RESULT_REUSE`, adds zero membership-source calls,
and completes the service decision in about 0.015 seconds.

An additional atomic structure is not justified for this phase because:

- the current schema already has generation-independent single-dimension indexes;
- a new persisted bitmap or membership structure would need generation-specific
  build, invalidation, storage, recovery, and full-scale recertification;
- single-dimension aggregates cannot answer multi-dimension intersections exactly;
- precomputing multi-dimension intersections would violate the no-permutation rule;
- no candidate structure has demonstrated a net runtime/storage advantage over
  exact-result reuse plus current indexed filtering.

The current benchmark therefore closes the optional gate with `NO IMPLEMENTATION`.
The retained timings provide a reproducible baseline if a future phase chooses to
prototype a generation-specific bitmap/index and compare exact equality, runtime,
and storage before adoption.

## Historical refused run and Phase 10 reference

The first Step 10 attempt on 2026-09-16 correctly returned
`REFUSED_NO_CURRENT_GENERATION`: schema 17 had no READY Phase 11 generation after
the demographic checksum changed. A schema-15 Phase 10 clean-room generation was
measured for reference only and was never treated as the Phase 11 decision gate.

Step 20 later produced current generation 1/scoring run 3. The completed benchmark
above supersedes the refused gate while retaining the historical reference at
`docs/evidence/phase11/10_atomic_segment_benchmark_phase10_frozen.json`.

## Harness validation and safety

The harness opens inventory connections with SQLite `mode=ro` and `query_only`,
refuses active work, applies existing Audience Engine currentness checks, covers
all seven required query shapes, and rejects unstable repeated results. It does
not import data, prepare intelligence, create indexes, or mutate application rows.

Validation command:

```text
pytest -q tests/test_phase11_atomic_segment_benchmark.py
```

## Completion

Step 10 is complete against the current Phase 11 5M generation with an explicit,
evidence-backed `NO IMPLEMENTATION` decision.
