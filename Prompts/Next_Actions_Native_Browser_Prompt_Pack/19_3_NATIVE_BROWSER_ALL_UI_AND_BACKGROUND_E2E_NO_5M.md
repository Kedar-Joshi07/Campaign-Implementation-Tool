# Prompt 19.3 — comprehensive native-browser UI and background functionality; no 5M scoring

## Common execution contract

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`. Audited baseline: `9bea771940f930504ee8635c7b14fc988a37568c`. Schema at that baseline: 33. Work on the actual current checkout or a verified descendant; never reset newer work to this SHA. Run `git rev-parse HEAD`, `git status --short`, and read applicable `AGENTS.md`. Record starting/candidate SHA and local diff identity when uncommitted. Preserve unrelated changes and all previous evidence.

Read this pack's `00_README_START_HERE.md`, `01_GUARDRAILS_SCOPE_AND_ORDER.md`, and `02_PENDING_REGISTER_AND_BASELINE.md` first. Discover actual paths with `rg`; suggested new paths are not existing commands. Complete implementation, tests and evidence, not just a plan. If a dependency is genuinely missing, report the exact blocked work while continuing independent tasks.

Keep v1/v2 probability semantics, calibrated artifacts, historical readers/exports, BROAD=.60, explicit v2 .50, default v2 .70 and probability governance intact. Keep v3 PRODUCT_BUYER_SIMILARITY, BUYER_PROFILE_DISTANCE_V1, inclusive minima .50/.60/.70/.80/.90, ANY/max selected-product policy, support floors 200/160/40, support-aware split V2, currentness and immutable lineage. Preserve original 20-scenario JSON and current 10,000 demo gate. Never change scores, filters, products, data or pass criteria to force counts or a GO.

All mutation/testing uses a dedicated disposable database, artifact root, browser profile and downloads directory on loopback. No operator DB import/replacement/migration, actual campaign sending, contact uploads or deployment. No commits, pushes, PRs, workflow dispatch or branch-setting changes unless authorized in the execution session. Preparatory code/test work continues without that remote authority; do not invent remote success.

Browser functionality scope excludes canonical 5M scoring, calibration rescoring of 5M, canonical bulk import and 5M performance certification. It uses bounded synthetic fixtures and real application/backend workers. No mocked successful API responses or fake worker completions as primary proof. The full browser prompt defines a hard row cap and fail-closed guard. Any future canonical-scale recertification is a separate opt-in stage, never invoked by browser/controller defaults.

Evidence must distinguish actual native headed browser execution, automated browser checks, backend-only tests, retained-component harness checks, fixture results, recorded earlier 5M results and fresh remote CI. No PII/secrets/raw worker tokens in shared evidence. Keep screenshots/traces of the synthetic QA environment locally for inspection; do not automatically save browser screenshots to ChatGPT Library.

Completion response: actual SHA/tree identity; files changed; defects reproduced and fixed; schema/API/data impact; exact commands/results; coverage/evidence pointers; statuses PASS/FAIL/BLOCKED/NOT_RUN; preserved contracts; remaining limitations; stage GO/NO-GO; concrete next action. Runtime, native UI, fresh bounded v3, recorded 5M, legacy probability, predictive claims, scoped POC and overall release are separate verdicts.


## A. Goal and prerequisites

Test every implemented current UI control, its relevant conditional states, and its actual backend processes using installed Chrome or Edge. This is a functionality test, not canonical five-million-row scoring or scale certification. Read the coverage contract and functional matrix in this pack. Complete 19_2's safe launcher/fixtures/guard first; if absent, implement those prerequisites before running any mutating UI action. The independent fresh v3 runner from 19_1 can provide the bounded fresh-build prerequisite without invoking legacy full-fresh 5M generation.

Do not stop after opening Home or completing one search. Inventory all current business controls and retained analyst/admin component controls, map the real background actions, execute cases, repair authorized defects through 19_4, and close coverage. No all-UI GO is allowed while an implemented required control or state remains untested or blocked. Missing browser or other prerequisites remains BLOCKED, not a silent pass.

## B. Use an actual installed native browser

Use `scripts/validation/browser/system_browser.py` and its advertised resolver/session interfaces where compatible. Resolve explicit SYSTEM_BROWSER_PATH first, then requested installed Chrome/Edge. On Windows use existing installed Chrome/Edge defaults or a verified override. On other supported local systems use a verified installed executable path. Primary requested run is **headed** with a fresh QA-only profile and downloads directory. Record executable, product version, Playwright/package versions, viewport and headless=False. Browser automation may drive the native browser; do not substitute a downloaded Playwright Chromium bundle, a screenshot-only simulation, or a cloud browser while labeling it native desktop.

Use the pinned browser lock. Do not run `playwright install` to silently substitute a bundled binary. If only headless/CI execution is possible, report its real scope separately and leave native headed certification pending. Honor the execution environment's browser-control skill/capability instructions if available. A real browser-launch permission failure is a named environment block; do not suppress it.

Do not attach to the operator's personal logged-in profile. Run on loopback only, with synthetic fixtures and no external campaign/provider traffic. Local trace inspection is allowed; uploading traces to external sites is unnecessary.

## C. Isolated application and no-5M guard

Start actual production frontend/FastAPI app and normal lifespan/coordinator/workers against the dedicated QA root. All DB, imports, catalog, profiles, scores, snapshots, feedback, logs, browser profiles and downloads stay inside that root. Set database and expected-fixture-row configuration before app import. Verify root/path isolation before startup, not only before a button click.

Use the following explicit modes:

1. **BUSINESS_NATIVE:** real production business routes, actual workers and ready or freshly built bounded synthetic intelligence.
2. **RETAINED_COMPONENT_NATIVE:** a labeled test-only harness that loads unchanged retained markup/controllers/events and real APIs. It exposes test navigation into otherwise hidden components without changing production navigation.
3. **FAULT_NATIVE:** the same real bounded app with named, isolated fault injection or actual transport interruption. Never fake a successful API/worker response.

Default QA demographic population ≤2,000. A separately named fixture may reach 20,000 solely to test the unchanged 10K qualification branch. Actual row count must never exceed the fixture manifest cap. A UI scoring/prepare control may execute real **bounded scoring**; no canonical 5M job, calibration rescore, LFS population import, full5m validation runner, or canonical bulk regeneration belongs in this test.

The guard covers direct score endpoints and indirect search preparation, Phase 10 dependencies, startup resume, feedback decisions and worker dispatch/publication. Record worker-admitted populations and source paths. If a job attempts canonical/root/over-cap work, reject before its body runs, record the violation and stop the unsafe scenario. Do not kill an already-started 5M job and then claim the guard passed. After each suite assert zero canonical-scale scoring dispatches, no foreign DB/artifact mutations, and no leftover unexpected active heavy jobs.

## D. Discover controls and define coverage before clicking

Rebuild the HTML/JS/API control inventory at the actual current SHA. Use and extend the existing build_ui_control_inventory/check_ui_control_coverage helpers; do not trust their older generic page guesses as a complete v3 map. Start with STATIC_UI_CONTROL_SEEDS.json and API_ROUTE_CATALOG.json in this pack, then inspect actual runtime DOM.

Enumerate buttons, links, inputs, file selectors, selects/options, checkboxes/radios, details/summary disclosures, tabs, menu options/chips, search/clear/select-all widgets, row actions, pagination, resize handles, keyboard controls and generated export/retry/feedback actions. Include every mode/profile/channel alternative. Forms/details containers map to actual tested children; read-only text is not invented as an interactive control.

Each record must name business/retained/global scope, view/state, source/locator/label, enable conditions, fixture, scenario, expected effect, actual browser/network/backend/file evidence, status and unresolved reason. Runtime controls created after a search/reopen/profile switch join the denominator. A source-backed deliberately nonexistent feature is listed separately, not scored PASS. A disabled action requires guard proof and a valid positive case when prerequisites can be met.

Cover the current business routes Home, Find Potential Customers, Results and Result Detail. The seven retained view families are saved-target-groups, campaigns, insights, historical-analysis, audience-explorer, data-status and model-training. Legacy overview/campaign-planner route aliases must map to their current business equivalents. Test normal production hashes for hidden retained routes do not accidentally expose them. Hidden view grouping is presentation metadata, not RBAC.

For retained component testing, use documented test navigation and the actual event handlers/modules. Do not claim a hidden=false DOM toggle proves normal user navigation. Retained-component controls still need actual functional actions and backend assertions; testing only their hidden state is insufficient for this user's all-functionality request.

## E. Observe actual background behavior

Attach console/page-error, failed-request, response, job/status and artifact/state observers before the first action. Capture sanitized method/path/status/discriminator/criteria identity and correlation IDs. Read QA SQLite/state and files to prove effects; do not expose contacts or ownership tokens in shared reports.

For each mutating action prove the actual sequence where applicable:

UI input/action → validated API request → durable context/run/attempt/job → real worker/coordinator → DB/cache/profile/generation/snapshot/export/feedback transition → visible completion/error/result.

A case passes only when independent expected outcomes match UI and persisted results. Browser success text alone is insufficient. A direct API/service call cannot replace the tested UI action. Setup helpers may prepare valid prerequisites, but the action under test is clicked/typed/selected through the native browser.

Use state/locator/network waits with bounded deadlines and diagnostic failure output, not long blind sleeps. Poll durable jobs, checking truthful queue/processing times, monotonic materialized counts, completion count and ETA uncertainty. Required CPU work may continue under a reasonable predeclared functional timeout; do not weaken assertions to hide slowness. Host interruptions are classified separately with actual evidence.

## F. Business navigation and Home

Exercise all three navigation tabs, Home shortcuts/recent cards, result-detail links, page title, aria-current, hash deep links, aliases, refresh, browser back/forward, repeated same-route click, invalid/unknown route/run ID, stale asynchronous navigation response, multiple tabs and page close/reopen.

Collapse/expand sidebar through both controls; drag its resize handle through permitted widths; keyboard adjust if implemented; confirm persisted preferences, correct aria-expanded/valuenow, narrow-screen behavior and no focus trap. Test backend-status retry, online/offline/degraded state, overview loading/empty/error/retry and current counts against the QA DB/API. Navigation and refreshing ready data must not start unwanted training/scoring.

## G. Find Potential Customers — every field/widget and score mode

For each dynamically built multi-select, test opening, searchable options, exact selection, deselection, chips, clear/select-all when implemented, keyboard arrows/Enter/Space/Escape, outside click, disabled unavailable choices, no-results search, refresh/catalog change and preserved valid selections. Include products; campaign types/categories; offer types; historical channels; age groups; income groups; gender; states/regions; education; marital status; employment; residency/type; family attributes and all advanced fields actually present.

Check normalization, field interdependencies, inclusive numeric bounds, invalid min>max, empty required products, missing/unknown options, whitespace/name inputs, reset/defaults, advanced disclosure, and form-submit validation. Verify exact request values and no duplicated/ghost product/criteria IDs.

V3 uses explicit version3/PRODUCT_BUYER_SIMILARITY and minimum 50/60/70/80/90 with cumulative >= semantics. V2 retains its original probability buckets/discrete bands and frozen default. Switch modes in both directions, including while preflight/options are pending: incompatible fields must not leak and a late old-mode response must not overwrite new state. Reopening a saved v1/v2 run uses stored score semantics. Distinguish optional unavailable probability from similarity readiness and do not fill it with zero/current.

Test ALL_MATCHING and explicit TOP_N/target count if implemented; qualified vs selected counts are separate. V3 percentile-only fields are disabled/omitted as intended. Invalid values/bool/NaN/mixed fields receive correct errors through normal validation. Pure UI validation cases produce no duplicate jobs.

## H. Preflight, submit, workers, progress and retries

Exercise ready/current preflight, a valid zero, absent intelligence, building/waiting, unsupported product, insufficient history, split solver unresolved, stale source/catalog and network/service failures. Missing/unprepared count is unknown/null, not zero. Exact fixture counts use an independent oracle; check OR dedup, threshold boundaries and matching materialized count. No requirement that a bounded QA case falsely qualifies for 10K.

Fresh bounded build: submit through the real form with no profile/generation, observe actual support-aware split/profile construction, scoring under cap, verification/attestation and result materialization. Ready bounded reuse: repeat same request and verify exact snapshot/intelligence reuse with no new score/profile job. Change threshold/filter/channel and prove permitted reuse/cache separation. Change selected products and prove exact context eligibility rather than global/category fallback.

Exercise double-click/rapid submit, queue capacity, simultaneous same/different context searches, dependency sharing, refresh/navigation while processing, lost network/rejoin, transient injected failure and displayed retry, permanent support block with no retry loop, shutdown and durable restart. Cancellation is tested only if actually implemented; otherwise record source-backed absence, never invent a cancel button.

Verify attempt and job IDs, guarded transitions, ownership token rotation privately, stale-worker rejection, no duplicate active work, immutable old attempts and one final snapshot. Inject only bounded faults inside QA runtime. The unknown/unresolved split is a distinguishable capacity/retry outcome, not mathematical infeasibility.

## I. Results, history, details and reusable membership

Test refresh, empty/error/retry, history paging/load older, all current sort/filter/row actions, opening valid/invalid/deleted IDs, back navigation and status updates. Reopen completed, queued, blocked, failed, stale, v1, v2 and v3 examples with their original labels and metadata. Check rerun-with-these-choices preserves original context/criteria/version and updates only deliberate edits.

Inspect result context/targeting/selection/score summary/provenance/download/feedback/technical sections and every disclosure/button. Counts equal independent preflight, immutable membership and reopened result. Full-precision scores decide membership before display rounding. Technical details are stable safe identifiers, not paths/PII/lease secrets. A completed stale result remains historical rather than pretending to be a new current generation.

Buyer similarity explanation uses actual winning profile distances/support and declared sample size; it never claims purchase probability, percentile, causal drivers or validated lift. A generic historical scenario name is not proof of predictive confidence. No off-by-one/member duplication from overlapping filters or paging.

## J. Native downloads, export profiles and feedback files

Enumerate actual channel/profile registry and API availability, including current v3 analytics/contact-only versions and legacy schemas. For every implemented selectable available profile, perform a native browser download with synthetic contacts, read actual file contents, and independently assert header/version/hash/member/consent/identifier/currentness/CSV-formula behavior. Exercise unavailable/unsupported/stale profiles, missing identifiers, opt-out, do-not-call, export audit counts, repeated export, abort and retry. Selecting a channel does not send a campaign or hit an external provider.

Selected analytical members and exportable contacts differ legitimately; UI counts/audit exclusions must reconcile. Filenames/disposition/content type and path safety are checked. Downloads stay in QA root and evidence uses hashes/counts, not real contacts.

Download CSV and JSON feedback templates; upload frozen valid synthetic feedback through the actual file input, then wrong-format/missing-columns/malformed-JSON/oversize/duplicate/wrong-person/future-or-invalid-date/mixed-mode/stale-membership cases supported by existing validators. Prove accepted/rejected batch writes, rollback/idempotence, run/person/profile lineage and displayed status. V3 feedback is retained with origin; it is not passed as similarity raw score into purchase calibration. A separately valid bounded v1/v2 feedback fixture can test the existing statistical gate without changing canonical history. No 5M calibration publication/rescore is admitted.

## K. Retained analyst/admin components and their real workers

Use the labeled isolated harness for each retained component; do not add production navigation.

**Historical Analysis:** refresh options/history, every campaign/product/channel/date/outcome filter, reset, analyze, selected/known-positive/unlabeled/baseline comparison controls, all breakdown tabs/profile dimensions, recent reopen, empty/error/retry and normalized filters. Independently verify analysis rows, selected/distinct/purchase counts, saved results and aggregate tables.

**Model Training:** select analysis, all training configuration/options, required validation, train, actual bounded job/polling/heartbeat/terminal states, candidate metrics/role details, saved model reopen and stale source failures. Use a bounded legacy-positive fixture with genuinely independent synthetic campaign groups so existing governance runs unchanged. Also prove a one-component fixture rejects correctly. Do not claim this fixes canonical probability topology or produces a v3 similarity model from the legacy button.

**Prospect Scoring:** select compatible model, invoke actual score control only with bounded QA data, poll genuine worker/generation, inspect source/currentness/artifacts and failure/retry/idempotence. The guard prevents canonical 5M execution. Count all admitted populations and verify expected row identity; this is UI/background functionality, not scale certification.

**Audience Explorer:** prepare/retry, score-run selection, all numeric/categorical/rank/percentile/decile filters, reset, estimate, search, pagination/load more, profile dimensions/comparison tabs/charts, saved-audience naming/save/reopen and invalid/empty/stale cases. Check genuine bounded analytics/rank/cache/membership/currentness. Preserve legacy rank semantics rather than calling percentiles buyer similarity.

**Data Status:** refresh, summary/status/reconciliation/import history and errors based on real fixture imports. No import/upload UI exists merely because a CLI import service exists; classify correctly. Use fixture setup/backend import hooks to test source changes, not an invented UI control.

**Saved Target Groups / Insights:** enumerate implemented refresh/list/open/details/preview/rerun/delete/paging or other actual actions. Read-only aggregates get rendering/source checks. A placeholder with no implemented behavior is documented as such, not a fictional pass or a reason to delete the view.

**Retained Campaign Planner:** test all five steps, context save/edit/back/next, targeting fields, match-strength recommendation, intelligence prepare/retry/status/attach/detach when implemented, preview/error/retry/load more, review/name/notes and save-target-group/create-draft. Exercise real Phase 10/targeting APIs and bounded workers; valid legacy-compatible grouped fixtures allow positive flows. Data-blocked cases must not bypass governance to enable Next.

**Campaign Builder:** new draft, audience selector, details/validation/all wizard steps/back/review/save/update/reopen/finalize/export/history/status controls. Verify actual local campaign state transitions, immutable audience binding, currentness, audit/idempotence and CSV. Finalize is a local state action, not campaign activation. Check disallowed stale/invalid/export states and duplicate submission.

## L. Responsive, keyboard, asynchronous and negative-state coverage

Run full functionality at one desktop viewport, then relevant navigation/forms/menus/detail/upload/download guards on1920×1080,1366×768,1024×768,768×1024 and390×844. These are local browser viewports, not physical-device certification. Test200% zoom, scroll/overflow, dialogs/menus clipping, hidden focus, focus restoration, accessible labels/tab order/keyboard selection and status live regions. Do not force disabled controls on to get coverage.

Simulate slow/offline/reconnected transport or controlled server delays while retaining real responses. No route.fulfill success stubs. Test stale async responses, duplicate events, browser refresh/back/forward, two tabs, and cleanup of obsolete polling. Record expected422/network errors in negative cases; unexpected console/page exceptions/5xx/unhandled promises remain findings.

Observe source replacement during preflight/materialization, restart after callback failure, stale snapshot download and file-publication interruption through isolated bounded fault cases. Verify latest-source checks, atomic publication and currentness, not just UI color. Test invalid IDs, user text and CSV cells against existing sanitization/guards, without live data or external security scans.

## M. Repair loop and final evidence

Create a defect ledger with control/case IDs, expected/actual effect, trace/network/DB evidence, severity and reproduction. Fix authorized functional issues narrowly through 19_4; rerun affected controls/backend assertions and final business smoke. Do not remove failing controls/tests, classify an implemented feature “not implemented” merely to avoid a failure, suppress console captures, or hide flakiness with uncontrolled retries.

Produce:

- `19_3_RUNTIME_CONTROL_INVENTORY.json`
- `19_3_CASE_RESULTS.json` with causal records
- `19_3_BACKGROUND_PROCESS_MATRIX.md/json`
- `19_3_NO_5M_DISPATCH_PROOF.json`
- `19_3_NATIVE_BROWSER_E2E.md/json`
- `19_3_DEFECTS_AND_RETESTS.md/json`
- private sanitized synthetic-QA screenshots/traces, labeled business/retained/fault scope; no automatic Library upload

Under `docs/evidence/post14b_closure/` preserve compact reports; keep bulky traces/fixtures/downloads under ignored QA output. Include actual source/SHA/browser/config/fixture identities, controls discovered/tested/uncovered, every state/case result, independent oracle, jobs/populations/row caps, source/DB/artifact integrity, actual timings/errors and cleanup results.

Final statuses: BUSINESS_NATIVE_UI_GO/NO-GO; RETAINED_COMPONENT_UI_GO/NO-GO; BACKGROUND_FUNCTIONAL_GO/NO-GO; NO_5M_GUARD_GO/NO-GO; ALL_IMPLEMENTED_UI_GO/NO-GO. All-UI GO needs no remaining unproved required implemented control/state and correct background effects in both scopes. Unimplemented future functionality is listed separately. Zero 5M dispatch is mandatory. Headless-only/missing-native runs cannot earn native headed GO. No canonical 5M, market-prediction, deployment or overall release claim follows from this test.

Once coverage is proven continue 19_5; if blocked, report precise resume commands and continue independent work. Do not end at “browser opened successfully.”

## N. Resume and evidence identity

Support resuming a long functional run from a compact case ledger, but only when code/tree, fixture/import manifests, browser configuration and guard identities still match. A changed executable invalidates affected previous cases; a changed source fixture invalidates its dependent assertions. Do not combine unrelated green cases across candidates into a single all-UI certificate. Preserve failed attempts and classify reruns.

At completion stop only server/browser/worker processes created by this QA run, using recorded ownership and process IDs. Confirm expected jobs are terminal, SQLite integrity and foreign keys pass, output paths remain contained, and fixture screenshots/downloads contain synthetic information only. Do not terminate another application or delete another runtime to make cleanup pass.
