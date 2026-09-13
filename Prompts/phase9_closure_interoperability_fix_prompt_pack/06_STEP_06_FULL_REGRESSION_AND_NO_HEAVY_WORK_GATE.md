# Step 6 — Full Regression & No-Heavy-Work Gate

Run:
- full pytest
- focused Phase 9 interoperability tests
- Phase 9 planner/preview/recommendation tests
- Phase 8 browser harness unit tests
- Clean-room Phase1→7
- compileall
- pip check
- git diff --check
- repository hygiene validation
- LFS pointer validation

Explicitly verify:
- Historical Analysis unchanged
- Model Training unchanged
- scoring contracts unchanged
- legacy Audience Explorer still works for legacy audiences
- Phase 9 multi-branch groups no longer reopen incorrectly
- Saved Target Groups still work
- Campaign Planner still works
- Campaign Draft links to correct Saved Target Group
- Email/Direct Mail export contracts unchanged
- multi-branch campaign membership unchanged
- no PII leak
- no latest-scoring fallback
- Phase 10 handoff unchanged

## Heavy-work gate
Do NOT retrain, rescore 5M, or rebuild ranks unless the fixes touched model/scoring/ranking semantics.

If heavy work becomes necessary, document the precise invalidation reason.

Create:
`docs/evidence/phase9_closure/06_REGRESSION_REPORT.md`

STOP.
