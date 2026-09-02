# Section 2 — Phase 7 Campaign Builder Implementation

Start from successful Section 1 SHA.

Flow:
Current saved audience
→ Campaign Draft
→ Review
→ Finalize immutable campaign
→ Resolve exact members
→ Apply channel deliverability
→ Join only approved contact PII
→ Stream CSV
→ Persist aggregate export audit
→ STOP before activation

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
