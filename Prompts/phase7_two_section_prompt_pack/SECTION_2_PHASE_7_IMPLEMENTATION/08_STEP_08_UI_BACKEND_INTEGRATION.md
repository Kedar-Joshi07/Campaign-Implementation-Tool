# Step 8 — Campaign Builder UI / Backend Integration

Enable Section 1 Campaigns workspace.

Load campaign options + recent campaigns using lightweight APIs.

Workflow:
choose current saved audience
→ details
→ create/edit draft
→ review exact count/currentness
→ finalize
→ export

FINALIZED:
immutable; show current/stale state and export eligibility.

Stale:
read-only, issues visible, export disabled, no force override.

Export:
require PII acknowledgement and use direct browser streaming/download where possible.
Do not fetch huge CSV into JS memory if direct streaming can be used.
Refresh export history after completion when practical.

Still no raw PII preview.

Apply stale-response/race protection and accessible progress states. STOP.
