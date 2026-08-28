# Step 10 — Phase 6 Final Acceptance and Phase 7 Handoff

Use HEAD from successful Step 9. Do not implement Phase 7.

## Acceptance

Input governance:
- current Phase5 scoring run verified;
- historical and demographic provenance current;
- BAGGING_PU/policy/evaluation/feature/artifact unchanged.

Ranking:
- Rank Contract v1;
- score DESC/person_id ASC;
- exactly 100 boundaries;
- percentile1 top1%, decile1 top10%, bands exact;
- no 5M rank/member table;
- no OFFSET rank scan.

Search/filter:
- approved filters only;
- parameterized SQL;
- keyset paging <=100;
- exact non-PII row allowlist;
- stale runs rejected.

Profile:
- universe/matching/selected/historical-positive aggregates;
- selected vs universe and historical positives;
- no identity linkage;
- finite JSON.

Saved audiences:
- ALL_MATCHING/TOP_N;
- immutable definition persistence;
- normalized filters + full provenance;
- no member copy;
- stale detection.

UI:
- Audience Explorer enabled;
- Campaigns disabled;
- prepare/filter/search/profile/save/reopen works;
- score semantics clear;
- no PII/export/activation.

Performance/regression:
- bounded rank prep;
- index/timing evidence;
- no unbounded materialization;
- full pytest/pip/compile/diff/validate_data pass.

## Finalize docs

Update:
```text
docs/PHASE_6_IMPLEMENTATION_SUMMARY.md
docs/evidence/phase6_5m_acceptance.json
Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md
Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md
Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md
```

Do NOT do comprehensive root README rewrite.

## Phase 7 handoff

Phase7 may consume saved audience_id only when:
- saved audience exists/current;
- saved scoring run current/canonical;
- historical and demographic provenance current;
- selection definition valid;
- resolved_count >0;
- filter/rank/selection contract versions supported.

Phase7 may then separately implement Campaign Builder, campaign metadata, selecting a saved audience, review, deterministic member streaming/materialization, explicit contact-PII contract, and CSV export.

Phase7 must never silently consume stale saved audience.

Do not freeze contact export fields in Phase6; Phase7 must explicitly define them.

## Commit/freeze

Create dedicated Phase6 implementation/freeze commit. Do not self-embed its SHA in the same evidence file. After commit, actual HEAD becomes authoritative Phase7 starting baseline.

Final report: starting SHA, final SHA, schema, files, preparation job/runtime, canonical IDs, boundary/band evidence, APIs, PII allowlist, filters, paging/profile/save evidence, provenance, performance, pytest/pip/compile/diff/validation, no Phase7 features, handoff, GO/CONDITIONAL GO/NO-GO.

STOP.
