# Step 10 — Optional Atomic Segment Index Optimization

## Objective
Evaluate the useful part of “precompute permutations” without combinatorial explosion.

First benchmark current exact Phase6 Audience Engine filtering on the current 5M scored generation.

Representative queries:
- no demographic filters + score threshold
- 1 state
- 5 states
- age bucket + income bucket
- multi age + multi income + states
- advanced demographics
- TOP_N

Record p50-like repeated local timings; no invented SLA.

Only if evidence shows material repeated-filter latency, implement an atomic optimization such as:
- additional SQLite indexes;
- compact materialized atomic segment membership;
- bitmap/index representation;
- precomputed score/rank bands.

Rules:
- atomic only (single dimension/bucket), not Cartesian combinations;
- generation-specific;
- invalidated by new scoring generation;
- deterministic;
- no PII;
- bounded storage growth;
- exact set intersection semantics;
- outputs must equal existing Audience Engine exactly.

Compare:
baseline SQL vs optimized path for correctness, runtime, storage.

If no meaningful benefit, explicitly choose NO IMPLEMENTATION and keep the benchmark evidence.
Phase 11 still passes; exact-result cache and Phase10 reuse are the primary optimization.

Evidence:
`docs/evidence/phase11/10_ATOMIC_SEGMENT_OPTIMIZATION.md`

STOP.
