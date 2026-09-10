# Phase 9 Step 12 — State and Validation Report

Date: 2026-09-10
Status: PASS

## Scope

This step makes the Campaign Planner's validation, loading, empty, error,
currentness, and save/retry behavior safe and understandable for business
users. It does not import project data, train or score a model, alter targeting
semantics, finalize or send a Campaign, or begin Phase 9 Step 13.

## Plain-language validation

Campaign-context and targeting request bodies are now validated by the Phase 9
contract service so that API clients receive business-readable messages rather
than Pydantic field paths or backend contract names.

Covered validation includes:

- at least one currently available product and an available delivery channel;
- a selection that was removed or became unavailable between load and save,
  with refresh/reselect guidance and the removed value identified;
- an unavailable Targeting Match choice;
- a family-size minimum above its maximum;
- zero or otherwise invalid family size;
- TOP_N without a positive whole-number target; and
- unavailable demographic/reference choices.

The browser adds matching required-field, family-range, and TOP_N validation
before submission while the backend remains authoritative.

## Loading, empty, error, and currentness states

Campaign Context distinguishes loading, load failure with **Try again**, and no
currently available products. Save failures are displayed without hiding the
form or clearing valid selections.

Targeting Preferences distinguishes loading and retryable load/save failures.
Edits remain in browser state after an error, and changing a value dismisses the
old error without resetting the form.

Targeting Intelligence retains its explicit-source boundary:

- no linked source is **Not available** and preview remains blocked;
- incomplete or stale intelligence is **Needs refresh** and preview remains
  blocked; and
- a current verified source is **Up to date** and permits exact preview.

Exact Target Group Preview distinguishes loading, retryable backend failure,
current non-empty results, and a current exact-zero result. A zero result keeps
the exact metrics visible, states that exactly zero people match, recommends
broadening preferences, and blocks Review & Save. No count is estimated or
fabricated.

Default Campaign review output maps backend state codes to **Up to date**,
**Needs refresh**, or **Not available**. Exact source and provenance values
remain available only in the existing collapsed **View technical details**
disclosures.

## Save, failure recovery, and idempotency

The Review & Save form now has a client-side in-flight guard in addition to its
disabled submit button. A second click while the first request is pending is
ignored with a plain status announcement.

The backend is also idempotent:

- repeating an identical completed save returns the existing immutable Saved
  Target Group and Campaign draft with `idempotent_replay=true`;
- no duplicate Saved Audience, Phase 9 Target Group metadata, or Campaign is
  created;
- changing only Campaign draft details updates the same draft while retaining
  the same identical Target Group;
- changing the targeting definition or Target Group identity creates a new
  immutable group through the existing Step 10 behavior; and
- if the Target Group saves but Campaign draft creation fails, retry reuses that
  saved group and creates the missing draft instead of duplicating the group.

Success distinguishes a newly created draft from an already-saved replay.
Target Group and Campaign draft failures have separate visible headings and
retry-safe messages. User-entered campaign and Target Group values remain in
the form.

## Error safety

Network and unreadable-response failures use stable application messages.
Structured framework validation arrays are converted to a general instruction
to review entered values. Known business validation/conflict messages remain
visible; unexpected Campaign Planner service failures are converted to a fixed
safe response.

Tests inject an exception containing SQL, a Windows path, and a raw exception
class name. None of those values appears in the API response or save-retry
message. Stack traces remain server-side.

## Tests

`tests/test_phase9_validation_and_states.py` verifies:

- required, removed/unavailable, invalid match, conflicting range, zero family
  size, and invalid TOP_N messages;
- loading, empty, retry, success/failure, and exact-zero frontend regions;
- business currentness labels;
- retry input preservation hooks and the client-side in-flight guard; and
- sanitization of SQL, local paths, and exception class names.

`tests/test_phase9_target_group_preview.py` adds an end-to-end zero-result proof:
the deterministic Very Strong + Ohio demographic selection resolves to exactly
zero people, returns null score summaries, an empty search page, and no
fabricated estimate.

`tests/test_phase9_save_target_group_campaign.py` adds a data-backed proof that
an identical repeat submission is idempotent and that a deliberately failed
Campaign creation reuses its already-saved Target Group on retry.

Existing context, targeting-contract, intelligence-boundary, frontend, and
progressive-disclosure regressions verify removed-option handling, no-link and
stale blocking, safe served UI behavior, and preservation of the advanced-only
provenance boundary.

## Files

- `app/main.py`
- `app/repositories/campaign_targeting_context_repository.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/campaign_targeting_contract_service.py`
- `app/services/target_group_campaign_service.py`
- `frontend/index.html`
- `frontend/js/api.js`
- `frontend/js/business-targeting.js`
- `frontend/js/campaign-context.js`
- `frontend/js/campaign-review.js`
- `frontend/js/target-group-preview.js`
- `frontend/js/targeting-intelligence.js`
- `tests/test_phase9_business_targeting.py`
- `tests/test_phase9_campaign_context.py`
- `tests/test_phase9_save_target_group_campaign.py`
- `tests/test_phase9_target_group_preview.py`
- `tests/test_phase9_targeting_contracts.py`
- `tests/test_phase9_validation_and_states.py`

## Verification

- Existing Step 10 create/reopen/edit/immutability/linkage/stale regression — 5
  passed.
- New repeat-save and failed-draft recovery case — 1 passed.
- Final Phase 9 contract, context, targeting, intelligence-boundary, and Step 12
  state suite — 27 passed.
- Exact demographic zero-result integration case — 1 passed.
- Complete served frontend regression — 39 passed.
- Step 11 progressive-disclosure regression — 3 passed.
- Python compilation and repository whitespace validation — passed.

Node.js and Ruff are not installed in this environment. The available served
frontend tests, static browser-contract assertions, Python compilation, strict
API response models, service/API integration tests, deterministic exact-count
fixtures, and repository diff validation provide the verification.

No repository data import, audience-preparation pipeline, model training, or
scoring run was executed. Automated tests used isolated temporary SQLite
databases and fixture-only audience preparation where exact currentness/count
verification required it.

## Acceptance result

PASS. Business users receive explicit loading, empty, exact-zero, retryable
error, success/failure, and currentness states; valid input survives errors;
repeat saves are deduplicated; and backend internals are not exposed.

STOP — no Phase 9 Step 13 work was performed.
