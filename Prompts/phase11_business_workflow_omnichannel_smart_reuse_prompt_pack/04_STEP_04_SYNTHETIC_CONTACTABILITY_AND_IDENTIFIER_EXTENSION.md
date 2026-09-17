# Step 4 — Deterministic Synthetic Contactability & Identifier Extension

## Objective
Add only the source fields required to truthfully support the expanded POC export profiles.

First audit whether current demographic generation can be extended without changing the frozen 11 model features.
New contactability/activation identifiers MUST NOT become model features.

Recommended deterministic demographic additions:
- email_contactable
- direct_mail_contactable
- sms_opt_in
- whatsapp_opt_in
- telemarketing_contactable or do_not_call
- push_token
- push_opt_in
- advertising_id
- advertising_targetable
- web_visitor_id
- onsite_targetable

Design realistic deterministic missingness/contactability rates and document them.
Do not use these new fields in historical PU training/scoring.

Update:
- generator header/output
- schema/importer
- validation rules
- reconciliation
- source summary
- deterministic generation tests
- canonical source documentation
- currentness/checksum behavior

Identifier rules:
- push_token deterministic synthetic opaque identifier
- advertising_id deterministic synthetic UUID-like identifier
- web_visitor_id deterministic synthetic opaque key
- identifiers nullable according to documented availability
- contactability flag cannot be true when required identifier is absent
- phone/email validation remains governed

Critical provenance rule:
This source change will change the demographic checksum and therefore invalidate prior Phase10 scoring for the new canonical source. That is expected.
Do NOT try to preserve old checksum by excluding new fields from provenance.

Because model features are unchanged:
- historical analysis can remain reusable;
- model can remain reusable if Phase10 compatibility permits;
- new canonical demographics require a new full scoring generation.

Regenerate canonical demographics deterministically and refresh LFS/hash documentation only after all tests pass.

Evidence:
`docs/evidence/phase11/04_CONTACTABILITY_IDENTIFIER_EXTENSION.md`

STOP.
