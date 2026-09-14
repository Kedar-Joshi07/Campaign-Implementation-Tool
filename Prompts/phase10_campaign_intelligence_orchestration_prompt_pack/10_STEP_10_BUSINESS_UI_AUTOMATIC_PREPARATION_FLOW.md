# Step 10 — Business UI Automatic Preparation Flow

When business user moves from Targeting Preferences toward Target Group Preview:
1. save/confirm context
2. save/confirm target preferences
3. ask Phase 10 readiness
4. if reusable, open exact preview
5. if build/refresh needed, automatically start
6. show plain-language persistent progress
7. poll durable state
8. when READY, load unchanged Phase 9 exact preview

No analyst/model/scoring-run selection in normal flow.

Use business language:
Targeting intelligence; Past campaign history; Potential customers; Preparing your Target Group;
Verifying results; Up to date; Needs refresh; Not enough past campaign history.

Hide by default:
PU, bagging, model/scoring run IDs, artifact/feature hashes.

Reuse messages:
- full reuse: Existing verified targeting intelligence matches this campaign and is ready.
- demographic refresh: Campaign history is still valid; refreshing matches for current potential-customer data.
- full build: Preparing new targeting intelligence for this campaign.

BLOCKED:
“There is not enough verified past campaign history for this combination yet.”
Offer Back to Campaign Context / review context / technical details. Never auto-drop a choice.

FAILED:
“We could not finish preparing targeting intelligence. Your campaign inputs are saved.”
Offer Try again / Back / technical details.

Navigate away/back must reconnect to durable orchestration.

Change behavior:
campaign details: no build
delivery channel: no build
prospect target filters: no build
Modeling Context dimension: re-resolve

If needed split frontend into focused intelligence state/api/progress/technical modules.
No React/Vue rewrite.

Accessibility: aria-live progress, keyboard, focus/error associations.
Responsive: 1920x1080, 1366x768, 1024x768, 768x1024, 390x844.

Evidence:
`docs/evidence/phase10/10_BUSINESS_UI.md`

STOP.
