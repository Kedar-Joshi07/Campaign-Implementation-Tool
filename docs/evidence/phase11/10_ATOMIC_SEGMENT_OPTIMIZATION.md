# Phase 11 Step 10 — Atomic Segment Optimization

## Decision

**NO IMPLEMENTATION.**

The current canonical runtime does not contain a READY Phase 10 generation for
the Phase 11 demographic source, so the mandatory current-generation benchmark
cannot legitimately execute. The benchmark gate refuses stale or historical
scores. Adding an atomic index/materialization without a current baseline and
an exact before/after equality comparison would violate Step 10 rather than
complete it.

No schema, query path, persisted application row, generation, score, rank, or
source artifact was changed by this step. Exact-result cache reuse and Phase 10
intelligence reuse remain the primary Phase 11 optimization strategy.

## Canonical runtime gate

Command:

```text
python scripts/validation/phase11/phase11_step10_benchmark.py --repetitions 3
```

Result: `REFUSED_NO_CURRENT_GENERATION`.

The read-only inventory recorded:

| Fact | Value |
|---|---:|
| schema version | 17 |
| database bytes | 6,702,706,688 |
| demographics | 5,000,000 |
| propensity-score rows | 10,000,000 |
| active jobs | 0 |
| active Phase 10 orchestrations | 0 |
| eligible READY generations | 0 |

This is the expected currentness boundary established in Step 4. Import 4
published the extended 40-column demographic source. Its import ID and checksum
differ from the two earlier score runs, so those runs are stale by the existing
Audience Engine and Phase 10 contracts. Step 4 explicitly deferred the required
fresh full-scoring generation to later certification.

The current schema already contains atomic indexes for state, age, income,
education, employment status, resident status, and employment type, plus the
canonical scoring-run/score/person rank index. Their presence is inventory, not
evidence that an additional structure would improve current-generation latency.

Machine-readable evidence:
`docs/evidence/phase11/10_atomic_segment_benchmark.json`.

## Frozen Phase 10 reference benchmark

For context only, the same harness ran against the retained Phase 10 Step 15
cleanroom database. Generation 3/scoring run 3 passed that database's exact
currentness gates with 5,000,000 scored people. That database is schema 15 and
does not contain the demographic indexes now present in schema 17, so these
measurements are not treated as the current Phase 11 baseline and cannot open
the implementation gate.

Each result is the median of three sequential local service calls. Result counts
were identical across all repetitions.

| Representative query | p50-like median (s) | Stable matching count | Stable selected count |
|---|---:|---:|---:|
| score threshold, no demographics | 0.421237 | 152 | 152 |
| one state | 7.028321 | 136,250 | 136,250 |
| five states | 11.863418 | 1,526,425 | 1,526,425 |
| age and income bucket | 7.142521 | 144,297 | 144,297 |
| multi-age/income range plus five states | 8.305201 | 328,920 | 328,920 |
| advanced demographics | 6.061058 | 805 | 805 |
| TOP_N 100 across five states | 11.794739 | 1,526,425 | 100 |

No SLA is inferred. The timings show why a future same-generation comparison is
worth retaining, but they do not isolate the effect of the current schema's
existing indexes and therefore do not prove benefit for a new atomic structure.

Machine-readable reference:
`docs/evidence/phase11/10_atomic_segment_benchmark_phase10_frozen.json`.

## Why no speculative optimization was added

Step 10 requires all of the following before implementation: a current 5M
generation, repeated baseline evidence, generation-specific invalidation,
bounded storage, deterministic construction, no PII, exact set equality, and a
baseline-versus-optimized runtime/storage comparison. The first prerequisite is
absent in the canonical runtime. A schema-15 reference cannot establish the
incremental value of adding another schema-17 index, bitmap, rank band, or
membership table.

Consequently:

- no Cartesian or atomic permutation table was created;
- no source-currentness rule was weakened;
- no stale scoring run was queried as though it were current;
- no storage or runtime benefit was invented;
- no import, training, scoring, rank generation, or heavy worker was launched.

The benchmark should be rerun after a later prompt creates the fresh Phase 11
full-5M generation. Only a same-generation, same-schema before/after experiment
may change this decision.

## Harness validation

The reproducible harness is
`scripts/validation/phase11/phase11_step10_benchmark.py`. It opens its direct
inventory connections with SQLite `mode=ro` and `query_only`, refuses active
work, requires existing Audience Engine currentness validation, checks stable
outputs, and records median/minimum/maximum timings. It never prepares
intelligence or creates an index.

Validation command:

```text
pytest -q tests/test_phase11_atomic_segment_benchmark.py
```

The test covers read-only enforcement, the exact seven representative query
shapes including real TOP_N selection semantics, and repeated-result stability.

Recorded results:

| Check | Result |
|---|---:|
| Step 10 harness tests | 3 passed in 8.16s |
| frozen Audience Engine regression | 13 passed in 60.96s |
| Phase 11 smart-reuse regression | 19 passed in 28.13s |
| benchmark harness Python compilation | passed |

## Stop boundary

Step 10 evaluation is complete with the explicit benchmark-gated
`NO IMPLEMENTATION` decision. Step 11 and later prompts were not started.
