# Step 9 — Recommendations & Match-Strength Comparison

## Objective
Help a business user choose targeting strictness without understanding percentiles or scoring mathematics.

## Comparison panel
For the current criteria and READY targeting source, compute exact counts for:

- Very Strong Match — 0.90+
- Strong Match — 0.80+
- Good Match — 0.70+
- Broad Match — 0.60+

Display:
- exact matching count
- % of available population
- optionally change vs current selection

## Recommendation
Provide a deterministic recommendation rule.

Do not use vague AI-generated advice.

Recommended baseline:
- Prefer STRONG when it produces a non-empty, practically usable population.
- If STRONG is empty/too small under a documented configurable minimum, recommend GOOD.
- If VERY_STRONG already provides a sufficiently large target group, it may be recommended for higher selectivity.
- If all thresholds are too small, say so clearly rather than lowering standards silently.

The exact rule and thresholds must be versioned/configurable and documented.

## Business copy
Use language such as:
- “Narrower”
- “Recommended”
- “Broader”
- “More selective”
- “Larger target group”

Avoid:
- precision/recall
- classifier threshold
- ROC/AUC
- calibration
- posterior probability

## Accuracy
All displayed counts must come from exact existing Audience estimate logic.
No sampling.

## Disclaimer
“Higher match strength means greater similarity under the current targeting intelligence; it does not guarantee a purchase or response.”

Create:
`docs/evidence/phase9/09_MATCH_STRENGTH_RECOMMENDATION_REPORT.md`

STOP.
