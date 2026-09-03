# Hardening Step 7 — Real 5M Rebenchmark & Reproducibility

Use current canonical 5M DB.
No regeneration, retraining, or rescoring.

Benchmark actual endpoints/services for:
1. EMAIL TOP_N 1K
2. DIRECT_MAIL TOP_N 50K
3. filtered DIRECT_MAIL ALL_MATCHING ~416K
4. top-decile/500K if practical
5. an undeliverable-heavy DB-copy case

Record:
- selected/deliverable/undeliverable/exported counts
- total runtime
- rows/sec
- query time
- deliverability time
- CSV encoding time
- checksum
- person-order checksum
- chunk/memory behavior
- source snapshot/currentness outcome

Repeat at minimum:
- 1K EMAIL twice
- 50K Direct Mail twice
- one large case twice if practical

Require identical counts/order/checksum on unchanged sources.

Timing is not an arbitrary pass/fail. But if ~416K still takes ~14 minutes, the profile
must clearly prove whether time is necessary exact work or unnecessary repeated work.
Continue optimization only for the latter.

Create:
`docs/evidence/phase7_final_export_hardening_5m.json`

STOP.
