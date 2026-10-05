# Prompt 13.6.1 Legacy Selection Mapping Closure

## Certification state

- Starting SHA: `728fa19ef88d891af82bceaa07fd4301d900514d`.
- Starting exact-SHA CI: run `37262707196`; Repository Hygiene, Python Validation, Tests, Frontend Contract, and Clean-Room Phase1-7 all succeeded.
- Candidate SHA: `a35dabbf0baa43e12dfe4bddc9ad72c29bdf5acb`.
- Prompt 13.6.1 status: **GO — PRE-14 STABILIZATION COMPLETE**.

This evidence supersedes Prompt 13.6 as the latest pre-14 authority. The original Prompt 13.6 evidence remains unchanged and auditable, but its GO claim was superseded after an independent post-implementation audit found a semantic reverse-mapping regression.

## Defect and root cause

The Prompt 13.6 selection registry correctly retained the explicit v2-to-legacy projection:

```text
0.90 -> VERY_STRONG
0.80 -> STRONG
0.70 -> GOOD
0.60 -> BROAD
0.50 -> BROAD
```

It incorrectly constructed the reverse mapping by dictionary inversion. Because that projection is many-to-one, last-write-wins behavior changed the historical `BROAD` mapping from `0.60` to `0.50`.

The Prompt 13.5 baseline at `58a5852d488aa686ed67ffa7ccecbc50463f4081` explicitly defined the frozen mapping as:

```text
VERY_STRONG -> 0.90
STRONG      -> 0.80
GOOD        -> 0.70
BROAD       -> 0.60
```

The current Phase 9 match-strength contract independently retains thresholds `0.90`, `0.80`, `0.70`, and `0.60`, with BROAD defined as `[0.60, 0.70)`.

## Repair

`app/selection_contracts.py` now defines the legacy-to-v2 compatibility mapping explicitly and with bounded types. A code comment records that v2-to-legacy projection is many-to-one and must never be mechanically inverted. The separate explicit v2 registry is unchanged, including the `0.50` bucket.

## Canonical scenario impact

The canonical pack remains byte-unchanged and contains 20 scenarios:

- VERY_STRONG: 1
- STRONG: 2
- GOOD: 7
- BROAD: 10

All 10 BROAD scenarios now translate to `0.60`; none translates to `0.50`. No scenario or demographic criterion was modified, and no Prompt 17 search was executed.

## Frozen invariants

- Selection contract version: `2`.
- Default v2 bucket: `0.70`.
- Demo qualification minimum: `10,000`.
- Explicit `0.50`: `[0.50, 0.60)`.
- Explicit `0.60`: `[0.60, 0.70)`.
- No v3 contract or bucket was introduced.

## Schema and data impact

- `CURRENT_SCHEMA_VERSION` remains `31`.
- No schema migration was created or run.
- No canonical database, calibration, search result, snapshot, or scenario definition was mutated.
- Canonical database SHA-256 remains `43b6d31ed6c4f33574f2450f3bf1e2ece0ab56d77fd9213e76de9e8e07ef4d77`.
- Canonical scenario SHA-256 is `d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`, with no tracked diff.

## Documentation repair

Root `README.md` now consistently states schema 31 and documents migration 31's promoted-calibration singleton, feedback statistical grouping/evaluation lineage, and worker ownership/fencing additions. `docs/README.md` names this evidence as the latest pre-14 authority.

## Files changed

- `app/selection_contracts.py`
- `tests/test_selection_contract_registry.py`
- `README.md`
- `docs/README.md`
- this Markdown evidence and its JSON companion
- the operator-supplied Prompt 13.6.1 source prompt

## Tests

- Focused contract, normalization, browser-form, and parity suite: **92 passed in 287.79 seconds**.
- Main non-heavy: **1,050 passed, 121 deselected in 2,305.55 seconds**.
- Frontend/API browser-or-integration: **125 passed in 579.23 seconds**.
- Phase 9: **69 passed in 630.32 seconds**.
- Phase 10: **90 passed in 4,296.55 seconds**.
- Phase 11 bounded: **354 passed, 5 deselected in 770.59 seconds**.
- `pip check`, compileall, evidence JSON validation, and `git diff --check`: **PASS**.
- Clean-Room Phase1-7: **PASS**, completed `2026-10-05T07:58:18Z`.

## Governance and remote certification

- Manual Full Validation: `MANUAL FULL VALIDATION REMOTE CERTIFICATION PENDING` unless authenticated dispatch becomes available after push.
- Branch protection re-read: `main.protected=false`; `BRANCH PROTECTION PENDING - ADMIN ACTION REQUIRED`.
- Exact-candidate-SHA CI: run `37281401935`; all five required jobs succeeded.

## Decision

**PROMPT 13.6.1 = GO — PRE-14 STABILIZATION COMPLETE.**

The only valid next action is to reconfirm the Prompt 13 business decision and run exactly one of Prompt 14A or Prompt 14B.

