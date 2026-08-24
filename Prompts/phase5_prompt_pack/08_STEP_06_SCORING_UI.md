# Step 6 — Prospect Scoring UI

## Location

Extend existing Model Training workspace. Keep Audience Explorer and Campaigns disabled.

## Prospect Scoring panel

For loaded COMPLETED model show model run, primary, artifact verification, feature compatibility, demographic universe, scoring availability.

Eligible CTA: `Score Prospect Universe`.

If canonical completed scoring exists, display it and do not offer duplicate default scoring.

## Active job

Show job/status/stage/progress/message/elapsed. Poll `/api/jobs/{job_id}` every ~1.5–2s and stop on terminal state.

## Completion aggregate

Show scored prospects, reconciliation, min/mean/max score, total runtime, rows/sec, artifact/feature contract.

Required note: propensity scores are relative look-alike affinity scores, not guaranteed purchase probabilities.

## No individual data

No person IDs, names, locations, incomes, scores, filters, top-percent audiences, percentiles, bands, audience selection or export.

## Compute lock

Any active training/scoring heavy job disables both Train and Score CTAs.

## Tests

Panel/CTA/eligibility/already-completed/active cross-disable/polling/summary/disclaimer; Audience Explorer disabled; no person table; no bands/percentiles; no hardcoded 5M values.

STOP after Step 6.
