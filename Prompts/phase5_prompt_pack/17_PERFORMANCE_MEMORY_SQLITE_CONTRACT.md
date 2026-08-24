# Phase 5 Performance, Memory, and SQLite Contract

Goal: 5M inference without 5M memory or one massive write transaction.

Default chunk `25,000` (~200 chunks), adjustable internally after measurement. Keyset by person_id; no OFFSET in scoring loop. Select only person_id+11 features; no `SELECT *`.

One source/transformed/score chunk in memory at a time. Do not accumulate all scores. Do not proactively densify whole data. Per-chunk `executemany` transaction; no per-row commit and no one 5M transaction.

Only initial required rank index; avoid speculative 5M indexes.

Record DB size before/after, total seconds, rows/sec, chunk count, largest chunk and transformed-memory estimate. Hardware runtime is evidence, not a Critical threshold unless clearly broken.

Progress writes at chunk/percentage boundaries. Aggregate COUNT/MIN/MAX/AVG is allowed after scoring.

Partial FAILED data may remain isolated rather than performing huge cleanup during startup.
