# Phase 11 Step 4 — Contactability and Identifier Extension

Date: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/04_STEP_04_SYNTHETIC_CONTACTABILITY_AND_IDENTIFIER_EXTENSION.md`

Frozen baseline: `881b5a652e869af1415547de452b9cccd2c18293`.

## Result

`PASS_STEP_04_CONTACTABILITY_IDENTIFIER_EXTENSION`

The canonical 5M demographic source now contains 40 columns. Twelve appended deterministic source fields support the ten backend omnichannel profile contracts without changing the original demographic values or the frozen model feature contract. Schema 16, strict imports, cross-field validation, reconciliation, source summaries, deterministic tests, and current canonical hash documentation are updated.

All workflow operations ran sequentially. No Step 5 implementation, canonical model training, full-5M scoring, canonical rank generation, campaign activation, commit, or push was performed by this Step 4 workflow. Selected regression tests exercised bounded model/scoring/rank fixtures. Step 13 remains the integration boundary for the result-snapshot download engine; source-supported profile metadata does not claim that download engine is already implemented.

## Implementation and reasoning

| File | Change |
|---|---|
| `data_generation_scripts/generate_us_demographic_synthetic.py` | Append nine 0/1 flags and three nullable identifiers; seed/person-ID integer mixing separate from the base RNG; distribution/availability/rule/hash summary |
| `app/database/schema.py` | Schema 16 fresh DDL and additive, idempotent 15→16 migration; preserve first 28 columns and old rows; false/null migration defaults; binary SQL CHECK constraints |
| `app/services/data_validation_service.py` | Governed supplied email/phone validation; required binary flags; opaque and UUID-like formats; required identifier/address relationships; Telemarketing/DNC exclusion |
| `app/services/data_reconciliation_service.py` | All channel counts and activation-identifier counts; nine cross-field structural violation metrics |
| `app/services/omnichannel_profile_contracts.py` | Source support unlocks all ten registry profiles, including the three formerly source-gated profiles; runtime availability still rejects legacy/missing source fields; privacy rules unchanged |
| `tests/test_phase11_contactability_identifier_extension.py` | Byte-deterministic gzip generation; chunk-independent appended fields; generated-row/summary checks; real v15 migration preservation; full-byte provenance drift; exact frozen feature contract |
| `tests/test_data_validation_service.py`, `tests/test_data_reconciliation.py` | Truthfulness, identifier-format, binary-flag, and structural-reconciliation matrix |
| `tests/test_data_import.py`, schema tests, profile tests | Extended fixture contract and schema-version/post-extension availability expectations |
| `tests/test_data_api.py`, `tests/test_health.py` | Isolate TestClient startup recovery as well as request dependencies, preventing fixture tests from reconciling the real 5M runtime |
| `README.md`, `data/README.md` | Current schema, source hashes/LFS identity, rate assumptions, source checksum policy, and expected stale-score boundary |
| Canonical gzip, sample, summary | Deterministically regenerated source with appended fields; no customer/campaign-sales source regeneration |

The importer already derives its exact demographic header and SQL insert columns from `DEMOGRAPHIC_COLUMNS`; extending that authority updates importer behavior without introducing a second header contract. Its staging/atomic publication and whole-file checksum implementation are retained unchanged.

The original demographic RNG is untouched by the extension. New flags/identifiers use separate ID-derived salts and are stable across chunk sizes. Base demographic generation is certified for the documented canonical seed/chunk configuration; this evidence does not claim that the legacy base RNG is chunk-size independent.

## Source contract

Appended columns, in order:

`email_contactable, direct_mail_contactable, sms_opt_in, whatsapp_opt_in, telemarketing_contactable, do_not_call, push_token, push_opt_in, advertising_id, advertising_targetable, web_visitor_id, onsite_targetable`.

Flags are required 0/1 values. Identifier absence is a CSV blank and becomes SQL NULL. Push is `pt_` plus 32 lowercase hex characters; advertising IDs are deterministic UUID-like v4/variant strings; website keys are `wv_` plus 32 lowercase hex characters. All are synthetic, not live platform identifiers. Identifiers are never invented during export.

The documented rates are synthetic POC assumptions, not measured population consent rates. The design includes independent per-channel permissions, nullable activation identifiers, and conditional opt-in/targetability so source presence is not conflated with permission. Full targets and observed shares are recorded in `data/README.md` and the canonical summary.

| Metric | Canonical count |
|---|---:|
| email_contactable | 4,398,985 |
| direct_mail_contactable | 4,599,610 |
| sms_opt_in | 2,100,825 |
| whatsapp_opt_in | 1,500,731 |
| telemarketing_contactable | 2,745,904 |
| do_not_call | 899,928 |
| push_token present / missing | 3,099,544 / 1,900,456 |
| push_opt_in | 1,673,698 |
| advertising_id present / missing | 3,699,362 / 1,300,638 |
| advertising_targetable | 2,514,943 |
| web_visitor_id present / missing | 3,349,299 / 1,650,701 |
| onsite_targetable | 2,410,207 |

Email, phone, and mailing address requirements are checked before accepting contactable rows. SMS/WhatsApp/Telemarketing cannot be true without phone. Telemarketing cannot be true with DNC. Push/Display/Website flags cannot be true without their source identifiers. Generated violations, import rejections, and all nine reconciled relationship violations are zero.

## Canonical generation, hashes, and publication

Generation used seed `20260818`, `N_ROWS=5000000`, `CHUNK=200000`, `ID_OFFSET=0`, and the existing canonical output names. It started only after the implementation/import/schema/compatibility test checkpoints were green. Generation completed in 228.3 seconds.

| Identity | Value |
|---|---|
| File | `data/usa_demographic_synthetic_5000000_rows.csv.gz` |
| Rows / columns | 5,000,000 / 40 |
| Bytes | 512,842,205 |
| Raw gzip SHA-256 / computed LFS object identity | `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d` |
| Decompressed CSV SHA-256 | `5694d2048e96b270a3d522e2cc08c1af26561f6fd3c08f104e9957e76653612c` |
| First 28 columns, all rows and original header | `a664b1a3904079a3c8b5c398de10009d52e8fd2ec6b4751a5caebb4512cb7dba` |
| Operational import source checksum | `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f` |

The first-28-column projection matches the old decompressed content hash exactly, proving byte-for-byte preservation of every original row/feature value—not merely similar distributions. The full new gzip SHA-256 was independently checked with `Get-FileHash`; `git lfs pointer --file=...` reports the same object SHA and size. This is the working-tree source identity, not a claim that the object was staged, uploaded, or remotely frozen.

Database initialization verified schema 16. Explicit replacement used:

`python scripts/import_demographics.py --file data/usa_demographic_synthetic_5000000_rows.csv.gz --replace --progress-every 200000`

Import 4 completed with 5,000,000 read/inserted and zero rejected, publishing source rows and provenance atomically. Persisted start: `2026-09-16T07:46:45Z`; completion: `2026-09-16T08:17:41Z` (30m56s, including a temporary throughput slowdown and final indexed-table publication). The run was monitored, not restarted. After continuation, completion was verified directly from persisted import metadata rather than assuming success from the lost execution-session handle.

`python scripts/validate_data.py --json` returned exit 0 / overall `OK` in 44.994 query seconds:

- Customers: 125,000, structural errors 0.
- Campaign sales: 570,000, structural errors 0.
- Demographics: 5,000,000 and 5,000,000 distinct person IDs, ages 18–100, structural errors 0.
- All nine new relationship violations: 0.
- All 57 required indexes: present.
- Imported contactability/identifier counts match the generated summary exactly.

## Frozen features and provenance/currentness

The frozen ordered features remain:

`age, gender, state, individual_yearly_income, marital_status, education, employment_status, resident_status, resident_type, family_member_count, type_of_employment`.

Feature contract version remains 1; contract SHA remains `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`. The unchanged feature file SHA is `b3e3f382080b480751080da4b1a03c9fdb3ed25fc7740e9490723a2c880234be`. Historical/model/scoring engine authorities are not rewritten.

All new fields are excluded from model inputs, including `SCORING_READ_COLUMNS`, which remains person ID plus the frozen 11 features. The importer hashes filename + NUL + all compressed bytes + NUL. No new field is excluded to preserve the old checksum.

Old import 3 checksum `e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75` is historical, not current. `resolve_current_scoring_context_lightweight` was called sequentially for scoring runs 1 and 2 after import:

- Status remains `COMPLETED`, preserving historical records.
- `is_canonical=false`.
- `demographic_source_verified=false`.
- `historical_source_verified=true`.
- Issues explicitly include current demographic import-ID mismatch and checksum mismatch, plus no current canonical run for the model.

Customer/campaign source imports and feature contract did not change. Historical analyses/models can therefore remain reusable when their existing exact Phase 10 gates permit; this is not a blanket waiver of those gates. The new demographic universe requires a new full scoring generation before current targeting/export. It is intentionally deferred to later certification and was not run here.

Persisted models/scoring runs/jobs remain 2/2/7. A separate failed historical analysis row 3 was observed after continuation (created `2026-09-16T09:04:48Z`, no matching observations); it was not removed or represented as successful Step 4 evidence.

Historical Phase 8–10 certification records and the Phase 9 baseline-pinned backend assertion script retain their old-source facts. They do not certify the changed canonical source; they are not rewritten to fabricate currentness.

## Test checkpoints

Pre-regeneration checkpoint 1:

`pytest -q tests/test_phase11_contactability_identifier_extension.py tests/test_data_validation_service.py tests/test_database_schema.py tests/test_data_import.py tests/test_data_reconciliation.py tests/test_phase11_omnichannel_profile_contracts.py tests/test_phase9_schema.py tests/test_phase10_schema_registry_repository.py tests/test_feature_preprocessing.py tests/test_prospect_scoring_service.py`

**171 passed in 203.97s.**

Pre-regeneration checkpoint 2:

`pytest -q tests/test_phase10_context_identity.py tests/test_phase10_historical_context_extension.py tests/test_phase10_historical_resolution.py tests/test_phase10_model_resolution.py tests/test_phase10_scoring_resolution.py tests/test_scoring_compatibility.py tests/test_data_api.py tests/test_health.py`

**91 passed in 310.38s.**

An earlier checkpoint had three expectation/fixture failures, which were corrected before regeneration. An initial compatibility/API run was stopped because TestClient startup recovery used the real runtime rather than the overridden request DB; fixture startup isolation was corrected, then the full selected checkpoint was rerun green. Interrupted and failed runs are not counted as successful validation.

The selected suites cover generator determinism, required/nullable source fields, schema migration, atomic import regressions, structural reconciliation, profile availability/privacy, unchanged feature processing/scoring, Phase 10 historical/model/scoring compatibility, and data/health APIs. This is targeted Step 4 validation, not a claim that the entire repository regression or Phase 11 browser/full-5M scoring certification has already run.

Final post-documentation checkpoint:

`pytest -q tests/test_phase11_contactability_identifier_extension.py tests/test_data_validation_service.py tests/test_phase11_omnichannel_profile_contracts.py`

**78 passed in 19.68s**, including 27 additional blank/out-of-range binary-flag cases. This overlaps the earlier targeted suites and is not counted as 78 additional unique tests.

`python -m compileall -q app data_generation_scripts scripts tests`: passed.

`git diff --check`: passed (exit 0) after rerunning outside the Windows sandbox restriction that prevented the LFS helper from starting. Only normal CRLF-to-LF notices remain; no staging, commit, or push occurred.

## Stop boundary

`STOP_AFTER_STEP_04`

Step 5 and all later prompts require the user's next instruction. No new full scoring generation is performed merely to make old source provenance appear current.
