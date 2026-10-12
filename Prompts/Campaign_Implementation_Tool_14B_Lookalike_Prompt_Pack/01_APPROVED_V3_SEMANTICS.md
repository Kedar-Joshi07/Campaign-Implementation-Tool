# V3 semantics and reference methodology

## Business contract

Selection version `3`; score semantics `PRODUCT_BUYER_SIMILARITY`; score-method version `BUYER_PROFILE_DISTANCE_V1`; membership version `3` (validate availability before allocation).

- Shared feature vocabulary: the existing 11 prospect-compatible demographic features. Preserve its raw validation contract and add a distinct similarity preprocessing/method contract. Exclude IDs, PII, campaign responses, purchase results, and prospect-unavailable fields from scoring inputs.
- Sales provide evidence of relevant historical buyer membership. For V1 of this method, use the existing `ATTRIBUTED_PURCHASE` definition, not all purchase rows interchangeably. Distinct buyer per product/context; repeat sales never multiply demographic weight. Context filters and historical window are explicit. Campaign delivery/export channel is separate from historical channel context.
- Product selection is `ANY_SELECTED_PRODUCT_MAX_V1`: fit separate profiles for each selected product; use the maximum valid product score, deduplicate people, retain the winning product. A selected product lacking eligible history blocks the context with a safe reason; do not silently drop it or broaden to a category. Equal winning-product scores use product_id ascending. ALL-products matching is out of scope and cannot be inferred.
- Audience filters are hard requirements. Apply the normalized AND/OR branches exactly; OR deduplicates by person_id. Do not train a new model on the marketer's narrow prospect filters. A filter changes eligibility, not the score for the same person under the same product/model context.
- Allowed minimums: 0.50, 0.60, 0.70, 0.80, 0.90. New UI default 0.70. Predicate is `score >= minimum`, inclusive; never an exclusive bucket. Tier labels are display-only: 90–100 Very Strong, 80–<90 Strong, 70–<80 Good, 60–<70 Broad, 50–<60 Exploratory. Each minimum includes all higher tiers.
- `ALL_MATCHING` is the normal v3 workflow. Explicit `TOP_N` remains separate if supported: score descending, person_id ascending; selected count=min(qualified,N), not qualified count. Preserve native stable person_id collation and pin it in the contract. All scores equal means all qualify or none by the threshold, not an arbitrary top percentile.

## Defined baseline score — learned profiles, declared distance

The baseline is a descriptive mixed-feature buyer-profile model. It learns multiple supported prototypes from actual historical buyer features, rather than matching the user's filter values or rescaling a purchase model. Distance is transparent policy; profiles are learned data. Do not claim that feature weights were learned when they are equal.

For feature j with normalized weight w_j=1/11:

- Numeric: d_j(x,c)=min(1, abs(x_j-c_j)/r_j). Learn r_j=q95-q05 on fit buyers only, without clipping inference values to those quantiles. Positive fallback scale: age 1 year; income 1 currency unit; family count 1 member when the fitted range is zero. Preserve raw validation limits. These fallback constants are not fitted parameters.
- Categorical: d_j=0 for an exact canonical match to the prototype mode, otherwise 1. Treat education as categorical here; education “Bachelor and above” is an explicit filter expansion, not an arbitrary numeric ordering in distance.
- Missing/unknown on either side contributes d_j=1, including missing–missing, with the fixed full denominator. Never drop missing features to inflate the score. Track feature coverage separately.
- Prototype distance D(x,c)=sum(w_j*d_j). Product score S_p(x)=1-min_c D(x,c), over retained supported prototypes. A score 0.90 means the minimum weighted distance is at most 0.10 under this method. It is a similarity index scaled to 0–100, not an empirically calibrated percentage of matching attributes.
- Coverage=sum(w_j for observed and known input features); coverage below 0.80 gives no valid score and `INSUFFICIENT_FEATURE_COVERAGE`. No NaN/infinite scores. All invalid values remain separately counted. Unknown categories cannot earn match credit. Preserve numeric-only out-of-range penalties; no clipping to prototype values.

Use deterministic mixed-type prototype learning with bounded storage: numeric medians, categorical modes, nearest-distance assignment, deterministic tie rules. Initial candidate k values are 1,2,4,8,16; fixed seed 20261005; maximum 50 iterations; convergence when assignments stop changing. Fit only on historical fit buyers. Deterministic initialization uses a seeded first row in sorted customer order, then farthest-first rows by this same distance; ties by internal customer identity. Initial scales come from fit buyers. Do not serialize customer IDs as prototypes.

Select the largest candidate k whose final clusters all have support >=max(30,ceil(0.02*n_fit)); do not tune k using held-out scores or campaign count targets. Empty/undersupported clusters invalidate that candidate, rather than becoming singleton anchors. Persist realized k, iteration limit/convergence, cluster support, prototype tie order, scales, and training parameters. No surviving candidate or nonconvergence is an explicit data/model issue. Implement efficiently with chunked assignment, not full pairwise buyer or 5M distance matrices. A different algorithm requires a documented new method contract, not a quiet substitution.

## Support and assurance policy

V1 descriptive minimum: 200 distinct attributed buyers per product after context filtering; 80/20 deterministic customer-disjoint fit/holdout, with >=160 fit and >=40 holdout buyers. These are POC engineering floors, not proof of market effectiveness. Split each customer consistently across every product using the same seeded identity-hash ordering. Persist exact sets/hashes privately in permitted lineage and public bounded counts. No customer enters training for one product and holdout for another in a composite evaluation.

Learn preprocessing and profiles only on fit customers. With multiple products, split the union first; fail a product if its realized fit/holdout support falls below floors. Holdout assesses descriptive coverage/stability, not independent campaign purchase prediction. Customer-disjoint descriptive evaluation can run despite the historical campaign-connected component; that fact must be exposed. It must never be passed off as Prompt 11-governed probability calibration, campaign-isolated lift, or response validation. Existing v2 split policy remains frozen.

Descriptive assurance: finite bounded scores; declared feature coverage; reproducibility; profile support; row-identity isolation; holdout score/coverage distribution; sensitivity by feature; cluster support; bootstrap fit-profile stability; train/prospect distribution comparison. Report quality evidence without inventing acceptance based on target selection yield. Missing required identity/support/coverage/reproducibility is NO-GO. Weak buyer/nonbuyer separation is an explicit predictive limitation, not permission to stretch scores.

UI label: “Buyer Similarity: 90 and above (0–100 index)” or “Look-Alike Score: 90+”. Helper: “Measures resemblance to learned historical buyer profiles for the selected products under a defined demographic distance. It is not purchase probability or percentile.” If a percentage symbol is retained for continuity, always qualify it as a similarity index; never “90% likely”, “90% of buyers match”, “90% confidence”, or “90th percentile”.

## Separate purchase probability

Retain v2 discrete bounds, legacy reverse mapping, models, calibrated-score tables, feedback, evaluation, exports, and history. New v3 does not depend on promoted purchase calibration. Optional probability may be shown only from an independently valid, explicitly associated lineage/currentness, with its own status. Absence/staleness must not become zero, current, or a reason to block otherwise valid similarity. Recalibrating v2 does not invalidate a probability-independent similarity generation. Changing its buyer source/profile does.
