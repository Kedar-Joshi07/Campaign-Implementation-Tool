# Section 1 — UI Changes, Updates & New Phase 7 UI

Start from `0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0`.

Run steps 1–10 in order.

This section may update frontend presentation/state/tests and small safe response fields
needed for clarity, but must NOT implement campaign persistence/member export yet.
Campaign write/finalize/export actions remain feature-gated until Section 2.

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
