# Step 4 — Business Campaign Wizard Shell

## Objective
Create the business-first campaign workflow without yet wiring all targeting logic.

## Wizard
Recommended steps:

1. Campaign Details
2. Campaign Context
3. Targeting Preferences
4. Target Group Preview
5. Review & Save

## Step 1 — Campaign Details
Fields:
- Campaign Name
- Description
- Planned Launch Date

Use simple helper text.

## Navigation
- Next
- Back
- Save draft where appropriate
- clear step status
- current step
- completed steps
- values retained when going back

## State
Use a dedicated campaign-planning state module rather than expanding one giant `campaigns.js`.

Recommended frontend modules:
- campaign-planner-state.js
- campaign-planner-form.js
- campaign-context.js
- targeting-preferences.js
- target-preview.js
- campaign-review.js

Vanilla JS remains acceptable.

## Existing Campaign Builder
Do not remove or break existing Phase 7 Campaign Builder.
Either:
- integrate the new wizard as the new default Create Campaign surface while retaining legacy/advanced entry;
or
- keep both temporarily with clear labels.

## Tests
Frontend contract tests for wizard sections, IDs, labels, Next/Back and state preservation.

STOP.
