# Phase 10 Step 15 — Clean-Head Full 5M Certification

## Result

**PASS.** The decisive Phase 10 production-scale path was initiated through installed Google Chrome, built new context-specific intelligence, scored the complete current 5,000,000-person prospect universe, prepared the exact rank and analytics artifacts, rendered the exact Phase 9 Target Group Preview, and saved a multi-branch Target Group linked to a Draft Campaign.

The machine-readable companion is [`15_FULL_5M_CERTIFICATION.json`](15_FULL_5M_CERTIFICATION.json).

## Clean baseline and isolated runtime

- Branch: `main`
- Clean precondition: yes; no dirty override
- Exact HEAD: `a24a24d8f809405533ad342d1ab71e5a425eaa84`
- HEAD subject: `feat(phase10): complete orchestration through browser certification`
- Isolated database: `data/step7_validation_runtime/phase10_step15/runtime.db`
- Browser: Google Chrome `153.0.8010.36`
- Server: real Uvicorn application against the isolated database; no mocked jobs

The preflight verified these canonical Git LFS object IDs:

| Source | LFS SHA-256 | Bytes |
|---|---|---:|
| `campaign_sales_570000.csv.gz` | `89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116` | 6,466,267 |
| `customer_master_125000.csv.gz` | `8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f` | 6,145,025 |
| `usa_demographic_synthetic_5000000_rows.csv.gz` | `adb33ce1daf92b547171960f69f893fec93296d3d514ac7e1bdffbf5c736ac71` | 333,670,533 |

The isolated import completed with 125,000 customers, 570,000 campaign-sales rows, and 5,000,000 demographic rows. All three imports rejected zero rows. Their durable source checksums are recorded in the JSON manifest.

## Mandatory browser initiation

The installed-browser business flow was exercised in order:

1. Campaign Details
2. Campaign Context
3. Targeting Preferences
4. Target Group Preview
5. Review and Save

The browser action initiated orchestration `6`; the decisive build was not initiated by a scoring or training script. Automatic preparation used the real worker path and finished `READY` with the following exact durable identities:

| Identity | Value |
|---|---|
| Targeting context | `4` |
| Campaign context SHA | `3b79ddc38f7c15f1cdc0fba54aa3f2555c6ee896145803b2b40f8092ec7f0a89` |
| Targeting criteria SHA | `ee2c59b1f6817d43fec582eb0c183eb97e56b292689469f29c01e98791bb3063` |
| Modeling context SHA | `27ee771a07470729ace3cd219106942813efe58d04f76fa055b044c2317d05f1` |
| Intelligence key SHA | `6fe4c881a2a7b99b6d4128b401ad944aa95589c43028e6279773685bf7e8f420` |
| Orchestration / generation | `6` / `3` |
| Analysis / model / scoring | `3` / `3` / `3` |
| Training / scoring job | `5` / `6` |

The build plan was `BUILD` for historical analysis, model, scoring, and rank. The resulting generation and final context binding are both `READY`.

## Historical compatibility, eligibility, and model validation

Historical analysis `3` selected 119,748 customers from 563,250 compatible observations. It reconstructed 25,473 known positives and 94,275 unlabeled customers, a positive rate of `0.212722`.

The governed PRIMARY model was `BAGGING_PU` under `PRIMARY_ROLE_GOVERNED`. Model artifact SHA-256 is `7bcd7b61f926a04ea648bb865ba397fb096cdb2b3cd8a40b09806792d9b33164`.

Validation used 23,950 customers: 5,095 known positives and 18,855 unlabeled. Observed-label ROC AUC was `0.6112045414504421`, observed-label average precision was `0.2826338623788278`, top-10 lift was `1.519136408243376`, and top-10 recall was `0.1519136408243376`. These are explicitly observed-label diagnostics, not true-positive/true-negative outcome claims. The stored quality flags were `CHALLENGER_OUTPERFORMED_PRIMARY` and `OBSERVED_LABEL_METRICS_ONLY`; role governance correctly retained the PRIMARY.

## Full 5M scoring assertions

| Assertion | Result |
|---|---:|
| Demographic source | 5,000,000 |
| Scored | 5,000,000 |
| Distinct person IDs | 5,000,000 |
| Duplicates | 0 |
| Invalid/nonfinite/out-of-range | 0 |
| Missing / extra | 0 / 0 |
| Minimum / mean / maximum | `0.06774103945805435` / `0.20595671379862576` / `0.9782832402557606` |
| Chunk size / chunks | 25,000 / 200 |
| Largest transformed matrix | 3,396,428 bytes |
| Runtime / throughput | 953.0632362 seconds / 5,246.2416 rows per second |
| Deterministic rescore | 256 rows, maximum absolute difference `0.0`, verified |

The scoring implementation was reviewed at its executed code path. It reads ordered chunks with `WHERE person_id > ?`, `ORDER BY person_id`, and bounded `LIMIT ?`; neither scoring query contains `OFFSET`. The service transforms, scores, persists, and deletes one chunk at a time. The run’s largest persisted chunk was exactly 25,000 rows. Its bounded `fetchall()` is confined to the maximum 100,000-row repository chunk contract and did not materialize the whole 5M population as a DataFrame, fetch-all result, or list.

Scoring run `3` produced exactly 100 percentile boundaries for a 5,000,000-person population and one current analytics snapshot for the same population.

## Stage timing

Orchestration `6` ran from `2026-09-15T09:33:58Z` through `2026-09-15T10:03:40Z` (1,782 seconds wall clock).

| Stage | Runtime/evidence |
|---|---:|
| Historical analysis | 41 seconds |
| Model job | 25 seconds |
| PRIMARY estimator fit | 5.6823319 seconds |
| Full prospect scoring | 953.0632362 seconds |
| Post-scoring verification, rank, and analytics | 571 seconds wall-clock interval |
| Final readiness and binding | 161 seconds wall-clock interval |

The last two values are intervals between durable stage timestamps because those sub-stages do not expose separate CPU timers.

## Exact preview, multi-branch save, and campaign linkage

The browser displayed an up-to-date preview over 5,000,000 available potential customers. Exactly 146 matched and 146 were selected. The displayed average, strongest, and lowest selected match scores were `0.690`, `0.976`, and `0.602`. The preview showed 25 privacy-safe rows and no contact PII.

Saved Target Group `1`, `Phase 10 Full 5M Multi-Branch Certification Target Group`, preserves two branches and immutable branch SHA `9430cde645b19f986691a3bd6a5a04f1618e7e53c79c243b88e4f6b6a605b2e6`. Direct resolution of that immutable definition produced:

| Check | Count |
|---|---:|
| Age 18–24 branch | 0 |
| Age 35–44 branch | 146 |
| Branch intersection | 0 |
| Union rows | 146 |
| Union distinct person IDs | 146 |
| Duplicates after union | 0 |

The durable Target Group count, legacy saved-audience count, and Campaign snapshot count are all 146. Draft Campaign `1`, `Phase 10 Full 5M Multi-Branch Certification`, links Target Group `1`, analysis/model/scoring `3/3/3`, and the same immutable branch SHA. Its channel is Email and status is `DRAFT`.

Legacy Campaign Builder reopen showed the saved audience and campaign as current and retained the 146-person count. It exposed no contact PII before export. No export was performed and the Campaign was not finalized.

## Reuse follow-up

Browser orchestration `4` reused the exact Modeling Context SHA `4a9d3c30e58e0214bb3d2454fec1f7199f71a1a2fb95707d1a3eee2bf1a61725` from orchestration `3` for a second campaign with different delivery/details. Its plan was `REUSE` for analysis, model, scoring, and rank, and it created no training or scoring job. Generation, analysis, model, and scoring identities remained `1/1/1/1`.

That certified event is preserved by immutable orchestration `4` and its exact
Modeling Context/intelligence hashes. The disposable runtime's mutable Campaign
Context `2` was changed during later validation, so its final row is not the
authoritative snapshot of the earlier reuse event; readiness correctly treats
that later analytical-context change as stale.

A separate targeting-only change on the decisive full-build context produced
two valid filter branches without creating a new generation, model run, or
scoring run. This proves prospect targeting remains outside Modeling Context
identity and does not trigger heavy work.

## Regression and repository gates

| Gate | Result |
|---|---|
| Full `pytest -q` | PASS — 647 passed in 1,468.02s |
| Phase 1–7 clean-room | PASS |
| Phase 8 system-browser harness | PASS — 13 passed in 1.72s |
| Phase 9 tests | PASS — 74 passed, 573 deselected in 530.85s |
| Phase 10 tests | PASS — 89 passed, 558 deselected in 459.25s |
| `compileall` | PASS |
| `pip check` | PASS — no broken requirements |
| SQLite `integrity_check` | `ok` |
| CI hygiene | PASS |
| Git LFS fsck | PASS |

The Phase 1–7 clean-room evidence is retained as `15_CLEANROOM_PHASE1_TO_PHASE7_REPORT.md` and `15_cleanroom_phase1_to_phase7.json` in this directory. Final diff and repository hygiene were rerun after writing this certification evidence.

## Certification conclusion

Phase 10 Step 15 is certified end to end at the full current 5M scale. The exact browser-triggered BUILD path, governed model, deterministic bounded scoring, rank/analytics preparation, Phase 9 binding, exact business preview, multi-branch deduplication, Saved Target Group, Draft Campaign, reuse behavior, legacy reopen boundary, and required regression gates all passed.
