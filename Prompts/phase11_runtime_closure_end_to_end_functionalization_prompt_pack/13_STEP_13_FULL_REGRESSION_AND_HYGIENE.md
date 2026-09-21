# Step 13 — Full Regression & Hygiene

Run:
- full pytest
- Phase1–7 clean-room
- Phase10 bounded clean-room
- Phase11 clean-room
- new runtime-closure tests
- browser harness/unit tests
- compileall
- pip check
- git diff --check
- repository hygiene
- Git LFS validation
- SQLite integrity_check where applicable

Explicitly verify no regressions in:
- Historical Analysis
- model training
- 5M scoring
- Audience Explorer APIs
- Campaign export
- Phase9 multi-branch behavior
- Phase10 reuse/build
- Phase11 exact-result cache
- all ten profile contracts

Run static/source assertions:
- app.main configures Phase11 coordinator;
- normal executor is not None after lifespan startup;
- no production dependency on Step19/20 server scripts;
- no unbounded `threading.Thread` per request in production coordinator.

Create:
`docs/evidence/phase11_runtime_closure/13_REGRESSION_HYGIENE.md`

STOP.
