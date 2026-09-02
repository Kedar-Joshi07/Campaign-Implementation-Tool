# Single Master Phase 7 Prompt

Start from `0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0` and execute every Section 1 step, commit Section 1, then every
Section 2 step.

Section 1 corrects business-facing UI drift and builds the Campaign Builder UI safely
feature-gated.

Section 2 implements schema v11 campaign persistence, current saved-audience handoff,
immutable finalized campaigns, exact deterministic member resolution, minimal explicit
Email/Direct Mail contact PII contracts, streaming CSV export and aggregate audit.

Never create a member table or persistent PII CSV.
Never implement actual activation/sending.
Never link customer_id to person_id.
Preserve all Phase 1–6 contracts and `propensity_score DESC, person_id ASC`.

Performance must be optimized only after correctness, data integrity, business logic,
reproducibility, provenance, and analytical usefulness are satisfied.

Performance optimizations MUST NOT introduce sampling/approximation, semantic changes,
reduced data coverage, weaker validation, altered business results, weaker currentness,
or less useful output.

Interactive lightweight operations should remain responsive. Exact heavy analytics,
preparation, integrity validation, deterministic member resolution, and large target
exports may take about 60 seconds normally and, where exact full-volume work genuinely
requires it, about 120–180 seconds.

Long-running exact work should use clear progress/loading/streaming states rather than
compromising process, logic, data quality, or usefulness.

Optimize unnecessary work, not necessary work.

Obey every STOP gate.
