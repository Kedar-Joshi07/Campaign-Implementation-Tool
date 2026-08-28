# Step 8 — Performance, Security, and Provenance Hardening

Use HEAD from successful Step 7. Do not run final real 5M acceptance until this passes.

## Query-plan evidence

Capture EXPLAIN QUERY PLAN and timings for:
1. unfiltered first page;
2. next keyset page;
3. top 1%;
4. top decile;
5. state filter;
6. age+income;
7. rank band+demographic filter;
8. estimate;
9. selected profile;
10. saved-audience list/detail.

Verify existing rank index `(scoring_run_id, propensity_score DESC, person_id ASC)` is used where expected. Add only measured/justified indexes and record size impact.

## No OFFSET hot path

No prospect search or rank preparation uses OFFSET. OFFSET is acceptable only for small metadata tables such as saved_audiences.

## Memory

Verify bounded chunks for rank prep, search <=100 rows, SQL/bounded profiling, no fetchall/5M DataFrame/list, no 5M member persistence.

## PII/API audit

Forbidden Phase6 response fields:
first_name,last_name,address_line_1,address_line_2,street,postal_code,city,phone_number,email,ethnicity,religion,occupation_industry,family_yearly_income,number_of_children_in_family,number_of_adults_in_family.

Also no source absolute paths, DB paths, raw SQL, or tracebacks.

## Provenance drift tests in bounded temporary DBs

- demographic drift => current score/saved audience becomes stale;
- customer/campaign drift => linked model/score/saved audience becomes stale;
- rank boundaries cannot override stale provenance;
- exact source restoration follows normal provenance rules.

Do not mutate real canonical DB for drift tests.

## Concurrency

While audience preparation active, other preparation/training/scoring submissions 409. While training/scoring active, preparation 409.

Read-only search/profile only allowed against already prepared current run.

## Input hardening

Test oversized arrays/text, NaN/Infinity, malformed cursor, unknown keys, SQL metacharacters, enums, duplicates, negative/huge TOP_N, unsupported contract versions.

## Phase boundary scan

No Phase7 campaign object/schema, activation API, export endpoint, target CSV, contact PII, or identity linkage.

## Gates

Run pip check, pytest, compileall, diff check, validate_data. Record performance and test evidence in Phase6 implementation summary.

STOP.
