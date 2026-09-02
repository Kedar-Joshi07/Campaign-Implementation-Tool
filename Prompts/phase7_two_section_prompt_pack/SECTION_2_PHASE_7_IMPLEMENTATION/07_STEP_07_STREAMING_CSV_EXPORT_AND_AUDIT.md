# Step 7 — Streaming CSV Export & Audit

Use FastAPI StreamingResponse.
Do not build whole CSV in memory.
Do not persist CSV in repo/data/artifacts.
Do not return rows as JSON.

Use Python csv module, bounded member chunks.
Safe filename:
`campaign_<id>_<profile>.csv`

Sequence:
1 validate finalized/current campaign
2 create STARTED export event
3 resolve exact selected members
4 join only approved profile contact fields
5 apply deliverability
6 stream header/rows
7 compute SHA-256 over actual CSV bytes
8 count selected/deliverable/undeliverable
9 mark COMPLETED with aggregate metadata

Client disconnect -> ABORTED where detectable.
Error -> FAILED with safe category.

Reconcile:
selected == finalized saved-audience count
deliverable + undeliverable == selected
exported rows == deliverable
no duplicate person_id
exact ordered columns
no forbidden fields

No persistent PII file/log/history rows.

Long exact exports may take 60–180 sec or more on local hardware; never truncate/sample.
STOP.
