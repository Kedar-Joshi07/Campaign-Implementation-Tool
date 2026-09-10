# Phase 9 Step 11 — Progressive Disclosure Report

Date: 2026-09-10
Status: PASS

## Scope

This step keeps the Phase 9 business workflow understandable by default while retaining complete audit provenance behind collapsed **View technical details** controls. It does not introduce authentication or RBAC, remove an earlier capability, change targeting selection, retrain or rescore a model, or begin Phase 9 Step 12.

## Default business explanation

The **Why these people?** explanation is deterministic and now includes:

- the current, up-to-date status;
- the exact number of people in the Target Group;
- the campaign delivery channel and number of selected products;
- the selected age, gender, location, income, and advanced business preferences that are present;
- the chosen match-strength label and plain-language meaning;
- the governed threshold and whether the explicitly linked source is general or context-compatible; and
- the existing non-causal statement that similarity scores do not establish why a person will act or predict a purchase.

Long multi-selects are bounded in the explanation: the first three values are named and any remainder is represented as a count. Empty optional criteria are described as no additional demographic preferences. Run IDs, SHA values, artifact identifiers, contract versions, Saved Audience IDs, and candidate names do not appear in this default explanation.

## Technical details contract

The existing targeting-intelligence provenance contract was extended additively with:

- selected candidate; and
- model-role policy version.

A strict Phase 9 technical-details response now combines only approved audit fields:

- targeting-source status and currentness;
- targeting/scoring run, source analysis, and model run;
- selected candidate and model policy;
- feature-contract version and SHA-256;
- customer, campaign-sales, and demographic source checksums;
- artifact SHA-256;
- complete Audience Filter branch hash;
- Saved Audience ID after save; and
- targeting-intelligence resolution, campaign-context, targeting-segment, business match-strength, Audience Filter, Target Group preview, Target Group/Campaign, and Saved Target Group contract versions.

The preview returns the exact full-branch filter hash but no Saved Audience ID before a save exists. The saved/reopened Campaign response returns the same filter hash plus its immutable Saved Audience ID. Tests reconcile every provenance value to the backend scoring/model/analysis rows, score-summary source checksums, and immutable Phase 9 Saved Target Group metadata.

Technical-detail response models forbid additional fields. The approved technical structure contains no person/customer ID, name, email address, phone number, city, street address, or postal code.

## Progressive-disclosure UX

Target Group Preview and Review & Save each expose **View technical details** in a native HTML `details` control. Neither control has the `open` attribute, so technical identifiers do not interrupt or dominate the default business task.

Before save, the preview panel shows source and filter provenance. After save or reopen, the Review & Save panel shows the immutable Saved Audience linkage and full Phase 9 contract lineage. Rendering uses `textContent`, `document.createElement`, and `replaceChildren`; it does not use `innerHTML`.

The panel explicitly states that the separation is for user experience only and is not an authentication or authorization boundary. No security guarantee or role enforcement was invented.

## Advanced tools and compatibility

The navigation group is labeled **Advanced / Analyst Tools**. The following existing destinations remain enabled and unchanged in capability:

- Historical Analysis;
- Model Training & Prospect Scoring; and
- Audience Explorer.

Data Status and the established model/scoring workspace also remain available. No Phase 1–8 route, view, action, persistence table, or workflow was removed.

The earlier literal **Advanced technical details** remains inside the collapsed audit copy for compatibility, while the user-facing disclosure action is **View technical details**.

## Tests

`tests/test_phase9_progressive_disclosure.py` verifies:

- the business explanation contains campaign context, actual preferences, plain match-strength meaning, exact group size, currentness, and non-causal language;
- prohibited technical identifiers are absent from the default explanation implementation;
- technical values match scoring, model, analysis, checksum, filter-hash, Saved Audience, and contract-version records;
- recursive no-PII validation of preview and saved technical details;
- both technical-detail controls are accessible and collapsed by default;
- technical labels are absent from the visible default Step 4/5 markup;
- safe DOM rendering;
- explicit role-neutral UX language; and
- retention of Historical Analysis, Model Training & Prospect Scoring, and Audience Explorer.

## Files

- `app/repositories/campaign_targeting_context_repository.py`
- `app/schemas/campaign_targeting.py`
- `app/services/target_group_campaign_service.py`
- `app/services/target_group_preview_service.py`
- `app/services/targeting_intelligence_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/campaign-review.js`
- `frontend/js/target-group-preview.js`
- `frontend/js/targeting-intelligence.js`
- `tests/test_phase9_progressive_disclosure.py`

## Verification

- `python -m pytest tests/test_phase9_progressive_disclosure.py -q` — 3 passed.
- Phase 9 source-boundary, exact-preview, Step 10 save/reopen, and complete frontend regression sequence — 55 passed; one legacy literal-label assertion initially failed.
- After restoring the compatible collapsed-panel phrase, the failed check plus Step 11 disclosure, navigation, and Review & Save checks — 4 passed.
- `python -m pytest tests/test_phase9_target_group_preview.py -q` — 4 passed after the technical contract and explanation changes.
- Step 10 create/reopen/edit/immutability/linkage/stale cases all passed inside the affected regression sequence.
- `python -m compileall -q app tests` — passed.
- `git diff --check` — passed with only existing Git line-ending warnings.

Ruff and Node.js are not installed in this environment. Python compilation, strict response-model validation, exact backend provenance reconciliation, service/API regression tests, served frontend checks, safe-rendering assertions, and repository diff validation provide the available verification.

No project import, audience-preparation job, model training, or scoring job was run. Automated tests used an isolated temporary SQLite fixture and fixture-only audience preparation.

## Acceptance result

PASS. The normal Campaign Planner path explains the current Target Group in business language, while analysts can expand complete backend-matched technical lineage without exposing PII or implying an authorization boundary.

STOP — no Phase 9 Step 12 work was performed.
