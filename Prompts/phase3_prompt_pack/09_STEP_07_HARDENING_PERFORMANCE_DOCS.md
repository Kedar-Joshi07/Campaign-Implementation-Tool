# Step 7 — Phase 3 Hardening, Full-Data Validation, Performance, and Documentation

## Objective

Prove Phase 3 works against the real POC dataset and is safe to hand to Phase 4.

## A. Full regression

Run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
```

Record exact results.

All Phase 1 and Phase 2 tests must still pass.

## B. Full-data model run

Using a valid completed Phase 2 `analysis_run_id`:

1. reconstruct cohort;
2. reconcile saved counts;
3. train primary PU candidate;
4. train challenger if enabled;
5. calculate evaluation metrics;
6. persist/reload artifact;
7. verify checksum.

Record:

- analysis run ID;
- model run ID;
- counts;
- runtime by stage;
- peak/approx memory if practical;
- feature count after encoding;
- selected candidate;
- key top-k lift/recall;
- artifact size;
- checksum.

## C. Performance sanity

This is a local POC.

Do not require production SLA.

However:

- customer-grain reconstruction should avoid materializing all 570K observations in Python;
- training should operate on ~selected-customer grain;
- no 5M demographic scan;
- no N+1 SQL;
- no unbounded grid search;
- record elapsed times.

If Bagging PU is too slow, document and skip it rather than destabilizing the POC.

## D. Reproducibility rerun

Run the same completed analysis twice with the same seed.

Verify:

- same reconstructed counts;
- same split membership/fingerprint if persisted only as aggregate/hash, not customer IDs;
- same feature-contract hash;
- same selected candidate;
- same or tolerance-equivalent metrics;
- materially identical validation scores on the same bounded verification sample.

Two model artifacts may have different file bytes because serialization can include nonsemantic details; if so, document it. The prediction behavior and metadata must be reproducible.

## E. Scope scan

Search repo for accidental:

- `propensity_scores`;
- 5M model scoring;
- enabled Model Training UI;
- Audience Explorer implementation;
- campaign builder/export;
- customer/person mapping;
- PII feature usage;
- behavioral feature leakage.

No accidental later-phase feature may be present.

## F. Documentation

Update README with:

- schema v3;
- dependencies;
- Phase 3 modeling semantics;
- feature contract;
- PU label meaning;
- training CLI;
- evaluation caveats;
- artifact layout;
- reproducibility;
- known limitations;
- Phase 4 boundary.

Add:

`docs/PHASE_3_IMPLEMENTATION_SUMMARY.md`

Include the exact accepted Phase 2 baseline:

`52396010f945b0328b84453ce25c587b11ed7fd7`

## G. Acceptance

Complete `10_PHASE_3_ACCEPTANCE_CHECKLIST.md` with concrete evidence.

Any failed Critical item = No-Go for Phase 4.

## Exit criteria

Phase 3 is demonstrably reproducible, leakage-safe, PU-correct, persisted, regression-safe, and ready for Phase 4 orchestration/UI.
