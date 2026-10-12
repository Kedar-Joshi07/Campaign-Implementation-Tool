# Stage 14B_03 learned buyer profiles and score method

Recorded 2026-10-06 from `main` at starting/current HEAD
`336875c30fc32b00323d916ecc45b232016168a1`. The candidate remains
`UNCOMMITTED`. Stage 14B_02 was the preceding GO. This stage did not commit,
push, migrate the operator database, alter source data, score five million
prospects, or execute Stage 14B_04.

## Implemented contract

`BUYER_PROFILE_DISTANCE_V1` uses the 11 frozen shared demographic fields with
equal weight `1/11`. Numeric distance is
`min(1, abs(input - prototype) / (fit q95 - fit q05))`; a zero fitted range
uses the declared positive fallback of one year, currency unit, or family
member. Categorical distance is zero only for an exact known canonical match.
Missing or unknown values on either side receive distance one, including
missing-to-missing. Input coverage below 0.80 returns no score and
`INSUFFICIENT_FEATURE_COVERAGE`.

Product score is `1 - min(prototype distance)`. The same function produces the
distance, selected prototype, coverage, score, and all feature contributions.
A 0.90 score therefore means weighted distance no greater than 0.10 under this
specific method. It is not a purchase probability, empirical accuracy,
confidence, percentile, or a statement that 90 percent of attributes match.

Fit-only bounded clustering uses candidates 1, 2, 4, 8, and 16, seed
20261005, at most 50 assignment iterations, numeric medians, categorical modes,
lexical mode ties, and frozen prototype-order nearest ties. Initialization uses
one seeded row in sorted internal-customer order followed by farthest-first
rows under the same distance. The largest converged candidate whose every
cluster has support at least `max(30, ceil(0.02*n_fit))` wins. Empty,
undersupported, and nonconvergent candidates fail closed. Assignment is
chunked; there is no all-pairs buyer or prospect matrix.

The artifact is bounded canonical JSON under a fixed governed relative path.
It records all parameters, source/context/split identities, candidate
diagnostics, convergence, support, scales, vocabularies, method and library
versions. Atomic write, SHA-256 verification, exact schema/method validation,
size bounds, and expected-current-lineage checks reject unsafe, partial,
corrupt, incompatible, or stale artifacts. Prototype payloads contain no
customer IDs or contact PII, and no pickle or other executable serialization is
accepted.

The schema-32 profile registry now has a single repository owner for lifecycle
writes. Exact builds are claimed under a 64-character execution token; another
current owner cannot join or publish, an expired lease can be deliberately
recovered, and an old token cannot heartbeat, cancel, or publish. Claim and
publication both compare the profile lineage with the latest completed customer
and campaign-sales imports. The artifact file is reloaded and checksum-verified
before profile and artifact rows become `PUBLISHED` in one transaction. Exact
retries reuse that row; cancellation records bounded `CANCELLED`, and a source
replacement before publication records `STALE/SOURCE_REPLACED` without a
published artifact row.

## Independent score oracles

For one known 11-feature prototype and fixed ranges:

- exact fully observed match: `1.0`;
- one known categorical mismatch: `10/11 = 0.9090909...`;
- two known categorical mismatches: `9/11 = 0.8181818...`;
- one mismatch plus half of one numeric range: `1 - 1.5/11 = 0.8636363...`;
- every feature missing: invalid with zero coverage, never score one.

The tests also prove monotonic/saturated numeric distance, missing and unseen
category penalties, modal and nearest ties, four supported multimodal groups,
singleton rejection, row-order and chunk-size invariance, holdout/prospect
leakage exclusion, unrelated-product isolation, relevant-buyer sensitivity,
and exact-match-only score one.

## Bounded canonical evidence

The read-only audit built PRD001 for 2024-01-01 through 2025-12-31 using the
current customer and campaign-sales checksums. Its 160 FIT and 40 HOLDOUT buyers
produced two retained prototypes with supports 84 and 76; the selected k=2
candidate converged in four iterations. JSON written only to temporary storage
round-tripped with artifact SHA-256
`54574c212a5fa6af3a0f66a5ed534c6299058f99c13ddcbaaff4cada169e3c63`.
The identical cohort fitted with assignment chunks 7 and 31 produced identical
bytes and hashes; scoring chunks 3 and 17 also produced identical ordered
results. A disposable schema-32 registry transactionally published and then
reused the exact profile as one row. Temporary storage and registry were
removed.

All 40 customer-disjoint holdout buyers had valid descriptive scores: minimum
0.3423659695, maximum 0.8824953315, mean 0.6448864754, and zero exact prototype
matches. These are descriptive checks only. Holdout never influenced ranges,
vocabulary, initialization, prototypes, candidate validity, or k selection.

## Verification

- `pytest -q tests/test_buyer_similarity_profile_service.py` — 11 passed in
  33.66s.
- Affected v3/cohort/feature/migration/legacy regression — 82 passed in
  108.23s.
- `python scripts/validation/audit_14b_03_profile_method.py` — PASS against the
  canonical source in read-only mode.
- Ruff over all Stage 14B_03 Python files — all checks passed.

Acceptance A13 through A18 pass. A01 through A12 remain inherited from the
prior certified stages. Later rows were not run by this stage. V1/v2 request,
probability, calibration, artifact, result, and cache behavior was not changed.

## Decision and boundary

Decision: **GO**. Release classification: `SIMILARITY_DESCRIPTIVE_GO`.
Predictive classification: `PREDICTIVE_VALIDATION_UNAVAILABLE`.

Stage 14B_04 still owns runtime worker composition, five-million-row score
generations, score staging/resume, and generation attestations. No full-scale,
demo, UI, export, remote-CI, commit, push, merge, or deployment claim is made
here.
