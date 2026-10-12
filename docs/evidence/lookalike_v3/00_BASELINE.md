# Stage 14B_00 baseline, decision, and golden compatibility

Recorded: 2026-10-05
Starting SHA: `336875c30fc32b00323d916ecc45b232016168a1`
Candidate: `UNCOMMITTED`
Decision: **GO — BASELINE REPRODUCIBLE AND REQUIREMENTS MAPPED**

## Scope and repository state

This stage froze the pre-v3 behavior and recorded the already-approved v3
direction. It did not implement v3, migrate a database, train a profile, score
prospects, alter scenarios, or execute any full-5M workflow.

The branch began on `main` at the prompt pack's exact trusted SHA. The preceding
authority is Prompt 13.6.1: implementation SHA
`a35dabbf0baa43e12dfe4bddc9ad72c29bdf5acb`, evidence SHA
`336875c30fc32b00323d916ecc45b232016168a1`, and exact-SHA CI run
`37281401935` with all five required jobs successful.

The only initial working-tree item was the untracked operator-supplied directory
`Prompts/Campaign_Implementation_Tool_14B_Lookalike_Prompt_Pack/`. It was
preserved. No tracked production file was modified in Stage 00.

The complete starting file/hash manifest is in
[`00_BASELINE.json`](00_BASELINE.json). It pins 26 authority, runtime, schema,
UI, validation, test, and scenario files.

## Approved v3 decision

The dated decision is recorded without changing the older Prompt 13 record:
[`00_APPROVED_V3_DECISION_ADDENDUM.md`](00_APPROVED_V3_DECISION_ADDENDUM.md).

The approved additive contract is:

- selection version `3`;
- semantics `PRODUCT_BUYER_SIMILARITY`;
- method `BUYER_PROFILE_DISTANCE_V1`;
- membership version `3`;
- product policy `ANY_SELECTED_PRODUCT_MAX_V1`;
- minimums `.50`, `.60`, `.70`, `.80`, `.90` with predicate `>=`;
- new UI minimum `.70` after certification.

A `.90` score means distance at most `.10` from the nearest supported learned
buyer prototype under the declared metric. It is not 90% purchase probability,
accuracy, confidence, percentile, or validated lift. The older conditional
percentile/lower-probability 14B choice is superseded; its evidence is not
rewritten.

## Frozen legacy behavior

The golden fixture is
[`14b_00_legacy_contract_golden.json`](../../../tests/fixtures/lookalike_v3/14b_00_legacy_contract_golden.json).
The new characterization suite exercises the real API, repositories, result
reader, snapshot registry, and export service.

| Contract | Frozen behavior |
|---|---|
| Unversioned submission | v1, legacy safe status response, no propensity bucket |
| V1 result | `LEGACY_RAW_SCORE`, “Match Strength”, membership version 1 |
| V2 | Explicit selection version 2 and membership version 2 |
| V2 `.50` | `[.50,.60)` |
| V2 `.60` | `[.60,.70)` and the only legacy `BROAD` translation |
| V2 `.70` | `[.70,.80)`, default bucket |
| V2 `.80` | `[.80,.90)` |
| V2 `.90` | `[.90,1.00]` |
| Demo policy | 10,000 selected customers |
| Currentness | `CURRENT`, `NOT_AVAILABLE`, `STALE`, `UNVERIFIED` |

Literal boundary fixtures cover `.49`, `.50`, `nextafter(.60,0)`, `.60`,
`.70`, `.80`, `.90`, and `1`. NaN, infinities, booleans, out-of-range scores,
and unsupported bucket spellings are rejected by the independent oracle/API
validation. All 20 scenario objects have individual hashes in the fixture.

The scenario file remains byte-identical at SHA-256
`d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`.
The distribution remains 1 VERY_STRONG, 2 STRONG, 7 GOOD, and 10 BROAD. Its
historical embedded minimum of 101 is retained as history and cannot override
the live 10,000 policy.

## Source, feature, and product baseline

The audit command streamed the complete 570,000-row sales gzip and hashed the
actual 512 MB demographic gzip. It did not import or score either source.

| Source | Current identity/result |
|---|---|
| Customers | `8a2c5601…d18f` |
| Sales | `89e6f846…4116`; 570,000 rows; 119,909 customers; 36 products |
| Product master | `317778cd…ba6a`; 48 catalog products |
| Demographics | `27d8e2a9…8b1d`; 512,842,205 compressed bytes |
| Feature contract | version 1, `a0cd5e8f…8535`, 11 ordered common features |

The pack's `PRODUCT_HISTORY_OBSERVATIONS.json` records product-master hash
`82f55d63…53b3`, which does not match the current raw tracked file. This is
resolved in favor of the actual tracked bytes at the trusted SHA:

- `git status` reports no product-master change;
- the independent Stage-00 hash is `317778cd…ba6a`;
- prior full-fresh evidence records the same `317778cd…ba6a` identity; and
- catalog contents, the 48/36 reconciliation, and all buyer counts reproduce.

This correction is recorded rather than editing the prompt pack's historical
observation.

Buyer evidence at this stage is an unfiltered observation: attributed-sale
flag equals one, deduplicated by customer and product. Thirty-two products meet
the initial 200-buyer floor, including `PRD001` exactly at 200. Four observed
products are below it: `PRD020` 142, `PRD022` 78, `PRD030` 133, and `PRD038`
133. Twelve catalog products have no observed sales. Context, date-window, and
feature-quality checks in Stage 02 may reduce support further. The complete
48-product manifest is in the JSON evidence.

The frozen feature vocabulary is age, gender, state, individual yearly income,
marital status, education, employment status, resident status, resident type,
family member count, and type of employment. Age uses the saved historical
contact cutoff; income is annual and nonnegative; categorical values are
trimmed, blanks become `Unknown/Other`, and fuzzy matching is prohibited.
Imports remain staged and ordered customers → campaign sales → demographics.

## Database identity

A fresh disposable database was initialized twice with current code:

- stored/code schema: 31;
- schema identity SHA-256:
  `93df3ec3c6887d52f17c0e8f3e815ee3dafb2c871b3269fdf951d642ed7ab3d2`;
- second initialization produced the identical signature;
- 132 schema objects and 38 tables;
- `PRAGMA integrity_check`: `ok`;
- foreign-key violations: zero.

The operator database is available at `data/campaign_poc.db`, size
7,574,577,152 bytes, and stored schema 26. It was opened with `mode=ro` only.
It was not migrated, copied, hashed again, or changed. Later migration work must
use the existing authorized disposable-copy workflow.

## Requirements-to-caller map

| Requirement | Current owners/callers that must remain aligned |
|---|---|
| Selection constants/bounds/defaults | `selection_contracts`, calibrated selection service, targeting schema, results service |
| Unversioned v1 / explicit v2 | potential-customer schema/router/submission service, result registry |
| Options/OpenAPI/currentness | potential-customer router/schema, targeting option service, business search form |
| Exact preflight/materialization | preflight service, Phase 11 orchestration, audience query service |
| Persisted history/currentness | schema, result registry, snapshot service, results service |
| Membership/export safeguards | result contracts, export service, omnichannel profiles |
| Scenario mapping/10K policy | selection registry, scenario preflight script, unchanged scenario JSON |
| Source/feature/date conventions | import service, feature contract, cohort and historical services |

The machine-readable map, including full paths, is in `00_BASELINE.json`.

## Gap matrix and preservation plan

V3 runtime work remains intentionally unimplemented. The assigned sequence is:

- Stage 01: registry, API discriminator, schema migration;
- Stage 02: exact product buyer cohorts/support;
- Stage 03: deterministic profile learning/artifacts;
- Stage 04: chunked scoring/generation verification;
- Stage 05: similarity readiness/preflight/search/cache;
- Stage 06: UI/mode switching;
- Stage 07: membership 3/export/feedback lineage;
- Stage 08: descriptive assurance/drift/explanations;
- Stage 09: production-path integration closure;
- Stages 15–19: faults, full5M, scenarios, documentation, final CI.

Implementation must add v3 names and storage separately, keep unversioned
requests on v1, preserve every v2 boundary and historical artifact, avoid
cross-mode cache/readiness reuse, retain the twenty scenario bytes and 10K
policy, and use disposable databases for migration/certification.

## Commands and results

Pre-change bounded compatibility command:

```text
.venv\Scripts\python.exe -m pytest -q tests\test_selection_contract_registry.py tests\test_preflight_http_contract.py tests\test_phase11_api_backward_compatibility.py tests\test_preflight_materialization_parity.py tests\test_phase11_results_history_detail.py tests\test_phase11_omnichannel_export_engine.py
```

Result inside the restricted shell: 81 passed and nine Playwright setup errors,
all from the same Windows named-pipe `WinError 5`; no application assertion
failed. Permission-adjusted rerun of the affected module: **14 passed in
88.31s**.

New golden suite:

```text
.venv\Scripts\python.exe -m pytest -q tests\test_lookalike_v3_baseline_compatibility.py
```

Result: **6 passed in 70.13s**.

Final affected regression:

```text
.venv\Scripts\python.exe -m pytest -q tests\test_selection_contract_registry.py tests\test_phase11_api_backward_compatibility.py tests\test_lookalike_v3_baseline_compatibility.py
```

Result: **26 passed in 118.74s**.

Read-only source audit:

```text
.venv\Scripts\python.exe scripts\validation\audit_14b_00_baseline.py
```

Result: **PASS**. The canonical database was opened read-only; only a disposable
fresh database was created.

## Acceptance and limitations

Stage-owned acceptance rows A01–A06 pass. A07–A45 belong to later stages and
remain `NOT_RUN`; a source file is not counted as proof.

No claim is made that v3 is implemented, descriptively validated, scored over
five million prospects, demo-qualified, remotely CI-certified, or ready for
release. Existing predictive response/lift validation remains unavailable and
is independent of the approved descriptive similarity implementation.

**Stage 14B_00 = GO.** The trusted baseline is reproducible, legacy behavior is
pinned by real characterization tests, the approved decision is append-only,
source provenance is reconciled, and every remaining requirement has a stage
owner. The next prompt is `14B_01_REGISTRY_API_SCHEMA_AND_MIGRATION.md`.
