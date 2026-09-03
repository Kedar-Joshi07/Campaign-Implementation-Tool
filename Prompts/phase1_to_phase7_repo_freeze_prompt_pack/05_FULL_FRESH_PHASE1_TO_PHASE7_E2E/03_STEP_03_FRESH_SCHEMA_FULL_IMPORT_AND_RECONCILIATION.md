# Step 3 — Fresh Schema, Full Import & Reconciliation

Create brand-new default runtime DB and verify current schema with empty application tables.

Import full generated files through official importers in order:
customers → campaign sales → demographics.

For each verify COMPLETED, read/insert/reject counts, checksum, staging cleanup and authoritative currentness.

Run full reconciliation.

Required: intended customer count, exactly 570K campaign rows, exactly 5M prospects, zero duplicate PKs, zero orphan historical FKs, zero invalid prospect ages, zero household/income-rule violations and zero historical underage contacts.

Capture schema/count evidence. STOP.
