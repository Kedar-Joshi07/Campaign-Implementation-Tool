# Step 2 — Fresh Environment & Full Synthetic Regeneration

Create new venv from accepted lock; record exact environment versions and run pip check.

Run actual generators in dependency order:
1. historical customers
2. campaign/product/campaign-sales
3. independent 5M demographics

Use frozen seeds. No manual edits/post-hoc repair.

Validate historical customers: intended count, unique IDs, DOB/adult rules, vocabularies, income/household/contact syntax, GZIP integrity.

Validate exactly 570,000 campaign rows: all historical FKs, dates, no underage contact, delivery/engagement/response/purchase/attribution/PU consistency, amounts and GZIP integrity.

Validate exactly 5,000,000 prospects: unique person_id, no customer_id linkage, age18–100, adults>=1, household equation, income rules, vocabularies and GZIP integrity.

Compare fresh compressed SHA and canonical decompressed-content SHA to accepted manifests. Unexplained drift = NO-GO.

Validate Git LFS state. STOP.
