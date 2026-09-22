# Phase 11 Step 18 — Bounded Clean-Room Certification

Date: 2026-09-17

## Outcome

`PASS_STEP_18_BOUNDED_CLEANROOM_PHASE11_CERTIFICATION`

Two fresh isolated deterministic databases completed all ten required
Phase 11 scenarios. Relevant hashes, counts, sources and outcomes matched.

## Scenario results

| Scenario | Clean room A | Clean room B |
| --- | --- | --- |
| 1 new business run new intelligence | PASS | PASS |
| 2 identical exact result reuse | PASS | PASS |
| 3 filter change intelligence reuse | PASS | PASS |
| 4 delivery profile change | PASS | PASS |
| 5 new modeling context | PASS | PASS |
| 6 consent contactability | PASS | PASS |
| 7 paid media hash only | PASS | PASS |
| 8 gated profile extension | PASS | PASS |
| 9 snapshot corruption | PASS | PASS |
| 10 restart recovery | PASS | PASS |

## Determinism

- Clean room A canonical SHA-256: `c9ce8954b92b107f506c08e15ec455e68fbc598ee09b284acdc4b8ff261bd109`
- Clean room B canonical SHA-256: `c9ce8954b92b107f506c08e15ec455e68fbc598ee09b284acdc4b8ff261bd109`
- Exact relevant-result equality: `true`

The comparison includes both Modeling Context identities, model artifact
hashes, final ordered score/rank hashes, result snapshot/export hashes,
deliverability counts, all scenario outcomes and final durable table counts.

## Certified facts

- The first new run built Phase 10 intelligence, selected 20 members and published a new snapshot.
- The identical repeat created a new search run, reused the snapshot exactly and made zero membership-source calls.
- A state-filter change reused generation/scoring and published a distinct 20-member snapshot.
- Switching the same target result to SMS reused both intelligence and snapshot.
- The P1 to P2 product/offer change created a new Modeling Context, generation, model and scoring run.
- Email reconciled 13 deliverable + 7 undeliverable = 20 selected; SMS reconciled 8 + 12 = 20.
- Paid media exported 20 hash-only rows with no raw email or phone columns/values.
- Push/Display/Website were unavailable without extension fields and available with the Step 4 contract; Push exported 20 rows.
- Corrupt membership was not served as an exact hit; deterministic intelligence-based repair revalidated it.
- Restart preserved eight searches and safely reconciled/resumed one durable Phase 10 parent to READY.

## Isolation and cleanup

Each run started with 40 customers, 80 campaign observations and 80
synthetic prospects, then added one governed demographic-drift row for
restart recovery. Databases, sources, models and result artifacts lived
only below the dedicated runtime directory.

- Runtime removed: `true`
- Canonical database opened: `false`
- Full 5M population used: `false`

## Verification

- A/B certification: PASS in 383.492 seconds.
- Clean-room runner contract tests: 3 passed.
- Focused Phase 10/Phase 11 regression: 100 passed, 19 browser cases deferred to Step 19.
- Python compilation, evidence integrity, whitespace and runtime cleanup: PASS.

## Machine-readable evidence

`docs/evidence/phase11/18_cleanroom_phase11.json`

## Stop boundary

Step 18 stops after bounded A/B clean-room certification. Real installed
system-browser certification, real-5M certification, CI and freeze work
remain owned by Steps 19–21.

`STOP_AFTER_STEP_18`
