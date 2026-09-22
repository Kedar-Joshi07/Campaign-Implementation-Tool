# Step 9 - Real Uvicorn Full 5M Certification

## Result

**PASS** - Installed Chrome exercised the production Phase 11 coordinator through real `python -m uvicorn app.main:app`. A new compatible Phase 10 intelligence generation was built and all 5,000,000 demographic people were scored. The exact-repeat, targeting-change, and delivery-profile-change paths then reused precisely the expected assets. No test executor, custom server, monkeypatch, asset corruption, or forced invalidation was used.

The machine-readable record is `09_REAL_APP_FULL_5M_CERTIFICATION.json` in this directory.

## Frozen baseline and runtime

- Branch: `main`
- Exact launch HEAD: `db3ceabc492ec17759dfdf6f6ae1186ac86ca77e`
- Commit: `feat: functionalize phase11 runtime closure`
- Git status at launch: clean
- Server: `python -m uvicorn app.main:app` at `http://127.0.0.1:8000`
- Browser: installed Google Chrome `153.0.8010.48`
- Database: `data/campaign_poc.db`, schema version 18
- Production coordinator/executors: enabled; no injection

The canonical gzip was 512,842,205 bytes with SHA-256 `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d`. Import 4 was `COMPLETED` with 5,000,000 read, 5,000,000 inserted, zero rejected, and source checksum `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f`.

The database contained exactly 5,000,000 demographic rows and 5,000,000 distinct person IDs, with zero duplicates and the inclusive identity range `US000000001` through `US005000000`.

## Environment-only preflight failure

The first sandboxed attempt created search 21/orchestration 12 and failed safely after 11 seconds because Windows denied creation of the production process-pool pipe (`WinError 5`). This was an execution-environment restriction, not a product defect. No implementation or asset was altered. The identical, unpatched Uvicorn command was relaunched with the required host permission; search 22 is the decisive certification run.

## Decisive 5M build

Chrome submitted search 22 for product `PRD008`, California, `BROAD`, `TOP_N=100`, and Direct Mail. Phase 10 orchestration 13 made the exact compatibility decision `analysis=BUILD`, `model=BUILD`, `scoring=BUILD`, `rank=BUILD`, created analysis 5/model 4/scoring 4/generation 2, and reached `READY`.

| Item | Result |
|---|---|
| Search 22 | `COMPLETED`, `NEW_INTELLIGENCE_BUILD`, snapshot 4 |
| Search time | `2026-09-21T04:35:20Z` to `05:14:43Z` (2,363 s) |
| Orchestration 13 | `04:35:32Z` to `05:10:06Z`; jobs 10 and 11 |
| Analysis 5 | 35,399 observations; 30,810 selected customers; 2,263 positives |
| Model 4 | `pulearn.BaggingPuClassifier`, `BAGGING_PU`, completed in 4 s |
| Scoring 4 | 5,000,000 rows in 200 chunks of 25,000 |
| Scoring runtime | 985.722 s; 5,072.423 rows/s |
| Score range | min `0.015047932063355144`; mean `0.07098477685554934`; max `0.15726005776003324` |
| Result | zero members because the valid BROAD threshold exceeded this model's maximum score |

### Full-population invariants

- scored rows: 5,000,000
- distinct person IDs: 5,000,000
- duplicate person IDs: 0
- orphan person IDs: 0
- null, nonfinite, negative, or above-one scores: 0
- score identity range: `US000000001` through `US005000000`
- rank boundaries: exactly 100; ranks 50,000 through 5,000,000; population 5,000,000
- analytics rows for scoring 4: exactly one; population 5,000,000
- generation 2: `READY` / `CURRENT`

### Build lineage and checksums

- customer import 1: `99a09d2f0db06980afe290cf74a4db1df76cf8c340534fb2088879fb093d9ea9`
- campaign-sales import 2: `2fdb11c576a180b7349e50e0bf9d3b0a66d0d354ba8d42062756c8cd840965c4`
- demographic import 4: `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f`
- feature contract: version 1, `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- model/scoring artifact: `c3bb696963416cb70e3bb1cfb04d681cf8e0e09f69bbeea0430b02c4672bfc6e`
- intelligence key: `987bed9bbb1681129ceda9065e2581d589173876201a85c20beefda92c42aabb`
- modeling context: `8cab3bbfb6238e0f92932ed2d28d2058f6b98b52af611a77fc5d1876e6e54f16`
- snapshot 4: `d3c86e8b094bf886f711d059dbe2075062022aab1f72f6850e6386fd1f5c03cc`, `CURRENT`

Chrome visibly displayed `Completed`, `Current`, `Prepared new targeting intelligence`, the 5,000,000 scored population, score summary, snapshot 4, and generation/scoring/model/analysis IDs 2/4/4/5.

## Required reuse scenarios

| Scenario | Search | Required change | Result | Snapshot | Generation / analysis / model / scoring | Duration |
|---|---:|---|---|---:|---|---:|
| Exact repeat | 23 | none | `EXACT_RESULT_REUSE` | 4 | 2 / 5 / 4 / 4 | 1,289 s |
| Targeting filter | 24 | California to Texas only | `INTELLIGENCE_REUSE` | 5 | 2 / 5 / 4 / 4 | 1,494 s |
| Delivery profile | 25 | Direct Mail to Email only | `EXACT_RESULT_REUSE` | 5 | 2 / 5 / 4 / 4 | 2,521 s |

Orchestrations 14, 15, and 16 each recorded `analysis=REUSE`, `model=REUSE`, `scoring=REUSE`, and `rank=REUSE`, with no training or scoring job IDs.

### Exact-repeat zero-scan proof

Search 23 retained snapshot 4 and created no snapshot, membership artifact, analysis, model, or scoring run. The production exact-cache branch in `phase11_search_orchestration_service.py` validates and completes with the existing snapshot before execution can reach the `membership_source` call. Therefore the membership-source invocation count for this branch was zero; the durable registry and artifact inventory corroborate the control flow.

### Targeting-filter proof

Search 24 changed only the state to Texas. Generation 2 and analysis/model/scoring 5/4/4 were retained, while the changed targeting/filter identity created snapshot 5. Its cache key is `d7c891b8b70220dbd2dc4ae4a1455c4231742e21e6e4f1c1a3347af7dc910493`; it is `CURRENT` and has SHA-256 `d3c86e8b094bf886f711d059dbe2075062022aab1f72f6850e6386fd1f5c03cc`.

### Delivery-profile/export-only proof

Search 25 retained Texas targeting, generation 2, analysis 5, model 4, scoring 4, and snapshot 5. It changed only `DIRECT_MAIL` / `DIRECT_MAIL_CONTACT_V1` to `EMAIL` / `EMAIL_CONTACT_V1`.

Both governed downloads were invoked through Chrome against the same snapshot:

| Export event | Search | Snapshot | Profile | Status | CSV SHA-256 |
|---:|---:|---:|---|---|---|
| 20 | 24 | 5 | `DIRECT_MAIL_CONTACT_V1` | `COMPLETED` | `48f11a5bab40e0f3016baead770eb74ebf5697ab83ced4c14cee111da92ceef9` |
| 19 | 25 | 5 | `EMAIL_CONTACT_V1` | `COMPLETED` | `6567c5165b018b5182ba70eaa5c90f6b5fe26771718fe6f68d14b72209c49192` |

This is an export-only change: membership and analytical lineage are identical, while the governed output profile and output checksum differ.

## Browser and HTTP proof

Chrome visibly verified all four completed result pages, their result-source labels, currentness, scored population, snapshot provenance, and lineage IDs. The final Email page showed Texas, `Reused previous exact result`, snapshot 5, generation/scoring/model/analysis 2/4/4/5, and `EMAIL_CONTACT_V1` ready. Browser warning/error observations were empty.

The real Uvicorn access log recorded successful `200` responses for result details and both governed downloads, including:

- `GET /api/potential-customer-search/runs/25/result`
- `GET /api/potential-customer-search/runs/25/download`
- `GET /api/potential-customer-search/runs/24/result`
- `GET /api/potential-customer-search/runs/24/download`

## Final registry state

| Registry | Count |
|---|---:|
| `campaign_search_runs` | 25 |
| `campaign_result_snapshots` | 5 |
| `phase10_intelligence_generations` | 2 |
| `historical_analysis_runs` | 5 |
| `model_runs` | 4 |
| `scoring_runs` | 4 |
| `phase10_orchestration_runs` | 16 |
| `campaign_result_export_events` | 20 |

All Step 9 requirements are satisfied. Step 10 was not started.
