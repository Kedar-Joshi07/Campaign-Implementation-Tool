# Hardening Step 4 — Deliverability & CSV Security

Add explicit fixture tests.

## EMAIL
Test:
- valid email
- blank email
- malformed email

Require:
selected = deliverable + undeliverable
only deliverable rows exported
saved audience selected count remains unchanged

## DIRECT_MAIL
Test:
- valid address
- missing address_line_1
- missing city
- missing state
- missing postal_code
- optional blank first_name/last_name

Same reconciliation rules.

## CSV formula injection
Create exported text beginning, after optional whitespace, with:
=  +  -  @

Test across names/address/email-like fields where applicable.
Verify safe output representation such as apostrophe prefix.
Stored source data must remain unchanged.

## CSV correctness
Test:
- commas
- quotes
- embedded newlines
- Unicode
- leading/trailing spaces
- empty optional fields
- UTF-8

## Leakage
Assert no:
- PII in exceptions/logs/export events/campaign detail/list
- prohibited fields in headers
- customer_id/history leakage

STOP.
