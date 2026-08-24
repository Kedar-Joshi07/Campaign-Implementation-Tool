# Step 2 — Prospect Data Access and Feature Compatibility

## Objective

Build scoreability and bounded demographic read boundary. No real score persistence.

## Scoreability

Create a compatibility service. Require COMPLETED, role policy 2, evaluation contract 2, selected BAGGING_PU, PRIMARY_ROLE_GOVERNED, feature v1/hash exact, verified artifact, candidate agreement. Reuse `load_verified_model_artifact`.

Reject legacy, failed/running, Elkan-selected, Naive, checksum/contract mismatch.

## Prospect snapshot

Capture `COUNT(*)`, `MIN(person_id)`, `MAX(person_id)`; count must be >0. Production code must not hard-code 5M.

## Exact chunk query

`fetch_scoring_chunk(after_person_id, limit)` selects only person_id + 11 frozen features and uses keyset ordering. No OFFSET; no forbidden columns.

Return internal `person_ids` plus feature DataFrame in exact `ORDERED_FEATURES` order.

## Preflight

Before full scoring, push a bounded initial chunk through:

```text
validate_and_normalize_feature_frame
→ persisted preprocessor.transform
→ persisted estimator scoring
```

No persistence. Worker still validates every chunk.

## Tests

Scoreable v2 Bagging passes; bad statuses/legacy/candidate/artifact/contract fail before scanning; exact 12 selected columns; forbidden columns absent; keyset deterministic; no OFFSET; zero population fails; invalid age/income/family fails; unknown category supported.

STOP after Step 2.
