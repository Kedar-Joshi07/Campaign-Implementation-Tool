# 03 — Execute the 20 Real Demo Searches

This is the core preload step. These are durable real-data runs, not test cases.

## 1. Preflight backup and baseline capture

Stop the application cleanly before backup if needed. Create a timestamped local backup of the canonical SQLite DB using SQLite's backup API or another SQLite-safe method. Do not copy a live WAL database naïvely.

Store backup and preload reports under an ignored local path, e.g.:
`output/demo_preload/`

Capture before-state counts:
- search runs by status;
- result snapshots;
- Phase 10 generations by lifecycle/currentness;
- analysis/model/scoring run counts;
- active jobs/orchestrations;
- result artifact directory inventory.

## 2. Start the normal application

Use the ordinary app runtime, e.g.:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Do not use a validation server or injected test executor.

Verify:
- `/api/health`
- `/api/version`
- `/api/data/status`
- `/api/potential-customer-search/options`

## 3. Resolve one common Campaign Context

From live backend options, select a context that has the best chance of already matching current READY Phase 10 intelligence.

Use one product or one coherent existing product set. Keep these identical for all 20 runs:
- `product_ids`
- `campaign_types`
- `campaign_categories`
- `offer_types`
- `historical_campaign_channels`
- campaign channel implied by chosen delivery profile

Do not guess option values. Read live options and validate every selected value.

Record this as `common_context` in the run manifest.

## 4. Load exact scenario definitions

Read `scenarios.json` from this prompt pack.

For each scenario build a `PotentialCustomerSearchRequest`:
- campaign_name = `DEMO S## — <scenario name>`
- description = `Preloaded real-data POC demo scenario ##. Canonical preload at f2b98ad.`
- planned_launch_date = null unless the UI/API requires a real future date; if required, use one consistent future date and record it.
- context = common_context
- criteria = exact scenario criteria plus pack defaults
- export_profile = common export profile

Do not include estimated pre-score population in the API request; it is reference metadata only.

## 5. Submit sequentially

For scenario 1 through 20:

1. POST `/api/potential-customer-search/runs`.
2. Persist returned `search_run_id` immediately in a checkpoint file.
3. Poll the production status/result endpoint every 5 seconds.
4. Capture lifecycle progress snapshots when state/version changes.
5. Wait for terminal state before starting the next scenario.
6. If COMPLETED, fetch the full Result Detail projection and persist only non-PII metadata into the preload manifest.
7. If BLOCKED/FAILED, capture safe issue object and stop the batch unless the failure is explicitly demonstrated to be isolated and retryable without altering scenario semantics.

Do not run the twenty jobs in parallel.

## 6. Required per-run evidence

Capture:
- scenario id/name;
- normalized context and criteria hashes;
- `search_run_id`;
- `targeting_context_id`;
- generation/analysis/model/scoring IDs from technical details;
- result snapshot id;
- result source (`EXACT_CACHE`, reuse/build equivalent as implemented);
- status/lifecycle status;
- final state_version;
- selected_count;
- currentness;
- processing_seconds;
- created/completed timestamps;
- final progress percent/count/unit;
- ETA behavior summary;
- download_eligible;
- issue object if present;
- whether count is >100;
- whether scenario is `DEMO_READY`.

Also compare scenario 2–20 against scenario 1 to show that targeting-only changes reused compatible intelligence rather than retraining/rescoring.

## 7. No silent fallback

If any selected_count <=100:
- keep the run unchanged;
- mark it not demo-ready;
- calculate a separate fallback suggestion (normally next broader Match Strength) using current exact data;
- do not submit the fallback unless explicitly instructed by the user.

## 8. Batch outputs

Create under `output/demo_preload/`:
- `demo_20_scenario_runs.json`
- `demo_20_scenario_runs.csv`
- `demo_20_scenario_progress.jsonl`
- `demo_20_scenario_preload_report.md`

The Markdown report must include a 20-row table with scenario name, exact selected count, status, result source, duration, currentness, demo-ready flag, and run ID.
