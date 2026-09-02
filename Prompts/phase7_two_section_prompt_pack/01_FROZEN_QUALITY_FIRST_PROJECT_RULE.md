# Frozen Quality-First Project Rule

Performance must be optimized only after correctness, data integrity, business logic,
reproducibility, provenance, and analytical usefulness are satisfied.

Performance optimizations MUST NOT introduce sampling/approximation, semantic changes,
reduced data coverage, weaker validation, altered business results, weaker currentness,
or less useful output.

Interactive lightweight operations should remain responsive. Exact heavy analytics,
preparation, integrity validation, deterministic member resolution, and large target
exports may take about 60 seconds normally and, where exact full-volume work genuinely
requires it, about 120–180 seconds.

Long-running exact work should use clear progress/loading/streaming states rather than
compromising process, logic, data quality, or usefulness.

Optimize unnecessary work, not necessary work.

## Phase 7 consequences
1. Exact saved-audience resolution is mandatory.
2. TOP_N remains deterministic.
3. ALL_MATCHING remains complete.
4. No approximate target counts.
5. No truncation/sampling to meet timing.
6. No weakening provenance/currentness.
7. Contact PII is exposed only by an explicit approved export profile.
8. No permanent member copy merely for convenience.
9. Large exports may take 60–180 seconds if exact processing requires it.
10. Correctness, logic, process quality and usefulness always outrank arbitrary latency.
