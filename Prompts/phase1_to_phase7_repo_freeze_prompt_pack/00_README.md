# Phase 1→7 Repository Freeze & Fresh E2E Prompt Pack

Run workstreams in this order:
1. Repository Housekeeping
2. Documentation Freeze
3. Clean-Room Validation
4. CI Freeze
5. Full Fresh Phase 1→7 Browser E2E

Each workstream is split into sequential STOP-gated prompts. Commit after each workstream.

## Frozen quality-first rule
Correctness, data integrity, business logic, reproducibility, provenance, and analytical usefulness take priority over arbitrary processing-time targets.

Never introduce sampling, approximation, truncation, semantic changes, reduced data coverage, weaker validation, or altered business results merely to improve speed.

Interactive lightweight operations should remain responsive. Exact heavy work may take 60 seconds, 120–180 seconds, or longer where justified. Improve architecture and progress visibility before compromising data/process/logic quality.

Optimize unnecessary work, not necessary work.

Final goal: a clean, documented, reproducible, CI-gated repository that can regenerate all synthetic data from source, create a fresh database, execute Phase 1→7 from zero, score all 5M prospects, prepare audiences, save an audience, create/finalize campaigns, and produce Email/Direct Mail target exports through a real browser user journey.
