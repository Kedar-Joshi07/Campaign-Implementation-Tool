# Step 12 — Validation, Error, Empty, Loading & Currentness States

## Objective
Make the workflow safe for users who do not understand the backend.

## Plain-language validation
Examples:

Instead of:
“score_min must be <= score_max”

Use:
“Choose a minimum match score that is not higher than the maximum.”

Instead of:
“scoring run stale”

Use:
“Targeting intelligence needs to be refreshed before this target group can be used.”

## Required state coverage

Campaign context:
- required selections
- unavailable option
- option removed between load/save

Targeting:
- no linked targeting intelligence
- stale intelligence
- invalid match threshold
- mutually conflicting filters
- selected demographic bucket returns zero people
- invalid TOP_N

Preview:
- loading
- empty
- exact zero matches
- retryable backend error
- current
- needs refresh

Save:
- save target group success/failure
- campaign draft success/failure
- double-click/idempotency behavior

## Error safety
Never expose:
- SQL
- stack traces
- local paths
- raw exception classes

## Preserve input
On retryable errors, preserve valid user inputs.

## Currentness
Business status:
- Up to date
- Needs refresh
- Not available

Advanced details may expose exact provenance reason.

Create:
`docs/evidence/phase9/12_STATE_AND_VALIDATION_REPORT.md`

STOP.
