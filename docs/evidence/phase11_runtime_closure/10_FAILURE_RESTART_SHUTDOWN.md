# Step 10 - Failure, Retry, Restart, and Shutdown Certification

## Result

**PASS** - Failure propagation, safe retry behavior, exact-cache corruption handling, export abort auditing, unexpected coordinator failure containment, real-Uvicorn restart recovery, and shutdown behavior were certified against the production Phase 11 composition. No canonical data or valid analytical asset was corrupted or deleted.

## Baseline and scope

- Branch: `main`
- HEAD: `db3ceabc492ec17759dfdf6f6ae1186ac86ca77e`
- Production composition: `app.main:app`, `Phase11SearchCoordinator`, `ResultSnapshotMaterializer`, and the existing Phase 10/model executor
- Real restart server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010`
- Restart database: one generated, isolated schema-version-18 database under `.tmp`; removed after certification
- Canonical `data/campaign_poc.db`: not used or modified by the failure/restart fixture

## Failure and retry matrix

| Required case | Certified behavior | Result |
|---|---|---|
| Phase 10 `BLOCKED` | Phase 11 persisted `BLOCKED`, no result snapshot or selected count, and returned only a stable business-safe message | PASS |
| Phase 10 `FAILED` | Phase 11 persisted `FAILED`, no result snapshot or selected count, and did not expose Phase 10 implementation detail | PASS |
| Snapshot materializer failure | Safe wrapper persisted `FAILED`; no snapshot row, fake `COMPLETED` state, selected count, or collaborator exception text was stored | PASS |
| Retry after materializer failure | A new durable search with the same valid identity completed and published exactly one snapshot; the failed run remained terminal and unchanged | PASS |
| Corrupt exact-cache snapshot | Exact reuse was rejected; the existing immutable identity was marked/repaired through materialization and fully revalidated before reuse | PASS |
| Export disconnect/abort | Export audit became `ABORTED`, row count remained zero, checksum remained null, a safe message was stored, and no PII/contact snapshot was created | PASS |
| Export source drift | Export audit became `FAILED`, currentness became `STALE`, no rows/checksum were reported, and the snapshot was marked stale | PASS |
| Unexpected coordinator exception | Active `QUEUED`/`PROCESSING` run became safe `FAILED`; private exception text was absent, tracking was cleared, and the application remained usable | PASS |

The materializer retry is intentionally a new search run. Terminal `FAILED` history is immutable; Step 10 did not reset or rewrite the failed run.

## Real Uvicorn restart certification

### Fixture

The isolated database contained 40 customers, 41 campaign-sales rows, and 60 demographic rows. Product `P2` had one historical observation, making it a valid selectable product but legitimately ineligible for model training. This created a deterministic terminal `BLOCKED` path without test-executor injection, full-scale work, or changes to the canonical database.

An initial non-certifying fixture attempt correctly failed closed because the added `P2` row made the recorded campaign-sales count stale. The generated fixture was discarded, recreated with its 41-row provenance reconciled, and then used for the certification below. No product implementation was changed to bypass that validation.

### Process A

1. Real Uvicorn started with `app.main:app` and reported a healthy schema/version-18 database.
2. `POST /api/potential-customer-search/runs` returned `201` and created search 1 as `QUEUED`.
3. The production coordinator advanced search 1 to `PROCESSING` with the safe message that targeting intelligence was being prepared.
4. The application was stopped by the normal console interrupt while the durable search was `PROCESSING`.
5. After shutdown, the database retained:
   - search status `PROCESSING`;
   - one Phase 10 orchestration;
   - zero historical analyses at that point;
   - zero model runs;
   - zero scoring runs;
   - zero result snapshots.

No terminal state was fabricated during shutdown.

### Process B

The same `app.main:app` and same database were restarted. Startup logs recorded:

```text
Phase 10 startup reconciliation completed | resumed_orchestrations=1
Phase 11 startup reconciliation completed | scheduled_searches=1
```

API polling observed `PROCESSING` repeatedly before the resumed search reached the correct terminal state:

- Phase 10 orchestration 1: `BLOCKED`, stage `BLOCKED`;
- Phase 11 search 1: `BLOCKED`;
- persisted safe error: `This search cannot proceed with the current intelligence.`;
- projected business-safe message: `Your search is saved but cannot proceed with the current targeting intelligence.`;
- processing duration: 56 seconds;
- application health after the terminal transition: `ok`.

Final analytical counts were:

| Registry | Count |
|---|---:|
| `phase10_orchestration_runs` | 1 |
| `historical_analysis_runs` | 1 |
| `model_runs` | 0 |
| `scoring_runs` | 0 |
| `jobs` | 0 |
| `campaign_result_snapshots` | 0 |

The single historical analysis is the legitimate resumed eligibility evaluation. There were no duplicate analyses and no model, scoring, job, or snapshot artifacts. Uvicorn process B remained healthy after the resumed failure and was then stopped; port 8010 had zero listeners. The generated temporary database was removed.

## Shutdown certification

The coordinator shutdown tests verified that:

- shutdown changes the coordinator to non-accepting before pool closure;
- a polling worker wakes immediately rather than waiting for its 30-second interval;
- durable `PROCESSING` state remains `PROCESSING` for the next startup;
- active-search tracking is empty after shutdown;
- submit-after-shutdown raises the stable `shutting down` error;
- queued futures are cancelled through bounded executor shutdown;
- no unhandled coordinator future/thread failure is emitted;
- application lifespan resets the Phase 11 submission seam;
- terminal `COMPLETED`, `BLOCKED`, and `FAILED` runs are not resubmitted;
- the pre-existing model/scoring executor shutdown contract remains `wait=False, cancel_futures=True`, is idempotent, and clears its singleton.

The real FastAPI lifespan test also completed reuse, controlled `BLOCKED`, controlled `FAILED`, result-detail, and governed-export calls before cleanly closing the lifespan. The controlled failure did not terminate or poison the application.

## Executed tests

All tests ran sequentially.

```text
python -m pytest \
  tests/test_phase11_smart_reuse_engine.py::test_phase10_terminal_state_propagates_safely_without_fake_result \
  tests/test_phase11_smart_reuse_engine.py::test_materializer_failure_fails_closed_and_new_run_retries_cleanly -q

3 passed in 22.39s
```

```text
python -m pytest <13 focused corruption/export/coordinator/restart/lifespan/shutdown cases> -q

13 passed in 81.11s
```

The focused matrix included:

- corrupt checksum/count exact-cache rejection and deterministic revalidation;
- corrupt snapshot repair to the original immutable identity;
- disconnect and consumer-close export aborts;
- export source-drift failure/currentness handling;
- coordinator unexpected-exception containment;
- polling-worker shutdown and submit rejection;
- processing-run restart and single resume;
- resumed snapshot publication idempotency;
- terminal-run exclusion from startup resume;
- real lifespan reconciliation/shutdown order;
- real-app failure containment and governed export;
- unchanged model/scoring executor shutdown.

The entire modified smart-reuse module was then rerun:

```text
python -m pytest tests/test_phase11_smart_reuse_engine.py -q

25 passed in 42.87s
```

## Conclusion

Every Step 10 requirement is satisfied. Failure paths fail closed, retry creates new durable work without rewriting history, restart recovery is automatic and idempotent, shutdown preserves durable state and rejects new work, and the existing model/scoring executor shutdown behavior is unchanged.

Step 11 was not started.
