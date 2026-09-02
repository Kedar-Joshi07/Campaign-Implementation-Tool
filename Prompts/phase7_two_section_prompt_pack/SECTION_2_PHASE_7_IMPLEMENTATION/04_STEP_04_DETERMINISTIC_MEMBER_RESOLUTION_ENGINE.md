# Step 4 — Deterministic Member Resolution Engine

No campaign_members/audience_members table.
No 5M Python list.

Source of truth is immutable saved audience:
scoring_run_id, canonical filters, selection mode/target, filter hash, resolved count,
contract versions.

Order always:
`propensity_score DESC, person_id ASC`

ALL_MATCHING: exact all matches.
TOP_N: exact first N after filters.

`resolved selected count == saved_audience_resolved_count` or hard fail.

Use bounded keyset pagination, never OFFSET.
Suggested chunk 25k–50k; one chunk in memory.

Internal resolver yields only:
person_id, propensity_score, percentile_bucket, decile, rank_band.

Contact fields are joined only in export layer.

Recheck currentness at start and completion of long work.
If provenance changes mid-process, abort/fail rather than mix sources.

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

60–180 sec for full exact member work may be acceptable. STOP.
