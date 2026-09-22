# Step 13 - Full Regression and Hygiene

Date: 2026-09-22

## Outcome

**PASS WITH EXECUTION-RECOVERY NOTE**

Every collected pytest case passed on the final implementation, and all required
clean-room, runtime-closure, browser-harness, compilation, dependency, repository,
Git LFS, SQLite, and source-assertion gates passed.

The final pytest result is an exhaustive partition of the 992 collected tests:

- the isolated embedded Phase 1-7 clean-room smoke passed (`1 passed`);
- the remaining suite, including installed-system-browser cases, passed
  (`991 passed`).

This partition was necessary because a permitted single-command rerun became
stuck inside the already-known embedded clean-room smoke after 65 passing tests.
It was interrupted after 15 hours 20 minutes, then the exact blocking test passed
alone in 222.91 seconds. The other 991 tests subsequently passed in one run. No
test was omitted from the final coverage set, and no passing result is inferred
from the interrupted process.

## Regression Discovery and Corrections

The first literal full-suite run completed in 3,312.58 seconds with `929 passed`,
`2 failed`, and `61 errors`.

- All 61 errors were the same sandbox-only Playwright startup failure:
  Windows named-pipe creation returned `WinError 5: Access is denied`. The cases
  passed when rerun with the required local browser-process permission.
- `test_openapi_and_phase1_routes_remain_available` exposed removal of the exact
  legacy OpenAPI phrase `Phase 2 aggregate historical campaign analysis` from
  the expanded Phase 11 application description. The phrase was restored without
  removing the newer runtime description.
- `test_result_api_is_additive_newest_first_bounded_and_preserves_each_submission`
  still assumed the pre-functionalization disconnected runtime. The test now
  explicitly installs a no-op executor for its bounded projection assertion and
  expects the current durable `QUEUED` status/message. Production execution was
  not disabled or weakened.

Both focused failures passed after correction, followed by the exhaustive final
992-test coverage.

## Executed Gates

| Gate | Command/result | Status |
| --- | --- | --- |
| Pytest collection | `992 tests collected` | PASS |
| Embedded Phase 1-7 smoke | `pytest -q tests/test_cleanroom_runner.py` - `1 passed in 222.91s` | PASS |
| Remaining full pytest matrix | `pytest -q --ignore=tests/test_cleanroom_runner.py` - `991 passed in 2405.80s` | PASS |
| Phase 1-7 clean-room | `python scripts/validation/run_cleanroom_phase1_to_phase7.py` | PASS |
| Phase 10 bounded A/B clean-room | `python scripts/validation/run_phase10_bounded_cleanroom.py` - SHA `a2f3230abf6945e8cdccad1bcfd317ac98e5bed0d3c63ccc184bb85c282ef5b7` | PASS |
| Phase 11 bounded A/B clean-room | `python scripts/validation/run_phase11_bounded_cleanroom.py` - SHA `c9ce8954b92b107f506c08e15ec455e68fbc598ee09b284acdc4b8ff261bd109` | PASS |
| Runtime-closure focused suite | coordinator, restart, concurrency, real-app API, and smart-reuse modules - `48 passed in 139.05s` | PASS |
| Browser harness unit contracts | `pytest -q tests/test_system_browser_harness.py` - `13 passed in 0.42s` | PASS |
| Phase 9 multi-branch + all profile contracts | focused multi-branch case plus profile-contract module - `28 passed in 45.65s` | PASS |
| Coordinator lifespan assertion | focused real-lifespan test - `1 passed in 17.27s` | PASS |
| Python compilation | `python -m compileall -q app scripts tests` | PASS |
| Dependency integrity | `python -m pip check` - no broken requirements | PASS |
| Diff hygiene | `git diff --check` | PASS; line-ending notices only |
| Repository/LFS pointer hygiene | `python scripts/validation/validate_ci_hygiene.py` | PASS |
| Local LFS object integrity | `git lfs fsck` | PASS - `Git LFS fsck OK` |
| Canonical SQLite integrity | read-only `PRAGMA integrity_check` | PASS - `ok` in 765.249s |

## Explicit Regression Verification

| Required area | Evidence | Result |
| --- | --- | --- |
| Historical Analysis | Phase 1-7 clean-room Step 3 completed aggregate historical analysis against official imported fixtures. | PASS |
| Model training | Phase 1-7 clean-room trained the governed bounded model and verified its artifact/provenance. | PASS |
| 5M scoring | Read-only canonical inspection found latest scoring run 4 `COMPLETED`, snapshot/scored/row/distinct-person counts all exactly 5,000,000, score range `0.015047932063355144` to `0.15726005776003324`, and 100 rank boundaries spanning buckets 1-100 with population 5,000,000. | PASS |
| Audience Explorer APIs | Phase 1-7 clean-room Step 4 passed options, estimates, filters, search, keyset pagination, profiles, and saved-audience currentness. | PASS |
| Campaign export | Phase 1-7 clean-room Step 5 passed Email and Direct Mail campaign creation/finalization, acknowledgement, deterministic export, CSV safety, and source-drift blocking. | PASS |
| Phase 9 multi-branch behavior | Focused exact-union interoperability test passed. | PASS |
| Phase 10 reuse/build | Bounded A/B clean-room passed reuse, rebuild, drift, rank-only, recovery, and deterministic equivalence scenarios. | PASS |
| Phase 11 exact-result cache | Phase 11 scenario 2 proved `EXACT_RESULT_REUSE`, the same immutable snapshot, zero membership-source calls, and no model/scoring build; smart-reuse focused tests also passed. | PASS |
| All ten profile contracts | Profile-contract module passed for Email, Direct Mail, SMS, WhatsApp, Telemarketing, Paid Social, Paid Search, Mobile Push, Display, and Website Onsite; focused combined gate reported 28 passing cases. | PASS |

The Phase 11 A/B runner passed all ten scenarios in both runs with identical
canonical result SHA, including new intelligence, exact-result reuse,
intelligence reuse, delivery-profile reuse, changed modeling context,
contactability enforcement, paid-media hash-only output, gated profile
availability, corrupt-snapshot repair, and restart recovery.

## Static and Source Assertions

### Application composition

`app/main.py` imports and constructs `Phase11SearchCoordinator`, creates the
production `ResultSnapshotMaterializer`, configures
`configure_phase11_search_executor(phase11_coordinator.submit)`, resumes durable
searches after Phase 10 reconciliation, and resets/shuts down the coordinator in
the lifespan teardown.

Result: **PASS**.

### Executor after lifespan startup

`test_real_application_lifespan_configures_and_resets_executor` passed. It proves
the normal submission executor is non-`None` while the real application lifespan
is active and is reset after shutdown.

Result: **PASS**.

### No production dependency on Step 19/20 server scripts

A source scan of `app/` found no reference to `phase11_step19`, Step 19/20 runner
modules, or `scripts.validation.browser`. Certification server scripts remain
test/evidence tooling only.

Result: **PASS**.

### No unbounded thread per request

The production coordinator contains no `threading.Thread`, `Thread(...)`, or
`_thread.start_new_thread` call. It owns one bounded `ThreadPoolExecutor` with
`max_workers=2` by default and a bounded tracked-run limit of 100; requests submit
to that shared executor.

Result: **PASS**.

## Repository Hygiene After Execution

- The Git index is empty; no files are staged.
- `git status` reports only implementation, documentation, tests, and refreshed
  tracked clean-room evidence.
- No runtime database, WAL/SHM file, generated model, result snapshot, export,
  browser artifact, or log appears in the worktree status.
- Phase 1-7, Phase 10, and Phase 11 temporary clean-room roots were cleaned by
  their runners.
- Canonical data files remain Git LFS managed and `git lfs fsck` passes.
- The SQLite validation opened the canonical database in `mode=ro`; no import,
  training, scoring, or data mutation was performed for the 5M verification.

Step 14 was not started as part of this execution.
