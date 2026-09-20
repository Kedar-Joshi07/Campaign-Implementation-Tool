# Phase 11 Omnichannel Profiles and PII Boundary

The immutable backend registry is the only profile authority. The current 40-column governed demographic source makes all ten profiles schema-available; a row is exported only if its required identifier and permission/contactability/targetability values pass.

All files begin with `person_id, propensity_score, percentile_bucket, decile, rank_band`, followed only by the profile-specific fields below.

| Channel | Profile | Required row condition | Profile-specific output |
|---|---|---|---|
| Email | `EMAIL_CONTACT_V1` | Valid email and email-contactable | `first_name, last_name, email` |
| Direct Mail | `DIRECT_MAIL_CONTACT_V1` | Required address and direct-mail-contactable | `first_name, last_name, address_line_1, address_line_2, city, state, postal_code` |
| SMS | `SMS_CONTACT_V1` | Valid normalized phone and SMS opt-in | `first_name, last_name, phone_number` |
| WhatsApp | `WHATSAPP_CONTACT_V1` | Valid normalized phone and WhatsApp opt-in | `first_name, last_name, phone_number` |
| Telemarketing | `TELEMARKETING_CONTACT_V1` | Valid phone, contactable, and not DNC | `first_name, last_name, phone_number` |
| Paid Social | `PAID_SOCIAL_AUDIENCE_V1` | Valid approved email and/or phone match identifier | `sha256_email, sha256_phone` |
| Paid Search | `PAID_SEARCH_AUDIENCE_V1` | Valid approved email and/or phone match identifier | `sha256_email, sha256_phone` |
| Mobile Push | `MOBILE_PUSH_CONTACT_V1` | Push token and push opt-in | `push_token` |
| Display | `DISPLAY_AUDIENCE_V1` | Advertising ID and targetable | `advertising_id` |
| Website Onsite | `WEBSITE_AUDIENCE_V1` | Web visitor ID and onsite-targetable | `web_visitor_id` |

Runtime schema availability uses exactly `AVAILABLE`, `UNAVAILABLE_MISSING_IDENTIFIER`, and `UNAVAILABLE_MISSING_CONSENT_CONTRACT`. Missing columns fail closed with a truthful unavailable reason; identifier presence never implies consent.

## Privacy rules

- Each profile has an exact ordered allowlist and rejects every unrelated contact, activation, consent, and sensitive demographic field.
- Phone is allowed only in SMS, WhatsApp, and Telemarketing output. It remains prohibited in Email and Direct Mail.
- Paid Social/Search normalize then SHA-256 hash email/phone and never emit raw values. These match keys are pseudonymous, not anonymous.
- Consent/contactability/targetability fields control eligibility but are never emitted.
- Contact PII is joined from current demographics only during streaming download. It is absent from JSON APIs, result UI, membership snapshots, manifests, and audit rows.
- CSV output is UTF-8 RFC 4180 with formula-injection mitigation and a deterministic safe filename.

The engine enforces `selected_count = deliverable_count + undeliverable_count` and, for a completed export, `row_count = deliverable_count`. The selected membership never changes when delivery profile changes.
