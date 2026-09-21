# Step 6 — Result Snapshot & Omnichannel Export Runtime Wiring

Verify the real runtime passes the same production dependencies used by certification:
- ResultSnapshotMaterializer
- project root
- current DB
- current Phase10 services

Run a completed search through the real runtime and validate:
- snapshot artifact exists;
- manifest exists;
- checksum validates;
- exact row count;
- no contact PII;
- Results API sees it.

Then validate all available omnichannel downloads through normal app routes:
EMAIL, DIRECT_MAIL, SMS, WHATSAPP, TELEMARKETING,
PAID_SOCIAL, PAID_SEARCH, MOBILE_PUSH, DISPLAY, WEBSITE_ONSITE.

For each:
- availability truthfulness
- currentness validation
- selected = deliverable + undeliverable
- row_count = deliverable
- checksum
- export event audit
- paid media raw PII absent
- formula-injection handling

Do not modify profile contracts unless a real bug is found.

Create:
`docs/evidence/phase11_runtime_closure/06_SNAPSHOT_EXPORT_RUNTIME.md`

STOP.
