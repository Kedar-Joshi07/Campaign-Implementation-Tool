# Model Training UI Contract

## Goal
Expose the governed Phase 3 engine clearly without hiding PU semantics.

## Role cards
```text
PRIMARY
PU Bagging + Logistic Regression

CHALLENGER 1
Elkan-Noto + Logistic Regression

DIAGNOSTIC CONTROL
Naive Logistic Regression
```
Diagnostic control treats U as N only for comparison and cannot be selected.

## Page
1. Source Analysis
2. Governance
3. Configuration
4. Job Progress
5. Completed Result
6. Candidate Comparison
7. Challenger Advisory
8. Recent Models

## Comparison rows
- role/status;
- recall @5/10/20;
- lift @5/10/20;
- observed-label ROC-AUC;
- observed-label AP;
- KS;
- fit time.

## Quality flag explanations
At minimum support:
- OBSERVED_LABEL_METRICS_ONLY
- CHALLENGER_OUTPERFORMED_PRIMARY
- LOW_TOP10_LIFT
- LOW_SCORE_VARIANCE if surfaced from failed/legacy detail.

## UX constraints
- no full-page block while training;
- no reload needed;
- polling stops terminally;
- no fake success;
- no hardcoded metrics;
- no prospect/person/customer table;
- no scoring controls.

## Language
Use Known Positive, Unlabeled, Look-alike ranking, PU model. Do not call unlabeled true negative or interpret score as guaranteed purchase probability.
