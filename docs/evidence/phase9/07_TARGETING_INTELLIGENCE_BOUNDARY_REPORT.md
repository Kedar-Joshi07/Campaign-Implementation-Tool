# Phase 9 Step 7 — Targeting Intelligence Boundary Report

Date: 2026-09-09
Status: PASS

## Scope

This step establishes an explicit, analytically honest boundary between a Phase 9 planning context and the scoring intelligence required by later target-group operations. It does not train a model, execute scoring, automatically choose a model/run, estimate a target group, search people, save a target group, or create a campaign.

## Resolution contract

The new versioned interface is:

`resolve_targeting_intelligence(database_path, targeting_context_id) -> TargetingIntelligenceResolution`

It returns exactly one business state:

| State | Meaning | Exact preview permitted |
| --- | --- | --- |
| `READY` | An explicitly linked scoring run is completed, current, canonical, provenance-verified, and compatible with the checkable campaign context | Yes |
| `NEEDS_REFRESH` | The linked scoring run has not completed successfully | No |
| `NOT_AVAILABLE` | No source is linked, or the linked source no longer exists | No |
| `INCOMPATIBLE_CONTEXT` | The source is current and verified, but its recorded analysis scope conflicts with or cannot be verified against this context | No |
| `STALE` | A completed link no longer passes current source/model/canonical checks | No |

The corresponding business messages are:

- “Targeting intelligence is ready”
- “Targeting intelligence needs refresh”
- “Targeting is not yet available for this campaign”

## No-fallback guarantee

Resolution reads only `campaign_targeting_contexts.source_scoring_run_id` for the requested planning context. If it is null, the resolver returns `NOT_AVAILABLE` immediately.

It does not:

- list scoring runs;
- order scoring runs by creation time;
- choose the latest scoring run;
- choose a completed scoring run;
- choose the first model; or
- infer a source from product, offer, campaign type, category, or delivery channel.

The no-link test installs a scoring-resolution function that fails if invoked. The test passes with `NOT_AVAILABLE`, proving that no unrelated scoring lookup occurs.

## Explicit Phase 9 linkage

The temporary Phase 9 mechanism is an advanced analyst/admin API action:

- `PUT /api/campaign-planner/contexts/{id}/targeting-intelligence`
- body: `{ "scoring_run_id": <positive integer> }`
- `DELETE /api/campaign-planner/contexts/{id}/targeting-intelligence` removes the link.

The normal business wizard contains no scoring-run ID field or raw source selector. The link action evaluates the exact requested run before storing it. Incomplete, unavailable, or stale/noncanonical sources are rejected. A current but context-incompatible source may be recorded so the explicit `INCOMPATIBLE_CONTEXT` state remains visible, but it cannot open the preview gate.

No source was linked to production/current workspace data while implementing this step.

## Currentness and provenance

Every linked-source resolution calls the existing lightweight scoring-currentness verifier with current-source matching enabled. This validates completed status, canonical run identity, model and analysis provenance, demographic source provenance, historical source provenance, feature contract, and artifact metadata without scanning all propensity scores.

Completed sources that fail these checks return `STALE`; incomplete/failed execution state returns `NEEDS_REFRESH`.

Advanced response details can include:

- analysis run ID;
- model run ID;
- scoring run ID;
- feature-contract version and SHA-256;
- artifact SHA-256; and
- customer, campaign-sales, and demographic source checksums.

These values are read-only and progressively disclosed. They are not shown as normal-user inputs.

## Context compatibility

Phase 9 evaluates only dimensions with an exact semantic match between the planning context and saved historical-analysis filters:

- product IDs;
- campaign types; and
- historical campaign channels.

For a constrained source, every selected planning value in that dimension must be within the recorded source scope. Source restrictions by campaign ID or product category return `INCOMPATIBLE_CONTEXT` because the current Phase 9 context cannot safely prove those constraints. Delivery channel is never silently compared with historical campaign channel.

An otherwise verified source with no context-specific source filters may be `READY` as general targeting intelligence, but the business explanation explicitly says it is not product-specific and that campaign context did not change or retrain it.

Phase 10 can replace the conservative compatibility evaluator with automatic discovery, reuse, or build orchestration without changing the public resolution boundary.

## Blocking behavior

- Campaign context and targeting preferences remain saveable without a source.
- `can_preview` is true only for `READY`.
- The wizard’s path beyond Target Group Preview is disabled unless the source gate is ready.
- The browser displays an explanation and a retry action for every blocked state.
- It explicitly states that exact counts and target-group saving are blocked.
- No placeholder, estimated, sampled, or fabricated target count is displayed.
- Advanced details reiterate that context never silently changes or retrains the source.

## Files

- `app/repositories/campaign_targeting_context_repository.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/targeting_intelligence_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/campaign-planner-form.js`
- `frontend/js/targeting-intelligence.js`
- `tests/test_frontend.py`
- `tests/test_phase9_targeting_intelligence_boundary.py`

## Verification

- `python -m pytest tests/test_phase9_targeting_intelligence_boundary.py -q` — 8 passed.
- `python -m pytest tests/test_phase9_schema.py tests/test_phase9_targeting_contracts.py tests/test_phase9_campaign_context.py tests/test_phase9_business_targeting.py tests/test_phase9_targeting_intelligence_boundary.py tests/test_frontend.py -q` — 63 passed.
- Focused Ruff checks for all Step 7 Python files and tests — all checks passed.
- `python -m compileall -q app` — passed.
- `git diff --check` — passed; Git emitted only the pre-existing README line-ending warning.

Node.js is not installed in this environment. The new frontend module is covered by served-asset, UI contract, state rendering, no-source-picker, and preview-gate assertions.

## Acceptance result

PASS. Phase 9 now refuses to fabricate or infer targeting intelligence, never falls back to an unrelated “latest” source, exposes all five required states, and opens the exact-preview gate only for an explicitly linked, current, verified, context-compatible or clearly general source.

STOP — no Phase 9 Step 8 work was performed.
