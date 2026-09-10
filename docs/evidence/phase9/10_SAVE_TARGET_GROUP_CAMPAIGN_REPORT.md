# Phase 9 Step 10 — Save Target Group and Campaign Draft Report

Date: 2026-09-10
Status: PASS

## Scope

This step completes the business Campaign Planner workflow by saving the exact reviewed selection as an immutable Saved Target Group and creating, or updating, its Phase 7 Campaign in `DRAFT` status. It does not finalize, export, activate, or send a campaign and does not begin Phase 9 Step 11.

## Immutable Saved Target Group

`POST /api/campaign-planner/contexts/{id}/save-target-group-and-create-draft` is gated by the same explicit `READY` targeting-intelligence and canonical Phase 6 preparation checks as the exact preview.

The save orchestration:

1. reloads the canonical saved Phase 9 context and targeting criteria;
2. rejects a criteria-hash race or non-READY/stale source;
3. normalizes every Phase 9 Audience Filter Contract branch;
4. materializes the exact OR-union with deterministic de-duplication and applies TOP_N once, when requested;
5. records the exact resolved count through the existing immutable Phase 6 Saved Audience persistence path; and
6. stores an additive immutable Phase 9 metadata record keyed by the Saved Audience ID.

The metadata record preserves:

- every normalized filter branch and a canonical SHA-256 over the complete branch list;
- the immutable campaign-context JSON, version, and SHA-256;
- the immutable targeting-criteria JSON, versions, and SHA-256;
- the explicit READY scoring-source ID and status;
- the exact resolved count; and
- the creation timestamp.

The underlying Phase 6 Saved Audience continues to preserve scoring, model, analysis, data-import, source-checksum, filter/rank/selection, and analytics provenance. Existing Saved Audiences remain unchanged. Schema migration 14 is additive and creates only `phase9_saved_target_groups` plus its context index.

## Exact Phase 7 linkage

The Campaign is created only after the Target Group has been saved. It preserves the campaign name, description, delivery channel, planned launch date, Saved Audience linkage, scoring/model/analysis lineage, exact count, selection definition, and complete Phase 9 filter-branch hash. The Campaign remains `DRAFT`; `finalized_at` remains null.

The Phase 7 member resolver recognizes Phase 9 metadata additively. Legacy Saved Audiences continue to resolve their single AND-filter definition exactly as before. A Phase 9 Target Group resolves all immutable branches as one parenthesized OR-union beneath the scoring-run predicate, applies the saved selection once, orders by score descending and person ID ascending, and cannot duplicate a person selected by more than one branch.

When criteria change after a save, another immutable Saved Audience and Phase 9 metadata record are created. The existing Draft Campaign is updated to the new Saved Target Group. The prior Saved Target Group and its context, criteria, filters, hash, count, and provenance are not updated. A non-Draft Campaign is rejected before a replacement Target Group is saved.

## Reopen and currentness

`GET /api/campaign-planner/contexts/{id}/campaign-draft` reopens:

- the immutable business campaign context;
- the immutable targeting criteria;
- the Saved Target Group name, description, exact count, complete filter hash, branch count, creation time, and immutable marker;
- the linked Campaign draft; and
- current targeting-source and combined Saved Audience/Campaign currentness.

Context, criteria, branch, count, source, Saved Audience, and Campaign linkages are checked on reopen. A changed source dataset returns `STALE` and presents **Needs refresh**. Another save is blocked until targeting intelligence is refreshed; no fallback source, estimate, or stale count is used.

## Business review and save experience

Review & Save now displays three business-readable summaries:

- Campaign — name, description, products, type, category, offer, channel, and planned launch date;
- Targeting — match strength, age, gender, location, income, and advanced choices; and
- Target Group — exact selected count, targeting-source status, and currentness.

The form suggests `<Campaign Name> Target Group`, keeps the name editable, accepts an optional Target Group description, and labels the result **Saved Target Group**. The success view shows the Saved Target Group and Campaign IDs, exact count, currentness, delivery channel, planned date, and Campaign `DRAFT` status. Reopening restores the server-owned immutable snapshots rather than relying only on browser-session state.

The default review contains no names, email addresses, phone numbers, street addresses, postal addresses, or contact records. It explicitly states that save does not expose contact PII, finalize, export, activate, or send. Existing Phase 7 PII acknowledgement and export controls were not relaxed or bypassed.

## Tests

`tests/test_phase9_save_target_group_campaign.py` proves:

- API creation of an immutable Saved Target Group and linked Draft Campaign;
- exact count, full branch hash, source, scoring/model/analysis lineage, context linkage, and no PII fields;
- reopen of immutable business context, criteria, Saved Target Group summary, and currentness;
- exact disjoint-branch Phase 7 member resolution with stable order and no duplicates;
- editing context, campaign details, and Target Group name before first save persists only the final values;
- criteria changes create a new Saved Target Group and update the same Draft Campaign without mutating the old group;
- stale source state is visible on reopen and blocks another save without creating an audience or campaign; and
- the schema’s fresh-install, upgrade, preservation, idempotence, constraint, and failed-migration rollback behavior.

Frontend assertions verify the required review regions, editable name, privacy/draft boundary, save and reopen endpoints, safe DOM rendering, exact-preview event linkage, and served JavaScript asset.

## Files

- `app/database/schema.py`
- `app/repositories/campaign_targeting_context_repository.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/campaign_service.py`
- `app/services/saved_audience_service.py`
- `app/services/target_group_campaign_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/campaign-planner-form.js`
- `frontend/js/campaign-review.js`
- `frontend/js/target-group-preview.js`
- `tests/test_frontend.py`
- `tests/test_phase9_save_target_group_campaign.py`
- `tests/test_phase9_schema.py`

## Verification

- Step 10 create/reopen/edit/immutability/linkage/stale suite — 5 passed.
- Complete pre-Step-10 Phase 9 and frontend regression sequence — 78 passed (39 Phase 9 and 39 frontend checks).
- Targeted final Review & Save browser-contract checks — 3 passed.
- Phase 6 Saved Audience and Phase 7 Campaign/API/export regression suite — 31 passed.
- Schema 14 fresh-install, v12 upgrade, idempotence, preservation, constraints, and v13 rollback suite — 4 passed.
- `python -m compileall -q app tests` — passed.
- `git diff --check` — passed; Git emitted only existing line-ending warnings.

Ruff and Node.js are not installed in this environment. The available Python compilation, service/API integration, exact-member reconciliation, legacy regression, served-asset, browser-contract, schema, and diff checks passed.

No project data import, model training, or scoring job was run. Automated tests used isolated temporary SQLite databases with deterministic local fixtures and fixture-only audience preparation.

## Acceptance result

PASS. A business user can review the exact current selection, save it as an immutable Saved Target Group, create or update a linked Campaign draft, and reopen the preserved business context and currentness without exposing PII or weakening Phase 7 export controls.

STOP — no Phase 9 Step 11 work was performed.
