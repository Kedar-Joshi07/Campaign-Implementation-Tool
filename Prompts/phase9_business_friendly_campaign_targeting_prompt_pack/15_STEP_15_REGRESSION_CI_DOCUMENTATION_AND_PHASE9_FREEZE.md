# Step 15 — Regression, CI, Documentation & Phase 9 Freeze

## Objective
Freeze Phase 9 only after proving no regression to the trusted Phase 1–8 implementation.

## Full regression
Run:
- full pytest
- clean-room Phase1→7
- Phase 8 system-browser harness unit tests
- Phase 9 contract/schema tests
- Phase 9 business UI tests
- Phase 9 system-browser control-coverage checker
- compileall
- pip check
- git diff --check
- repository hygiene
- LFS pointer validation

## Frozen Phase 1–8 regression checks
Explicitly confirm:
- Historical Analysis still works
- PU Model Training still works
- Prospect Scoring contracts unchanged
- Audience Explorer remains functional
- old Saved Audiences reopen correctly
- Campaign Builder legacy/advanced path remains functional
- Email/Direct Mail export contracts unchanged
- currentness/provenance unchanged
- PII boundary unchanged

Do not run a second 5M scoring job merely for documentation if no scoring/backend code changed and the Phase 8 source remains valid. If scoring logic changed, full 5M recertification is mandatory.

## CI
All required CI checks must be green on the exact Phase 9 implementation SHA.

Add Phase 9 tests to normal CI where bounded and appropriate.
Do not put long system-browser/5M work into ordinary CI unless infrastructure is intentionally configured.

## Documentation
Create:
- `docs/PHASE_9_IMPLEMENTATION_SUMMARY.md`
- `docs/evidence/phase9/README.md`
- `docs/evidence/phase9/PHASE9_FINAL_ACCEPTANCE.md`

Update:
- root README
- docs index
- UI navigation docs
- API docs
- schema version
- terminology
- Phase 10 handoff

## Final report
Return:
1. Phase 1–8 baseline SHA
2. Phase 9 schema/contracts SHA
3. Phase 9 UI implementation SHA
4. Phase 9 certification candidate SHA
5. final Phase 9 implementation SHA
6. browser/version
7. Phase 9 controls discovered
8. PASS
9. JUSTIFIED_EXCLUSIVE
10. FAIL
11. business campaign scenario
12. context selections
13. targeting selections
14. exact target-group count
15. saved target-group ID
16. campaign draft ID
17. PII preview result
18. currentness result
19. accessibility/responsive result
20. browser console/network result
21. pytest result
22. clean-room result
23. Phase 1–8 regression result
24. CI result
25. Phase 10 handoff readiness
26. FINAL DECISION GO / NO-GO

## GO criteria
Phase 9 is GO only if:
- business user can complete the default workflow without ML terminology
- targeting output is exact and provenance-backed
- campaign-context selectors do not make false analytical claims
- no unrelated latest-scoring fallback exists
- saved target group remains immutable/provenance-preserving
- PII is absent before governed export
- all controls are accounted
- Phase 1–8 regression is clean
- exact-SHA CI is green

Suggested commit:
`feat: add business-friendly campaign targeting experience`

STOP.
