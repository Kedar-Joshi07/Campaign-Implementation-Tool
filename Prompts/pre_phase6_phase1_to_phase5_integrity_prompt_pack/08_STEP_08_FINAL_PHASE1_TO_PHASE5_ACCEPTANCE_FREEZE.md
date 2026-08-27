# Step 8 — Final Phase 1→5 Acceptance and Freeze

Use the HEAD after successful Step 7.

Do not implement Phase 6.

## Acceptance matrix

Phase 1:
- schema/import/reconciliation works;
- current source import provenance trustworthy;
- no identity linkage;
- campaign contacts adult-only;
- demographic adult contract enforced.

Phase 2:
- filters/PU semantics unchanged;
- exact historical source provenance captured;
- source cannot drift during completed analysis.

Phase 3:
- saved analysis provenance validated;
- exact 11-feature contract unchanged;
- deterministic split/preprocessing;
- Bagging PRIMARY governance unchanged;
- stale analysis cannot silently train against changed data.

Phase 4:
- one shared max_workers=1 executor;
- global heavy-job exclusion;
- training APIs/UI and stale-job handling unchanged.

Phase 5:
- model historical provenance current;
- demographic source provenance current;
- scoring run canonical only when both sides are current;
- keyset 5M scoring and exact reconciliation unchanged;
- stale historical runs remain audit history;
- no Phase 6 functionality.

## Crash consistency

Explicitly prove:

A crash/failure at the final demographic source publication boundary cannot expose:
- new live demographics with old completed provenance, or
- new completed provenance with old live demographics.

## Docs

Update:
- README
- Phase 5 implementation summary
- progress tracker
- acceptance checklist
- Phase 6 handoff contract

Add final integrity evidence:
`docs/evidence/phase1_to_phase5_final_integrity.json`

No PII/absolute paths/raw SQL/tracebacks.

## Final gates

Run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Run the relevant end-to-end API paths.

Commit a dedicated final integrity commit.

If one documentation-only SHA stamp is needed afterward, it is acceptable.

The actual final HEAD becomes the only authoritative Phase 6 starting baseline.

## Final report

Include:
- starting SHA `5f54c5e7138afaf615984babd32cac3a6bf2a99b`;
- final SHA;
- schema version;
- exact files changed;
- crash-window fix;
- underage contact before/after count;
- whether campaign source was regenerated;
- customer/campaign/demographic import IDs/checksums;
- current analysis/model/scoring IDs;
- feature/artifact SHAs;
- score reconciliation;
- deterministic re-score;
- complete test result;
- confirmation no Phase 6 functionality;
- final GO / CONDITIONAL GO / NO-GO.

STOP.
