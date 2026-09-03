# UI Step 4 — Product Language & Long-Running Export Status

Remove stale wording:
- `Phase 7 shell`
- `backend feature-gated until Section 2`
- any message implying Campaign Builder backend is not implemented

Use accurate wording:
- `Campaign Builder`
- `Governed draft, finalize, currentness and target-list export`
- `This POC stops at target-list export and does not activate or send campaigns.`

Update FastAPI/app description to reflect Phase 1–7 implemented within current POC scope.

## Export status problem

Current polling every 2 seconds for 60 attempts stops after ~120 seconds, while a real
416K export took ~14 minutes.

Replace this with adaptive/status-aware polling:
- first 30 sec: ~2 sec interval
- next 2 min: ~5 sec
- thereafter: ~10–15 sec
- continue while latest event is STARTED and Campaigns view remains active
- provide `Refresh Export Status`
- if any wall-clock ceiling is used, show `Still running — refresh status`; never silently stop

Show:
- STARTED / COMPLETED / FAILED / ABORTED
- elapsed time
- profile
- exact selected/deliverable/exported counts when safely available
- checksum after completion

Do not mark a long exact export failed simply for exceeding 60/120/180 sec.
Keep direct streaming download; do not buffer huge CSV in JS memory. STOP.
