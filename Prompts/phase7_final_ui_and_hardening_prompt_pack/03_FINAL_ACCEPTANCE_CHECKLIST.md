# Final Phase 7 UI & Hardening Acceptance Checklist

## UI
- [x] IDs are exact integers
- [x] target/reconciliation/export counts are exact integers
- [x] compact K/M/B limited to suitable KPI surfaces
- [x] age inputs 18..100
- [x] family inputs min 1
- [x] stale shell/feature-gated wording removed
- [x] app/FastAPI description accurate
- [x] long export remains trackable beyond 120 sec
- [x] manual export-status refresh works
- [x] browser/a11y regression passes

## Export architecture
- [x] baseline profiling captured
- [x] dominant cost identified
- [x] unnecessary repeated work removed
- [x] deterministic order unchanged
- [x] selected count unchanged
- [x] deliverability counts unchanged
- [x] person-order checksum unchanged
- [x] CSV checksum unchanged for unchanged sources
- [x] no permanent member table
- [x] no sampling/truncation
- [x] no persistent PII CSV

## Snapshot/currentness
- [x] explicit export snapshot contract
- [x] consistent read snapshot
- [x] true mid-export drift test
- [x] no mixed provenance
- [x] future stale export blocked

## Deliverability/security
- [x] blank/malformed email tested
- [x] incomplete direct-mail address tested
- [x] selected = deliverable + undeliverable
- [x] exported rows = deliverable
- [x] formula-leading text hardened
- [x] commas/quotes/newlines/Unicode tested
- [x] no PII logs/errors/history
- [x] prohibited fields absent

## Lifecycle
- [x] progress/status safe for long exports
- [x] COMPLETED/FAILED/ABORTED terminal handling
- [x] stale STARTED recovery after restart
- [x] no silent 120-second polling stop

## Evidence/docs
- [x] correct Section 1 SHA
- [x] Section 2 progress completed
- [x] acceptance matrix completed
- [x] absolute temp paths sanitized
- [x] timing claims match referenced evidence
- [x] older evidence marked historical/superseded

## Final regression
- [x] Phase 1–6 intact
- [x] pytest
- [x] pip check
- [x] compileall
- [x] diff check
- [x] validate_data
- [x] browser E2E
- [x] no regeneration
- [x] no retraining
- [x] no rescoring
- [x] no activation/send
- [x] FINAL DECISION = GO
