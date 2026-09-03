# Final Phase 7 UI & Hardening Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD: `4748d9e7aa837ad2e66876c20714d576d3ed1f31`

Reference:
- Phase 6 closure: `0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0`
- Phase 7 Section 1 UI: `dda2ac69540ad96896d379f83da2d338a1292854`
- Current Phase 7 implementation: `4748d9e7aa837ad2e66876c20714d576d3ed1f31`

## Purpose

Phase 7 is functionally implemented. This final pass closes the remaining audit findings
before freezing Phase 7.

### Section 1 — UI finalization
- exact IDs/counts vs compact KPI formatting
- browser input-contract cleanup
- stale Phase 7 shell/feature-gated wording removal
- accurate product/app descriptions
- long-running export status that does not silently stop at 120 seconds
- final browser/a11y regression

### Section 2 — Phase 7 hardening
- profile the 416K+ ~14-minute exact export
- remove unnecessary repeated selection/contact work
- preserve exact deterministic membership and checksum equivalence
- define safe consistent export-snapshot behavior
- true mid-export source-drift test
- undeliverable contact tests
- CSV formula-injection/encoding tests
- stale STARTED export recovery
- evidence/progress/acceptance cleanup
- real 5M rebenchmark and final Phase 1–7 freeze

## Hard non-goals
No data regeneration, retraining, 5M rescoring, sampling, approximation, truncation,
permanent member table, persistent server PII CSV, customer/person identity linking,
new channels, or real activation/sending.

## Quality-first rule

Performance must be optimized only after correctness, data integrity, business logic,
reproducibility, provenance, and analytical usefulness are satisfied.

Performance optimizations MUST NOT introduce sampling, approximation, truncation,
semantic changes, reduced data coverage, weaker validation, altered business results,
weaker source/model currentness, or less useful output.

Interactive lightweight operations should remain responsive. Exact heavy analytics,
integrity validation, deterministic member resolution, deliverability checks, and large
target exports may take about 60 seconds normally and, where exact full-volume work
genuinely requires it, approximately 120–180 seconds or longer if justified.

If exact work takes longer, improve processing architecture and user-visible status first.
Never compromise process, data, logic, provenance, or output quality for an arbitrary SLA.

Optimize unnecessary work, not necessary work.

Run every file in Section 1 first, commit it, then run Section 2.
