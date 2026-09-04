# Phase 7 Implementation Summary

Status: FINALIZED

Phase 7 adds governed Campaign Builder workflows on top of the completed Phase 6 audience stack. The implementation is intentionally bounded to target-list export and does not include activation/send platform orchestration.

## Scope delivered

- Campaign draft creation from current saved audiences.
- Campaign updates while in DRAFT state.
- Campaign currentness evaluation before finalize/export.
- Campaign finalize transition to FINALIZED.
- Deterministic export generation for EMAIL and DIRECT_MAIL contact profiles.
- Export-event auditing with provenance and currentness metadata.

## Workflow states

Campaign lifecycle states are frozen to:

- DRAFT
- FINALIZED

No ACTIVE/SENT/LAUNCHED states are implemented.

## Handoff and currentness model

Phase 7 accepts immutable saved audiences as the handoff contract from Phase 6. Campaign eligibility is gated by source and contract currentness checks:

- Saved audience currentness must pass.
- Scoring provenance must remain current and canonical.
- Historical and demographic source checksums/import IDs must match.
- Feature/artifact governance checks must pass.
- Audience rank boundaries and analytics snapshot readiness must pass.

## Deterministic member resolution

Member resolution is deterministic and reproducible for the same saved audience definition and source state.

- Selection mode and filters are normalized and persisted.
- Rank-band and score ordering are stable.
- Export rows preserve deterministic person ordering.

## Export contract and profiles

Frozen contracts:

- campaign_contract_version = 1
- campaign_export_contract_version = 1
- campaign_member_resolution_contract_version = 1
- campaign_export_snapshot_contract_version = 1

Supported channels and export profiles:

- EMAIL -> EMAIL_CONTACT_V1
- DIRECT_MAIL -> DIRECT_MAIL_CONTACT_V1

Email profile columns:

- person_id
- propensity_score
- percentile_bucket
- decile
- rank_band
- first_name
- last_name
- email

Direct-mail profile columns:

- person_id
- propensity_score
- percentile_bucket
- decile
- rank_band
- first_name
- last_name
- address_line_1
- address_line_2
- city
- state
- postal_code

## Deliverability and export auditing

Each export event records aggregate audit metadata:

- selected_count
- deliverable_count
- undeliverable_count
- row_count
- csv_sha256
- started_at/completed_at
- start_provenance_sha256
- source_changed_during_export
- completion_currentness_state
- safe_error_message (for safe failure reporting)

Export requires explicit acknowledge_pii=true.

## PII boundary and CSV safety

PII boundary controls:

- No arbitrary field picker for exports.
- Forbidden fields are excluded (for example customer_id, phone_number, ethnicity, religion, occupation_industry).
- Campaign and audience APIs remain aggregate/metadata focused; no activation/send adapters are added.

CSV safety:

- Formula-leading cell values are hardened before stream output.
- Streaming export does not persist server-side CSV files.

## Schema evolution

Phase 7 introduces additive schema migrations:

- v11: campaigns and campaign_export_events tables.
- v12: export provenance/currentness additions for hardened auditability.

Current schema version after Phase 7 freeze: 12.

## 5M evidence and freeze confidence

Phase 7 evidence confirms real 5M baseline continuity and deterministic export behavior under the frozen contracts. See evidence index in docs/evidence/README.md and these key artifacts:

- docs/evidence/phase7_final_acceptance_and_freeze.json
- docs/evidence/phase7_final_export_hardening_5m.json
- docs/evidence/phase7_export_profiling_baseline.json
