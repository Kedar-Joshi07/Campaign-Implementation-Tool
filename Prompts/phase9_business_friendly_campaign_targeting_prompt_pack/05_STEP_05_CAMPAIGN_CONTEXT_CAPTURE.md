# Step 5 — Campaign Context Capture

## Objective
Capture the business meaning of the campaign in plain language.

## Controls
Implement dynamic, backend-driven selectors:

- Product multi-select
- Campaign Type multi-select
- Campaign Category multi-select
- Offer Type multi-select
- Campaign Channel

Use values from actual current historical/reference data.

Do not hardcode business options in JavaScript when backend reference data exists.

## Product multi-select semantics
Phase 9 captures selected products as one business context request.

Do NOT perform model fusion.

Phase 10 will define automatic context-to-model resolution.

## Combination semantics
For context capture:
- multiple values within one dimension = OR
- different dimensions = AND

Example:
Products A or B
AND Campaign Type Promotion
AND Offer Type Discount

Persist that meaning canonically.

## Channel
Distinguish:
- campaign delivery channel for final campaign
from
- historical channel context if Phase 10 later chooses to use it for model compatibility.

Do not silently equate them without explicit contract.

## User help
Use plain questions:
- “What are you promoting?”
- “What type of campaign is this?”
- “What kind of offer are you planning?”
- “How will this campaign reach people?”

## Validation
- no unknown IDs
- canonical sorted multi-selects
- no duplicate values
- channel valid
- context readable after save/reopen

Create:
`docs/evidence/phase9/05_CAMPAIGN_CONTEXT_REPORT.md`

STOP.
