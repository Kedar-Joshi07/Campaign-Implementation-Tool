# Phase 11 Step 12 — Results History and Result Detail UI

## Outcome

Step 12 is implemented as an additive, database-backed business results surface.
The existing Step 8 submission/status endpoints and response shape remain intact;
the richer history and detail projections are exposed separately:

- `GET /api/potential-customer-search/results`
- `GET /api/potential-customer-search/runs/{search_run_id}/result`

No application server, canonical database, import, historical analysis, training,
scoring, ranking, 5M filtering, export, or campaign activation was run.

## Results history

The Results screen now reads immutable `campaign_search_runs` from SQLite in
newest-first order. It uses a maximum page size of 100 at the API boundary and
20-row keyset pages in the browser. "Load Older Searches" sends the last visible
run ID as `before_search_run_id`.

Every submission retains its own card and run ID. Browser rendering uses a map
keyed by `search_run_id`, so an overlapping page or refresh updates an existing
card instead of inserting a duplicate. An intentionally repeated identical
submission test proves both durable rows remain visible independently.

Cards present:

- search/run ID and Campaign Name;
- created/completed timestamps and status;
- selected products with business names;
- Campaign Type, Category, and Offer summary;
- delivery channel/profile and Match Strength;
- targeting summary and selected Potential Customer count;
- the exact governed business result-source label;
- processing duration;
- View Result;
- Download Potential Customers only when the API marks the result eligible.

The UI handles queued/processing, completed, blocked, and failed rows. Automatic
refresh occurs only while at least one row is `QUEUED` or `PROCESSING`, every
five seconds, for at most 60 cycles. Navigation away cancels the timer. Manual
refresh resets the bound.

## Result detail

The result detail API reopens the immutable context, canonical targeting
criteria, and saved filter branches from persisted contract JSON. It returns:

- exact campaign context and targeting criteria;
- exact selection mode, requested count, and resolved count;
- result-source explanation and currentness;
- aggregate scoring and demographic summaries;
- immutable snapshot/generation/model/analysis provenance;
- delivery/download profile;
- audit identifiers and hashes for optional technical disclosure.

For a completed result, detail loading validates the physical snapshot and
manifest against the run and READY generation before reporting it as current.
A corrupt or missing artifact is presented as stale and cannot become download
eligible.

The technical section is collapsed by default. Artifact filesystem paths are
never projected. The service recursively refuses response objects containing
contact-PII field names, and browser rendering uses DOM `textContent` rather
than HTML injection. Only analytical membership and aggregate information are
described on screen.

## Result source labels

The registry values map exactly to the required business terms:

| Registry source | Business label |
|---|---|
| `EXACT_RESULT_REUSE` | Reused previous exact result |
| `INTELLIGENCE_REUSE` | Reused existing targeting intelligence |
| `NEW_INTELLIGENCE_BUILD` | Prepared new targeting intelligence |

## Download boundary

The Step 12 UI implements the eligibility gate and conditional link rendering.
The backend deliberately reports `download_eligible=false` until Step 13 adds
the governed export engine. This avoids offering a link that cannot yet satisfy
the privacy, permission, and audit contract. Step 12 does not create a partial
or fake download.

## Validation

All backend fixtures used small temporary SQLite databases and temporary result
artifact roots. The browser tests used the installed system Chromium through
the repository's Playwright harness with request interception.

| Validation | Result |
|---|---:|
| Final Step 12 API/service/static suite | 5 passed, 2 deselected in 24.84s |
| Final updated history system-browser check | 1 passed in 20.81s |
| Responsive detail system-browser check | 1 passed in 17.13s |
| Step 12 API/service/static tests plus focused Step 8/11 regression | 9 passed, 2 deselected in 26.56s |
| Step 12 history/detail system-browser tests plus navigation regression | 4 passed, 4 deselected in 29.39s |
| Completed materialized snapshot/detail projection correction check | 1 passed in 31.78s |

Covered behavior includes newest-first keyset paging, API bounds and safe 404s,
repeated identical submissions, old status-contract compatibility, all terminal
status rendering, active-only bounded polling, overlapping-page de-duplication,
conditional download rendering, exact context/criteria/selection reopening,
all three exact result-source labels, current completed snapshot validation,
aggregate score/provenance display, no-contact-PII projection, default-collapsed
technical details, mobile 390px layout, and retained business navigation.

## Stop boundary

Earlier uncommitted Phase 11 changes were preserved. Nothing was staged,
committed, pushed, frozen, or exported.

`STOP_AFTER_STEP_12`

Step 13 and subsequent prompts have not been started.
