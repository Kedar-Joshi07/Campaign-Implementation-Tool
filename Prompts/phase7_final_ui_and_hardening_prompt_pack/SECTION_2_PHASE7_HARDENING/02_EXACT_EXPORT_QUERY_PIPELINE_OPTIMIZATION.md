# Hardening Step 2 — Exact Export Query Pipeline Optimization

## Goal
Remove repeated work while proving exactly identical business output.

Current pattern repeatedly:
member query -> 25K IDs -> temp ID table -> second demographics join -> CSV -> repeat.

Evaluate this preferred architecture first:

1. Build one exact SELECT for the finalized campaign.
2. Join demographics only once when demographic filters/contact fields require it.
3. Apply exact saved-audience filters.
4. Order once:
   `propensity_score DESC, person_id ASC`
5. Apply LIMIT only for TOP_N.
6. Execute one cursor.
7. Consume with `fetchmany(chunk_size)`.
8. Select only approved contact fields for the channel in that same cursor where safe.
9. Compute percentile/decile/rank band from the already-prepared 100 boundaries.
10. Apply exact deliverability and stream CSV.

This should eliminate repeated filtered query execution, temp-ID churn, and the second
demographic lookup per chunk.

If one-cursor design is not fastest, a connection-local TEMP table containing only
`person_id` and `propensity_score` is allowed if benchmarked and faster. It must never
become persistent and must contain no contact PII.

Profile percentile classification. If it linearly scans 100 boundaries per row, a
binary/bounded lookup may be used only if exact boundary/tie semantics are proven
identical.

Do not add speculative indexes. Any new index requires real before/after timing,
query-plan evidence, DB-size impact, and exact-output equivalence.

For each reference campaign before/after require:
- selected_count identical
- deliverable_count identical
- undeliverable_count identical
- exported row_count identical
- person-order SHA identical
- CSV SHA identical
- headers identical

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

STOP unless equivalence passes.
