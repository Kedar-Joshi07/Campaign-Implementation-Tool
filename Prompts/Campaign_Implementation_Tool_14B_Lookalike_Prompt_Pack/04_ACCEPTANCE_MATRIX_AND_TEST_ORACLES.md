# Acceptance matrix and independent test oracles

Every row needs a test/evidence pointer and PASS, FAIL, BLOCKED, or NOT_RUN status in the final report. A source file alone is not proof.

| ID | Requirement | Independent expected proof | Owner |
|---|---|---|---|
| A01 | Approved v3 direction | Dated addendum; previous decision preserved | 00 |
| A02 | Pinned code and unversioned API | Actual HEAD; golden HTTP responses | 00/01 |
| A03 | v1 semantics | Raw fixtures reopen and select unchanged | 00/09 |
| A04 | v2 bounds | Literal boundary fixture and discrete bins | 00/09 |
| A05 | BROAD = .60 | Explicit literal assertions; 10 translations | 00/17 |
| A06 | v2 .50 and default .70 | [.50,.60) and default golden response | 00/09 |
| A07 | Schema and migration | Fresh/populated 31/reinitialize signatures | 01 |
| A08 | Mixed request rejected | v3 plus probability fields fails validation | 01/05 |
| A09 | Relevant product buyers | Exact join; distinct buyers; repeated sales dedup | 02 |
| A10 | Catalog versus observed history | Streamed 36 sales products versus 48 master | 02 |
| A11 | Unsupported product | No history or 199 buyers blocks; no alias | 02/06 |
| A12 | Fit/holdout separation | Union customer identity sets do not intersect | 02/03 |
| A13 | Training-only preprocessing | Alter holdout/prospects; fit unchanged | 03 |
| A14 | Learned profiles | Relevant buyer changes change artifact | 03/08 |
| A15 | Score mathematics | Manually summed prototype distance fixture | 03 |
| A16 | Missing and unknown values | No false match credit or improved coverage | 03 |
| A17 | Valid bounds | Finite score in [0,1] or invalid reason | 03/04 |
| A18 | Supported multiple profiles | No singleton/outlier anchors | 03 |
| A19 | ANY/max product match | Controlled per-product scores and winner tie | 04 |
| A20 | Hard filters | Highest score outside criteria excluded | 05 |
| A21 | Cumulative minimum | .80 includes .92/.88; v2 .80 excludes .92 | 05 |
| A22 | Count and member parity | Preflight = membership = reopened count | 05/07 |
| A23 | OR deduplication | Overlapping branches emit each person once | 05 |
| A24 | TOP_N distinction | Qualified count differs from min(N, qualified) | 05 |
| A25 | Probability-independent readiness | Ready similarity with absent calibration succeeds | 05/09 |
| A26 | Preserved probability governance | Existing split/calibration blocker not bypassed | 05/09 |
| A27 | Reachable build | Missing artifact → prepare → ready → count | 05/06 |
| A28 | Complete cache identity | Each semantic identity change separates keys | 05 |
| A29 | Fast reuse | No heavy training or deep scan per request | 04/16 |
| A30 | Mode-switch UI race | Late response for old mode is ignored | 06 |
| A31 | Score wording | Index language; no probability/percentile claim | 06/18 |
| A32 | Versioned results/exports | Correct readers for membership 1, 2, 3 | 07 |
| A33 | Full precision | Membership decisions before display rounding | 07 |
| A34 | Export safeguards | Consent, identifiers, dedup, formula protection | 07 |
| A35 | Feedback isolation | Similarity never becomes probability raw input | 07 |
| A36 | Current sources | Source replacement makes old reuse stale | 04/05/15 |
| A37 | Fenced publication | Old owner cannot write; no partial ready state | 15 |
| A38 | Full 5M population | Actual unique source = valid plus invalid rows | 16 |
| A39 | Bounded resources | Measured CPU/RAM/disk/WAL and timings | 16 |
| A40 | Unchanged 20 scenarios | Original hash plus explicit v3 translation | 17 |
| A41 | 10K demo qualification | Current registry; old 101 metadata not override | 17 |
| A42 | Client honesty | No invented products, probability or lift claims | 18 |
| A43 | Complete bounded regression | Actual repository CI suite results | 09/19 |
| A44 | Exact-SHA remote CI | Run head equals candidate; required jobs pass | 19 |
| A45 | Separate decisions | Runtime, descriptive, predictive, 5M, demo distinct | 19 |

## Manual scalar score oracle

Use one fully known 11-feature prototype, equal weights and fixed numeric ranges:

- Exact match: S = 1.
- One categorical mismatch: S = 10/11, about .9090909.
- Two categorical mismatches: S = 9/11, about .8181818.
- One mismatch plus an age difference equal to half the fitted age range: S = 1 − 1.5/11, about .8636364.
- All features missing: invalid coverage; not a valid score of 0 or 1.

These prove the declared score calculation, not marketing accuracy. Selection examples .96/.92/.88/.73 are controlled fixture values, not claimed canonical learned outputs.

## Cross-version boundary oracle

V2 request .80 selects [.80,.90). V3 minimum .80 selects [.80,1]. Put .80, nextafter(.90,0), .90 and 1 into independent fixtures using distinct typed score columns. Verify the intended difference and no cross-mode cache hit.
