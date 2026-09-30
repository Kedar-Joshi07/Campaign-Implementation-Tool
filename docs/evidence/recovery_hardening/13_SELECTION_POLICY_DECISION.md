# Prompt 13 — Zero-customer root cause and selection-policy decision gate

## Decision status

**Human/business decision required. No selection policy was changed.**

This document presents the evidence and the permitted options. It does not
lower thresholds, rename percentiles as probabilities, modify calibration,
fabricate feedback, widen filters, reduce the 10,000-customer qualification
minimum, or submit a nonqualifying search.

## Execution baseline

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- Audit date: 2026-09-30.
- The working tree already contained the preserved, uncommitted outputs of
  recovery-hardening Prompts 01–12.
- All database diagnostics in this prompt opened
  `data/campaign_poc.db` with SQLite URI `mode=ro`.
- The canonical database metadata remains schema version 26 while the working
  code supports schema version 30. It was not migrated by this diagnostic.
- Persisted calibration artifact 2 is the database's only `PROMOTED` artifact.
  Its source checksums still match current import IDs 1, 2, and 4, but its old
  row-count-only verification attestation is now `STALE` under the hardened
  attestation contract. Operational reuse therefore still requires the current
  migration and deep-verification path.

## Exact root cause

The zero-customer result is correct under selection contract v2. It is not
caused by demographic scarcity or failed result materialization.

- Artifact 2 contains exactly 5,000,000 calibrated rows.
- Every calibrated probability is between `0.06517788696708109` and
  `0.07855599400877739`.
- Contract v2 begins at an absolute calibrated purchase probability of `0.50`.
- Consequently, every approved v2 bucket contains zero rows.
- All 21 persisted current preflight cache rows have bucket and intersection
  counts of zero, while their demographic pools range from 74,514 to 5,000,000.

The promoted sigmoid is:

```text
p = sigmoid(0.37049473523728327 * raw_score - 2.6691478891308806)
```

The governed raw-score domain is `[0, 1]`. Even at raw score `1`, this transform
produces only `0.09123456767048603`. A probability of `0.50` would require raw
score `7.204280210409537`, outside the allowed domain. Therefore 0.50 is not
merely absent from the current five million rows: it is mathematically
unreachable under this calibration artifact.

The outcome itself is uncommon and the model has weak separation. The historical
calibration-evaluation prevalence is 5.9928%, and the historical ROC-AUC is only
0.5440. Calibration therefore compresses predictions close to the base rate.

## Canonical distribution diagnostics

### Calibrated probability and raw-score quantiles

Quantiles use deterministic linear interpolation over all 5,000,000 rows.

| Quantile | Raw propensity score | Calibrated purchase probability |
|---:|---:|---:|
| Min | 0.015956734 | 0.065177887 |
| p1 | 0.028236535 | 0.065455642 |
| p5 | 0.035087057 | 0.065611071 |
| p10 | 0.039583930 | 0.065713285 |
| p25 | 0.047242404 | 0.065887704 |
| p50 | 0.056370792 | 0.066096161 |
| p75 | 0.066878959 | 0.066336886 |
| p90 | 0.077853291 | 0.066589159 |
| p95 | 0.085366988 | 0.066762395 |
| p99 | 0.102623991 | 0.067161856 |
| Max | 0.558759756 | 0.078555994 |

Means are `0.057919803` raw and `0.066132489` calibrated.

### Approved v2 bucket populations

| Absolute probability bucket | Population |
|---|---:|
| 0.90–1.00 | 0 |
| 0.80–<0.90 | 0 |
| 0.70–<0.80 | 0 |
| 0.60–<0.70 | 0 |
| 0.50–<0.60 | 0 |
| Below 0.50 / no v2 bucket | 5,000,000 |

### Observed absolute-threshold counts

These counts are diagnostics, not approved replacement thresholds.

| Minimum calibrated probability | Population at or above |
|---:|---:|
| 6.5% | 5,000,000 |
| 6.6% | 3,091,893 |
| 6.7% | 94,841 |
| 6.8% | 2,639 |
| 6.9% | 199 |
| 7.0% | 65 |
| 7.2% | 23 |
| 7.5% | 5 |
| 7.8% | 2 |
| 8.0% | 0 |

### Top-percentile population sizes

These are relative ranks. The displayed probability remains the absolute
calibrated purchase probability.

| Top share of 5M | Population | Boundary raw score | Boundary probability |
|---:|---:|---:|---:|
| 0.2% | 10,000 | 0.121617124 | 0.067604068 |
| 0.5% | 25,000 | 0.110508949 | 0.067345112 |
| 1% | 50,000 | 0.102624174 | 0.067161860 |
| 2% | 100,000 | 0.095083497 | 0.066987038 |
| 5% | 250,000 | 0.085367067 | 0.066762396 |
| 10% | 500,000 | 0.077853318 | 0.066589160 |
| 20% | 1,000,000 | 0.069747421 | 0.066402739 |
| 25% | 1,250,000 | 0.066878968 | 0.066336886 |
| 50% | 2,500,000 | 0.056370794 | 0.066096161 |

The top 0.2% has exactly 10,000 customers globally, but any demographic
intersection can only reduce that number. This is why global percentile size
alone does not prove that a filtered scenario qualifies.

## Outcome and calibration diagnostics

The modeled outcome is `ATTRIBUTED_PURCHASE`.

| Population | Rows | Purchases | Observed base rate |
|---|---:|---:|---:|
| Reconstructed historical cohort | 30,633 | 1,892 | 6.1763% |
| Model validation partition | 6,127 | 378 | 6.1694% |
| Calibration-fit partition | 1,705 | 113 | 6.6276% |
| Calibration-evaluation partition | 4,422 | 265 | 5.9928% |

### Reliability / calibration curve

All evaluation predictions fall in the standard `[0.0, 0.1)` reliability bin:

| Probability interval | Rows | Mean predicted | Observed purchase rate |
|---|---:|---:|---:|
| 0.0–<0.1 | 4,422 | 6.6225% | 5.9928% |

Because uniform-width bins conceal the compressed ranking, the following
equal-frequency diagnostic curve is also shown. It is ordered from the lowest
to the highest predicted probability.

| Decile | Rows | Probability range | Mean predicted | Observed rate |
|---:|---:|---:|---:|---:|
| 1 | 443 | 6.5319%–6.5793% | 6.5659% | 4.7404% |
| 2 | 443 | 6.5793%–6.5919% | 6.5858% | 4.5147% |
| 3 | 442 | 6.5919%–6.6018% | 6.5969% | 4.5249% |
| 4 | 442 | 6.6018%–6.6100% | 6.6059% | 6.5611% |
| 5 | 442 | 6.6100%–6.6182% | 6.6140% | 7.4661% |
| 6 | 442 | 6.6182%–6.6282% | 6.6231% | 4.2986% |
| 7 | 442 | 6.6283%–6.6383% | 6.6332% | 6.7873% |
| 8 | 442 | 6.6383%–6.6509% | 6.6444% | 6.3348% |
| 9 | 442 | 6.6509%–6.6706% | 6.6592% | 7.4661% |
| 10 | 442 | 6.6706%–6.8541% | 6.6969% | 7.2398% |

The non-monotonic observed rates and narrow probability range show that the
model ranks only weakly. Small numeric probability differences must not be
marketed as large differences in customer intent.

### Historical precision and lift diagnostics

| Evaluation top slice | Rows | Purchases | Precision | 95% Wilson interval | Lift |
|---:|---:|---:|---:|---:|---:|
| 1% | 45 | 4 | 8.8889% | 3.5111%–20.7339% | 1.4833 |
| 5% | 222 | 14 | 6.3063% | 3.7933%–10.3058% | 1.0523 |
| 10% | 443 | 32 | 7.2235% | 5.1629%–10.0196% | 1.2054 |
| 20% | 885 | 65 | 7.3446% | 5.8041%–9.2539% | 1.2256 |

Persisted calibration metrics are ROC-AUC `0.544008969`, average precision
`0.068868320`, top-decile lift `1.205366498`, Brier score `0.056369909`, log
loss `0.227049857`, and ECE `0.006297550`.

These values reproduce artifact 2 exactly, but they are **historical diagnostic
metrics, not Prompt 11-governed metrics**. Artifact 2 uses calibration contract
v1 and the old `MIN(campaign_id)` grouping method. Model run 5 has no persisted
three-way split lineage. Prompt 11 proved that the applicable campaigns are
connected through shared customers, so independent model-training,
calibration-fit, and calibration-evaluation groups cannot currently be formed.
Therefore no ROC-AUC, AP, lift, expected precision, or risk band with proper
Prompt 11 held-out lineage is currently available. Production-policy claims
must not treat the table above as governed evidence.

## Is a 50% individual purchase probability plausible?

It is theoretically possible for a rare-outcome problem to contain individuals
with 50% purchase probability if strong, validated predictors exist. The current
system provides no such evidence:

- the historical base rate is approximately 6%;
- rank separation is weak (`ROC-AUC ≈ 0.544`);
- the highest observed calibrated probability is 7.8556%;
- the current sigmoid cannot exceed 9.1235% anywhere in its valid raw-score
  domain; and
- no leakage-safe Prompt 11 evaluation exists to justify extrapolation.

Accordingly, 50% is not statistically plausible under the current model,
calibration, features, and data. It must remain an unmet threshold unless new
governed data/model evidence supports it.

## Policy options requiring an explicit decision

### Option A — retain the 0.50+ absolute-probability contract

**Semantics:** Preserve v2 exactly: a customer qualifies only when calibrated
individual purchase probability falls in one of the existing 0.50–1.00 ranges.

**Risks:** The UI remains truthful but unusable for the current generation. A
future model could still fail to reach 0.50. Pressure to manufacture higher
probabilities must be resisted.

**Required UI changes:** No selection-contract change. Improve explanatory
empty-state text to say that the approved probability threshold is above the
current model's supported range and provide model/data remediation guidance.

**Migration/contract changes:** None. Preserve v2.

**Demo implications:** Current demo remains NO-GO. No qualifying searches may be
submitted.

**10K feasibility without widening:** No. The global eligible population is
zero, so every filtered intersection is zero.

**Next implementation path if approved:** Prompt 14A.

### Option B — introduce lower absolute-probability bands as a new version

**Semantics:** Continue selecting by absolute calibrated purchase probability,
but introduce separately approved v3 boundaries that reflect this outcome's
observed probability scale. For illustration only, empirical boundaries such as
p50 `6.6096%`, p75 `6.6337%`, p90 `6.6589%`, p95 `6.6762%`, and p99 `6.7162%`
could anchor business-defined bands. These are evidence-derived candidates, not
approved thresholds.

**Risks:** The distribution is extremely compressed. Tiny numeric changes may
move many people between bands, and users may overinterpret statistically weak
differences. Fixed probability boundaries can also change population sizes after
recalibration. Prompt 11-governed validation is unavailable, so final bands
cannot yet claim validated precision or lift.

**Required UI changes:** Replace v2 labels only for v3 requests; show exact
percentage ranges, current population per band, base rate, calibration
currentness, and a plain-language warning that probabilities are absolute and
close together. Historical v1/v2 results retain their recorded semantics.

**Migration/contract changes:** Add—not mutate—a v3 selection contract, schema
constraints, request/response discriminators, canonical hashing, preflight
identity, result membership lineage, export metadata, cache identity, and exact
boundary tests. Existing v2 thresholds remain unchanged.

**Demo implications:** Globally, evidence-derived lower bands can contain more
than 10,000 rows; for example, `>=6.7%` contains 94,841. This does not prove that
the exact demographic intersections of the 20 scenarios qualify.

**10K feasibility without widening:** Potentially, but not yet proven. After
business approval of exact bands, every unchanged scenario must pass exact
current preflight. No band may be selected merely to force a demo count.

**Next implementation path if approved:** Prompt 14B.

### Option C — introduce versioned percentile/top-X% selection

**Semantics:** Select relatively by rank while continuing to display the
calibrated absolute purchase probability. The contract must explicitly choose
one of two meanings:

1. **Global percentile:** rank across the full five-million-person generation,
   then intersect with demographic criteria.
2. **Within-criteria percentile:** apply the approved demographic criteria first,
   then select the top X% of that exact eligible pool.

These meanings are not interchangeable and need distinct contract identifiers.

**Risks:** Percentile is not probability. A top-ranked customer may still have
only about a 6.7% calibrated probability. Global percentiles can yield small or
zero intersections. Within-criteria percentile changes the comparison population
per search and needs careful deterministic tie-breaking, cache identity, and
business explanation.

**Required UI changes:** Say “Top X% by model rank,” state whether ranking is
global or within the selected audience, show both selected count and calibrated
probability range, and never use probability language for percentile membership.

**Migration/contract changes:** Add a v3 discriminator, percentile scope,
percentage value, deterministic ordering/tie policy, canonical request hash,
preflight/materialization parity, immutable snapshot lineage, exports, and
backward-compatible result rendering.

**Demo implications:** Global top 0.2% contains exactly 10,000 before filters and
therefore cannot guarantee 10,000 after filtering. For within-criteria ranking,
the smallest current scenario pool is 74,514; top 15% would deterministically
select at least 11,177 from each current pool before any separate contactability
constraints. That is a materially different business policy and requires
explicit approval.

**10K feasibility without widening:** Global percentile: conditional and likely
insufficient for narrower scenarios unless a broader approved percentile is
used. Within-criteria percentile: mathematically feasible for the currently
recorded demographic pools at 15% or greater, but exact preflight remains
mandatory and the policy must not be chosen solely to satisfy the demo.

**Next implementation path if approved:** Prompt 14B.

### Option D — introduce versioned lift/risk bands

**Semantics:** Select business-readable tiers based on independently validated
expected response rate or lift relative to the outcome base rate, while also
showing absolute calibrated probability.

**Risks:** Current evidence does not support this option. The historical decile
curve is non-monotonic, lift is modest, confidence intervals are wide in the
highest slices, and the evaluation violates the Prompt 11 isolation contract.
Calling current ranks “high lift” or “high risk” would overstate evidence.

**Required UI changes:** If later justified, display the reference base rate,
expected response interval, lift definition, evaluation period/sample size,
confidence or uncertainty, and currentness. Do not show a band when validation
is stale or insufficient.

**Migration/contract changes:** A future v3/v4 contract would need versioned band
definitions tied to a governed evaluation artifact, sample-size/uncertainty
floors, monotonicity requirements, lineage and expiry, preflight parity, and
immutable result metadata.

**Demo implications:** NO-GO today. A new leakage-safe prospective evaluation
or independently groupable dataset is required before such bands can be
published.

**10K feasibility without widening:** Unknown and not currently supportable.
Counts may be calculated only after statistically valid bands are approved.

**Next implementation path if later approved with valid evidence:** Prompt 14B.

## Decision required from the operator

Choose one of the following; this document does not choose for you:

- Approve **Option A** and run
  `14A_KEEP_ABSOLUTE_PROBABILITY_MODEL_IMPROVEMENT_PATH.md`.
- Explicitly approve a new versioned contract under **Option B or C** (or a
  future statistically justified Option D), including exact semantics and
  boundaries/scope, then run
  `14B_VERSIONED_SELECTION_CONTRACT_V3_IF_APPROVED.md`.

Until that decision is recorded, the zero-customer condition remains an honest
policy/data blocker and the implementation must not proceed to either 14A or
14B automatically.

## Verification record

Read-only canonical diagnostics covered:

- database/schema, promoted artifact, generation, import, and attestation
  lineage;
- five-million-row minimum, maximum, mean, exact quantiles, threshold counts,
  bucket counts, and top-percentile boundaries;
- reconstruction of the historical cohort and the artifact-2 calibration fit
  and evaluation populations;
- uniform and equal-frequency reliability data;
- ROC-AUC, average precision, precision intervals, and lift reproduction; and
- the sigmoid's reachable probability range over its valid raw-score domain.

Focused unchanged-contract command:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_preflight_materialization_parity.py::test_preflight_cache_key_changes_for_every_semantic_identity_component \
  tests/test_search_recovery_calibration_feedback.py::test_published_calibration_has_exact_bucket_boundaries_and_attestation
```

Result: `2 passed in 26.49s`.

A broader parity command was also attempted:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_preflight_materialization_parity.py \
  tests/test_search_recovery_calibration_feedback.py::test_published_calibration_has_exact_bucket_boundaries_and_attestation
```

Result: `2 passed, 15 setup errors in 52.99s`. All 15 errors shared the same
fixture precondition: `verified_generation_source` expected Phase 10 status
`READY`, while current Prompt 11 governance correctly returned `BLOCKED`
because the fixture cannot form a leakage-safe grouped split. No parity
assertion failed. This is a known fail-closed data/governance blocker, not a
Prompt 13 code regression; Prompt 13 changed no runtime implementation.
