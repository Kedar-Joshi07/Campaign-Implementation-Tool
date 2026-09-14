# Phase 10 Master Guardrails

Baseline: `7e54754053bf998e65c59a36c0096d5404bb6479`

1. Preserve Phase 1–9 behavior, contracts, currentness, privacy and deterministic semantics.
2. Never pick latest/first/arbitrary analysis, model or scoring run before exact compatibility.
3. Correctness, provenance, reproducibility and exactness outrank runtime.
4. Never silently broaden Campaign Context to make a model train.
5. Multi-product v1 = one combined model; positive if ANY selected product has the governed conversion.
6. Delivery channel is not a modeling dimension; historical campaign channels are.
7. Prospect targeting filters are post-score Audience Engine filters, never model inputs/context keys.
8. No customer_id↔person_id identity bridge or PII matching.
9. Preserve Bagging PU PRIMARY; challenger cannot auto-promote; diagnostic control never selectable.
10. New scoring means complete current canonical prospect universe; no production sampling.
11. No contact PII in Phase 10 planning, compatibility, progress, registry or preview APIs.
12. Long-running orchestration must be durable across refresh/navigation/restart.
13. Avoid nested single-worker ProcessPool deadlock: parent orchestration may call synchronous worker/core logic, not submit and block on the same single-worker executor.
14. Retention is non-destructive in Phase 10: classify retirement eligibility but do not automatically delete score/model/analysis history.
15. Default UI must use business language; technical jargon appears only under explicit disclosure.
16. Final browser certification uses installed Chrome preferred, Edge fallback.
17. No GO without full regression, bounded clean-room, real browser, true full 5M preparation path, exact-SHA CI and consistent evidence.
