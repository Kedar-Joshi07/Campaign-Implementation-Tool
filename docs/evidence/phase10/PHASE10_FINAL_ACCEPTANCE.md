# Phase 10 Final Acceptance

Generated: 2026-09-15

## Candidate decision

`READY_FOR_EXACT_SHA_CI`

All local implementation, browser, clean-room, full-5M, regression, repository, lineage, and privacy gates are green. Final `GO` is conditioned only on GitHub Actions passing every required job for the exact committed candidate SHA. The final result and exact run are recorded in `PHASE10_FINAL_FREEZE_REPORT.md` after remote verification.

## Functional acceptance

- Exact canonical Modeling Context is separate from Phase 9 Campaign Context and prospect targeting.
- Historical, model, scoring, rank, and analytics compatibility layers fail closed and rebuild only invalid downstream work.
- No latest-run fallback exists in the normal preparation or Phase 9 bridge.
- Durable orchestration supports exact active-work joining, idempotent READY reuse, progress polling, safe retry, and recovery from verified state.
- READY publication atomically binds generation, orchestration, and the Phase 9 scoring source.
- Phase 9 preview, recommendations, multi-branch Target Group save, Campaign Draft, currentness, legacy interoperability, and governed export lineage remain compatible.
- Lifecycle reconciliation is non-destructive and preserves protected lineage.

## Certification evidence

| Gate | Result |
|---|---|
| Final Step 16 full pytest | PASS — 647 passed in 1,600.94s |
| Phase 1–7 clean-room | PASS |
| Phase 8 browser harness | PASS — 13 passed |
| Phase 9 focused regression | PASS — 74 passed |
| Phase 10 focused regression | PASS — 89 passed |
| Phase 10 bounded clean-room | PASS |
| Installed-Chrome Phase 10 business flow | PASS |
| Step 14 control coverage | PASS — every reachable control terminally classified |
| Clean-head full 5M scoring | PASS — 5,000,000/5,000,000 distinct |
| Score integrity | PASS — zero duplicate, invalid, missing, or extra rows |
| Deterministic rescore | PASS — 256 rows, max absolute difference `0.0` |
| Rank and analytics | PASS — 100 boundaries and one current snapshot |
| Multi-branch exact union | PASS — 146 distinct, zero duplicates |
| Saved Target Group and Campaign Draft | PASS |
| Pre-export contact PII boundary | PASS |
| SQLite integrity | `ok` |
| Compileall / pip check / diff hygiene | PASS |
| Repository hygiene / Git LFS fsck | PASS |

## Full-scale trusted lineage

| Item | Exact value |
|---|---|
| Clean baseline HEAD | `a24a24d8f809405533ad342d1ab71e5a425eaa84` |
| Browser | Google Chrome `153.0.8010.36` |
| Modeling Context SHA | `27ee771a07470729ace3cd219106942813efe58d04f76fa055b044c2317d05f1` |
| Intelligence key SHA | `6fe4c881a2a7b99b6d4128b401ad944aa95589c43028e6279773685bf7e8f420` |
| Orchestration / generation | `6` / `3` |
| Analysis / model / scoring | `3` / `3` / `3` |
| Model artifact SHA | `7bcd7b61f926a04ea648bb865ba397fb096cdb2b3cd8a40b09806792d9b33164` |
| Target Group / Campaign | `1` / `1` |
| Target Group branch SHA | `9430cde645b19f986691a3bd6a5a04f1618e7e53c79c243b88e4f6b6a605b2e6` |

## Release boundaries

- Full 5M scoring is release-certification work and is not placed in normal CI.
- Normal CI runs bounded Phase 9 and Phase 10 contract/UI tests plus the existing Phase 1–7 clean-room.
- Contact PII remains unavailable to planning/orchestration/preview surfaces and requires finalized-Campaign export acknowledgement.
- This POC remains single-node SQLite with local artifacts and no send/activation integration.

## Finalization condition

Change this candidate decision to `GO` only after the `CI` workflow is queried by the exact committed candidate SHA and the following jobs all conclude `success`:

- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract, including bounded Phase 9 and Phase 10 validation
