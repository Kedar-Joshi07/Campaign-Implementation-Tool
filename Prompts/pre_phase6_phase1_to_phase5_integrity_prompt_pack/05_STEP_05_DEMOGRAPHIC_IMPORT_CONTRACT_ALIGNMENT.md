# Step 5 — Demographic Import Contract Alignment

Use the HEAD from successful Step 4.

Do not begin Phase 6.

## Problem

The current committed demographic generator and Phase 5 feature contract define the prospect universe as adults:

```text
18 <= age <= 100
number_of_adults_in_family >= 1
```

But Phase 1 row validation still accepts:
- age 0..120;
- number_of_adults_in_family = 0.

That allows a future import to pass Phase 1 and fail only later during Phase 5 scoring.

## Required alignment

Update demographic application-level validation to require:

```text
18 <= age <= 100
number_of_adults_in_family >= 1
number_of_children_in_family >= 0
family_member_count >= 1
children + adults = family_member_count
individual income >= 0
family income >= individual income
```

Do NOT alter the frozen model feature contract.

## Reconciliation

Add structural issues for:

```text
age_below_18_count
age_above_100_count
adult_count_below_1
```

Current committed 5M source must produce zero for all.

## Schema decision

Do not rebuild the 5M table solely to tighten SQLite CHECK constraints unless the migration is proven safe and worthwhile.

For this POC, application validation + reconciliation can be authoritative if clearly documented.

If schema checks are tightened, use an explicit safe migration and prove populated-data preservation.

## Tests

Cover exact boundaries:
17 reject
18 accept
100 accept
101 reject
0 adults reject
1 adult accept

Run all regressions.

STOP and report.
