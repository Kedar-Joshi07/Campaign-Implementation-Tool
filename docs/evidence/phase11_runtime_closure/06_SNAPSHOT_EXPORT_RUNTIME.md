# Phase 11 Result Snapshot and Omnichannel Export Runtime Wiring

## Scope and baseline

- Prompt: `06_STEP_06_RESULT_SNAPSHOT_AND_EXPORT_RUNTIME_WIRING.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Execution window: 2026-09-20 to 2026-09-21 (Asia/Calcutta)
- Result: **PASS**

Step 6 verified the existing snapshot materialization and all ten governed export profiles through the real FastAPI application. No profile contract, profile availability rule, snapshot schema, or export implementation was changed.

## Production runtime composition

The application was launched with the normal entry point:

```text
python -m uvicorn app.main:app
```

Startup created the production `ResultSnapshotMaterializer` with the repository project root, the current `data/campaign_poc.db`, and the current Phase 10 services through the Phase 11 runtime coordinator. Startup reconciliation completed before the application accepted requests:

```text
Phase 11 runtime composition completed | workers=2 poll_seconds=5.0
Phase 10 startup reconciliation completed | resumed_orchestrations=0
Phase 11 startup reconciliation completed | scheduled_searches=0
Result export startup reconciliation completed | reconciled_stale_exports=0
```

The application shut down cleanly after the live verification.

## Completed real-runtime search

A Direct Mail search was submitted through the normal `POST /api/potential-customer-search` route and observed through the normal status route until terminal completion.

| Field | Verified value |
| --- | --- |
| Search run | 12 |
| Campaign name | `Runtime Step6 DIRECT_MAIL` |
| Status | `COMPLETED` |
| Export profile | `DIRECT_MAIL_CONTACT_V1` |
| Result source | `EXACT_RESULT_REUSE` |
| Selected count | 4 |
| Result snapshot | 2 |
| Generation | 1 |
| Analysis run | 4 |
| Model run | 3 |
| Scoring run | 3 |
| Phase 10 orchestration | 8, `READY` |
| Phase 10 reuse plan | analysis/model/scoring/ranking all `REUSE` |

The real coordinator took the queued run through Phase 10 compatibility/currentness validation, reused the compatible durable lineage, validated/materialized the existing exact result, and published the terminal result. The Results API returned snapshot 2 as `CURRENT` and download eligible. No new analysis, model, scoring, or ranking run was created.

The current runtime emitted scikit-learn compatibility warnings because the stored artifact records 1.7.2 while the executing environment provides 1.7.1. Compatibility validation nevertheless completed successfully; this is recorded as an environment observation, not suppressed or treated as proof of equivalence by itself.

## Snapshot artifact validation

Snapshot 2 was validated independently against SQLite, its manifest, and the gzip CSV artifact.

| Check | Result |
| --- | --- |
| Artifact | `artifacts/results/result_snapshot_000002/members.csv.gz` exists |
| Manifest | `artifacts/results/result_snapshot_000002/manifest.json` exists |
| SQLite SHA-256 | `249419a561584431d7755a4d688f07a0b1accf40b321b7c4bb3656dcc475be0f` |
| Manifest `file_sha256` | `249419a561584431d7755a4d688f07a0b1accf40b321b7c4bb3656dcc475be0f` |
| Actual artifact SHA-256 | `249419a561584431d7755a4d688f07a0b1accf40b321b7c4bb3656dcc475be0f` |
| SQLite resolved count | 4 |
| Manifest row count | 4 |
| Actual decompressed row count | 4 |
| Stored columns | `person_id`, `propensity_score`, `percentile_bucket`, `decile`, `rank_band` |
| Contact PII columns | none |

The checksum and row count agree across all three sources. The immutable membership snapshot contains scoring membership only; channel contact data is joined only while a governed export stream is produced.

## Omnichannel route certification

`GET /api/potential-customer-search/options` reported all ten profiles as available with no unavailable reason. Every download below was then requested through the normal live route:

```text
GET /api/potential-customer-search/runs/{search_run_id}/download
```

Every response returned HTTP 200, `text/csv; charset=utf-8`, and the correct `X-Export-Profile` value.

| Channel | Profile | Run | Selected | Deliverable / rows | Undeliverable | CSV SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Email | `EMAIL_CONTACT_V1` | 5 | 4 | 4 | 0 | `626a82bc81eac4107aecd73284b059feb9a522a63b2caa1d26d3259090c981d6` |
| Direct Mail | `DIRECT_MAIL_CONTACT_V1` | 12 | 4 | 4 | 0 | `fe762d40926bde0b88b8c19cdd210a9e38f583ea7d441b76a87cfe0883058492` |
| SMS | `SMS_CONTACT_V1` | 6 | 4 | 0 | 4 | `989b258eb94558c6749f051c625cf08d0b4121e2de22fc10b40d61759f165a8c` |
| WhatsApp | `WHATSAPP_CONTACT_V1` | 7 | 4 | 1 | 3 | `a58f3efb43c21d1f82a2515f59e78c21051c42758c455ac9eeafba649deae84d` |
| Telemarketing | `TELEMARKETING_CONTACT_V1` | 13 | 4 | 2 | 2 | `a516e5df6c5a3211b0b2d583d3b9ac92748f7a8ccdd1b07fbd5cddf27378c239` |
| Paid Social | `PAID_SOCIAL_AUDIENCE_V1` | 8 | 4 | 4 | 0 | `846709c59fae3c54f6d1de9f7000fc22ee35969718fc9c5dfa8da1a9a4d98a74` |
| Paid Search | `PAID_SEARCH_AUDIENCE_V1` | 14 | 4 | 4 | 0 | `846709c59fae3c54f6d1de9f7000fc22ee35969718fc9c5dfa8da1a9a4d98a74` |
| Mobile Push | `MOBILE_PUSH_CONTACT_V1` | 15 | 4 | 3 | 1 | `bd162fd13f222a369b05ebf24a19b54aa76b3449196b5121c60e9daee6ab9588` |
| Display | `DISPLAY_AUDIENCE_V1` | 16 | 4 | 2 | 2 | `a5e5dfa4fca053205c1dd2268fe4469df138ca8b86b348d4cbefe83ed18095b9` |
| Website Onsite | `WEBSITE_AUDIENCE_V1` | 17 | 4 | 3 | 1 | `152b287a58bdff1dade3a6a5c3e4d3db71adfef24b9cdf68bae71191261ca527` |

For every row in the matrix:

- `selected_count = deliverable_count + undeliverable_count`;
- streamed CSV row count equals `deliverable_count`;
- the downloaded-file SHA-256 equals the terminal audit SHA-256;
- the export audit status is `COMPLETED`;
- audit currentness is `CURRENT`;
- the audit references snapshot 2; and
- `safe_error_message` is null.

The live downloads created terminal export events 7 through 16. Paid Social and Paid Search intentionally produce the same deterministic audience-key payload and therefore the same checksum. The zero-deliverable SMS export correctly contains its governed header and zero data rows.

### Bounded carrier setup

Runs 5-8 already represented Email, SMS, WhatsApp, and Paid Social. Run 12 is the full normal-runtime search proof for Direct Mail. To avoid repeating the same approximately 14-minute, 5M-row Phase 10 currentness validation for five additional profiles, runs 13-17 were created with the production repositories as immutable carrier records over the already validated targeting identity, generation 1, scoring run 3, and snapshot 2. They were completed with `EXACT_RESULT_REUSE`; no fabricated snapshot or export artifact and no new heavy-work run was created.

This optimization affected only preparation of profile-specific carrier records. All ten CSVs, including runs 13-17, were generated and audited by the real application download route and production export service.

## Privacy and CSV safety

- Paid Social, Paid Search, Display, and Website Onsite headers and rows contain audience keys rather than raw email addresses, phone numbers, mobile identifiers, or postal addresses.
- Inspection of all ten live files found zero unescaped cells beginning with `=`, `+`, `-`, or `@`.
- Formula-injection mitigation is applied to every header/data cell by the export engine.
- The canonical four-person data did not contain a hostile formula payload, so the dedicated regression test injected those edge cases and verified safe escaping and normalization.
- Phase 11 JSON contracts were also regression-tested to ensure they expose neither contact PII nor raw filesystem paths.

## Focused automated regression

Executed:

```text
python -m pytest \
  tests/test_phase11_omnichannel_export_engine.py::test_every_profile_streams_exact_header_counts_checksum_and_privacy \
  tests/test_phase11_omnichannel_export_engine.py::test_csv_edge_cases_normalization_and_formula_injection \
  tests/test_phase11_omnichannel_export_engine.py::test_download_api_streams_governed_file_and_safe_statuses \
  tests/test_phase11_api_backward_compatibility.py::test_phase11_json_contracts_do_not_return_contact_pii_or_raw_paths -q

13 passed in 53.14s
```

The parametrized cases cover all ten profiles, including exact governed headers, deliverability counts, deterministic checksum behavior, paid-media privacy, real router behavior, safe failure states, and formula-injection controls.

## Repository impact and sequencing

- No production source or contract change was required by Step 6.
- This evidence document is the only Step 6 repository change.
- Step 5 was explicitly skipped at the time of this certification and was subsequently completed in `05_CONCURRENCY_IDEMPOTENCY.md`.
- Step 7 was not started.

## Decision

**PASS - Step 6 result snapshot and omnichannel export runtime wiring are certified.**

The real runtime can complete a durable search, expose its current immutable result through the Results API, and generate all ten governed omnichannel exports with reconciled counts, deterministic checksums, durable audits, contact-privacy controls, and CSV formula-injection protection.
