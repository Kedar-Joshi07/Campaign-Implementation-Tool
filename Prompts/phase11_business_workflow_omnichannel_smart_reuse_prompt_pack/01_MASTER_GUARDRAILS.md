# Phase 11 Master Guardrails

Baseline: `881b5a652e869af1415547de452b9cccd2c18293`

- Preserve every frozen Phase 1–10 analytical/currentness/privacy contract.
- Do not rewrite Historical Analysis, PU training, scoring, ranking, Phase 9 targeting,
  or Phase 10 compatibility/orchestration unless a proven bug requires it.
- Normal users see only Home, Find Potential Customers, Results.
- Hide legacy UI; do not delete it and do not claim hiding is security.
- Do not implement auth/RBAC in Phase 11; leave a clean future role-gating seam.
- Never precompute the Cartesian product of all targeting options.
- Reuse order: exact result → Phase 10 intelligence → new Phase 10 build.
- Delivery profile and prospect filters do not alter Phase 10 Modeling Context.
- Every user submission creates an immutable search-run record, even when result snapshot is reused.
- Result snapshots contain analytical identity only, never name/email/phone/address.
- PII is joined only during governed channel-specific export/download.
- Use profile-specific field allowlists; do not globally permit phone/email.
- Do not assume phone/email presence implies consent/contactability.
- Do not invent push tokens, advertising IDs or visitor IDs during export.
- No customer_id↔person_id linkage.
- Exact result cache is invalid after generation/source/model/currentness/contract drift.
- Atomic-segment indexing is optional and benchmark-gated.
- Paid-media hashes are pseudonymous, not anonymized.
- No direct campaign activation/send integration in this phase; downloads remain governed files.
- Preserve export checksums, counts, currentness, audit and CSV formula-injection mitigation.
- Final certification must prove filter/profile changes avoid 5M rescoring and a genuinely new
  Modeling Context can still trigger a correct full 5M build.
