# Step 5 — Contact PII & Export Contract v1

Contact PII remains forbidden outside finalized-campaign export.

Base columns:
person_id, propensity_score, percentile_bucket, decile, rank_band

EMAIL_CONTACT_V1 adds:
first_name, last_name, email

DIRECT_MAIL_CONTACT_V1 adds:
first_name, last_name, address_line_1, address_line_2, city, state, postal_code

Never export:
ethnicity, religion, occupation_industry, family_yearly_income,
number_of_children_in_family, number_of_adults_in_family,
unrelated demographics, historical customer_id/history, phone_number.

## Deliverability contract
Campaign audience remains the full saved audience.

EMAIL deliverable requires a nonblank conservatively valid-format email.

DIRECT_MAIL deliverable requires nonblank:
address_line_1, city, state, postal_code.
Names may be blank.

Return:
selected_audience_count
deliverable_count
undeliverable_count

Require:
deliverable + undeliverable = selected.

Do not infer/enrich missing contact data.

## CSV injection
For exported text whose first non-whitespace char is = + - @, use a documented safe
spreadsheet representation (e.g. apostrophe prefix). Do not change stored data.

Never log names/emails/addresses. STOP.
