# Single Master Prompt — Final Phase 7 UI & Hardening

Required starting HEAD:
`4748d9e7aa837ad2e66876c20714d576d3ed1f31`

Execute every Section 1 step, create the UI-finalization commit, then execute every
Section 2 hardening step.

Goals:
- exact IDs/counts in UI
- correct age/family browser contracts
- remove stale shell/feature-gated wording
- long-running export status beyond 120 seconds
- profile the ~416K / ~14-minute export
- remove unnecessary repeated selection/contact work
- preserve exact membership, order, deliverability and checksum
- define a consistent export snapshot contract
- test true mid-export source drift
- test undeliverable rows and CSV formula injection
- recover stale STARTED export events
- reconcile evidence, tracker and acceptance matrix
- rerun real 5M and full Phase 1–7 acceptance

Never regenerate data, retrain, rescore, sample, truncate, approximate, weaken
currentness, create permanent member tables, persist PII CSVs, or implement activation.

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

Obey every STOP gate.
