# Step 4 — Model Training UI

## Objective
Enable Model Training navigation and make Phase 3 training usable end to end through HTML/CSS/Vanilla JS.

## Navigation
Enable `Model Training`.
Keep `Audience Explorer` and `Campaigns` disabled.

## Required page sections
### 1. Source Analysis
Select a completed analysis and show analysis name/id, conversion definition, date range, selected customers, positives, unlabeled.

### 2. Training Configuration
Fields:
```text
Model Name
Random Seed
Validation Fraction
Run Elkan-Noto Challenger
```
Defaults 42, 20%, true.

Display fixed governance cards:
```text
PRIMARY
PU Bagging + Logistic Regression

CHALLENGER 1
Elkan-Noto + Logistic Regression

DIAGNOSTIC CONTROL
Naive Logistic Regression
```
No algorithm picker. Bagging cannot be disabled.

CTA: `Train Look-alike Model`.

### 3. Active Job / Progress
Show status, progress bar, stage, safe message, job ID, source analysis, timestamps/elapsed time. Poll job endpoint every ~1–2 seconds and stop on COMPLETED/FAILED.

### 4. Completed Model Summary
Show model_run_id, source analysis, selected PRIMARY, cohort counts, transformed feature count, top-10 lift/recall, quality flags, artifact verification.

### 5. Candidate Comparison
Table/card columns:
```text
PRIMARY Bagging
CHALLENGER Elkan
DIAGNOSTIC Naive
```
Rows:
- status;
- recall @5/10/20;
- lift @5/10/20;
- observed-label ROC-AUC;
- observed-label AP;
- KS;
- fit time.

Clearly mark Naive as diagnostic-only and non-selection-eligible.

### 6. Challenger advisory
If `CHALLENGER_OUTPERFORMED_PRIMARY`, show:
> Challenger exceeded the primary on one or more validation diagnostics. The governed primary remains selected under policy v2.

### 7. Recent Model Runs
Show run ID, name, analysis, status, selected model, timestamps, top-10 lift, quality. Click to load detail.

## States
Support loading, no analyses, ready, submitting, queued, running, completed, failed, API error, retry.
Disable submit while active training exists.

## Metric help
Explain:
- Unlabeled is not confirmed negative.
- observed-label ROC-AUC/AP are diagnostics.
- lift measures enrichment in the highest-ranked slice.
- model score is not guaranteed calibrated purchase probability.

## JS
Use existing API utility and a dedicated model-training module. Avoid inline event spaghetti. No hardcoded result values.

## Frontend tests
Model Training enabled, later pages disabled, correct endpoints, active-job disable, polling terminal stop, failure rendering, challenger advisory, diagnostic label, no person/prospect table, no scoring controls.

## Exit
Browser can launch and inspect a governed training run end to end.
