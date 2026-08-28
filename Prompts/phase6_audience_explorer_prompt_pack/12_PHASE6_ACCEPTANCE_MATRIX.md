# Phase 6 Acceptance Matrix

Any failed Critical item = NO-GO.

## Critical
- [ ] Current Phase5 scoring/current provenance gate reused.
- [ ] Historical source currentness required.
- [ ] Demographic source currentness required.
- [ ] No customer_id/person_id linkage.
- [ ] Score remains relative affinity.
- [ ] Schema migration preserves Phase1–5 data.
- [ ] No 5M audience_members table.
- [ ] No 5M rank table.
- [ ] Ranking score DESC/person_id ASC.
- [ ] Percentile preparation keyset/memory-bounded.
- [ ] Exactly 100 boundaries.
- [ ] Search keyset/no OFFSET.
- [ ] Search page <=100.
- [ ] Exact non-PII row allowlist.
- [ ] Forbidden PII absent.
- [ ] Filter/Rank/Selection contracts versioned.
- [ ] ALL_MATCHING works.
- [ ] TOP_N deterministic.
- [ ] TOP_N profile does not materialize IDs.
- [ ] Historical comparison aggregate-only.
- [ ] Saved audience captures full provenance.
- [ ] Saved audience detects historical drift.
- [ ] Saved audience detects demographic drift.
- [ ] Audience Explorer enabled.
- [ ] Campaigns disabled.
- [ ] No export/activation.
- [ ] Full regression passes.
- [ ] validate_data OK.

## Real 5M
- [ ] rank preparation completed.
- [ ] boundary count 100.
- [ ] population 5,000,000.
- [ ] top1 50,000.
- [ ] decile1 500,000.
- [ ] ELITE 50,000.
- [ ] VERY_HIGH 200,000.
- [ ] HIGH 250,000.
- [ ] MEDIUM 750,000.
- [ ] LOW 1,250,000.
- [ ] VERY_LOW 2,500,000.
- [ ] multiple pages no duplicates/gaps.
- [ ] representative filters verified.
- [ ] selected vs universe profile verified.
- [ ] selected vs historical positives verified.
- [ ] saved validation audience reopens exactly.
- [ ] acceptance evidence sanitized.

## Phase boundary
- [ ] No Campaign Builder business object.
- [ ] No contact PII export contract.
- [ ] No target CSV.
- [ ] No activation.
- [ ] Comprehensive root README remains deferred.
