# Phase 11 API and Schema Reference

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/business/overview` | Metadata-only business KPIs |
| `GET` | `/api/business/recent-results?limit=5` | Bounded recent searches |
| `GET` | `/api/potential-customer-search/options` | Backend-owned context, criteria, and profile options |
| `POST` | `/api/potential-customer-search/runs` | Validate, persist, and hand off one immutable search |
| `GET` | `/api/potential-customer-search/runs` | Bounded newest-first search history |
| `GET` | `/api/potential-customer-search/runs/{search_run_id}` | Business-safe run projection |
| `GET` | `/api/potential-customer-search/runs/{search_run_id}/status` | Pollable status |
| `GET` | `/api/potential-customer-search/results` | Rich Results history projection |
| `GET` | `/api/potential-customer-search/runs/{search_run_id}/result` | Result detail, currentness, aggregates, and lineage without contact PII |
| `GET` | `/api/potential-customer-search/runs/{search_run_id}/download` | Governed streaming CSV for the saved profile |
| `GET` | `/api/export-profiles` | Backend-owned omnichannel profile registry |

Validation errors use 422, missing lineage uses 404, incomplete/stale/conflicting state uses 409, and unexpected errors return a sanitized 500. JSON APIs never return contact identifiers, local artifact paths, SQL text, or stack traces. Contact data can appear only in the authorized CSV projection for the run's immutable saved profile.

## Schema version 18

The migration chain is additive and idempotent:

| Version | Phase 11 addition |
|---:|---|
| 16 | Twelve governed demographic contactability/consent/activation fields |
| 17 | `campaign_search_runs`, `campaign_result_snapshots`, `campaign_result_export_events` |
| 18 | `campaign_search_future_lineage` nullable write-once future seam |

### Search runs

Each `campaign_search_runs` row is a distinct intentional submission with exact context, canonical targeting criteria/branches and hashes, selection mode/count, delivery profile, analytical lineage, result source, status, counts, timestamps, and safe error state. Statuses are `QUEUED`, `PROCESSING`, `COMPLETED`, `BLOCKED`, and `FAILED`. Result sources are `EXACT_RESULT_REUSE`, `INTELLIGENCE_REUSE`, and `NEW_INTELLIGENCE_BUILD`.

### Result snapshots

`campaign_result_snapshots` stores immutable metadata for one analytical membership artifact: exact cache key, generation, criteria/branch hashes, selection, resolved count, portable artifact URI, compressed SHA-256, and currentness. It stores no contact PII. Currentness is `CURRENT`, `STALE`, or `UNVERIFIED`.

### Export events

`campaign_result_export_events` is append-only aggregate audit. It records run/snapshot/profile lineage; selected, deliverable, undeliverable, and emitted counts; exact CSV checksum; status; timestamps; currentness; and a bounded safe message. Status is `RUNNING`, `COMPLETED`, `FAILED`, or `ABORTED`.

### Future lineage

`campaign_search_future_lineage` is one-to-one with a search run. `activation_id`, `provider_campaign_id`, `feedback_batch_id`, and `outcome_dataset_id` remain nullable, completed-search-only, write-once, and non-deletable. Phase 11 exposes no API that populates them.

## Frozen contract versions

- Search run: `1`
- Result cache key: `1`
- Result membership: `1`
- Result export: `1`
- Omnichannel export profile: `1`
- Existing audience filter, selection, rank, feature, Campaign, Phase 9, and Phase 10 contracts remain unchanged.

The retained Phase 1–10 routes remain registered. UI hiding does not remove or authorize APIs, and the legacy finalized-Campaign Email/Direct Mail export endpoint remains separate and unchanged.
