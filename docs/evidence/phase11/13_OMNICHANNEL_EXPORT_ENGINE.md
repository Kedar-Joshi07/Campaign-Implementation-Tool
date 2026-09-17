# Phase 11 Step 13 — Omnichannel Download / Export Engine

## Outcome

Step 13 is implemented. A completed, current business-search result can now be
downloaded through its immutable saved export profile at:

`GET /api/potential-customer-search/runs/{search_run_id}/download`

The endpoint resolves analytical membership only from the immutable Step 11
snapshot, joins current governed demographic contact/activation fields at
download time, applies the backend-owned profile contract, and streams UTF-8
RFC 4180 CSV. It does not create or persist a contact-PII result snapshot.

## Layering and activation

Implementation:

- `app/services/phase11_export_service.py` — preflight, currentness, bounded
  membership/contact join, profile projection, CSV stream, checksum, and audit;
- `app/routers/potential_customer_search.py` — additive download endpoint and
  safe 404/409/422/500 mapping;
- `app/services/phase11_results_service.py` — download eligibility activated
  only for completed results with a current snapshot, READY reusable generation,
  and matching current demographic import identity;
- `tests/test_phase11_omnichannel_export_engine.py` — ten-profile, privacy,
  streaming, audit, API, and edge-case matrix.

The saved run owns the selected profile. A caller cannot substitute a different
profile at download time. The engine verifies that the stored delivery channel
and profile still match the immutable backend registry.

## Currentness and source validation

Before any audit row or response byte is created, the engine verifies:

1. the run exists and is `COMPLETED`;
2. the run references the expected immutable snapshot and READY generation;
3. the physical compressed membership file and manifest pass the Step 11
   validator;
4. snapshot metadata, selection, criteria/branch hashes, generation, checksum,
   count, and currentness match;
5. the profile's required identifier and contactability columns exist in the
   actual demographics schema;
6. the latest completed demographics import ID and checksum exactly match the
   generation's governed demographic source;
7. selected count equals the snapshot/run count and reconciles with the
   deliverable and undeliverable counts.

The demographic source identity is checked again inside the streaming read
transaction and after streaming. The compressed membership checksum is also
checked after streaming. Source or snapshot drift fails the audit and marks the
snapshot stale rather than claiming a current export.

Result history/detail currentness now also compares the generation's
demographic import ID/checksum to the latest governed demographics import, so a
stale-source result does not advertise an eligible download.

## Bounded streaming design

The export uses a bounded two-pass process:

1. validate and scan membership in 250-person chunks to calculate exact
   deliverability counts;
2. create the `RUNNING` aggregate audit row with reconciled immutable counts;
3. scan the snapshot again in the same bounded chunks, selecting only the
   source columns required by that profile and streaming rows directly.

The first pass is necessary because the Step 5 audit contract makes selected,
deliverable, and undeliverable counts immutable. It avoids storing a whole
result list while ensuring an aborted export still has truthful terminal
deliverability counts. No population-sized Python collection, SQL `IN` list, or
server-side PII file is created.

Disconnect checks occur before output and at each bounded chunk. Explicit
disconnects, task cancellation, and consumer closure record `ABORTED`; stream
or currentness failures record `FAILED`; successful exhaustion records
`COMPLETED`.

Application startup also reconciles at most 100 aggregate `RUNNING` result
export audits older than one hour to `ABORTED`. Recovery changes only status,
completion time, currentness, and the fixed safe message; immutable lineage and
reconciled counts remain unchanged, and no contact rows are involved.

## Profile behavior

All ten profiles are enabled because Step 4 added and validated their canonical
schema/importer fields. Runtime availability remains fail-closed if those
fields are absent.

| Profile | Governed output behavior |
|---|---|
| `EMAIL_CONTACT_V1` | valid normalized lowercase email and email-contactable rows; names retained |
| `DIRECT_MAIL_CONTACT_V1` | contactable rows with required postal fields; names retained |
| `SMS_CONTACT_V1` | SMS-opted-in rows with normalized governed US phone; names retained |
| `WHATSAPP_CONTACT_V1` | WhatsApp-opted-in rows with normalized governed US phone; names retained |
| `TELEMARKETING_CONTACT_V1` | valid governed phone, contactable and not DNC; names retained |
| `PAID_SOCIAL_AUDIENCE_V1` | lowercase SHA-256 email and/or phone match keys only |
| `PAID_SEARCH_AUDIENCE_V1` | lowercase SHA-256 email and/or phone match keys only |
| `MOBILE_PUSH_CONTACT_V1` | existing push token with push opt-in |
| `DISPLAY_AUDIENCE_V1` | existing normalized advertising ID with targetability |
| `WEBSITE_AUDIENCE_V1` | existing website visitor ID with onsite targetability |

Paid-media files never contain raw email or phone. One valid approved identifier
is sufficient and the other hash may be blank. These hashes remain explicitly
pseudonymous, not anonymous.

Names are emitted only by the five profile contracts that require them. No
profile emits ethnicity, religion, occupation, family income, model-feature
demographics, consent flags, or unrelated channel identifiers.

## CSV and audit guarantees

The ordered CSV header is exactly each registry profile's `output_columns`.
Every text value is protected against leading-whitespace `=`, `+`, `-`, or `@`
formula injection. Python's CSV writer preserves commas, embedded quotes,
newlines, Unicode, and blanks under RFC 4180 quoting rules.

Each download persists aggregate metadata only:

- search run, snapshot, export contract, profile, and profile version;
- selected, deliverable, undeliverable, and emitted row counts;
- SHA-256 of the exact streamed header and rows;
- start/completion timestamps, status, currentness, and bounded safe failure.

The tested equations are:

`selected_count = deliverable_count + undeliverable_count`

`row_count = deliverable_count` for completed exports.

No raw file paths, SQL, stack traces, identifiers, or contact values are stored
in the audit table or returned through JSON error responses.

## Backward compatibility

The existing finalized-Campaign Email and Direct Mail export endpoint was not
rewritten. Its acknowledgement, currentness, streaming, audit, and response
contracts remain unchanged. Focused Campaign/API and CSV hardening regressions
passed alongside the new result-download engine.

## Validation

All Step 13 fixtures used four-person temporary SQLite databases and temporary
snapshot artifact roots. No canonical result was exported.

| Suite | Result |
|---|---:|
| All ten exact profile/header/privacy/checksum cases | 10 passed in 109.40s |
| Remaining API, CSV edge, availability, abort, drift, and boundedness cases | 7 passed, 10 deselected in 75.40s |
| Startup recovery and real download API recheck | 2 passed in 38.29s |
| Close/disconnect/source-drift terminal audit checks | 3 passed in 36.75s |
| Step 12 result projection plus Step 13 engine non-browser integration | 21 passed, 2 deselected in 59.55s |
| Profile, registry audit, legacy Campaign, Email/Direct Mail CSV regressions | 33 passed in 83.32s |
| Focused real download API response/status check | 1 passed in 12.69s |

Coverage includes every enabled profile, exact headers, deliverability and
undeliverability, normalized phone/email, one-or-both paid-media hashes,
push/display/website gating, formula prefixes, commas, quotes, embedded newline,
Unicode, blank/invalid identifiers, immutable source membership, source drift,
physical snapshot currentness, response filename/security headers, safe API
statuses, checksum equality, disconnect and consumer-close behavior,
and absence of a second PII-rich snapshot.

Python compilation and the additive OpenAPI path check passed.

## No-heavy-work and stop boundary

No canonical import, demographic regeneration, historical analysis, model
training, scoring, ranking, 5M filtering, full-size download, campaign
activation, or outbound send was run. No server was left running. Nothing was
staged, committed, pushed, or frozen.

`STOP_AFTER_STEP_13`

Step 14 and subsequent prompts have not been started.
