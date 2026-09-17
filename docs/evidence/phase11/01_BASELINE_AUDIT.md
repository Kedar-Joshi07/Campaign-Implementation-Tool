# Phase 11 Baseline Audit and Phase 10 Freeze

Generated: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/01_STEP_01_BASELINE_AUDIT_AND_PHASE10_FREEZE.md`

## Step result

`PASS_STEP_01_BASELINE_AUDIT_AND_PHASE10_FREEZE`

The Phase 10 baseline is trusted and the Phase 11 extension seams are recorded.
This step is inventory and evidence only. It introduces no Phase 11 feature,
schema, source-data, API, service, repository, UI, training, scoring, ranking,
snapshot, or export behavior.

## Repository baseline

| Item | Exact value |
|---|---|
| Repository | `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git` |
| Branch | `main` |
| HEAD | `881b5a652e869af1415547de452b9cccd2c18293` |
| Cached `origin/main` | `881b5a652e869af1415547de452b9cccd2c18293` |
| HEAD subject | `docs(phase10): close freeze evidence audit gaps` |
| HEAD commit time | `2026-09-16T01:08:58+05:30` |
| Application version | `0.1.0` |
| SQLite schema version | `15` |
| Default runtime database | `data/campaign_poc.db` |
| Runtime database bytes | `3,951,042,560` |
| Tracked application status | Clean |
| Pre-step untracked scope | `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/` only |

The untracked Phase 11 prompt pack is user-provided implementation input. It
was not modified, staged, or treated as part of the frozen Phase 10 application
baseline. After this evidence-only step, the worktree additionally contains the
untracked `docs/evidence/phase11/` directory created by the prompt.

## Exact-SHA Phase 10 freeze and CI

Phase 10 is frozen at the current repository baseline. GitHub Actions was
queried by exact `head_sha=881b5a652e869af1415547de452b9cccd2c18293`.

- Workflow: `CI`.
- Run number: `17`.
- Run ID: `35014987151`.
- URL: <https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/35014987151>.
- Status/conclusion: `completed` / `success`.
- Created/completed: `2026-09-15T19:40:07Z` / `2026-09-15T19:43:44Z`.

| Required job | Job ID | Result |
|---|---:|---|
| Repository Hygiene | `104536049516` | SUCCESS |
| Python Validation | `104536244574` | SUCCESS |
| Tests | `104536430671` | SUCCESS |
| Clean-Room Phase1-7 | `104536430778` | SUCCESS |
| Frontend Contract | `104536430846` | SUCCESS |

This is the latest exact-SHA CI run for the Phase 11 starting SHA. It is not a
branch-latest or unrelated-run inference. The trusted Phase 10 implementation
candidate remains `dbbba2d19f1013c04f65bdba5db285772a0c6878`; the baseline
also contains the exact-CI-verified documentation/freeze milestone and its
evidence-integrity follow-up.

## Frozen contract and policy versions

| Contract or policy | Version/value |
|---|---|
| Feature contract | `1`; SHA-256 `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535` |
| Model-role policy | `2` |
| Evaluation contract | `2` |
| Audience Filter / Rank / Selection / Analytics | `1 / 1 / 1 / 1` |
| Campaign / Export / Member Resolution / Export Snapshot | `1 / 1 / 1 / 1` |
| Campaign Targeting Context / Targeting Segment | `1 / 1` |
| Business Match Strength / Age Bucket / Income Group | `1 / 1 / 1` |
| Targeting Intelligence Resolution | `1` |
| Target Group Preview / Campaign / Saved Target Group | `1 / 1 / 1` |
| Match Strength Recommendation contract/rule | `1 / 1` |
| Phase 10 Modeling Context | `1` |
| Phase 10 Compatibility | `1` |
| Phase 10 Historical Window | `1` |
| Phase 10 Multi-product Positive | `1` |
| Phase 10 Training Eligibility | `1` |
| Phase 10 Automated Training | `1` |
| Phase 10 Orchestration | `1` |
| Phase 10 Intelligence Generation | `1` |
| Phase 10 Lifecycle | `1` |

Frozen Phase 10 policy values are `ATTRIBUTED_PURCHASE`,
`contacted_only=true`, combined multi-product ANY-positive customer-grain
labels, minimum selected/P/U counts `14/7/7`, random seed `42`, validation
fraction `0.20`, governed `BAGGING_PU` PRIMARY, Elkan-Noto challenger enabled,
and no challenger auto-promotion.

The frozen model input remains exactly 11 fields: age, gender, state,
individual yearly income, marital status, education, employment status,
resident status, resident type, family member count, and type of employment.
Contact, contactability, consent, push, advertising, and visitor identifiers
must not enter this contract.

## Canonical data and runtime state

The default database was opened through SQLite read-only URI mode. No database
initialization or migration was invoked.

| Dataset | Import ID | Read/inserted/rejected | Canonical checksum | Current rows |
|---|---:|---:|---|---:|
| Customers | 1 | 125,000 / 125,000 / 0 | `99a09d2f0db06980afe290cf74a4db1df76cf8c340534fb2088879fb093d9ea9` | 125,000 |
| Campaign sales | 2 | 570,000 / 570,000 / 0 | `2fdb11c576a180b7349e50e0bf9d3b0a66d0d354ba8d42062756c8cd840965c4` | 570,000 |
| Demographics | 3 | 5,000,000 / 5,000,000 / 0 | `e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75` | 5,000,000 |

Canonical Git LFS objects are:

| Source | LFS SHA-256 |
|---|---|
| `data/customer_master_125000.csv.gz` | `8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f` |
| `data/campaign_sales_570000.csv.gz` | `89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116` |
| `data/usa_demographic_synthetic_5000000_rows.csv.gz` | `adb33ce1daf92b547171960f69f893fec93296d3d514ac7e1bdffbf5c736ac71` |

Current analytical/application counts include two analyses, two models, two
completed full-5M scoring runs, 10,000,000 score rows, 200 rank boundaries, two
analytics snapshots, two Phase 9 Saved Target Groups, four Campaigns, and two
completed export events. The canonical default database currently has zero
Phase 10 generation, orchestration, and context-binding rows; Phase 10 build and
reuse certification used a separate isolated runtime and is retained in
committed evidence. Phase 11 must not confuse the canonical data database with
that disposable certification registry.

## Historical channel versus export-profile boundary

Historical campaign data contains these exact channel values:

- Direct Mail
- Display
- Email
- Mobile Push
- Paid Search
- Paid Social
- SMS
- Telemarketing
- Website / On-site

Historical presence is analysis context only. It does not make a channel a
governed export profile.

The current Campaign contract permits only `EMAIL` and `DIRECT_MAIL` and maps
them only to `EMAIL_CONTACT_V1` and `DIRECT_MAIL_CONTACT_V1`. The default
database confirms three Email campaigns, one Direct Mail campaign, and one
completed 50,000-row export event for each current profile. No SMS, WhatsApp,
Telemarketing, Paid Social, Paid Search, Push, Display, or Website export
profile exists at baseline.

The current export event schema is:

`export_event_id, campaign_id, export_contract_version, export_profile, status,
selected_count, deliverable_count, undeliverable_count, row_count, csv_sha256,
started_at, completed_at, safe_error_message,
export_snapshot_contract_version, start_provenance_sha256,
source_changed_during_export, completion_currentness_state`.

Existing exports require a finalized Campaign and explicit PII acknowledgement,
stream members in bounded chunks, apply CSV formula-injection mitigation,
reconcile counts/currentness, and persist checksum/audit state. Phase 11 should
compose these guarantees but use a separate search-result export registry rather
than weakening the existing `campaign_id` and finalization semantics.

## Current demographic boundary

The generator, importer, schema, and runtime table agree on these 28 columns:

`person_id, first_name, last_name, gender, age, address_line_1,
address_line_2, street, postal_code, city, state, country, phone_number, email,
individual_yearly_income, marital_status, education, employment_status,
resident_status, resident_type, family_member_count,
number_of_children_in_family, number_of_adults_in_family, ethnicity,
type_of_employment, occupation_industry, family_yearly_income, religion`.

Email, phone, and postal address data exist. The current source does not contain
email/direct-mail contactability, SMS or WhatsApp permission, telemarketing/DNC,
push token/opt-in, advertising ID/targetability, or web visitor
ID/targetability. Therefore Push, Display, and Website profiles cannot be
truthfully enabled at baseline, and phone/email presence cannot be treated as
consent.

Adding those fields in Step 4 must change the canonical demographic checksum.
Because the feature contract is unchanged, exact historical analysis and model
reuse may remain valid, but Phase 10 must reject the old scoring provenance and
produce a new full-current-universe scoring generation.

## Phase 9 and Phase 10 persistence baseline

### Phase 9 Saved Target Group

The current `phase9_saved_target_groups` schema is:

`audience_id, targeting_context_id, target_group_contract_version,
filter_branches_json, filter_branches_sha256,
campaign_context_contract_version, campaign_context_json,
campaign_context_sha256, targeting_segment_contract_version,
business_match_strength_contract_version, targeting_criteria_json,
targeting_criteria_sha256, source_scoring_run_id, source_status,
resolved_count, created_at`.

It preserves the complete multi-branch definition and exact source/count, but
it is not a Phase 11 per-submission search history or reusable membership-file
registry.

### Phase 10 generation registry

`phase10_intelligence_generations` stores immutable intelligence and analytical
lineage: generation/compatibility versions, intelligence key, canonical
Modeling Context and historical-filter JSON/hashes, policy versions, all three
source import IDs/checksums, feature/model/evaluation/training identities,
analysis/model/scoring IDs, artifact hash, score-semantics JSON/hash,
rank/analytics/lifecycle versions, generation status, lifecycle state, and
created/verified/used timestamps.

### Phase 10 durable orchestration

`phase10_orchestration_runs` stores orchestration version, targeting context,
Modeling Context and intelligence-key hashes, status, stage, monotonic progress,
business/technical messages, reuse plan, analysis/model/scoring/generation IDs,
training/scoring job IDs, timestamps, and safe failure text.

`phase10_context_bindings` maps a targeting context to the exact Modeling
Context, orchestration, generation, binding status, and usage timestamps.

Phase 11 must add search-run and result-snapshot persistence alongside these
tables; it must not overload or reinterpret Phase 10 generation/orchestration
records.

## Phase 10 full-5M and reuse evidence

The authoritative Phase 10 full-scale manifest records:

- installed Chrome `153.0.8010.36` browser initiation;
- a READY full build with orchestration/generation `6/3` and
  analysis/model/scoring `3/3/3`;
- 5,000,000 scored and 5,000,000 distinct people;
- zero duplicate, invalid, missing, or extra scores;
- chunk size 25,000 and 200 chunks;
- deterministic 256-row rescore maximum difference `0.0`;
- exactly 100 rank boundaries and one current analytics snapshot;
- a 146-person exact multi-branch union with zero duplicates; and
- complete Saved Target Group/Campaign lineage with no pre-export contact PII.

The exact reuse follow-up used orchestration `4` and reused generation,
analysis, model, and scoring `1/1/1/1`; its plan was REUSE for analysis, model,
scoring, and rank and it created no training or scoring job. Phase 10 browser
certification separately proved that delivery-channel changes and prospect
targeting-filter changes do not create model, scoring, or generation records.

These facts establish the Phase 11 middle layer: same Modeling Context plus a
different filter or delivery profile must reuse Phase 10 intelligence and must
not retrain or rescore. Phase 11 exact-result reuse is a new higher layer and
must not weaken Phase 10 currentness checks.

## Current UI navigation and Campaign Planner controls

Current visible navigation contains nine entries:

1. Home / Overview
2. Create Campaign
3. Saved Target Groups
4. Campaigns
5. Insights
6. Data Status
7. Historical Analysis
8. Targeting Intelligence / Model Management
9. Audience Explorer

Navigation is hash-based in `frontend/js/app.js`; `viewTitles`, `showView`,
`requestedView`, and `initializeNavigation` are the central seams. All nine view
modules are initialized at startup. The Phase 11 implementation should replace
the scattered visible list with centralized view-group metadata while keeping
advanced source and module initialization compatible with regression needs.

The current Campaign Planner is a five-step shell:

1. Campaign Details: name, optional description, optional launch date.
2. Campaign Context: products, types, categories, offers, delivery channel,
   and historical channels.
3. Targeting Preferences: Match Strength, gender, age groups, states, region
   shortcut, income groups, marital status, education, employment status,
   resident status/type, employment type, family-size range, top percentage,
   ALL_MATCHING/TOP_N, and target count.
4. Target Group Preview: automatic Phase 10 preparation, durable progress,
   exact counts, explanation, recommendation, profile, paged privacy-safe rows,
   and collapsed technical details.
5. Review & Save: immutable Target Group and Campaign Draft.

The current multi-value controls are native multi-select boxes and require
Ctrl/Command guidance. Phase 11 Step 7 replaces their presentation with one
reusable searchable accessible component while preserving the same backend
values and OR-within/AND-across semantics.

## Phase 11 frontend visibility plan

| Current component/view | Phase 11 normal-user disposition |
|---|---|
| `overview-view`, `overview.js` | Remain and become business `Home` |
| `campaign-planner-view` and its focused modules | Remain as implementation source; compose into single `Find Potential Customers` form |
| New Results history/detail | Add as the third normal business view |
| `saved-target-groups-view`, `saved-target-groups.js` | Hide from normal navigation; retain code and compatibility |
| `campaigns-view`, `campaigns.js` | Hide from normal navigation; retain legacy Campaign/export behavior |
| `insights-view` | Hide from normal navigation; retain source |
| `data-status-view`, `data-status.js` | Hide from normal navigation; retain source/API/tests |
| `historical-analysis-view`, `historical-analysis.js` | Hide from normal navigation; retain source/API/tests |
| `model-training-view`, `model-training.js` | Hide from normal navigation; retain source/API/tests |
| `audience-explorer-view`, `audience-explorer.js` | Hide from normal navigation; retain source/API/tests |
| `campaign-context.js`, `business-targeting.js` | Reuse beneath the single business form |
| `targeting-intelligence.js` | Reuse durable Phase 10 plan/prepare/poll/retry behavior |
| `target-group-preview.js` | Reuse exact result/filter/profile semantics, not as a separate analyst screen |
| `campaign-review.js` | Retain for backward compatibility; Phase 11 Results uses search-run/snapshot records |

Normal Phase 11 navigation is exactly Home, Find Potential Customers, and
Results. UI hiding is not authorization. Direct legacy-route behavior must be
chosen consistently in Step 2/6, and a future RBAC seam must not require
rebuilding navigation.

## Existing lower-level callable seams

Phase 11 must compose these functions instead of duplicating Phase 1-10 logic.

### Phase 10 intelligence preparation

- `get_phase10_intelligence_plan(database_path, targeting_context_id)`:
  read-only exact readiness/reuse plan.
- `prepare_phase10_targeting_intelligence(...)`: normal API-level start/join/
  reuse path.
- `get_phase10_preparation(...)`: durable status/progress/currentness read.
- `retry_phase10_targeting_intelligence(...)`: controlled retry from verified
  state.
- `prepare_phase10_orchestration(...)`: lower durable orchestration service;
  Phase 11 should normally use the API service boundary above.

Existing HTTP routes are below
`/api/campaign-planner/contexts/{targeting_context_id}` with
`/intelligence-plan`, `/targeting-intelligence/prepare`,
`/targeting-intelligence/preparation`, and
`/targeting-intelligence/preparation/retry`.

### Phase 9/10 source currentness

- `resolve_targeting_intelligence(...)`: resolves only the source explicitly
  attached to the context; never latest/first.
- `resolve_current_scoring_context_lightweight(...)` and
  `validate_completed_scoring_run_provenance_lightweight(...)`: bounded scoring
  currentness/provenance.
- `get_audience_preparation_status(...)`: rank/analytics readiness.
- `get_phase10_preparation(...)`: generation/binding/currentness projection.
- `validate_saved_audience_currentness(...)`: immutable saved-audience check.
- `reconcile_phase10_lifecycle(...)` and
  `touch_phase10_usage_for_context(...)`: lifecycle and usage metadata.

### Estimate, search, and profile

- Business context path: `get_target_group_preview(...)` and
  `search_target_group_preview(...)`.
- Lower Audience Engine path: `estimate_audience(...)`, `search_audience(...)`,
  and `profile_audience(...)` after exact prepared/current scoring validation.
- `normalize_audience_filters(...)` and `normalize_selection(...)` remain the
  authoritative filter/selection normalization seam.

### Immutable Target Group and Campaign Draft

- `save_target_group_and_create_campaign_draft(...)` preserves exact Phase 9
  branches, count, scoring lineage, immutable Saved Audience, Saved Target
  Group, and Campaign Draft.
- `save_resolved_audience_definition(...)` is the lower saved-membership
  definition boundary used by established flows.

### Campaign member resolution and export

- `_resolve_campaign_member_query_context_on_connection(...)` verifies the
  immutable saved definition and currentness within one read transaction.
- `_iter_selected_member_chunks(...)` performs bounded exact member traversal.
- `stream_campaign_export_csv(...)` owns finalized-Campaign currentness, PII
  acknowledgement, bounded streaming, deliverability, formula mitigation,
  checksum, and audit behavior.

The member-resolution helpers are currently private and campaign-shaped. Phase
11 should extract or wrap a focused reusable public core for immutable result
snapshots rather than importing private functions or weakening Campaign
finalization rules.

## Frozen source-signature inventory

These SHA-256 signatures identify the Phase 1-10 contract authorities at the
Phase 11 baseline. Intentional additive Phase 11 changes must be reviewed
against this inventory; unrelated drift is prohibited.

| Authority file | Bytes | SHA-256 |
|---|---:|---|
| `app/database/schema.py` | 104551 | `a38c357dcc0ff90318fc3d405c692005688b9531fc91eb8087fa02975b3465da` |
| `app/ml/feature_contract.py` | 7188 | `b3e3f382080b480751080da4b1a03c9fdb3ed25fc7740e9490723a2c880234be` |
| `app/ml/model_roles.py` | 1477 | `d7a9d265df00ac56f83be1118aa283e3342835e5170a8aad4b0797fd8311df08` |
| `app/ml/evaluation.py` | 18976 | `0768b07b1848862eafe162e19ba6e3781762518e063c102147d0f1214987fbcb` |
| `app/schemas/historical.py` | 11690 | `710075979ef21b3260cd240366cbe7dcd773e8bbe9c8a1c97a5111370e8982b3` |
| `app/schemas/campaign_targeting.py` | 23590 | `3d94f6bc1b4245dbcefc9bb43def1b1d8553f1c67628112b75858190abf0413e` |
| `app/schemas/phase10_intelligence.py` | 15890 | `f7e870175c5125905fbc4e5bf4933c5ebbf1b9cdc3ba437dce1a86cfb1a1cf71` |
| `app/services/historical_analysis_service.py` | 25482 | `889de2418aa03d2f145dc310395621a4b3163ce9c2adc1e6ad5affa023ac0465` |
| `app/services/training_cohort_service.py` | 7880 | `e961297041643bdccfb250b45f1fc28ee5e8d0f7f331fe13b5a9f27e5847671d` |
| `app/services/prospect_scoring_service.py` | 67644 | `18d33860ad11e697895e14597f79de493c06156f86f03d89ca6b536298fe8b08` |
| `app/services/audience_preparation_service.py` | 78026 | `fc66386ecf8dc47bf12f5a1de4e3e96209ec8d6860d8883cee28429475b3d30d` |
| `app/services/audience_query_service.py` | 122167 | `f0805691723ef619994ff3e387615fb8b0fe03fc292a3dcdf1f74ea6cf1ad77f` |
| `app/services/campaign_contracts.py` | 2256 | `c5d06cd29ed6f023e4d301eb971c0c37d76d13103bdf48311df9c9e688d26729` |
| `app/services/campaign_service.py` | 65099 | `fc899b332653746b5a6ec75695f0e45368e58cd691da72767383be84075ec97e` |
| `app/services/targeting_intelligence_service.py` | 15467 | `8909bc98eb3d5089687273db2a5c871642d33d1c8dff56199363c4c868b2dc43` |
| `app/services/target_group_preview_service.py` | 22345 | `b1e88a501cb250b6541dd2018184fad05af20c80cab27fc7acd7c518d43fc5b1` |
| `app/services/target_group_campaign_service.py` | 21784 | `815154af5e6fe2e873f1eef40526d5d854f0dfcf52f587c533056076c007ed4c` |
| `app/services/phase10_context_identity_service.py` | 16133 | `ef71533e48a6b3b20086dbf1616e98a1a96030c82f378aea56cd812f9be27e83` |
| `app/services/phase10_historical_resolution_service.py` | 14633 | `4e8720d97089ddefdcc2b16b01889627d39bdd5a2191eed91bc3da97269b85c6` |
| `app/services/phase10_model_resolution_service.py` | 30328 | `3f102bcca1eec445a5f7c0d558110338597d7a2a44b0e40e1e57c3d77e73b373` |
| `app/services/phase10_scoring_resolution_service.py` | 30874 | `5e47c9a0a873e56adac0853bba3913200ed2a0b741747024b6f67bf537712963` |
| `app/services/phase10_orchestration_service.py` | 26032 | `5a4b70f9a30d734e2c6a27d80b5ddd19af065c1c42ee327a873d37eaf523ac06` |
| `app/services/phase10_lifecycle_service.py` | 10895 | `352030e59041c52a01801ab9297e212d5adfa569a0733b5be74998f7e05cf15a` |
| `app/repositories/phase10_intelligence_repository.py` | 62197 | `e0214e92467135ddb4a047cd86e750803b4bbdfda3499970840eaec2f5f7513b` |

## Phase 11 implementation constraints handed forward

- Preserve all frozen Phase 1-10 behavior and exact currentness checks.
- Keep Campaign Context, Phase 10 Modeling Context, prospect targeting, delivery
  profile, search-run identity, and result-snapshot identity distinct.
- Reuse order is exact snapshot, then Phase 10 intelligence, then minimum
  compatible Phase 10 build.
- Every intentional submission creates a new search-run event even when an
  existing snapshot is reused.
- Never precompute the Cartesian product of targeting options.
- Membership snapshots contain analytical identity only and never contact PII.
- Contact PII is joined only during governed profile-specific streaming export.
- Profile-specific allowlists replace global phone/email assumptions.
- New contactability/activation identifiers remain outside the model feature
  contract and must participate honestly in source provenance.
- No `customer_id` to `person_id` bridge, no activation/send integration, no
  automatic deletion, no fake feedback loop, and no claim of reinforcement
  learning.

## Execution declaration and stop boundary

- Phase 11 feature implementation: not started.
- Schema migration: not run.
- Canonical demographic regeneration/import: not run.
- Training, scoring, rank, or analytics work: not run.
- UI/navigation changes: not started.
- Existing application/database/artifact mutations: none.
- Required Step 1 evidence: created.

`STOP_AFTER_STEP_01`
