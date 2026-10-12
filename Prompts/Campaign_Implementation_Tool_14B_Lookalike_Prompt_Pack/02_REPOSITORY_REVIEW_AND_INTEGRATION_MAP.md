# Review record and integration map

## Scope and limits

Read-only review of checked-out `336875c30fc32b00323d916ecc45b232016168a1` and its recursive tree, prior 14B/15–19, current evidence, generators, feature contract, cohort reconstruction, selection, API, registry/schema, Phase 10/11, frontend, and CI. Repository unchanged. No new implementation, full repository tests, canonical DB migration, model training, 5M similarity scoring, or new CI certification was performed during prompt creation. The canonical DB is not committed in this checkout; prior DB metrics below are recorded historical evidence, not rerun results.

Source inventory: 151 implementation/contract/UI/generator/workflow files indexed by path and SHA-256 in `REVIEWED_SOURCE_INDEX.json`. Indexing shows the inspected source surface, not that every file received an independent behavioral test. `PRODUCT_HISTORY_OBSERVATIONS.json` contains a fresh streamed CSV coverage audit with per-product distinct attributed-buyer counts. It does not apply the later v3 historical/context/quality filters.

## Verified observations

- `app/selection_contracts.py` owns v2. Defaults .70, demo minimum 10K, BROAD → .60, explicit .50 remains separate; v2 buckets are discrete. Preserve it.
- `app/schemas/potential_customer_search.py`: preflight is v2-only; run/history discriminators currently accept 1/2. Submission already dispatches using probability fields. Extend schemas intentionally; do not rely on a frontend-only label change.
- `app/services/potential_customer_preflight_service.py`: current cache/count/readiness are coupled to calibration. Its v3 branch needs independent similarity artifact identity and mode-specific public readiness.
- `app/services/phase11_search_orchestration_service.py`: cache, member iterators, dependency orchestration, attestation reuse, calibration readiness, completion all need version-aware v3 handling.
- `app/services/phase10_context_identity_service.py`: product_ids already enter modeling context. Existing product awareness does not prove it computes buyer similarity. Retain compatible dimensions without erasing the legacy model identity.
- `app/services/phase10_model_resolution_service.py`: governed campaign-split validation can block canonical PU training. V3 needs its own descriptive profile builder/readiness; routing it through the existing mandatory probability training chain would preserve the blocker.
- `app/ml/feature_contract.py`: 11 shared features, training-only imputation/scaling, unknown-category handling. Frozen probability preprocessing is not the new mixed-distance score contract.
- `app/services/training_cohort_service.py` and `app/repositories/model_training_repository.py`: reconstruct customer-grain data with customer/sales lineage. Reuse proven join/reference-date behavior; preserve original PU training semantics.
- `app/database/search_recovery_schema.py` and registry tables: CHECK constraints explicitly restrict 1/2; v3 requires real additive migration and new column consistency constraints, not a new Python constant alone. Inspect all related DDL and historical migration paths.
- `app/services/phase11_result_contracts.py`: two immutable membership schemas. V3 must have its own typed membership reader/writer, currentness, export support, and file/schema integrity checks.
- `frontend/js/business-search-form.js`: submits propensity_bucket and radio options. New mode must have its own state, request discriminator, options metadata, helper text, saved-run reopening, and race handling.
- `data_generation_scripts/generate_campaign_sales.py`: purchases use engagement/response/affinity/offer/repeat/season/channel/latent factors; these cannot be inserted as cold-prospect input features. Historical buyer similarity does not establish that demographics predict those events well.

## Fresh input audit

`campaign_sales_570000.csv.gz`: 570,000 rows, 119,909 distinct customer_ids, 36 distinct product_ids. Product master: 48 products. Sales summary: distinct_products=48, a mismatch with actual observed history. Correct the reporting definition and generator summary for future output; preserve existing raw data and historical evidence. Reconcile observed coverage via verified import metadata at implementation time.

PRD001 Wireless Earbuds 01 has 200 distinct attributed buyers in the full file before filtering; narrow contexts can readily put it below the proposed 200 floor. PRD020 Skin Care Set 20: 142; PRD022 Electric Toothbrush 22: 78; PRD030 Athleisure Set 30: 133; PRD038 Mechanical Keyboard 38: 133. These are expected unsupported cases under V1 floors, not a reason to lower them silently.

Exact Headphones and Mobile Phone names are absent from the product catalog. Earbuds and Tablet are different products. Do not invent a mapping.

## Recorded prior evidence, not newly rerun

Prompt 13 evidence reports 5M calibrated probabilities ~0.06518–0.07856, sigmoid maximum ~0.09123, diagnostic AUC ~0.544, and no independent campaign split. It explicitly says those metrics lack governed split lineage. Prompt 13.6/13.6.1 closes runtime/registry/statistical hardening; schema 31 remains. These facts motivate separation, not a promise of buyer-similarity yield.

## Integration ownership

| Surface | Existing anchors | Required change |
|---|---|---|
| Policy | selection_contracts, campaign_targeting_contract_service | additive typed v3 registry + exact filters |
| Inputs | historical_repository, model_training_repository, import/currentness services | product buyer evidence and common features |
| Intelligence | phase10 context/model/scoring/orchestration | distinct profile artifacts, independent v3 resolver |
| Score storage | scoring repositories, attestation | v3 per-product/model/source identity, verified score generation |
| Search | preflight/submission/Phase11 orchestration | one shared v3 predicate + cache dispatch |
| Results | membership registry/snapshot/results | immutable v3 schema, history and labels |
| UI | business-search-form, status, business-targeting, planner | separate score mode and index wording |
| Export | phase11_export_service, omnichannel profiles | v3 membership dispatch + existing contact gates |
| Feedback | phase11_feedback_service, lineage, worker | identify v3 origin; no similarity-as-probability calibration |
| Validation | pytest/CI/cleanroom/full-fresh | v1/v2 unchanged + new v3 suites and full-scale runner |

## Technical references

The score formula is a pack-specific design, not a score standardized by these references. References support training-only preprocessing and cautions about clustering assumptions:
- [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)
- [scikit-learn clustering guide](https://scikit-learn.org/stable/modules/clustering.html)
Do not upgrade the project's dependency locks simply because documentation describes a newer release.

### Additional export and startup findings

The current channel membership bridge explicitly reads only v1/v2 and projects legacy propensity/rank fields. The channel profile base headers also require those fields. Therefore adding membership 3 alone is insufficient: a versioned export projection/profile is needed, retaining old schemas while avoiding fake similarity-as-propensity or rank columns.

Runtime health currently tracks workflow composition availability. Extend mode-specific data readiness without disguising actual infrastructure failure; profile/calibration absence is not the same as failed worker/database composition.
