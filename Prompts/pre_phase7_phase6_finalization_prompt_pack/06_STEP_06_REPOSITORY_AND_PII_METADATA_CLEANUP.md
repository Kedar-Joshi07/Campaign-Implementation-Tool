# Step 6 — Repository and PII Metadata Cleanup

Use HEAD from Step 5.

## Remove generated DB artifact

Remove from Git:

`artifacts/phase6_step8_perf_security.db`

The test/evidence script must create its DB when needed.

## Update .gitignore

Add:

```text
artifacts/*.db
artifacts/*.db-wal
artifacts/*.db-shm
```

Do not ignore JSON evidence.
Do not remove required model artifact behavior.

## Sanitize evidence

Ensure committed evidence contains no:
- absolute Windows/Linux paths;
- PII;
- person IDs;
- raw SQL;
- tracebacks.

## Complete `_PII_POLICY["blocked_fields"]`

Align metadata to the full frozen Phase 6 prohibited set:

```text
first_name
last_name
address_line_1
address_line_2
street
postal_code
city
phone_number
email
ethnicity
religion
occupation_industry
family_yearly_income
number_of_children_in_family
number_of_adults_in_family
```

Include any other explicitly frozen blocked contact/address fields.

Do not change the actual approved row allowlist.

Re-run leakage tests across:
- options;
- search;
- profile;
- saved audience detail/currentness;
- preparation status/list.

Confirm no Phase 7 export/activation surface.

STOP.
