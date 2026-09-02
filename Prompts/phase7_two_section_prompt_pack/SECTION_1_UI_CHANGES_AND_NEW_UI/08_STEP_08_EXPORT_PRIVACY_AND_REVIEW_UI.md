# Step 8 — Export Privacy & Review UI

Expose only these profiles:

EMAIL_CONTACT_V1:
person_id, propensity_score, percentile_bucket, decile, rank_band,
first_name, last_name, email

DIRECT_MAIL_CONTACT_V1:
person_id, propensity_score, percentile_bucket, decile, rank_band,
first_name, last_name, address_line_1, address_line_2, city, state, postal_code

Channel automatically determines profile.
No arbitrary field picker.

Never expose:
ethnicity, religion, occupation_industry, family_yearly_income,
children/adults counts, customer_id, historical behavior, phone_number.

Before export require:
`I understand this target-list export contains contact PII and is intended only for
approved POC campaign use.`

Explain:
- no PII in Audience Explorer;
- only finalized/current campaign can export;
- no persistent server-side CSV;
- no actual send/activation.

Export history displays aggregate metadata only:
event ID, time, profile, status, row count, checksum short form.

No PII rows in UI/history. STOP.
