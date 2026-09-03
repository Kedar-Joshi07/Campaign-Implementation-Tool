# Step 3 — Scripts, Data, LFS & Orphan Cleanup

Audit `_step3_*` and all Phase 3/5/6/7 validation, benchmark and evidence helpers. Separate active operational CLIs from historical debug/validation utilities using `scripts/validation/phaseX/` or `scripts/archive/` where useful.

Inspect orphan datasets including `usa_demographic_synthetic_20000_rows.csv.gz`; keep only if clearly documented as a fixture.

Run `git lfs ls-files` and `git lfs status`; audit `.gitattributes`, large non-LFS files, duplicate GZIPs and model artifacts. Do not rewrite history. STOP.
