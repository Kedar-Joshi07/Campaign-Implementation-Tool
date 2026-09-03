# Hardening Step 5 — Export Status Lifecycle & Recovery

Keep export events meaningful for long-running exact work.

If safe, update aggregate progress at bounded intervals (e.g. every 1–5 chunks):
- selected_count processed
- deliverable_count
- undeliverable_count
- row_count

Never write per-row progress and never store PII.

## Disconnect/abort
Verify client disconnect:
- marks ABORTED where detectable
- preserves safe partial aggregate counts
- leaves no persistent PII file

Do not create a fake cancel endpoint unless actual cancellation can be safely implemented.

## Startup recovery
Add startup reconciliation for export events stuck in STARTED after interruption/restart.

Use a documented threshold and mark them ABORTED/FAILED with safe message such as:
`Export interrupted before completion.`

Do not leave permanent STARTED records.

## UI contract
Long-running UI must:
- poll adaptively beyond 120 sec
- display elapsed time
- show safe aggregate progress if available
- expose manual refresh
- stop only on terminal status or explicit view teardown

STOP.
