# Single Master — Pre-Phase-7 Phase 6 Finalization

Repository:
`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD:
`b2cdfa95713aa2f8d9309be4881079f703df1831`

Do not implement Phase 7.
Do not regenerate data.
Do not retrain.
Do not rerun Phase 5 5M scoring.

Execute in order:

1. Baseline audit and confirm known finalization issues.
2. Remove arbitrary TOP_N 1M cap; enforce `1 <= TOP_N <= current scoring universe`.
3. Add prepared/current/ready semantics to audience run list/status and UI selection.
4. Instrument real Phase 6 rank-preparation metrics and persist bounded job results.
5. Capture real 5M Phase 6 performance evidence; relabel existing Step 8 timing as synthetic query-plan evidence.
6. Remove tracked synthetic SQLite DB; ignore generated artifact DBs; sanitize evidence; complete PII metadata.
7. Run full final regression on actual final code; refresh Phase 6 acceptance/handoff docs; commit finalization.

Final HEAD becomes the candidate Phase 7 starting baseline.

Return strict GO/NO-GO report and STOP.
