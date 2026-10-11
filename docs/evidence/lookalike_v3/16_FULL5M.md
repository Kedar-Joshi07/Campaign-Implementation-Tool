# Prompt 16 — canonical five-million-row certification

Recorded 2026-10-09 UTC. Starting and working HEAD: `336875c30fc32b00323d916ecc45b232016168a1`; candidate: **UNCOMMITTED**. Preceding gate: Prompt 15 GO. The worktree already contained uncommitted 14B work. This stage added the versioned full-scale runner and this evidence pair, corrected v3 preflight's insufficient-split classification, and added a focused regression. No operator database, canonical input, old result, v1/v2 probability contract, deployed service, or remote branch was changed.

## Decision

**FULL5M_NO_GO for the recorded common scenario.** The real source files were imported into a disposable schema-33 database and both eligible product profiles were scored and verified over all 5,000,000 demographic people. This proves full-population scoring and recovery for those exact profiles; it does **not** prove that the recorded three-product search can run. The prior scenario manifest at `output/demo_preload/demo_20_scenario_checkpoint.json` fixes products `PRD001`, `PRD003`, and `PRD004` with empty historical filters. `PRD001` has 200 distinct attributed buyers but the shared union split gives 158 fit and 42 holdout buyers, below the frozen 160-fit minimum. `PRD003` has 251/206/45 and `PRD004` has 1,461/1,164/297 (buyer/fit/holdout). No threshold, product, historical filter, or source was changed to make the context pass.

The exact recorded-context API preflight now returns `PROFILE_NOT_ELIGIBLE`, `build_available=false`, and `selected_count=null`. Before the focused correction, the same case was misleadingly classified as `SIMILARITY_SOURCE_STALE` because a raw `COUNT(DISTINCT buyer)` check ignored fit/holdout support. The correction calls the exact cohort contract and checks the current customer/sales source checksums. The 200-buyer/159-fit synthetic regression passes. The live five-million-row disposable preflight confirms the corrected result in 8.804 seconds. This is a truthful blocked response, not an exact customer count.

## Sources, environment, and advance limits

The runner independently streamed each actual gzip input, counted CSV data lines, hashed compressed and decompressed bytes, then matched import provenance and table counts. These are data files, not LFS pointer stubs. Detailed payload hashes and all source lineage are in [`16_FULL5M.json`](16_FULL5M.json) and the ignored scratch `output/lookalike_stage16_full5m/run_manifest.json`.

| Input | Real data rows / import ID | Compressed SHA-256 | Import source checksum |
|---|---:|---|---|
| Customers | 125,000 / 1 | `8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f` | `99a09d2f0db06980afe290cf74a4db1df76cf8c340534fb2088879fb093d9ea9` |
| Campaign sales | 570,000 / 2 | `89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116` | `2fdb11c576a180b7349e50e0bf9d3b0a66d0d354ba8d42062756c8cd840965c4` |
| Demographics | 5,000,000 / 3 | `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d` | `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f` |

Catalog SHA-256: `317778cd2f591ad34757413915c33ad9298c7fb70fbbe22605d8078be3b9ba6a`. Environment: Windows 11 build 26200, Python 3.12.0, SQLite 3.42.0, 10 physical/12 logical CPUs, 16.85 GB RAM. Initially available RAM was 3.31 GB and disk free was 292.15 GB. The disposable DB ended at 5,318,819,840 bytes; profile artifacts are 5,521 and 7,076 bytes; WAL ended at zero bytes. Scratch files are ignored and must not be committed. The operator's `data/campaign_poc.db` was not migrated or written.

The runner declared these bounds before measuring: source audit 600 s, fresh import 3,600 s, cohort/profiles 1,800 s, one-product score 5,400 s, one-product deep verification 1,200 s, warm generation reuse 10 s, exact preflight 180 s, materialization 600 s, history projection 2 s, and export first byte 10 s. A bound is not considered passed for a path that could not run. Peak process memory and isolated deep-verify/index/publication stage timings were not instrumented, so those gates remain unproved; resource snapshots are not peak-memory measurements.

## Measured execution

| Work | Observed | Result |
|---|---:|---|
| Independent gzip/source audit | 14.133 s | Counts and hashes matched |
| Fresh imported/migrated schema-33 database | 542.774 s | 125K + 570K + 5M inserted; zero rejected |
| Exact cohort and supported profile fitting/publication | 22.855 s | `PRD003` profile 1 (4 prototypes); `PRD004` profile 2 (8 prototypes); no `PRD001` profile |
| `PRD003` generation 1, including restart, deep verification and return | 2,088.216 s | 5M published/attested; resumed the same generation after 25K committed rows |
| `PRD004` generation 2, including deep verification and return | 3,704.424 s | 5M published/attested |
| Independent post-publication full-population audit, including distributions/composite | 542.909 s | Passed for both generations |
| Warm targeting options | 1.022 s | Below existing 2 s warm limit on this host |
| Warm verified-generation reuse | 0.058 / 0.054 s | Same generation IDs, no new score build |
| Recorded-context blocked preflight | 8.804 s | Correct `PROFILE_NOT_ELIGIBLE`; no false count |

For the forced restart, a child process exited after the first durable 25,000-row `PRD003` stage chunk; no generation was published before recovery. A successor took the stale fenced lease, completed all 5M scores, and published exactly generation 1. The interruption process took 20.018 s; the measured 2,088.216 s is the successor scoring call including its internal checks. `PRD004` ran sequentially, without a restart. Chunk size was 25,000. The recorded `SCORING_PROSPECTS` stage windows were 19:17:53–19:42:10 UTC and 19:52:53–20:37:48 UTC; the public generation-call durations are longer, so those windows must not be presented as entire scoring/verification timings. Neither product exceeded the predeclared one-product 5,400 s bound. The isolated 1,200 s verification bound is **not certified** because that substage was not separately timed.

Observed one-product calls cost about 35 and 62 minutes on this host. An unmeasured 50-product maximum-context workload could therefore be very large; these two timings are not a universal scaling estimate or a latency SLA. A single verified generation can serve multiple thresholds without rescoring, as the 0.05-second exact-identity warm reuse checks demonstrated. We did not assert that a different exact product set can reuse these profiles.

## Full-population integrity and distributions

Each generation has 5,000,000 rows, 5,000,000 distinct people, 5,000,000 valid scores, zero invalid scores, zero missing and zero extra demographic IDs, and a VERIFIED attestation tied to the current source/artifact checksums. Thirteen fixed positions per product also matched an independent scalar scorer. Full SQL over the two existing generations found a maximum-score winner for every one of the 5M people: `PRD003` 1,859,374 and `PRD004` 3,140,626, including one equal-score tie resolved to `PRD003`. This is a diagnostic pairwise aggregate, **not** a prepared two-product search; profile context identity includes the original three-product set.

| Product | Minimum–maximum | p05 / p25 / p50 / p75 / p95 | Cumulative ≥.50 / ≥.60 / ≥.70 / ≥.80 / ≥.90 |
|---|---|---|---|
| `PRD003` | .231115–.999674 | .479339 / .579008 / .648492 / .704183 / .801758 | 4,555,404 / 3,230,996 / 1,337,086 / 264,622 / 17,489 |
| `PRD004` | .294118–.999746 | .515678 / .597233 / .669418 / .731036 / .812869 | 4,834,668 / 3,695,342 / 1,676,385 / 332,915 / 21,368 |

Tier counts (`BELOW_MINIMUM`, `EXPLORATORY`, `BROAD`, `GOOD`, `STRONG`, `VERY_STRONG`) were `444,596 / 1,324,408 / 1,893,910 / 1,072,464 / 247,133 / 17,489` for `PRD003` and `165,332 / 1,139,326 / 2,018,957 / 1,343,470 / 311,547 / 21,368` for `PRD004`. These empirical distributions are not predictive conversion-quality claims or expected percentile quotas. All 5M prospect feature rows were streamed for aggregate-only drift context; numeric means include age 48.663, yearly individual income 43,249.854, and family members 2.103. No contact PII or row traces were placed in evidence. The query plan used the covering `idx_buyer_similarity_score_lookup` for score lookup but still used a temporary B-tree for `ORDER BY`; demographics person lookup used its primary-key index. That sort remains a performance observation, not a claimed optimized path.

## Exact-context boundary and checks not promoted to passes

An exploratory probe dropped `PRD001` while retaining the recorded historical filters. Its API response was `SIMILARITY_SOURCE_STALE` with no selected count, because the already-published profiles carry the **three-product context hash**. That probe is `BLOCKED_EXACT_CONTEXT_IDENTITY`, not a passing supported-subset search or a replacement common scenario. Preparing an independent two-product context would require its own exact cohort/profile/generation and approval to use it as a scenario; none was silently substituted.

Consequently the recorded-context exact count, immutable result snapshot count/hash, result materialization, history response, export first byte, and sequential browser/demo scenarios were **not run**. There is no truthful full-scale result to time or export. Full-scale source replacement was not injected into the verified scratch database; bounded regression `test_source_replacement_mid_score_marks_stale_and_publishes_nothing` passed. Bounded `test_fast_reuse_never_consults_v2_calibration_tables` passed; an actual five-million-row v2 calibration promotion and independence probe was not run. The 5M result is runtime/integrity certification for two fixed profile generations, not a predictive-validation, full-context, or demo-readiness GO.

## Reproduction and checks

Run stages sequentially with `python scripts/validation/run_14b_16_full5m.py --phase <stage>` for `audit`, `import`, `profiles`, `score`, `verify`, `preflight`, then optional `subset-preflight`. The script guards its scratch target to a dedicated child of `output/`, resumes verified generations rather than repeating scoring, and retains the ignored `run_manifest.json` for complete measured fields. These completed commands did not run in parallel. The actual input manifest, DB, and profile artifacts remain in `output/lookalike_stage16_full5m/` for local inspection; they are not committed.

- `python -m pytest tests/test_lookalike_v3_preflight_search.py tests/test_buyer_similarity_cohort_service.py -q` → **16 passed in 49.84 s**, including the new 200-buyer/159-fit boundary regression.
- `python -m pytest tests/test_buyer_similarity_scoring_service.py -q -k 'source_replacement_mid_score or fast_reuse_never_consults_v2_calibration_tables'` → **2 passed, 11 deselected in 19.09 s**.
- `python -m pytest tests/test_lookalike_v3_fault_recovery.py -q -k 'insufficient_historical_buyers_block_once_without_retry_loop'` → **1 passed, 26 deselected in 29.38 s**.
- `python -m ruff check app/services/buyer_similarity_preflight_service.py scripts/validation/run_14b_16_full5m.py tests/test_lookalike_v3_preflight_search.py` → pass.

`git diff --check` passed (only pre-existing README CRLF conversion warnings); the small JSON evidence parsed successfully. There was no full-repository regression, remote exact-SHA CI, or browser certification in this stage. The existing v1/v2 schema, APIs, score rows and semantics were not modified. The production change is confined to v3's unready preflight classification and its plain-language guidance; no schema migration is added here.

**Next-stage gate:** Do not start Prompt 17 as a FULL5M_GO continuation. The recorded context needs genuinely sufficient product-specific fit/holdout evidence under the frozen contract, or an explicitly approved new recorded scenario/context followed by its own full preparation and result certification. Relaxing support floors or silently dropping `PRD001` would not close this gate.
