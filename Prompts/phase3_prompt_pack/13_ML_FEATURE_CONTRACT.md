# ML Feature Contract — Version 1

This file is authoritative for Phase 3.

## Purpose

The PU look-alike model is intended to learn **what known-positive historical customers look like** using attributes that will later exist for completely independent demographic prospects.

Therefore, a feature is allowed only when the historical customer table and demographic scoring universe have a semantically compatible concept.

## Frozen raw features

| Order | Feature | Type | Historical source | Future prospect concept |
|---:|---|---|---|---|
| 1 | `age` | numeric | derived from `customers.date_of_birth` at saved analysis end date | `demographics.age` |
| 2 | `gender` | categorical | `customers.gender` | `demographics.gender` |
| 3 | `state` | categorical | `customers.state` | `demographics.state` |
| 4 | `individual_yearly_income` | numeric | customer | demographic |
| 5 | `marital_status` | categorical | customer | demographic |
| 6 | `education` | categorical | customer | demographic |
| 7 | `employment_status` | categorical | customer | demographic |
| 8 | `resident_status` | categorical | customer | demographic |
| 9 | `resident_type` | categorical | customer | demographic |
| 10 | `family_member_count` | numeric | customer | demographic |
| 11 | `type_of_employment` | categorical | customer | demographic |

This order should be stable and versioned.

## Internal non-feature fields

- `customer_id` — row identity/reconciliation only
- `pu_label` — target label only

Both must be removed from X before preprocessing.

## Explicitly prohibited

### Identifiers/PII
- first_name
- last_name
- email
- phone_number
- address_line_1
- address_line_2
- street
- postal_code
- city if not approved as a future stable feature
- customer_id
- person_id

### Campaign behavior
- campaign_id
- campaign_name
- campaign_type
- channel
- creative
- offer
- target_segment
- contacted_flag
- engagement
- response
- conversion
- purchase
- order
- quantity
- sales
- margin
- recency
- frequency
- campaign counts

### Unsupported customer/prospect mismatch
- ethnicity (not present in Customer schema)
- religion
- occupation industry
- family yearly income
- any inferred field obtained by linking to demographics

## Age calculation

Reference date = saved normalized `contact_date_to`.

Completed age:

```text
reference_year - birth_year
- 1 when birthday has not occurred by reference month/day
```

Do not use current date.

## Numeric handling

### age
Expected adult customer modeling range should be documented. Source anomalies outside the approved bounds should be surfaced rather than silently normalized into typical ages.

### individual_yearly_income
- nonnegative;
- finite;
- missing may be imputed from training split.

### family_member_count
- integer;
- >= 1 when present;
- missing may be imputed from training split.

## Categorical handling

Canonical normalization:

1. convert null to `Unknown/Other`;
2. trim surrounding whitespace;
3. blank after trim → `Unknown/Other`;
4. retain original meaningful category text;
5. encoder must tolerate unseen categories in validation/future prospects.

Do not perform fuzzy matching or invent category equivalences inside Phase 3 unless the exact mapping is explicitly frozen and tested.

## Feature contract fingerprint

Canonical JSON should include:

```json
{
  "version": "1",
  "ordered_features": [],
  "numeric_features": [],
  "categorical_features": [],
  "normalization": {},
  "preprocessing": {}
}
```

Serialize with stable key ordering and compact separators, then SHA-256 hash UTF-8 bytes.

This fingerprint is required in `model_runs` and the artifact.

## Compatibility rule for later prospect scoring

Before a model scores demographics, the future scoring service must confirm:

- artifact feature-contract version supported;
- fingerprint matches model metadata;
- every required raw field can be constructed;
- no silently missing feature;
- unseen categorical values are handled by the persisted preprocessor.

Phase 3 does not perform that 5M scoring.
