# Omnichannel Export Profile Contract

Introduce `OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION = "1"`.

Every profile defines:
channel, profile version, required identifiers, consent/contactability requirements,
field allowlist, forbidden fields, normalization, deliverability, output format and audit.

## Existing
EMAIL → EMAIL_CONTACT_V1
DIRECT_MAIL → DIRECT_MAIL_CONTACT_V1

## New immediately supported
SMS → SMS_CONTACT_V1
- valid normalized phone
- sms_contactable=true
- base rank fields + first_name,last_name,phone_number

WHATSAPP → WHATSAPP_CONTACT_V1
- valid normalized phone
- whatsapp_contactable=true

TELEMARKETING → TELEMARKETING_CONTACT_V1
- valid normalized phone
- telemarketing_contactable=true / do_not_call=false

PAID_SOCIAL → PAID_SOCIAL_AUDIENCE_V1
PAID_SEARCH → PAID_SEARCH_AUDIENCE_V1
- at least one approved match identifier
- default export uses sha256_email and/or sha256_phone
- no raw identifiers unless a future provider contract explicitly requires them

## Enable only after governed source extension
MOBILE_PUSH → MOBILE_PUSH_CONTACT_V1
- push_token + push_opt_in/contactable

DISPLAY → DISPLAY_AUDIENCE_V1
- advertising_id + advertising_targetable

WEBSITE_ONSITE → WEBSITE_AUDIENCE_V1
- web_visitor_id/account visitor key + onsite_targetable

Historical presence of a channel does not mean export availability.
Backend exposes availability reason:
AVAILABLE / UNAVAILABLE_MISSING_IDENTIFIER / UNAVAILABLE_MISSING_CONSENT_CONTRACT.

Normalize email by trim+lowercase for hash.
Normalize synthetic US phone deterministically to a canonical E.164-like representation.
SHA-256 outputs lowercase hex and must be documented as pseudonymous.

Every download records search_run_id, snapshot_id, profile/version, selected/deliverable/
undeliverable/row counts, checksum, timestamps and currentness.
