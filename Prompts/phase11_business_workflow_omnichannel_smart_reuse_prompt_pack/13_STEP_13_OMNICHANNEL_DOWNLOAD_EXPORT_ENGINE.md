# Step 13 — Omnichannel Download / Export Engine

## Objective
Download the selected result snapshot through the chosen governed profile without changing membership.

Input:
search_run_id / result_snapshot_id + selected export profile.

Resolve exact person IDs from immutable snapshot, then join current governed contact source at export time.

For every enabled profile:
- validate profile availability
- validate currentness/source
- validate required identifier/contactability
- classify deliverable vs undeliverable
- stream output
- avoid server-side whole-result list materialization
- formula-injection mitigation for CSV
- audit start/completion/failure
- compute checksum
- handle disconnect/abort
- never persist a second PII-rich result snapshot

EMAIL/DIRECT_MAIL behavior must remain backward compatible.

SMS/WhatsApp/Telemarketing:
- normalized governed phone in output
- only contactable rows

Paid Social/Paid Search:
- hashed normalized identifiers
- no raw contact columns
- support one or both identifier hashes
- exact header contract tested

Push/Display/Website:
enable only if Step4 identifiers/flags exist in canonical schema and importer.
If not enabled, UI/API return clear unavailable reason rather than fake file.

Deliverability equation:
selected_count = deliverable_count + undeliverable_count
row_count = deliverable_count.

Keep names only where profile contract needs them.
Do not expose ethnicity/religion/occupation/family income or other prohibited fields.

Add CSV edge-case tests:
=,+,-,@, comma, quote, newline, Unicode, blank/invalid identifiers.

Evidence:
`docs/evidence/phase11/13_OMNICHANNEL_EXPORT_ENGINE.md`

STOP.
