# 01 — Master Guardrails

## Starting state

Work only in:
`C:\POCs\Campaign Implementation Tool`

Required Git SHA:
`f2b98adfcf1a01f23f1c201aa2cf5a2df1521a2d`

Before any mutation:

```powershell
git rev-parse HEAD
git status --short
git branch --show-current
```

Hard fail if HEAD differs. If the worktree is dirty, inventory every change and do not overwrite unrelated work.

## Canonical runtime

Use the real configured database (`data/campaign_poc.db` unless application config resolves another canonical path), real canonical data, real Phase 10/11 orchestration, real result snapshots, and the normal application startup path.

Forbidden shortcuts:
- pytest/TestClient/temp database for scenario preload;
- test executor injection or monkeypatching;
- manually inserting completed rows into registry tables;
- manually attaching an arbitrary/latest scoring run;
- editing result counts;
- fabricating progress/ETA;
- regenerating or replacing source datasets;
- deleting prior model/scoring/search/result history;
- running the 20 scenarios concurrently;
- weakening currentness/provenance checks;
- exporting contact PII merely to prove the runs completed.

The 20 preload scenarios must be executed sequentially. This POC is SQLite/single-node and a prior grouped concurrency run exposed a transient artifact-root race even though isolated rerun passed.

## Reuse policy

Keep one common Campaign Context / Modeling Context across all 20 searches. Only targeting criteria change.

Expected reuse order:
1. validated exact result cache, when an exact prior result already exists;
2. compatible current Phase 10 intelligence;
3. minimum required Phase 10 build only when compatibility requires it.

Never use “latest run wins”.

If no current READY intelligence exists for the selected common context, the first real scenario may cause the normal production orchestration to build the missing layer(s). Wait for it to finish. Scenarios 2–20 should then reuse that compatible intelligence whenever their unchanged modeling context permits it.

## Delivery/export profile

Resolve available profiles from the live backend. Prefer `EMAIL_CONTACT_V1` only if the backend says it is available and the corresponding campaign channel is valid. Otherwise choose one currently AVAILABLE/RELEASE_IMMEDIATE profile and use its exact backend-owned channel/profile pair for all scenarios.

Do not invent an export profile or channel.

## Scenario invariant

For all 20:
- `top_matching_percent = null`
- `selection_mode = ALL_MATCHING`
- `target_count = null`
- same campaign context
- same export profile/channel

Targeting criteria come exactly from `scenarios.json`.

## Demo readiness rule

A scenario is demo-ready only when:
- terminal status = `COMPLETED`;
- lifecycle progress = 100%;
- selected_count > 100;
- snapshot/currentness = `CURRENT`;
- result can be reopened from the production Results endpoint;
- no unsafe/internal failure text is exposed;
- download eligibility is truthful for the selected profile.

If a scenario returns <=100, do **not** broaden it silently. Preserve the real run, mark it `DEMO_COUNT_TOO_SMALL`, and record a separately proposed fallback for human approval.
