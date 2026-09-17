# Step 3 — Omnichannel Profile & Privacy Contracts

## Objective
Replace the two-profile export contract with an extensible profile registry while retaining
all Phase 7 audit/currentness guarantees.

Create a profile registry owned by backend code, not frontend constants.

Each profile must define:
- channel code
- export profile/version
- availability
- required identifiers
- consent/contactability requirements
- exact output columns
- field allowlist/prohibited fields
- identifier normalization
- deliverability validation
- hashing rules
- filename/format
- audit contract

Implement/retain:
EMAIL_CONTACT_V1
DIRECT_MAIL_CONTACT_V1
SMS_CONTACT_V1
WHATSAPP_CONTACT_V1
TELEMARKETING_CONTACT_V1
PAID_SOCIAL_AUDIENCE_V1
PAID_SEARCH_AUDIENCE_V1

Declare gated:
MOBILE_PUSH_CONTACT_V1
DISPLAY_AUDIENCE_V1
WEBSITE_AUDIENCE_V1

Do not enable gated profiles until Step 4 source identifiers exist and pass importer/currentness tests.

Replace any global assumption “phone prohibited everywhere” with profile-specific allowlists.
Still prohibit unrelated sensitive demographics from every profile.

Paid media:
- normalize email/phone;
- output deterministic SHA-256 match keys;
- raw identifier excluded by default;
- missing one identifier allowed if another approved identifier is present.

Consent/contactability:
- SMS requires SMS permission;
- WhatsApp requires WhatsApp permission;
- Telemarketing respects DNC/contactability;
- Email requires email contactability;
- Direct Mail uses direct-mail contactability;
- Push requires push opt-in;
- Display/Website use targetability flag rather than contact consent.

Keep formula-injection mitigation for CSV text.

Add comprehensive unit/contract tests.

Evidence:
`docs/evidence/phase11/03_OMNICHANNEL_PROFILE_CONTRACTS.md`

STOP.
