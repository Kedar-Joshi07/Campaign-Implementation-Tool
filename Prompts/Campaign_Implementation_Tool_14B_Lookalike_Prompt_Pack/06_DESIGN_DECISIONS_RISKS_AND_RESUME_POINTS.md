# Design decisions, risks, and resume points

Approved scope: additive product-aware look-alike v3 for the POC, with purchase probability retained. This pack specifies a baseline metric; it does not assert that it is optimal or that canonical scenarios qualify.

| Choice or issue | Decision and consequence | Owner |
|---|---|---|
| Score type | Learned buyer profiles and explicit mixed-feature distance | 03 |
| Meaning of 90 | Similarity distance <= .10; not probability or percentile | 01/06 |
| Thresholds | v3 cumulative minimum; v2 discrete bands remain frozen | 05 |
| Multiple products | ANY/max over separate profiles; tie by product_id | 02/04 |
| Missing features | Full-denominator penalty; coverage floor .80 | 03 |
| Support floors | 200 buyers, 160 fit, 40 holdout; POC policy | 02 |
| Calibration blocker | Remains in v2; separate similarity resolver | 05 |
| Method quality | Supported profiles and declared weights; no causal claim | 03/08 |
| Buyer specificity | Resemblance may be shared by many nonbuyers | 08 |
| Product coverage | 48 catalog; 36 observed; some below buyer support floor | 02 |
| Example products | Exact Headphones/Mobile Phone absent; separate fixture | 06/18 |
| Audience criteria | Do not refit or renormalize the score on filters | 05 |
| Resource fanout | Reuse profiles; measure per-product score cost | 04/16 |
| Canonical database | Not present during prompt creation; old DB metrics not rerun | 00/16 |
| Common context | Recorded manifest required; no guessed replacement | 16/17 |
| Old scenario minimum 101 | Historical metadata; current 10K gate applies | 17 |
| Twenty scenarios | Explicit translation and measured qualification | 17 |
| Feedback learning | Record origins; do not claim automatic profile retraining | 07/18 |
| Governance | Read branch protection/manual workflow at final candidate | 19 |
| External actions | No campaign sending; commits/push require session authority | 19 |

A future generator or taxonomy change needs a separately versioned dataset, clear business reason, seeds, support/coverage checks and preserved previous lineage. Do not regenerate history to force 90 scores or 10K results. Regeneration is outside this pack's default implementation.

If this score method is unsuitable, report the quality issue and propose a versioned replacement. Do not silently change weights or scales to make the demo qualify. A changed method identity requires new dependent artifacts.

Implementation choices such as module names, chunk size within measured budgets, and which existing reusable seam to extend do not require another business approval. If a genuinely missing common-context manifest blocks scenario work, identify that one missing input while continuing independent work.
