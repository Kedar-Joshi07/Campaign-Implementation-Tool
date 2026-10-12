# Approved v3 buyer-similarity decision addendum

Date: 2026-10-05
Trusted implementation baseline: `336875c30fc32b00323d916ecc45b232016168a1`

## Decision

The operator has approved an additive product-aware look-alike workflow for
this POC. The new workflow will learn supported demographic buyer profiles from
historical customers and attributed product sales, score the independent
prospect population for resemblance to those profiles, apply the campaign's
strict audience criteria, and select prospects meeting an explicit minimum
similarity score.

This decision supersedes the *choice* of the older conditional Prompt 14B
percentile/lower-probability alternatives. It does not rewrite or invalidate
the evidence that led to that decision. The original Prompt 13 record remains
unchanged at
[`13_SELECTION_POLICY_DECISION.md`](../recovery_hardening/13_SELECTION_POLICY_DECISION.md).

## Exact score meaning

The approved v3 contract is separate from purchase probability:

- Selection contract version: `3`.
- Score semantics: `PRODUCT_BUYER_SIMILARITY`.
- Score method: `BUYER_PROFILE_DISTANCE_V1`.
- Membership contract version: `3`.
- Product policy: `ANY_SELECTED_PRODUCT_MAX_V1`.
- Allowed minimums: `0.50`, `0.60`, `0.70`, `0.80`, and `0.90`.
- Selection predicate: `buyer_similarity_score >= similarity_minimum`.
- New-business-UI minimum after certification: `0.70`.

A score of `0.90` means that the weighted distance to the nearest supported
learned buyer prototype is at most `0.10` under the declared method. It does
not mean 90% purchase probability, 90% accuracy, confidence, validated lift,
or a 90th percentile.

V3 minimums are cumulative. A minimum of `0.80` includes valid scores from
`0.80` through `1.00`. This intentionally differs from v2 bucket `0.80`, which
continues to mean `[0.80, 0.90)` calibrated purchase probability.

## Preserved probability capability

Existing v1 and v2 behavior remains authoritative for historical and explicit
probability-mode callers:

- unversioned search submission retains its pinned v1 behavior;
- v2 remains absolute calibrated purchase probability with discrete buckets;
- `BROAD` continues to translate to v2 bucket `0.60`;
- explicit v2 bucket `0.50` remains `[0.50, 0.60)`;
- the v2 default remains `0.70`;
- the demo qualification minimum remains `10,000`;
- historical models, calibrations, results, exports, feedback lineage, and
  their limitations remain readable and are not converted to v3.

No threshold, scenario, product, filter, generated source, outcome, or evidence
is changed to force a result count. Predictive response/lift validation remains
unavailable until independently governed outcome evidence supports it.

## Implementation boundary

This addendum authorizes the staged implementation described by the approved
14B prompt pack. It is not itself evidence that v3 profiles have been trained,
that five million prospects have been scored, that the twenty scenarios
qualify, or that release certification has passed. Those are separate gates.

Stage-00 baseline evidence is recorded in
[`00_BASELINE.md`](00_BASELINE.md) and [`00_BASELINE.json`](00_BASELINE.json).
