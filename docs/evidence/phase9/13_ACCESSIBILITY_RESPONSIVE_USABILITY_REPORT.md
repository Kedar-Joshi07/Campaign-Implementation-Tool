# Phase 9 Step 13 — Accessibility, Responsive Design and Business Usability Report

Date: 2026-09-10
Status: PASS

## Scope

This step verifies that a non-technical user can complete the five-step Campaign
Planner with a keyboard, assistive-technology semantics, and the required
desktop, tablet, and mobile viewport sizes. It improves accessibility and
responsive presentation without changing targeting semantics, importing
project data, training or scoring a model, saving a production Campaign, or
beginning Phase 9 Step 14.

## Accessibility implementation

The Campaign Planner now provides:

- an ordered stepper with current/completed/available state text, an explicit
  keyboard instruction, and a single current step;
- programmatic labels for every form field and helper text connected through
  `aria-describedby`;
- visible `:focus-visible` treatment for controls, step buttons, disclosures,
  error summaries, and successful-save status;
- native keyboard-operable multi-selects, with selected values exposed as a
  list of removable buttons;
- predictable focus return to the originating field after a selected chip is
  removed;
- focus movement to the relevant visible error when loading or saving fails;
- polite live regions for progress, empty/result/currentness state, page status,
  selected-value changes, and successful saves;
- status words and explanatory text in addition to color styling;
- an accessible Target Group result table with a caption and scoped column
  headers;
- native `details`/`summary` disclosures so help and technical provenance do
  not require a mouse; and
- the existing reduced-motion media query, which suppresses nonessential
  transitions and animation for users who request reduced motion.

## Keyboard-only system-browser proof

The live application was exercised in the system browser without mouse input
for the critical interactions:

1. Campaign Name was cleared, focus was advanced through the form, and **Next**
   was activated with the keyboard.
2. Validation announced **Enter a campaign name before continuing** and focus
   returned to Campaign Name.
3. The Targeting Preferences step was opened with Enter.
4. The Location multi-select was focused and Ohio was selected from the
   keyboard.
5. The generated **Remove State: Ohio** chip button was activated with Enter.
6. Ohio was removed, **Targeting choice removed** was announced, and focus
   returned to the Location multi-select.

The browser accessibility tree also confirmed labeled controls throughout all
five steps, current step state, live helper/status content, table semantics,
and the save-consequence explanation on Review & Save.

## Responsive system-browser proof

One deterministic six-person browser fixture was prepared once, linked to one
current targeting-intelligence source, and used for every viewport. The same
completed wizard session was traversed through all five steps at each size; no
backend import, training, or scoring work was repeated per viewport.

| Viewport | Steps checked | Controls outside viewport | Sidebar overflow | Workspace overflow | Stepper layout |
| --- | ---: | ---: | ---: | ---: | --- |
| 1920×1080 | 5 | 0 | 0 px | 0 px | 1 column |
| 1366×768 | 5 | 0 | 0 px | 0 px | 1 column |
| 1024×768 | 5 | 0 | 0 px | 0 px | 2 columns |
| 768×1024 | 5 | 0 | 0 px | 0 px | 1 column |
| 390×844 | 5 | 0 | 0 px | 0 px | 1 column |

Visual inspection and measured layout checks found and corrected three issues:
desktop sidebar text overflow, intrinsic-width overflow in the exact-preview
table, and crowded tablet navigation. Long navigation labels now wrap safely,
secondary hints collapse at the compact desktop boundary, the navigation grid
adapts from two columns to one, and the preview panel/table remain contained by
the available workspace width.

## Business usability review

The normal path answers all eight required business questions:

1. **What campaign am I creating?** Campaign name, description, and timing are
   captured in Campaign Context and summarized again before save.
2. **What am I promoting?** Currently available products and the delivery
   channel are selected with short labels and helper text.
3. **Who do I want to reach?** Match strength, location, demographic, household,
   and optional advanced business preferences describe the intended audience.
4. **How selective is my target group?** The selected Targeting Match label and
   its plain-language meaning explain selectivity.
5. **How many people match?** Target Group Preview shows the exact matching
   count, eligible universe, percentage, and searchable people table.
6. **Why were they selected?** The deterministic **Why these people?** section
   explains campaign context, selected preferences, match strength, and the
   non-causal nature of similarity scoring.
7. **Is the targeting result up to date?** Targeting Intelligence and Preview
   show **Up to date**, **Needs refresh**, or **Not available**, with explanatory
   text rather than color alone.
8. **What happens when I save?** Review & Save states that an immutable Saved
   Target Group and an editable Campaign draft will be created; nothing is
   finalized or sent.

The normal workflow does not require knowledge of `analysis_run_id`,
`model_run_id`, `scoring_run_id`, PU learning, algorithms, model artifacts, or
hashes. Approved audit identifiers remain in collapsed **View technical
details** disclosures. Copy remains short and task-oriented, with longer audit
material progressively disclosed.

## Files

- `frontend/index.html`
- `frontend/css/main.css`
- `frontend/css/components.css`
- `frontend/js/business-targeting.js`
- `frontend/js/campaign-context.js`
- `frontend/js/campaign-review.js`
- `frontend/js/target-group-preview.js`
- `tests/test_phase9_accessibility_responsive.py`

## Verification

- Phase 9 accessibility/responsive static contract and Step 12 state suite — 9
  passed.
- Complete served frontend regression — 39 passed.
- Live system-browser keyboard workflow — passed.
- Full five-step system-browser traversal at all five required viewports —
  passed with zero measured control, sidebar, or workspace overflow.
- Python compilation and repository whitespace validation — passed.

The successful browser run and its temporary context/source records used an
isolated fixture database, which was removed after verification. One unsaved
context created in the repository database during initial setup was also
removed after its existing source proved context-incompatible. The browser
workflow did not invoke the final save action, so it created no Saved Target
Group or Campaign draft.

## Acceptance result

PASS. A business user can understand and complete the Campaign Planner with a
keyboard, its state and result structures are exposed accessibly, and the full
wizard remains usable at every required viewport without requiring backend or
model terminology.

STOP — no Phase 9 Step 14 work was performed.
