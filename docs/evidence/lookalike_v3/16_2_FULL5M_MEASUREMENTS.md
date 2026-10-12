# Prompt 16.2 — full-5M resource and timing measurements

Recorded 2026-10-10 on Windows 11, Python 3.12.0, SQLite 3.42.0, 12 logical / 10 physical CPUs, 16,849,256,448 bytes system RAM. Starting HEAD `336875c30fc32b00323d916ecc45b232016168a1`; candidate **UNCOMMITTED**. This is an additive follow-up to [Prompt 16.1](16_1_SUPPORT_AWARE_FULL5M.md), not a rewrite of its measured 2.053-second history miss. Runner: `scripts/validation/run_14b_16_2_measurements.py`. Its disposable DB and detailed runtime manifest are under ignored `output/lookalike_stage16_2_measurements/`; no operator canonical DB, source gzip, campaign, or contact was changed.

## Verdict and measurement meaning

**Prompt 16 full-5M performance/certification: GO on this named hardware and isolated current dataset.** The missing process-memory, indexed-publication, and separate index-rebuild measurements were captured; the unchanged 2-second history budget passed in six fresh observations. This does **not** certify Prompt 17's 20 scenarios, remote CI, a universal latency guarantee, or purchase-response prediction. The earlier history miss remains historical evidence, and the PRD004 recovery cost below is not hidden.

RSS is the process's real resident set sampled with `psutil` every five seconds, from process start through completion. Reported peaks are the largest observed samples; a shorter-than-five-second spike could be missed. Elapsed times use `time.perf_counter()`. The index rebuild is an explicit `REINDEX` on the isolated database; score publication's indexed `INSERT ... SELECT` is timed separately but necessarily includes SQLite's normal index maintenance. Do not subtract the index rebuild from publication or portray them as the same operation. Heartbeat, CPU, read/write bytes, DB/WAL bytes and resource minima were journaled. Budgets were recorded but never used as process timeouts.

## Full scoring, verification, indexed publication, and memory

All generations publish exactly 5,000,000 unique demographic identities. Generation IDs 3/4/5 belong to support-aware PRD001/PRD003/PRD004 profiles. Scores and source lineage match the independently verified [16.1 population audit](16_1_SUPPORT_AWARE_FULL5M.md).

| Product | Complete successful scoring process | Claim + chunk loop | Deep verify | Indexed score insert | Full verify + committed publish | Sampled peak RSS | Peak WAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| PRD001 | 3,984.540 s | 2,379.742 s | 95.517 s | 1,417.499 s | 1,604.798 s | 346,927,104 B | 1,626,736,712 B |
| PRD003 | 1,750.860 s | 1,533.050 s | 18.575 s | 167.813 s | 217.811 s | 337,780,736 B | 1,616,333,712 B |
| PRD004, successful retry | 2,088.605 s | 1,789.218 s | 23.975 s | 236.944 s | 299.387 s | 347,992,064 B | 1,592,050,432 B |

The PRD004 worker from the first scoring command ceased unexpectedly after its durable 4,450,000-row checkpoint. It was not killed for a budget overrun and was no longer present when checked. The checkpoint's start and final heartbeat were 2026-10-09T19:03:51Z and 19:28:14Z: **1,463 seconds of active partial work**. The fenced stale-lease recovery intentionally deleted staged rows and rescored from zero under a new token while retaining generation 5. The successful retry was launched detached to avoid an interactive-session interruption. It completed without interruption. Total measured *active* PRD004 work across the aborted segment and successful retry was at least 3,551.605 seconds; the overnight idle gap is excluded. The aborted process's exact peak RSS cannot be certified because its live file was damaged during the session termination; the retry's 347,992,064-byte peak is certified. This is a measurement limitation, not a fabricated zero or a claim that the 4.45-million-row checkpoint was resumed in place.

The unchanged 5,400-second *complete successful product process* budget passed for all three products. The earlier aborted PRD004 segment is also shown separately so actual resource cost is not concealed. The scoring process's final DB grew from 5,318,819,840 bytes at the verified import to 8,560,308,224 bytes after all three generations. The smallest observed free disk across phase monitors remained above 267 GB.

The separate, full score-lookup `REINDEX` took **158.656 seconds**, sampled peak RSS **205,647,872 bytes**, and peak WAL **701,607,192 bytes**. The index existed and was maintained during score insert; `REINDEX` measured a standalone rebuild, not the initial index creation. It ran only after all three generations were published and before preflight.

## End-to-end process measurements

| Isolated process/phase | Wall elapsed | Sampled peak RSS | Outcome |
|---|---:|---:|---|
| Canonical gzip identity audit | 17.303 s | 210,448,384 B | 125K customers, 570K sales, 5M demographics verified |
| Consistent disposable DB copy, reused-import validation, quick/foreign-key checks | 194.771 s | 203,526,144 B | PASS; copy-only/import registry preserved |
| Three-product cohort and profile fitting/publication | 28.594 s | 205,795,328 B | PASS, frozen V2 partition |
| Standalone score-lookup index rebuild | 158.716 s | 205,647,872 B | PASS; inner `REINDEX` 158.656 s |
| Uncached common-context preflight | 46.965 s | 199,217,152 B | CURRENT, ≥0.70 count 2,412,119 |
| Independent product audits, feature stream, warm reuse, composite SQL check | 635.180 s | 204,136,448 B | PASS, exact three-product context |
| Uncached recorded Scenario 20 preflight | 19.496 s | 200,249,344 B | CURRENT; inner count 18.717 s |
| Production-path search and immutable snapshot | 20.453 s | 205,111,296 B | 25,765 members; inner execution 19.118 s |
| Exact reuse, history/detail, hash check, streamed EMAIL export | 17.560 s | 202,776,576 B | Reused snapshot 1; export 2,813,047 B |
| Five additional history projections | 5.714 s total | 199,626,752 B | All five under 2 s |

The independent per-product audit portions took 76.632 / 79.496 / 82.704 seconds for PRD001 / PRD003 / PRD004. The full independent verify *process* took 635.180 seconds; its inherited inner phase timer recorded only 306.434 seconds before the final composite SQL check, so the process timer is the correct end-to-end number. Similarly, the copied-import inner timer of 2.455 seconds excludes DB backup and integrity checks; the process timer of 194.771 seconds is the end-to-end measure.

## Exact results and budgets

The independent full SQL max/winner aggregate has 5,000,000 valid people and no invalid people. Winner counts PRD001/PRD003/PRD004 are 785,715 / 1,833,366 / 2,380,919. Cumulative counts ≥0.50 / 0.60 / 0.70 / 0.80 / 0.90 are 4,935,724 / 4,280,439 / 2,412,119 / 591,372 / 43,384. The common-context preflight count agrees exactly at ≥0.70. Recorded Scenario 20 retains its original filters and `VERY_STRONG` ≥0.90 minimum; its uncached exact preflight returned 25,765 from 2,114,560 demographic-eligible people. The immutable snapshot has 25,765 members and the same verified SHA-256 `8905567a1611c8d2851ac6a3f2ccb3691e2b14b8aa097207fcec574e0a1c9895` as prior full-5M evidence.

The second search reused snapshot 1 in 8.635 seconds; no profile/generation was rebuilt. History measured 1.454 seconds in that path, then 1.202, 1.135, 1.088, 1.161 and 1.083 seconds in five additional calls. All six passed the **unchanged** predeclared 2-second history budget; the earlier 2.053-second miss is still recorded in 16.1 and means there is no universal sub-2-second claim. Export first byte took 2.269 seconds against its 10-second budget. The 180-second preflight and 600-second materialization budgets passed on this pass.

## Commands, checks, and limitations

The runner phases were executed strictly in order: `audit`, `import`, `profiles`, `score`, `index`, `preflight`, `verify`, `scenario-preflight`, `scenario-search`, `scenario-reuse-export`, `history`, each via `python scripts/validation/run_14b_16_2_measurements.py --phase <name>`. Heavy phases used hidden detached processes with captured stdout/stderr; the monitor observed them without timeout or kill. `score` was re-invoked once only after proving the first PRD004 worker absent and its durable lease stale. Runner/score changes passed Ruff and compile checks. The focused scoring suite passed **13/13** after the measured run; JSON parsing passed and `git diff --check` found no whitespace errors (only line-ending conversion warnings).

No fresh canonical import was performed in this pass: the earlier verified 5M disposable import was copied with SQLite's consistent backup API, source identities were re-audited, and the copy passed quick/foreign-key checks. The prior fresh-import time remains 542.774 seconds in 16.1. The absolute peak of the aborted first PRD004 worker is unavailable; no value is invented. The measurements are representative of the named hardware and source state, not a general service-level guarantee. Prompt 17 and later stages were not run.

Machine-readable summary: [16_2_FULL5M_MEASUREMENTS.json](16_2_FULL5M_MEASUREMENTS.json). Detailed ignored runtime manifest: `output/lookalike_stage16_2_measurements/run_manifest.json`.
