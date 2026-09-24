# 05 — Housekeeping & Current-Baseline Cleanup

Perform housekeeping only after the audit and demo preload are safely complete.

## A. Current documentation truth

Known required check: code is schema version 19, while the current-version section of README may still state schema version 18. Correct genuinely current documentation.

Do **not** rewrite historical evidence merely because it records schema 18 at the time it was captured. Historical evidence should stay immutable. Instead:
- clearly label it historical/superseded where ambiguity exists;
- add a concise current baseline document, e.g. `docs/CURRENT_BASELINE.md`;
- record SHA `f2b98adfcf1a01f23f1c201aa2cf5a2df1521a2d`, schema 19, lifecycle contract 1, current visible workflow, known POC limitations, and latest validation date.

## B. Repository hygiene

Refresh the repository-housekeeping inventory. The old inventory predates current Phase 11/schema-19 work.

Check:
- no DB/WAL/SHM/runtime result artifacts tracked;
- no `.env`, secrets, browser traces, logs, temp/backup files tracked;
- LFS pointers valid for canonical large data;
- no obsolete untracked helper scripts in repo root;
- no duplicate generated evidence pretending to be current;
- prompt packs/evidence have an index identifying current vs historical material.

Do not mass-delete old prompt packs immediately before the demo. Archive/index them instead; deletion is a post-demo choice.

## C. Known concurrency observation

Investigate the transient artifact-root race seen once in a grouped concurrency run.

Look especially for:
- mutable module-global artifact roots in tests;
- concurrent tests sharing one fixed temp/artifact directory;
- cleanup racing another worker;
- result snapshot path allocation outside the same locking/transaction boundary.

Make each test/process use an isolated artifact root. Add repeated concurrency stress coverage if the cause is test isolation. If it can affect production runtime, classify as MUST FIX BEFORE DEMO or BLOCKER according to reproducibility and real-runtime exposure.

## D. Polling/status consistency

Review the 5-minute bounded Results/Result Detail auto-poll window. If long real runs can exceed it, either:
- visibly indicate that auto-refresh paused and manual Refresh Progress remains available; or
- use a safe longer/adaptive bounded policy.

Also make status badges consistently prefer durable lifecycle status where pause/stop/restart states are displayed.

## E. ETA improvement note

Current bounded ETA may derive from overall progress percentage rather than direct processed-record throughput. If true, document it as a bounded approximation. A future refinement may use observed stage/record throughput with per-stage estimates, but do not destabilize the demo solely to perfect ETA.

## F. POC limitations

Keep these explicit:
- no authentication/RBAC/tenant isolation;
- single-node SQLite / bounded single-worker compute posture;
- local artifacts;
- no live activation/send integration;
- no automated provider feedback/retraining loop.

These are accepted POC boundaries, not hidden defects.
