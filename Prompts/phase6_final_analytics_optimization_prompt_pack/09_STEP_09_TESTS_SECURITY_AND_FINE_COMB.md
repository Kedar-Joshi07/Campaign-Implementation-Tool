# Step 9 — Regression, Security, PII, Scope & Repository Hardening

## Snapshot-currentness tests
Cover exact currentness plus demographic/customer/campaign drift, feature/artifact mismatch, analytics/rank contract mismatch, restored exact provenance, and historical snapshot inspectability without current eligibility.

## Unknown/Other + vocabulary
Test NULL/empty/whitespace/literal Unknown across options/filter/profile/search. For each categorical field, valid current values accepted and unsupported values rejected.

## Save-audience tests
Verify profile-snapshot saves do not issue redundant expensive analysis, no-profile saves use estimate path only, server remains authoritative, and persisted aggregate values remain correct.

## SQL/security
Dynamic field names only from internal allowlists. User values parameterized. Snapshot JSON never becomes executable SQL.

## Public PII scan
Reject first/last name, addresses, street, postal code, city, phone, email, ethnicity, religion, occupation industry, family income, child/adult household counts, absolute paths, raw SQL, tracebacks from public payloads.

## Phase 7 scope scan
No Campaign Builder, campaign business/member objects, target CSV/PII export, activation/email/address/phone export. Saved audience remains handoff boundary.

## Code-quality scan
Inspect changed code for duplicate SQL/band logic, broad exceptions, unsafe interpolation, schema drift, unused imports/dead constants, missing exports/types, oversized functions, stale comments/debug code. Refactor only where it reduces risk.

## Temp artifacts
Remove temp DBs, benchmark copies, pyc/__pycache__, temporary JSON/CSV/logs/local-path artifacts.

## Documentation
Do not comprehensively rewrite root README. Update current Phase 6 summary/progress/acceptance/handoff docs and clearly mark old performance evidence historical/superseded.
