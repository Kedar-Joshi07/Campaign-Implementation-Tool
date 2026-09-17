# Step 18 — Bounded Clean-Room Phase 11 Certification

Use isolated deterministic bounded data and fresh DB/artifact directory.

Scenario 1 — new business run/new intelligence:
Home → Find Potential Customers → submit → Phase10 build → snapshot → Results → export.

Scenario 2 — identical repeat:
submit exact same request intentionally again.
Assert:
- new search_run
- same result_snapshot
- EXACT_RESULT_REUSE
- no Audience full re-filter
- no model/scoring build.

Scenario 3 — filter change:
same Modeling Context, new demographics.
Assert:
- same Phase10 generation/scoring
- new result snapshot
- INTELLIGENCE_REUSE.

Scenario 4 — delivery-profile change:
same targeting result, switch Email→SMS or equivalent.
Assert no intelligence rebuild; export profile changes only.

Scenario 5 — new Modeling Context:
product/offer/context change.
Assert Phase10 re-resolution/build according to compatibility.

Scenario 6 — consent/contactability:
selected members split exactly into deliverable/undeliverable per profile.

Scenario 7 — paid media:
hash-only output; raw contact PII absent.

Scenario 8 — gated profile:
Push/Display/Website unavailable until required source field/contract is present; after Step4
extension they become AVAILABLE and export correctly.

Scenario 9 — snapshot corruption:
corrupt/delete file and prove exact cache fails closed rather than serving bad result.

Scenario 10 — app restart:
completed history/snapshots persist; active durable Phase10 process reconnects safely.

Run clean-room twice and compare deterministic relevant hashes/counts.

Evidence:
machine JSON + `docs/evidence/phase11/18_CLEANROOM_REPORT.md`

STOP.
