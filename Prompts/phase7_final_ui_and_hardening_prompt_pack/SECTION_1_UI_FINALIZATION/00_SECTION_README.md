# Section 1 — Final UI/Product Finalization

Start from `4748d9e7aa837ad2e66876c20714d576d3ed1f31`.

This is a narrow UI correctness and clarity pass. Do not change campaign/member/export
business semantics here.

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
