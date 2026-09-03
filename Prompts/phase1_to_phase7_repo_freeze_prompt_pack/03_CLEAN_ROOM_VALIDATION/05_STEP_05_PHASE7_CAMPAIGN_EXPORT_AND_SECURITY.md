# Step 5 — Clean-Room Phase 7

Create/edit/finalize campaign normally. Verify finalized immutability/currentness and exact deterministic member resolution.

Create Email and Direct Mail exports. Verify selected=deliverable+undeliverable, rows=deliverable, exact profile headers/order/checksums.

Test blank/malformed email, incomplete address, CSV formula prefixes = + - @, commas/quotes/newlines/Unicode, no prohibited PII and no customer_id linking.

Exercise source-drift/export-snapshot behavior in isolated state. STOP.
