# Step 11 — Advanced Technical Details & Progressive Disclosure

## Objective
Keep full auditability without overwhelming normal business users.

## Default view
Hide technical implementation identifiers.

## “Why these people?”
Business explanation:
- selected campaign context
- selected targeting preferences
- match-strength meaning
- target-group size
- current/up-to-date status

## “View technical details”
Expandable panel may show:
- targeting/scoring run
- source analysis
- model run
- selected candidate
- feature contract version
- model policy
- source checksums/currentness
- artifact SHA
- audience filter hash
- saved audience ID
- Phase 9 contract versions

## Advanced navigation
Retain:
- Historical Analysis
- Model Training & Prospect Scoring
- Audience Explorer

Label as analyst/advanced tools.

Do not remove any Phase 1–8 capability.

## Role-neutral design
No authentication/RBAC is required for this POC unless already present.
Use UX separation only; do not invent security guarantees.

## Tests
Verify:
- default business path contains no required technical jargon
- technical detail is accessible
- provenance values match backend
- no PII leaks into technical detail

Create:
`docs/evidence/phase9/11_PROGRESSIVE_DISCLOSURE_REPORT.md`

STOP.
