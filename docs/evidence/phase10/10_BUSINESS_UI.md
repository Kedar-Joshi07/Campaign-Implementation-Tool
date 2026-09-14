# Phase 10 Business UI Automatic Preparation Flow

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/10_STEP_10_BUSINESS_UI_AUTOMATIC_PREPARATION_FLOW.md`

## Step result

`PASS_STEP_10_BUSINESS_UI_AUTOMATIC_PREPARATION_FLOW`

The Campaign Planner now moves a business user from saved Targeting
Preferences into an automatic, durable targeting-intelligence preparation
flow. The normal path requires no analyst selection and no model, scoring-run,
job, artifact, or generation identifier.

## End-to-end browser flow implemented

When the user continues from Targeting Preferences, the UI now:

1. waits for Campaign Context and Targeting Preferences validation/save;
2. opens Target Group Preview so progress is visible immediately;
3. asks the Phase 10 intelligence-plan endpoint for exact readiness and reuse;
4. opens the existing Phase 9 exact preview immediately when READY;
5. otherwise starts preparation automatically for new/stale intelligence;
6. renders persistent business-language stage and percentage progress;
7. polls the durable context preparation binding while QUEUED/RUNNING; and
8. on READY, resolves the unchanged Phase 9 targeting source and dispatches the
   existing `targeting-intelligence-resolved` event, which loads the unchanged
   preview, recommendation, search, review, and save flow.

Opening Step 4 through the stepper, returning from Step 5, or navigating away
from and back to the Campaign Planner asks the server for the durable state
again. A request-generation guard prevents older in-flight requests or poll
callbacks from replacing a newer context state.

## Business language and reuse decisions

Technical orchestration stages are mapped to the required visible language:

- Targeting intelligence;
- Past campaign history;
- Potential customers;
- Preparing your Target Group;
- Verifying results;
- Up to date;
- Needs refresh; and
- Not enough past campaign history.

The UI distinguishes exact reuse outcomes with the governed messages:

- `Existing verified targeting intelligence matches this campaign and is ready.`
- `Campaign history is still valid; refreshing matches for current potential-customer data.`
- `Preparing new targeting intelligence for this campaign.`

Campaign name/description/date, delivery channel, and prospect Targeting
Preferences remain outside analytical identity and therefore do not request a
new build. A Modeling Context change is detected by the Step 9 plan and starts
exact re-resolution. The frontend never removes, broadens, or silently changes
a user choice.

## BLOCKED and FAILED behavior

BLOCKED shows:

`There is not enough verified past campaign history for this combination yet.`

It offers Back to Campaign Context and collapsed technical details. The
Campaign Context and preferences remain untouched.

FAILED shows:

`We could not finish preparing targeting intelligence. Your campaign inputs are saved.`

It offers Try again, Back to Campaign Context, and collapsed technical details.
Try again uses the Step 9 retry endpoint, whose durable engine resumes from the
highest verified reusable stage.

## Progressive disclosure and safety

The default Step 4 surface contains no raw source selector and no PU, bagging,
model-run, scoring-run, artifact, or feature-hash language. Phase 10 and Phase
9 technical lineage remains available only inside the closed-by-default
`View technical details` disclosure. Dynamic content is written through
`textContent`/DOM creation; no `innerHTML` rendering was introduced.

## Accessibility and responsive behavior

- The preparation container is a polite atomic live region and switches to an
  alert for failure.
- The progress track has progressbar semantics, numeric bounds, current value,
  and business-language `aria-valuetext`.
- Active preparation sets `aria-busy`; READY/terminal state clears it.
- BLOCKED/FAILED state receives programmatic focus.
- Retry and Back controls have explanatory associations and are keyboard-native
  buttons.
- Returning to context moves both planner state and focus without discarding
  inputs.
- Existing 1100px, 780px, and 520px responsive layouts cover the required
  desktop, tablet, portrait-tablet, and 390px mobile sizes; the progress copy
  wraps and planner actions stack at narrow widths.
- Existing reduced-motion rules also cover the progress-width transition.

Real multi-viewport system-browser interaction and visual certification remain
reserved for the explicitly ordered Step 14 prompt.

## Verification

| Gate | Result |
|---|---|
| Step 10 focused UI contracts | PASS - 5 tests in 0.57s |
| Step 10 UI plus Step 9 API bridge and identity/change contracts | PASS - 40 tests in 15.98s |
| Existing frontend, Phase 9 state, progressive-disclosure, and accessibility/responsive regression | PASS - 66 tests in 23.47s |
| Ruff new Python test checks | PASS |
| Diff whitespace/error check | PASS (line-ending notices only) |
| Production imports/training/scoring | Not run |
| Real system-browser certification | Not run; Step 14 boundary |

API integration tests used bounded temporary SQLite databases and temporary
model artifacts. No production/repository runtime database or analytical
artifact was modified.

## Stop boundary

Step 10 stops after the business UI's automatic plan/prepare/poll/retry/READY
flow, durable reconnection, business state copy, progressive disclosure,
accessibility contract, responsive contract, and focused regression. It does
not implement Step 11+ lifecycle/retention, comprehensive matrix, clean-room,
system-browser certification, full-5M certification, CI, documentation freeze,
or Phase 10 freeze work.

`STOP_AFTER_STEP_10`
