# Step 7 — Campaign Builder Multi-Step UI

Create 4 steps:

## 1 Choose Audience
Only current eligible saved audiences.
Show name/id, selected count, selection mode, scoring/model run, currentness, created
date, bounded top traits. No contact PII.

## 2 Campaign Details
- campaign name required
- description optional
- channel required: EMAIL or DIRECT_MAIL
- planned launch date optional/informational

## 3 Review
Show campaign details, immutable audience definition summary, exact resolved count,
score/rank context, source/model currentness, export profile, privacy warning, and
immutable-after-finalize warning.

## 4 Finalize / Export
- Finalize Campaign
- Export Target List

Export disabled until finalized/current.

DRAFT is editable.
FINALIZED is immutable.
If stale later: historical/read-only; export blocked.

No raw PII preview.
Use accessible stepper, inline field errors and top error summary. STOP.
