# Required functional families and background assertions

Every family below must expand into executable cases for the actual current controls. Inventory runtime widgets; do not stop at this family table.

| ID | Surface | Native UI functionality | Backend / durable proof |
|---|---|---|---|
| U01 | Startup/global | load, health/version, retry, title, sidebar collapse/expand/resize | real health/component state; no heavy jobs from navigation |
| U02 | Routing | Home/Find/Results/detail, hash aliases, reload/back/forward, unknown/invalid IDs | correct requests; stale detail response cannot replace newer page |
| U03 | Home | metrics/cards, recent results, empty/error/retry, action shortcuts | counts agree with DB/API; queued/completed/blocked shown honestly |
| U04 | Search context | exact products and all historical context fields | canonical normalized context; source/catalog identity |
| U05 | Every multiselect | open/search/select/deselect/all/clear/chips/keyboard/outside-click/disabled | payload contains exact options; no ghost choices |
| U06 | Targeting | all age/income/gender/geography/education/marital/employment/resident/family fields, advanced reveal/reset | strict AND/OR predicates; unavailable choices rejected; dedup |
| U07 | Score modes | v3 minima50–90+, advanced v2 discrete bands, mode switches | discriminator/fields/cache separation; no probability dependency in v3 |
| U08 | Selection | ALL_MATCHING/TOP_N, target count, invalid bounds/missing product/form validation | exact qualified vs selected count; no silent filter widening |
| U09 | Preflight | ready/unprepared/building/stale/unsupported/zero/network failure, response races | actual counts/currentness; missing!=zero; failed callback cannot preserve stale cache |
| U10 | Submit/progress | create, double-click protection, queued/waiting/building/processing/completed, cancel only if implemented | real coordinator/worker; attempts/leases; truthful counts/ETA/timing |
| U11 | Retry/restart | transient failure retry, data block, server/worker restart, refresh while active | old token fenced; new attempt/history; one heavy dependency; no loop |
| U12 | Results list | refresh, pagination/load older, sorting/filter controls if present, card open | correct ordered records; no duplicate/missing list items |
| U13 | Result detail | context/criteria/counts/summary/provenance/technical toggles/rerun/back | immutable membership; versioned labels; original choices and ID matching |
| U14 | Downloads | every available channel/profile and contact-only alternative, blocked/unavailable, abort/retry | actual downloaded CSV/file; consent/identifier/hash/currentness/audit counts |
| U15 | Feedback | CSV/JSON template, choose file, valid upload, malformed/mixed/duplicate/oversize/wrong person/stale outcomes | validation/transaction/dedup/lineage; v3 not routed into probability calibration |
| U16 | Historical analysis retained | options, all filters/outcomes/date controls/reset/analyze, all tabs/profile comparisons, recent reopen | actual analysis record/counts/breakdowns; no future/identity leakage |
| U17 | Model training retained | source/options/config/train, progress/job polling, model/candidate details/reopen | bounded actual worker on valid grouped fixture; unsupported canonical split rejected separately |
| U18 | Scoring retained | choose model/score/poll/readiness/retry only on bounded QA | exact capped population, real job/generation/artifact; zero 5M dispatches |
| U19 | Audience Explorer retained | prepare/retry, filters/min-max/rank/percentile/decile, estimates/search/pagination/profile dimensions/tabs/save | genuine bounded rank/analytics/cache/selection/saved membership; old semantics preserved |
| U20 | Data Status retained | refresh/status/summary/import history/reconciliation and errors | actual fixture imports/metadata/expected QA counts, no invented upload control |
| U21 | Saved Target Groups retained | refresh/list/open/preview/search/paging and actions actually present | immutable saved audience/context/source/currentness; deleted/stale states |
| U22 | Insights retained | every implemented interaction, empty/read-only/placeholder classifications | actual source-backed aggregates; no false functionality for static placeholders |
| U23 | Planner retained | all five steps, context/filter/edit/back/next/intelligence prepare/attach/detach/retry/preview/load more/review/save | genuine Phase 10/targeting/context/draft APIs on bounded compatible data |
| U24 | Campaign Builder retained | new/select audience/details/steps/review/draft/edit/finalize/export/history | durable campaign transitions/idempotency/currentness/CSV/audit; no campaign send |
| U25 | Source changes | preflight/result open during source change, catalog disappearance, reimport | atomic import + latest source checks + stale invalidation + safe restart repair |
| U26 | Accessibility/layout | keyboard/focus/labels/live regions/zoom,desktop/tablet/mobile, overflow/loading/empty/error | no hidden focus traps; actual payload unaffected by viewport |
| U27 | Security/data boundaries | query/path invalid IDs, duplicate requests, malicious text/file cells, technical detail masking | safe errors, input validation, CSV formula guards, no tokens/contact leakage |
| U28 | Lifecycle | close/reopen page, multi-tab, slow network, offline, shutdown/restart after queued work | durable recovery, no stray pollers/jobs, stopped processes and integrity checks |

### Channel/profile matrix

Enumerate actual OMNICHANNEL_PROFILE_REGISTRY and /api/export-profiles at runtime, including v1/v2 export schemas, v3 versioned fields and contact-only variants. Synthetic fixtures provide valid email/phone/address/opt-in/opt-out/do-not-call/advertising IDs/push/web visitor variants needed by actual profiles. No real destination/provider contact or activation. Unavailable profiles get explicit guard tests; available profiles get actual browser download + independent file assertions.

### States and boundaries

At least happy path, empty state, invalid input, disabled precondition, stale source, missing intelligence, temporary failure, retry/restart, and incompatible mode for each relevant family. V3 threshold exact/just-below and numeric filter inclusive bounds need independently known fixtures. Do not force all 28 families into states their actual controls don't implement; classify absent capabilities with source proof while testing every implemented one.
