# Step 20 — Full 5M Smart-Reuse & New-Build Certification

## Objective
Prove Phase11 actually reduces unnecessary full-universe work while retaining the ability to
perform a correct full build when needed.

Start from committed clean HEAD, empty git status and verified canonical data/LFS hashes.

Because Step4 changes canonical demographics/contactability fields, certify the new canonical
5M source first:
- 5,000,000 rows
- deterministic regeneration/hash
- contactability consistency
- Feature Contract model inputs unchanged

## Scenario A — genuine new/invalidated demographic generation
From browser business flow, initiate a request whose Phase10 path requires the new current
5M scoring generation due to source checksum change or genuinely new Modeling Context.

Verify:
- correct analysis/model reuse or build decision
- full 5,000,000 scoring when required
- distinct 5,000,000
- duplicates 0
- invalid/nonfinite/out-of-range 0
- rank 100 boundaries
- analytics current
- exact result snapshot
- search run COMPLETED

## Scenario B — exact repeat
Submit exact same business request again.
Verify:
- NEW search-run row
- SAME immutable result snapshot
- EXACT_RESULT_REUSE
- no new analysis/model/scoring
- no full score-table filtering/materialization
- timing captured

## Scenario C — targeting-filter change
Same Modeling Context, change age/state/income/match strength.
Verify:
- SAME generation/model/scoring
- INTELLIGENCE_REUSE
- new exact snapshot
- no 5M scoring.

## Scenario D — delivery-profile change
Same result criteria but change Email/SMS/WhatsApp/Paid Social as allowed.
Verify:
- targeting membership unchanged
- no Phase10 rebuild
- channel-specific download counts/validators applied only at export.

## Snapshot/full lineage
For at least one result record exact:
search_run → snapshot → generation → scoring → model → analysis → source checksums.

Save/export at least one multi-branch Target Group/result.

Run:
full pytest, Phase1–10 clean-room/regression requirements, Phase11 tests,
compileall, pip check, diff hygiene, repo/LFS hygiene, SQLite integrity_check.

Evidence:
machine manifest + `docs/evidence/phase11/20_FULL_5M_CERTIFICATION.md`

STOP.
