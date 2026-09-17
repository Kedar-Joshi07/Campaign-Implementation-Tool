# Step 17 — Comprehensive Test Matrix & Performance Gates

## Objective
Lock correctness before expensive browser/full-scale certification.

A. Navigation/UI:
- only 3 business tabs visible
- legacy views hidden, code intact
- direct-route strategy consistent

B. Multi-select:
- search/select/deselect/select-all/clear
- keyboard/focus/ARIA
- values round-trip to backend
- no duplicate selected values

C. Search-run persistence:
- new run every intentional submit
- statuses/transitions
- exact criteria/context hashes
- restart/reopen
- failure preserves history

D. Exact-result cache:
- identical current request reuses snapshot
- criteria mismatch misses
- selection mismatch misses
- contract-version mismatch misses
- snapshot missing/corrupt rejects
- stale generation rejects

E. Intelligence reuse:
- same Modeling Context + different delivery profile = no new model/scoring
- same context + changed age/gender/state/income = no new model/scoring
- exact Audience membership still changes correctly

F. New build:
- incompatible/new Modeling Context invokes Phase10 correctly
- no duplicate orchestration

G. Result snapshot:
- exact row count/checksum
- no PII fields
- deterministic schema
- atomic publication/recovery
- same snapshot reused by repeated search history

H. Profiles:
EMAIL, DIRECT_MAIL, SMS, WHATSAPP, TELEMARKETING, PAID_SOCIAL, PAID_SEARCH;
gated profiles availability behavior.
For each: validator, allowlist, invalid identifier, consent, counts, checksum.

I. Paid media:
- hash normalization deterministic
- no raw identifiers
- pseudonymous disclaimer/contract

J. Contactability source:
- deterministic generation
- importer validation
- impossible states rejected
- model feature contract unchanged

K. Results UI:
- newest-first
- active status refresh
- blocked/failed/completed
- detail
- download

L. Privacy:
recursively scan default business APIs for names/emails/phones/addresses where not explicitly
a governed download response.

M. Phase1–10 full regression.

## Performance gates
Measure, do not invent SLA:
- Home load
- options load
- exact cache hit
- intelligence-reuse filter
- snapshot write/read
- result history
- each export profile
- optional atomic optimization comparison

Exact cache must be materially faster than re-filter/materialize path and must not scan all 5M scores.

Evidence:
`docs/evidence/phase11/17_TEST_MATRIX_PERFORMANCE.md`

STOP.
