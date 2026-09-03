# Step 11 — EMAIL Export Through Browser

Trigger export only through Campaign Builder UI and capture download with Playwright.

Validate:
- safe filename
- exact EMAIL_CONTACT_V1 headers
- selected/deliverable/undeliverable counts
- rows = deliverable
- deterministic member order
- CSV SHA matches persisted export event
- every exported row has deliverable email
- no prohibited fields

Verify completed export history/status in UI.

Do not call export API directly to create the download. STOP.
