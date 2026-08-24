# Score Semantics and Summary Contract

Use **Look-alike Propensity Score** / **PU Propensity Score**. Higher = stronger learned affinity to known-positive pattern. It is not calibrated purchase probability.

Current Bagging score must be finite `[0,1]`. Persist full model float; UI formatting only. Do not assume same numeric score is comparable across different models.

Phase 5 summary stores count, min/max/mean, total seconds, rows/sec, chunk size, model/feature/artifact provenance and age-semantics note.

Do not persist rank, percentile, decile, top-N%, or high/medium/low in Phase 5. Phase 6 owns those semantics.
