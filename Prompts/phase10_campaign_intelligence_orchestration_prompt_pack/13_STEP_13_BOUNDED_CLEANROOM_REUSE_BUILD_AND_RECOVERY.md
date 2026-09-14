# Step 13 — Bounded Clean-Room Phase 10 Certification

Use an isolated fresh deterministic database and bounded sources.

Required scenarios:

1. Full new build:
Campaign Context → Modeling Context → new Historical Analysis → eligibility → governed
model → bounded full-universe scoring → rank/analytics → READY → preview → Saved Target Group → Campaign Draft.

2. Exact reuse:
Second campaign with identical Modeling Context but different name/delivery channel.
Assert same generation/model/scoring and no new heavy job.

3. Target-filter-only change:
Change match strength/demographics; same intelligence generation; preview only changes.

4. Demographic-source change:
Same history/context. Assert analysis/model reused, scoring+rank rebuilt.

5. Historical-source change:
Assert old analysis/model/scoring no longer current and downstream resolution occurs.

6. Rank-only recovery:
Invalidate only rank/analytics; reuse scoring and rebuild rank.

7. Insufficient history:
BLOCKED; no model/scoring; no broadening.

8. Restart/retry:
simulate durable RUNNING interruption; restart/reconcile/retry from highest verified stage.

9. Multi-branch Target Group:
disjoint age/income buckets after READY; exact union/no duplicates/hash/count/Campaign membership.

Run deterministic clean-room A and B and compare canonical hashes/counts/results.

Runtime must clean up and not modify production canonical files.

Produce machine-readable JSON and:
`docs/evidence/phase10/13_CLEANROOM_PHASE10_REPORT.md`

STOP.
