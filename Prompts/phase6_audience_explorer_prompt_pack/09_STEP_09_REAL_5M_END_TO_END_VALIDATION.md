# Step 9 — Real 5M End-to-End Phase 6 Validation

Use HEAD from successful Step 8. Validate the real current POC database. Resolve canonical IDs dynamically; do not hard-code baseline IDs.

## Pre-run gate

Run full tests/pip/compile/diff/data validation, current provenance validation, and Phase5 deterministic sample re-score. Do NOT rerun 5M scoring unless Phase5 currentness is actually broken.

## Real rank preparation

Prepare the current canonical scoring run.

Expected:
- 202 unless already prepared;
- job COMPLETED;
- exactly 100 boundary rows;
- total population 5,000,000;
- percentile1 rank 50,000;
- percentile5 rank 250,000;
- percentile10 rank 500,000;
- percentile100 rank 5,000,000.

Record job ID, runtime, chunk size/count, throughput/memory evidence, verification.

## Exact ranking counts for N=5,000,000

Top 1% = 50,000.
Top decile/decile1 = 500,000.

Bands:
- ELITE 50,000
- VERY_HIGH 200,000
- HIGH 250,000
- MEDIUM 750,000
- LOW 1,250,000
- VERY_LOW 2,500,000

Sum must equal 5,000,000.

## Search

Verify unfiltered first page, several keyset pages with no duplicates/gaps, and representative filters: state; age; income; gender+state; rank band+state; decile+age+income. Every returned row must satisfy filters and exact order. No PII.

## Profile

Run profiles for universe, top1%, top decile, realistic demographic filter, and filtered TOP_N 50,000. Verify counts, finite shares/indexes, selected-vs-universe, selected-vs-historical-positive, historical positive reconciliation, and no identity linkage.

## Save validation audience

Create one useful deterministic validation audience such as `Phase 6 Validation — Top 50K` with TOP_N 50,000 (or lower if chosen filters yield less). Record audience_id, resolved_count, filter hash, currentness, provenance. Reopen and confirm exact saved definition/profile snapshot. Do not export members.

## UI E2E

Validate enabled Audience Explorer, preparation progress, filters, estimate, ranked page, profile, save/reopen, Campaigns disabled, no export, score disclaimer.

## Evidence

Create sanitized `docs/evidence/phase6_5m_acceptance.json` containing canonical run IDs, provenance, prep metrics, boundary/band counts, filter/search/profile evidence, saved audience evidence, tests, and no-PII/no-Phase7 scan.

No raw person IDs, PII, absolute paths, SQL, or tracebacks.

STOP.
