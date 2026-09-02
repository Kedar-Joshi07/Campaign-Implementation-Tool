# Step 7 — Save Audience Optimization & Non-Blocking Frontend

## Objective
Avoid duplicate analytics computation and let search/results remain usable while profiles load.

## Save backend
- `include_profile_snapshot=false`: estimate only.
- `include_profile_snapshot=true`: run optimized profile once and derive/verify matching/selected counts server-side. Do not redundantly run a full estimate first unless it is a truly lightweight metadata fast path.
- Never trust client aggregates.
- Require selected_count >=1.

Persist bounded aggregate snapshot only; no PII/person IDs.

## Frontend
After estimate, start search and profile independently. Search must render as soon as ready. Profile gets its own loading/error/retry state and failure must not erase estimate/search/saved audiences.

Initial workspace: resolve run/options -> render workspace -> fast estimate/search -> load profile independently. Do not keep entire page blocked on profile.

## Async race protection
Use AbortController or request generation token. Old estimate/search/profile responses must never overwrite newer filter state. Latest request wins.

## Preserve saved-audience behavior
Immutable definitions, current/stale semantics, stale read-only mode, reopen workflow.

## Tests
Prove stale responses ignored, search renders before profile, profile failure isolated, loading states reset, options refresh bypasses cache, stale saved audience remains read-only.

Save-with-profile threshold `<=60 sec`. For heavy bounded runs, `120-180 sec` is acceptable only if data authenticity, process quality, and output usefulness are fully preserved.

Quality guardrail: do not trade correctness or provenance for speed. If behavior or data meaning changes, treat as NO-GO regardless of runtime.
