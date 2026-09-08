# Step 8 — System Browser: Campaign Builder & Both Export Profiles

Enter Campaign Builder via normal navigation and also test the `Use in Campaign Builder` handoff.

Exercise every current Campaign control:
- saved audience selector
- campaign name
- description
- channel
- planned launch date
- Next
- Back
- review
- edit/back-to-details
- create/save draft
- draft update
- finalize
- PII acknowledgement
- export
- export history refresh
- campaign list/detail
- retry/refresh/status controls

Validation:
- blank campaign name
- missing audience
- required channel/state
- back/forward value preservation
- finalized immutability

## EMAIL
Create a new EMAIL campaign through browser:
draft → review → finalize → acknowledge PII → export.

Capture system-browser download.

Verify:
- exact EMAIL_CONTACT_V1 columns/order
- selected/deliverable/undeliverable counts
- rows=deliverable
- deterministic person order
- CSV SHA equals export audit
- no prohibited fields

## DIRECT_MAIL
Create a new DIRECT_MAIL campaign and repeat full lifecycle.

Verify exact DIRECT_MAIL_CONTACT_V1, address deliverability, reconciliation, checksum and prohibited-field exclusion.

Verify long-running export status remains trackable beyond 120 seconds if needed.

Update all Campaign control statuses.

Create `docs/evidence/phase8/08_SYSTEM_BROWSER_CAMPAIGN_EXPORT_REPORT.md`.

STOP.
