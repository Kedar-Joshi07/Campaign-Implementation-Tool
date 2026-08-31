# Step 2 — TOP_N Selection Contract Fix

Use HEAD from Step 1.

Do not change Selection Contract v1.

## Required rule

Remove the arbitrary hard-coded 1,000,000 cap.

Enforce dynamically:

```text
1 <= target_count <= current canonical scoring_run.scored_person_count
```

For the current 5M universe:
- 1 valid;
- 1,000,001 valid;
- 5,000,000 valid;
- 5,000,001 invalid.

Do not hard-code 5M in runtime.

Keep `normalize_selection()` structural only:
- TOP_N requires positive integer;
- ALL_MATCHING requires null target.

Apply universe-dependent validation after canonical scoring context is loaded.

Enforce the same rule consistently in:
- estimate;
- profile;
- save audience.

## Optimization

When `target_count >= matching_count`:
- `selected_count = matching_count`;
- avoid unnecessary large TOP_N ordering/materialization where practical;
- keep saved selection mode as TOP_N if user requested TOP_N.

## Tests

Add:
1. TOP_N=1 valid.
2. TOP_N=1,000,001 valid when universe permits.
3. TOP_N=universe_count valid.
4. TOP_N=universe_count+1 rejected.
5. small fixture dynamic universe behavior.
6. matching_count < target_count resolves to matching_count.
7. profile remains correct.
8. saved audience persists requested TOP_N.
9. ALL_MATCHING unchanged.
10. full regression passes.

Update Phase 6 docs/acceptance notes.

STOP.
