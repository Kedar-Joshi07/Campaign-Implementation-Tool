# Step 10 — Real 5M Phase 7 End-to-End Validation

Use current canonical 5M DB. No regeneration/retrain/rescore.

Test current saved audiences for:
small TOP_N ~1k
medium TOP_N 50k
large/top-decile if practical
demographic ALL_MATCHING
stale audience negative case

EMAIL E2E:
draft -> finalize -> export -> exact columns -> deliverability counts -> checksum ->
no forbidden fields -> no duplicate person_id.

DIRECT_MAIL: same.

Reproducibility with unchanged sources:
selected order/count identical
deliverable count identical
CSV checksum identical if no volatile timestamp inside CSV.

On DB copy simulate source drift:
campaign remains historical, currentness false, export blocked.

Capture exact timings/throughput but do not reject correct heavy work merely for 60–180 sec.
Investigate unnecessary repeated work only.

Browser E2E:
Audience Explorer -> saved audience -> Use in Campaign -> Builder -> draft -> review ->
finalize -> privacy confirmation -> download -> export history.

Create `docs/evidence/phase7_real_5m_acceptance.json`. STOP.
