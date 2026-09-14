# Step 14 — Real System-Browser Business Flow Certification

Use installed Chrome preferred, Edge fallback.

Create dynamic inventory of every Phase10 business-facing control/state.
Allowed terminal status: PASS, FAIL, JUSTIFIED_EXCLUSIVE.
No generic EXCEPTION and no reachable NOT_RUN.

Browser scenarios:

A. READY reuse:
business user completes Campaign Planner and exact preview opens automatically with no raw technical ID.

B. Preparation required:
controlled environment requires build; business progress states display; user navigates away/back and reconnects; eventually READY.

C. Insufficient history:
plain blocked message, Back action, no fallback/broadening, inputs retained.

D. Deterministic failure/retry:
safe error, retry, no stack/path leak, inputs retained.

E. Delivery-channel reuse:
same Modeling Context Email vs Direct Mail; no second model/scoring build.

F. Targeting-filter change:
match strength/demographic filters change exact preview without heavy intelligence rebuild.

Technical details:
hidden by default, opens explicitly, shows provenance/status IDs/hashes, contains no PII.

Responsive:
1920x1080, 1366x768, 1024x768, 768x1024, 390x844.

Accessibility:
keyboard, focus, aria-live progress, labels, errors, semantic loading states.

Telemetry:
zero unexplained JS exception, critical network failure, or console error.

Create screenshots, telemetry summary, UI coverage JSON and:
`docs/evidence/phase10/14_SYSTEM_BROWSER_CERTIFICATION.md`

STOP.
