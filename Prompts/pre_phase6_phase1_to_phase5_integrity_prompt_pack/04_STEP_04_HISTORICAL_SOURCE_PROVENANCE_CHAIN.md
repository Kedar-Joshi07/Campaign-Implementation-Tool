# Step 4 — Historical Source Provenance Chain (Phase 2 → Phase 3 → Phase 5)

Use the HEAD from successful Step 3.

Do not begin Phase 6.

## Problem

Phase 3 currently reconstructs a saved Phase 2 analysis and reconciles:

- observation count;
- selected customer count;
- positive count;
- unlabeled count.

Those counts are necessary but not sufficient.

A controlled customer/campaign reimport could theoretically change cohort membership/features while leaving the same four totals.

Also, Phase 5 scoreability validates model governance/artifact/feature provenance but does not currently prove that the model's historical training source is still the current historical source.

## Goal

Create a complete controlled provenance chain:

```text
customer import
+
campaign_sales import
        ↓
Phase 2 analysis source provenance
        ↓
analysis_run_id
        ↓
Phase 3 model
        ↓
model_run_id
        ↓
Phase 5 scoring
        ↓
scoring_run_id
```

## Schema

Use an additive migration (next schema version) and preserve all old rows.

Preferred explicit nullable fields on `historical_analysis_runs`:

```text
customer_import_id
customer_source_checksum
campaign_sales_import_id
campaign_sales_source_checksum
```

Use FKs to `data_import_runs(import_id)` only if safe with the existing schema/history.

Checksums must be 64-char SHA-256 when present.

Legacy analyses remain readable but have unknown historical provenance.

Do not fake/backfill checksum provenance for an old analysis unless it can be proven.

## Phase 2 analysis creation

Before analysis queries:

1. resolve latest COMPLETED customer import;
2. resolve latest COMPLETED campaign_sales import;
3. require valid checksum and count alignment to live tables;
4. capture provenance.

Immediately before marking analysis COMPLETED:
- resolve both again;
- require exact same import IDs/checksums/counts.

Persist source provenance atomically with analysis completion.

If source changed during analysis, fail the run.

## Phase 3 training handoff

Before reconstruction:
- require completed analysis;
- for provenance-aware analyses, require current historical source imports match the saved analysis provenance;
- then reconstruct and reconcile counts.

If current source differs:
- stop with a safe stale-analysis error;
- do not create a governed model run from changed sources.

For legacy analyses without provenance:
- preserve read compatibility;
- do not silently call them source-verified.
- Decide and document whether new governed training is refused for legacy analyses; preferred for the final clean baseline is to refuse and require a new analysis.

## Phase 5 model scoreability

Extend model scoreability/current-chain validation so a model is current-source-governed only when its linked analysis historical provenance is valid/current.

Do not mutate completed historical model rows.

A historical model may remain inspectable, but after customer/campaign source replacement it must not be treated as the current model for a new canonical scoring chain without explicit legacy policy.

## Phase 5 completed scoring canonicality

Extend canonical scoring validation used for Phase 6 so current canonical requires BOTH:

1. current demographic source provenance matches scoring run;
2. model's linked historical analysis provenance matches current historical sources.

A source change in either domain makes the old score run historical/noncanonical.

## Tests

Cover:
- Phase 2 capture/recheck source provenance;
- source changes during analysis → failure;
- Phase 3 same counts but changed import provenance → stale analysis rejection;
- legacy analysis behavior explicit;
- stale historical model after campaign replacement not current-scoreable;
- old completed score run becomes noncanonical after historical source change;
- new analysis → new model → new scoring can become canonical;
- demographic-only source change behavior remains correct;
- no identity linkage introduced.

STOP and report.
