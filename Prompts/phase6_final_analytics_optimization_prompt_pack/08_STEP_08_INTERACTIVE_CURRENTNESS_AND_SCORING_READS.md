# Step 8 — Remove Remaining Deep Scans from Ordinary Read APIs

## Rule
**Interactive read = lightweight currentness. Deep integrity = explicit completion/preparation/audit.**

## Call-site audit
Classify every caller of deep provenance/integrity functions and full score/prospect aggregate helpers as INTERACTIVE or DEEP/AUDIT. Migrate interactive callers.

## Required fixes
Review/fix `get_scoring_status()` and `get_scoring_run_detail()` to use lightweight canonical/currentness helpers. Do not COUNT/COUNT DISTINCT/MIN/MAX/AVG 5M merely to render status/detail.

Avoid `fetch_prospect_snapshot()` on every status read when authoritative import/scoring metadata already provides the required current values. Keep full snapshot scan for scoring preflight/deep acceptance only.

## Lightweight governance hardening
Metadata-only currentness must enforce expected:
- scoring model_role_policy_version
- model metrics model_role_policy_version
- evaluation_contract_version
- governed selection policy
- primary_candidate BAGGING_PU
- selected_candidate BAGGING_PU
- expected challenger list
- expected diagnostic controls
- artifact SHA metadata consistency

Do not load/hash the model artifact for every read.

Where response contracts permit, distinguish `is_canonical`, `demographic_source_verified`, `historical_source_verified`.

## Deep gates retained
Keep deep validation at scoring completion, audience preparation, explicit integrity audit, final acceptance.

## Regression guard
Instrument full-scan helpers to fail if invoked from ordinary scoring/audience/saved-audience read paths. Those paths must remain lightweight.

## WAL measurement
Measure per-connection `PRAGMA journal_mode=WAL` overhead/lock churn. Change only if clearly safe/measurably beneficial; otherwise leave it.

Do not rebuild demographics solely to tighten legacy physical CHECKs.

Targets: scoring status/detail `<5 sec`, preferred `<2 sec`.
