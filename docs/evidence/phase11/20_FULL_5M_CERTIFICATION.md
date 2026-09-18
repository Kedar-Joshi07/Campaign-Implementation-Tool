# Phase 11 Step 20 — Full 5M Smart-Reuse and New-Build Certification

Date: 2026-09-18

## Outcome

`PASS_STEP_20_FULL_5M_REUSE_AND_NEW_BUILD_CERTIFICATION`

Step 20 completed from clean committed baseline
`a137b71e33ab37d7551880c927c05318a599939d`. The run used the canonical
database and installed Chrome, performed one required current 5M intelligence
build, and then proved exact-result, intelligence, and delivery-profile reuse.
Step 21 was not started.

## Canonical source certification

- Canonical demographic rows: `5,000,000`; columns: `40`.
- Canonical and regenerated gzip SHA-256:
  `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d`.
- Canonical and regenerated size: `512,842,205` bytes.
- Deterministic sample SHA-256:
  `7508731b51c5c2cf6b89b03268d223753511cd43db6f44bf0c39e17fac94ee16`.
- Contactability contract violations: `0`.
- Feature Contract SHA-256 remained
  `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`;
  none of the 12 contactability/identifier fields entered model inputs.

## Browser scenarios

| Scenario | Result | Durable evidence |
| --- | --- | --- |
| A — current 5M build | PASS | Search 3, generation 1, analysis 4, model 3, scoring 3, snapshot 1; `NEW_INTELLIGENCE_BUILD`. |
| B — exact repeat | PASS | New search 4 reused snapshot 1 with `EXACT_RESULT_REUSE`; membership-source calls added: `0`; no analysis/model/scoring/generation/snapshot count changed. |
| C — targeting change | PASS | Search 5 reused generation 1/model 3/scoring 3 with `INTELLIGENCE_REUSE`; created snapshot 2 with 4 exact members and no 5M scoring. |
| D — delivery change | PASS | Searches 6–8 reused snapshot 2 for SMS, WhatsApp, and Paid Social; no Phase 10 or snapshot rebuild. |

Installed browser: system Chrome `153.0.8010.48`. Browser telemetry recorded no
console errors, page errors, failed requests, or HTTP errors. The Scenario A
completion screenshot is stored under
`docs/evidence/phase11/system_browser/step20/`.

## Full-scoring invariants

- Scoring rows: `5,000,000`; distinct people: `5,000,000`; duplicates: `0`.
- Null, nonfinite, or out-of-range scores: `0`.
- Invalid demographic/person lineage: `0`.
- Rank boundaries: `100` covering percentiles 1–100 and population `5,000,000`.
- Current analytics snapshots: `1`, population `5,000,000`, demographic import 4.
- Search 3 → snapshot 1 → generation 1 → scoring 3 → model 3 → analysis 4.
- Source imports/checksums:
  customers 1 / `99a09d2f0db06980afe290cf74a4db1df76cf8c340534fb2088879fb093d9ea9`;
  campaign sales 2 / `2fdb11c576a180b7349e50e0bf9d3b0a66d0d354ba8d42062756c8cd840965c4`;
  demographics 4 / `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f`.

Scenario A intentionally resolved zero members because its bounded low-income
branches had no score at or above the BROAD threshold. Scenario C changed all
requested targeting dimensions to a valid high-income multi-branch selection,
resolved 4 members, and became the saved/exported multi-branch result.

## Governed downloads

- Email: 4 deliverable rows.
- SMS: 0 deliverable and 4 undeliverable rows, correctly enforced only at export.
- WhatsApp: 1 deliverable and 3 undeliverable rows.
- Paid Social: 4 deliverable rows; only SHA-256 email/phone identifiers were emitted.

All four download events completed, and every CSV row count matched its durable
export event. Delivery changes did not alter membership.

## Regression and hygiene gates

| Gate | Result |
| --- | --- |
| Full pytest | `966 passed in 2484.49s` |
| Explicit Phase 11 pytest | `265 passed, 701 deselected in 472.89s` |
| Phase 1–7 clean-room | PASS |
| Phase 10 bounded clean-room | PASS; canonical SHA `a2f3230abf6945e8cdccad1bcfd317ac98e5bed0d3c63ccc184bb85c282ef5b7` |
| `compileall` | PASS |
| `pip check` | PASS — no broken requirements |
| `git diff --check` | PASS |
| CI repository/LFS hygiene validator | PASS |
| Canonical SQLite `PRAGMA integrity_check` | `ok` in `910.516s` |

The Phase 10 bounded clean-room initially exposed a stale fixture: newly required
Phase 11 contactability flags were blank. The fixture was corrected to emit
explicit governed `0` values, after which the complete clean-room passed.

Machine-readable evidence: `docs/evidence/phase11/20_FULL_5M_CERTIFICATION.json`.
