# Step 12 — Green CI, Branch Protection & Phase 8 Freeze

## Local regression
Run:
- full pytest
- clean-room Phase1→7
- system-browser harness unit tests
- control-coverage checker
- compileall
- pip check
- git diff --check
- repository hygiene
- current data validation
- deterministic generation/hash checks

## GitHub CI
Push/trigger candidate.

Every required check must be GREEN:
- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract
- any additional required certification check

No GO while a required check is red.

## Branch protection
After stable green checks, enable main protection if authorized. Require stable check names and avoid locking out the owner.

If programmatic change is unavailable, update `docs/BRANCH_PROTECTION.md` with exact settings and check names.

## Documentation freeze
Create/update:
- `docs/PHASE_8_IMPLEMENTATION_SUMMARY.md`
- `docs/evidence/phase8/PHASE8_FINAL_ACCEPTANCE.md`
- README/docs index
- evidence registry
- progress tracker
- acceptance checklist

## Final report
Include:
1. starting SHA
2. CI-fix SHA
3. browser-harness SHA
4. certification candidate SHA
5. final implementation SHA
6. optional closure SHA
7. browser product/version
8. controls discovered
9. PASS
10. JUSTIFIED_EXCLUSIVE
11. FAIL
12. Historical Analysis browser run
13. Model browser run
14. 5M scoring browser run
15. saved audience
16. Email export checksum
17. Direct Mail export checksum
18. console/network result
19. DB integrity
20. pytest count
21. clean-room result
22. CI checks
23. branch protection
24. deterministic GZIP result
25. LFS result
26. no dirty override
27. FINAL DECISION

Suggested commit:
`test: certify phase1-7 with system browser and green ci`

Phase 8 is GO only when the system-browser certification passes, all required controls are accounted, full 5M scoring was initiated through UI, and all required CI checks are green.

STOP.
