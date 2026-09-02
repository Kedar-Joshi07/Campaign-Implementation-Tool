# Step 11 — Final Phase 7 Acceptance & Freeze

Run:
```powershell
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```
Run browser acceptance.

Revalidate Phase 1–6 unchanged:
Feature SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`, BAGGING_PU governance, source provenance, 5M scores,
100 boundaries, analytics snapshot, non-PII Audience Explorer, saved-audience immutability.

Phase 7 must prove:
schema v11 additive
no member table
DRAFT/FINALIZED
finalized immutable
current saved-audience eligibility
campaign currentness
exact deterministic resolver
EMAIL_CONTACT_V1
DIRECT_MAIL_CONTACT_V1
deliverability reconciliation
CSV injection hardening
no PII outside export stream
no persistent server CSV
aggregate-only export audit
stale export blocked
browser workflow
no activation/send integration

Commit:
`feat: complete phase7 campaign builder and target export`

Final report must include SHAs, schema/contracts, tables, absent member table, profiles,
allowed/prohibited fields, currentness, timings, checksums, reconciliation, stale test,
PII/logging scan, browser E2E, Phase 1–6 regression, all test gates, no data regeneration,
no retraining/rescoring, no real activation, and GO/CONDITIONAL GO/NO-GO.

Quality/data/process correctness outranks arbitrary timing. STOP.
