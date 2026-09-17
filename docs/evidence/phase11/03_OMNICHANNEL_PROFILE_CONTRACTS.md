# Phase 11 Omnichannel Profile and Privacy Contracts

Generated: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/03_STEP_03_OMNICHANNEL_PROFILE_AND_PRIVACY_CONTRACTS.md`

Baseline: `881b5a652e869af1415547de452b9cccd2c18293`

## Step result

`PASS_STEP_03_OMNICHANNEL_PROFILE_AND_PRIVACY_CONTRACTS`

The two-profile constants are now backed by an immutable, backend-owned Phase
11 registry. All ten requested profile contracts exist, privacy is enforced by
exact per-profile allowlists, availability is evaluated without inventing
source fields, and the existing Email/Direct Mail Campaign workflow remains
backward compatible.

Step 3 does not change the database schema or canonical demographic source.
Step 4 supplies and verifies the missing governed contactability/identifier
fields. Step 13 composes this registry into the new result-snapshot streaming
download engine.

## Implementation inventory

| Artifact | Purpose |
|---|---|
| `app/services/omnichannel_profile_contracts.py` | Backend authority for registry metadata, availability, normalization, deliverability, hashing, allowlist projection, filenames, CSV safety, and audit fields |
| `app/services/campaign_contracts.py` | Phase 7 compatibility facade; Email/Direct Mail values now derive from the registry while the legacy Campaign channel surface remains unchanged |
| `tests/test_phase11_omnichannel_profile_contracts.py` | Focused unit and privacy-contract matrix for every profile |

Contract version:
`OMNICHANNEL_EXPORT_PROFILE_CONTRACT_VERSION = "1"`.

The registry and channel mapping use immutable `MappingProxyType` containers;
each profile is a frozen, slotted dataclass. Frontend constants are not an
authority and unrecognized channel/profile input is rejected.

## Profile registry

The common analytical columns remain:

`person_id, propensity_score, percentile_bucket, decile, rank_band`.

Every output below is those five columns followed by the listed
profile-specific columns.

| Channel | Export profile | Release state | Baseline availability | Identifiers | Contactability/targetability | Profile-specific output |
|---|---|---|---|---|---|---|
| `EMAIL` | `EMAIL_CONTACT_V1` | Immediate | `UNAVAILABLE_MISSING_CONSENT_CONTRACT` | valid email | `email_contactable=true` | `first_name, last_name, email` |
| `DIRECT_MAIL` | `DIRECT_MAIL_CONTACT_V1` | Immediate | `UNAVAILABLE_MISSING_CONSENT_CONTRACT` | address line 1, city, state, postal code | `direct_mail_contactable=true` | `first_name, last_name, address_line_1, address_line_2, city, state, postal_code` |
| `SMS` | `SMS_CONTACT_V1` | Immediate | `UNAVAILABLE_MISSING_CONSENT_CONTRACT` | valid normalized phone | `sms_opt_in=true` | `first_name, last_name, phone_number` |
| `WHATSAPP` | `WHATSAPP_CONTACT_V1` | Immediate | `UNAVAILABLE_MISSING_CONSENT_CONTRACT` | valid normalized phone | `whatsapp_opt_in=true` | `first_name, last_name, phone_number` |
| `TELEMARKETING` | `TELEMARKETING_CONTACT_V1` | Immediate | `UNAVAILABLE_MISSING_CONSENT_CONTRACT` | valid normalized phone | contactable and not DNC | `first_name, last_name, phone_number` |
| `PAID_SOCIAL` | `PAID_SOCIAL_AUDIENCE_V1` | Immediate | `AVAILABLE` | valid email or phone | approved match identifier | `sha256_email, sha256_phone` |
| `PAID_SEARCH` | `PAID_SEARCH_AUDIENCE_V1` | Immediate | `AVAILABLE` | valid email or phone | approved match identifier | `sha256_email, sha256_phone` |
| `MOBILE_PUSH` | `MOBILE_PUSH_CONTACT_V1` | Gated | `UNAVAILABLE_MISSING_IDENTIFIER` | push token | `push_opt_in=true` | `push_token` |
| `DISPLAY` | `DISPLAY_AUDIENCE_V1` | Gated | `UNAVAILABLE_MISSING_IDENTIFIER` | advertising ID | `advertising_targetable=true` | `advertising_id` |
| `WEBSITE_ONSITE` | `WEBSITE_AUDIENCE_V1` | Gated | `UNAVAILABLE_MISSING_IDENTIFIER` | web visitor ID | `onsite_targetable=true` | `web_visitor_id` |

“Immediate” means the profile contract is implemented and is not one of the
three source-identifier-gated profiles. It does not waive source truthfulness.
The Phase 10 demographic source lacks the explicit Email, Direct Mail, SMS,
WhatsApp, and Telemarketing permission/contactability fields, so those new
registry paths honestly report the missing-consent status until Step 4. The
legacy finalized-Campaign Email/Direct Mail path is not switched off or
rewritten during this intermediate step.

The exact exposed availability vocabulary is:

- `AVAILABLE`
- `UNAVAILABLE_MISSING_IDENTIFIER`
- `UNAVAILABLE_MISSING_CONSENT_CONTRACT`

Availability is resolved against actual source columns. With the complete Step
4 field set, all ten schemas resolve to `AVAILABLE`; actual rows still must pass
their identifier and consent/contactability tests.

## Profile-specific privacy boundary

The former global “phone is prohibited everywhere” assumption is removed.
`PROHIBITED_EXPORT_FIELDS` remains only as a compatibility alias for common
prohibitions. It no longer contains `phone_number` or `email`.

Each profile now owns both:

- an exact ordered field allowlist, equal to its exact output columns; and
- an exact prohibited-field set containing every unrelated contact,
  activation, consent, and sensitive demographic field known to this contract.

Phone is allowed only for SMS, WhatsApp, and Telemarketing. Raw email and phone
are both prohibited for Paid Social and Paid Search. Email does not receive
phone, SMS does not receive email/address, and activation profiles do not
receive unrelated contact identifiers.

Common prohibited demographics include:

`customer_id, age, gender, individual_yearly_income, marital_status, education,
employment_status, resident_status, resident_type, family_member_count,
number_of_children_in_family, number_of_adults_in_family, ethnicity,
type_of_employment, occupation_industry, family_yearly_income, religion`.

The exact allowlist projection returns no unspecified key. Contactability,
consent, and targetability controls are used for validation but never written
to output.

## Identifier normalization and validation

### Email

- Require text with a valid single-address structure.
- Trim surrounding whitespace.
- Lowercase before contact output or hashing.
- Reject blank, malformed, and over-320-character values.

Example: `"  Person@Example.COM "` becomes `person@example.com`.

### Synthetic US phone

- Accept a 10-digit US number or 11 digits beginning with `1`.
- Ignore ordinary formatting punctuation and whitespace.
- Reject alphabetic extensions, wrong lengths, and invalid NPA/NXX leading
  digits.
- Produce canonical `+1NXXNXXXXXX` text.

Example: `(202) 555-0123` becomes `+12025550123`.

### Push, advertising, and website identifiers

- Never synthesize an identifier during export.
- Push and website identifiers are trimmed.
- Advertising IDs are trimmed and lowercased by output projection.
- Missing identifiers make a row undeliverable.
- The profiles remain gated until Step 4 creates deterministic source values
  and passes generator/importer/currentness verification.

## Consent, contactability, and targetability

- Email requires a valid normalized email and `email_contactable=true`.
- Direct Mail requires the governed postal fields and
  `direct_mail_contactable=true`.
- SMS requires a valid normalized phone and `sms_opt_in=true`.
- WhatsApp requires a valid normalized phone and `whatsapp_opt_in=true`.
- Telemarketing requires a valid normalized phone and at least one governed
  contactability/DNC control. An explicit false contactability value or true
  DNC value blocks delivery.
- Paid Social/Search require one or both approved match identifiers; they do
  not infer contact consent from raw presence.
- Push requires a token and push opt-in.
- Display and Website use targetability flags rather than contact consent.

Identifier presence never implies consent or contactability.

## Paid-media hashing contract

Paid Social and Paid Search use only these output match keys:

`sha256_email, sha256_phone`.

Rules:

1. Normalize email by trim plus lowercase.
2. Normalize phone to the canonical synthetic-US representation.
3. Hash UTF-8 normalized text with SHA-256.
4. Emit lowercase 64-character hexadecimal.
5. Allow either hash to be blank when the other approved identifier is valid.
6. Reject a row when neither identifier is valid.
7. Never include raw email or phone in paid-media output.

Verified vectors:

| Normalized input | SHA-256 |
|---|---|
| `person@example.com` | `542d240129883c019e106e3b1b2d3f3cb3537c43c425364de8e951d5a3083345` |
| `+12025550123` | `d5ab8b77e69a81dfc634c3556c620d5d6753df6fc28c73c88c79a9332b705382` |

These hashes are pseudonymous, not anonymous or anonymized. No such claim is
made by code, tests, or evidence.

## File and CSV contract

Every profile declares:

- format `CSV_UTF8_RFC4180`;
- deterministic filename template
  `potential_customers_{search_run_id}_{profile}.csv`;
- a path-safe search-run identifier requirement; and
- CSV formula-injection mitigation.

Text whose first non-whitespace character is `=`, `+`, `-`, or `@` is prefixed
with a single quote. Commas, quotes, newlines, and Unicode continue to be
handled by the CSV writer when Step 13 composes this contract into streaming
downloads.

## Audit contract

Each profile carries this exact audit field contract:

`export_event_id, search_run_id, snapshot_id,
omnichannel_contract_version, export_profile, profile_version, status,
selected_count, deliverable_count, undeliverable_count, row_count, csv_sha256,
started_at, completed_at, currentness_state, safe_error_message`.

Step 13 must preserve these reconciliation equations:

- `selected_count = deliverable_count + undeliverable_count`
- `row_count = deliverable_count`

It must also retain currentness validation, streaming, checksum, safe failure,
disconnect/abort, and no persistent PII-rich snapshot guarantees from Phase 7.

## Backward compatibility

The existing Campaign API remains restricted to `EMAIL` and `DIRECT_MAIL` in
this step. Its exact profile codes and ordered columns are now sourced from the
registry but remain byte-for-byte equivalent at the contract-value level.

No Campaign table, export-event table, router, schema, or request model was
expanded. No existing export logic was redirected to permission columns that do
not exist yet. Existing Email and Direct Mail finalization, streaming,
currentness, counts, checksums, abort handling, and formula mitigation therefore
remain operational.

The Phase 11 result-download path is separate and is implemented in Step 13
after Step 4 source fields and Step 5/11 run/snapshot identities exist.

## Frozen analytical boundary

No contactability, consent, phone, email, push, advertising, or visitor field
was added to the model feature contract. The frozen feature file remains 7,188
bytes with SHA-256:

`b3e3f382080b480751080da4b1a03c9fdb3ed25fc7740e9490723a2c880234be`.

The 11 features remain exactly:

`age, gender, state, individual_yearly_income, marital_status, education,
employment_status, resident_status, resident_type, family_member_count,
type_of_employment`.

## Intentional signature inventory

| File | Bytes | SHA-256 | Status |
|---|---:|---|---|
| `app/services/campaign_contracts.py` | 2,519 | `3d4d60d3ab2bebb9c02c8a7789903408727128503513fdb2d1b11879e60cc5cd` | Intentional Step 3 compatibility-facade change; baseline was `c5d06cd29ed6f023e4d301eb971c0c37d76d13103bdf48311df9c9e688d26729` |
| `app/services/omnichannel_profile_contracts.py` | 22,568 | `a09415bb04d358c34d64c822be54140890179d86bd57bc85bd506181b4f48399` | New backend registry |
| `tests/test_phase11_omnichannel_profile_contracts.py` | 16,371 | `ede57e7220c0c1e0552d8576ec8c60488a0531d2a56fcbe186abad03fe2d0798` | New focused tests |
| `app/ml/feature_contract.py` | 7,188 | `b3e3f382080b480751080da4b1a03c9fdb3ed25fc7740e9490723a2c880234be` | Unchanged |

No other frozen Phase 1-10 authority was intentionally changed.

## Validation evidence

### New Step 3 contract suite

Command:

`pytest -q tests/test_phase11_omnichannel_profile_contracts.py`

Result: **27 passed in 22.37 seconds**.

Coverage includes:

- immutable registry and exact channel/profile mapping;
- seven immediate and three gated release states;
- current-source and post-Step-4 source-column availability;
- exact output columns, allowlists, and prohibited fields;
- profile-specific phone rules;
- email and phone normalization;
- deterministic paid-media hashes and one-identifier behavior;
- every profile's identifier and consent/targetability validator;
- paid-media no-raw-identifier projection;
- CSV formula mitigation and safe filenames;
- legacy Campaign compatibility; and
- exclusion of all contactability/activation fields from model features.

### Phase 7/9 Campaign/export regression

Command:

`pytest -q tests/test_campaign_api.py tests/test_campaign_export_hardening.py tests/test_phase9_save_target_group_campaign.py`

Result: **20 passed in 487.85 seconds**.

This regression uses isolated temporary databases and real bounded streaming
exports. It confirms existing Campaign API, Email/Direct Mail deliverability,
count reconciliation, currentness, mid-export drift, abort recovery, UTF-8/CSV
safety, and Phase 9 saved-target-group member resolution remain intact.

## Deferred work and stop boundary

- Step 4: add deterministic governed source fields, importer/schema validation,
  source regeneration, checksum/currentness change, and gated-profile proof.
- Step 5: add search-run and result-snapshot registries.
- Step 13: integrate these contracts into snapshot member resolution, governed
  streaming downloads, and export audit persistence.
- No canonical import, regeneration, training, scoring, ranking, or database
  migration ran in Step 3.
- No frontend constants or UI availability claims were added.
- No direct activation/send integration was added.

`STOP_AFTER_STEP_03`
