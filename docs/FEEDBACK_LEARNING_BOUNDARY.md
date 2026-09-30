# Feedback learning boundary

## What the current automatic path does

The governed feedback path performs **recalibration**. It validates attributed-
purchase outcomes against immutable search-result membership, reuses the raw
scores from one existing completed scoring run, fits sigmoid and isotonic
calibration candidates, evaluates them on a separate grouped feedback holdout,
and may publish a new calibration artifact when non-regression gates pass.

Recalibration does not change model features, coefficients, preprocessing, raw
scores, ranks, or the model run. It creates no `model_runs` row and is not model
retraining or reinforcement learning.

## What true model learning would require

True feedback-driven retraining is intentionally not implemented. A future
version must be separately authorized and versioned, and must complete all of
the following as one governed workflow:

1. construct a deduplicated, leakage-controlled training dataset from validated
   feedback and the frozen feature contract;
2. create a new immutable `model_runs` row rather than modifying an incumbent;
3. preserve campaign/group train, validation, calibration-fit, and final-
   evaluation boundaries;
4. train and evaluate a challenger against the incumbent under the frozen model
   role and integrity policies;
5. reject non-finite metrics and require approved improvement/non-regression
   gates;
6. rescore the current demographic universe under the new model;
7. publish new scoring and Phase 10 generation lineage with current source,
   model, schema, artifact, and verification checksums;
8. leave the incumbent generation active unless explicit promotion succeeds;
9. preserve every input batch, decision, rejected challenger, and promotion
   record without rewriting historical artifacts.

Until that workflow exists, UI, API, worker logs, and business documentation
must describe the automatic feedback behavior only as recalibration.

## Drift boundary

PSI is calculated only when a promoted recalibration reference window and a new
window share the exact selection-basis hash: scoring run, generation,
calibration artifact, selection contract, propensity/match choice, selection
mode/count, targeting-criteria hash, and filter-branch hash. Feedback-selected
customers are never compared with the full demographic universe.

When no comparable reference exists, PSI is recorded as unavailable and cannot
trigger recalibration. The governed new-label ratio remains an independent
trigger after the minimum label, class, and distinct-run floors are satisfied.
