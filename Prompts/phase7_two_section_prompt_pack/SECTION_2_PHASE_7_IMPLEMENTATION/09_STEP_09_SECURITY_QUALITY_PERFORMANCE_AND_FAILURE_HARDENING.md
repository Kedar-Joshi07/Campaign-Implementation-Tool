# Step 9 — Security, Quality, Performance & Failure Hardening

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

Security:
parameterized values, internal field allowlists, safe filename, CSV injection protection,
no PII in logs/errors/history, no customer/person identity linkage.

Must stay lightweight:
campaign options/list/detail/currentness, draft create/update, finalize metadata checks.

Heavy exact work may take time:
member resolution, deliverability scan, export, explicit deep audit.

Failure tests:
stale audience, source change pre-finalize, pre-export and mid-export, missing rank/analytics,
missing contact endpoint, client disconnect, DB lock, invalid PII acknowledgement,
export-event update failure.

Prefer safe failure over misleading partial result. STOP.
