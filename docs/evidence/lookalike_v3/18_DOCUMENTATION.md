# Prompt 18 — documentation, architecture and client explanation

Recorded 2026-10-11 (IST). Starting and working HEAD
`336875c30fc32b00323d916ecc45b232016168a1`; candidate **UNCOMMITTED**.
The worktree already contained uncommitted 14B implementation and Prompt
16/17 evidence; those changes were preserved. Preceding authority is the
[Prompt 17 exact 20-scenario report](17_SCENARIOS.md), following the
[Prompt 16.2 full-5M resource gate](16_2_FULL5M_MEASUREMENTS.md). No operator
database migration, canonical import, model training, five-million-row
rescoring, campaign send, retention deletion, commit, push, or deployment was
performed by Prompt 18.

## Documentation gate: GO

The current [architecture](../../BUYER_SIMILARITY_ARCHITECTURE.md),
[operator/demo guide](../../BUYER_SIMILARITY_OPERATOR_AND_DEMO.md), and
[model factsheet](08_MODEL_FACTSHEET.md) now reconcile schema 33,
`SIMILARITY_CUSTOMER_SPLIT_V2`, v3 cumulative resemblance selection,
preserved v1/v2 probability bands, independent readiness/currentness,
immutable membership and guarded export. The root, docs, prompt-pack and
evidence indexes point to the current reports while leaving historical
Prompt 15/16 failures and the old union-hash artifacts intact. Historical
Phase 11 API/feedback pages carry current-boundary notices rather than
pretending their earlier schema-19 statements are the latest contract. Live
OpenAPI includes validated explicit-v3 preflight and submission examples;
operators are told to replace the frozen disposable catalog token with the
one returned by their own options endpoint.

Client claims are intentionally limited. A 90 index means nearest-profile
weighted demographic distance at most 0.10 under
`BUYER_PROFILE_DISTANCE_V1`; it is not a 90% purchase likelihood,
confidence, percentile, accuracy or lift. The model uses 11 equally
weighted prospect-compatible features with FIT-only scales; missing or
unknown features penalize distance and coverage below 0.80 is invalid.
The support-aware customer-disjoint HOLDOUT is descriptive buyer stability
evidence, **not** campaign-isolated probability calibration or prospective
response validation. V3 feedback is retained with result lineage but does
not automatically retrain profiles or recalibrate probability; the separate
v1/v2 automatic path is calibration-only. Current catalog 48 versus 36
observed sales products, absent exact headphone/mobile-phone examples, and
unsupported products are disclosed.

## Evidence-backed decisions (separate gates)

| Gate | Current fact | Authority |
|---|---|---|
| Integrated runtime | Bounded single-node v3 path and v1/v2 compatibility passed earlier integration/fault gates | [09](09_INTEGRATION_CLOSURE.md), [15.1](15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md) |
| Descriptive method integrity | Declared reproducible score/lineage, supported three-product context; product-specific predictive discrimination remains unproven | [factsheet](08_MODEL_FACTSHEET.md), [assurance](08_MODEL_DATA_ASSURANCE.md) |
| Predictive/response/lift claims | **NO-GO / unavailable** independent outcomes and prospective validation | [factsheet](08_MODEL_FACTSHEET.md) |
| Full 5M | `FULL5M_GO_ON_NAMED_HARDWARE`; 5,000,000 valid and 0 invalid composite scores for PRD001/003/004 generations 3/4/5 in the isolated DB | [16.2](16_2_FULL5M_MEASUREMENTS.md) |
| Unchanged 20-scenario demo | `DEMO_GO`; 20 current exact preflights qualified at ≥10,000, 20 real completed results with identical member counts, 20 system-Chrome captures with technical detail, governed representative export PASS | [17](17_SCENARIOS.md), [translation](17_V3_TRANSLATION.json) |
| Remote CI/final release | **PENDING**; this uncommitted tree is not an exact-SHA remote-green release | Prompt 19 not run |

The demo's original scenario JSON SHA-256 is
`d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`.
Its common source identity is
`1c465d13b20fbd4400e708fef9876a5fa07be2b06c2b92741ad13817f1b573bb`;
profile-set SHA-256 is
`b754deaacf04a6b2781c9b090ed2b476a24c33fa2cb770c7a6c2c7be972e1def`.
The smallest/largest exact selected counts are 25,765/627,218. The
Scenario 20 current result [screenshot](17_browser_screenshots/scenario_20_run_22.png)
shows the 25,765-member 0.90-minimum case. Those counts and identities are
source/context-specific and cannot be borrowed for an operator's different
database. Prompt 17's scenario 7 duration includes durable restart recovery;
scenario 14 includes an observed host/monitoring pause, so neither is a pure
compute benchmark. Prompt 16.2's process/RSS/WAL measurements are explicitly
hardware-specific.

## Verification in this step

- `git rev-parse HEAD` → the trusted starting SHA above; `git status --short`
  confirmed the existing dirty 14B tree before edits. No applicable
  `AGENTS.md` was found by the repository file search.
- Pydantic validation of the two examples obtained from `app.openapi()` →
  **PASS**; their exact criteria agree. The example catalog token is a
  frozen Prompt 17 value, not a live-token promise.
- `python -m pytest -q tests/test_lookalike_v3_contract_migration.py
  tests/test_lookalike_v3_baseline_compatibility.py` → **20 passed in
  38.62 s**. Prompt 17's targeted preflight/snapshot tests were **18 passed**
  and its existing system-browser UI tests were **11 passed**; Prompt 18 did
  not rerun the full repository suite.
- `python -m ruff check app/schemas/potential_customer_search.py` → PASS.
  `git diff --check` → no whitespace errors; only existing line-ending
  conversion warnings. Documentation links and JSON/evidence integrity were
  checked after writing this report.

No new schema migration or data change was made by Prompt 18. The only code
change is documentation-only OpenAPI example metadata on the existing
explicit v3 request schemas; it does not change validation or legacy API
defaults. All other edits are documentation/index/evidence. No PII or raw
member IDs are in this report.

Prompt 18's changed/new files are `README.md`, `docs/README.md`,
`Prompts/README.md`, the pack's `00_README_START_HERE.md`,
`docs/BUYER_SIMILARITY_ARCHITECTURE.md`,
`docs/BUYER_SIMILARITY_OPERATOR_AND_DEMO.md`, the historical-boundary notices
in `docs/PHASE_11_API_AND_SCHEMA.md`, `docs/PHASE_11_RUNTIME_ARCHITECTURE.md`,
`docs/PHASE_11_RESULT_SNAPSHOTS_AND_SMART_REUSE.md`, and
`docs/PHASE_11_FUTURE_FEEDBACK_LINEAGE.md`, the current
`docs/FEEDBACK_LEARNING_BOUNDARY.md`,
`docs/evidence/lookalike_v3/08_MODEL_FACTSHEET.md` and evidence README,
`app/schemas/potential_customer_search.py`, and this Markdown/JSON evidence
pair. Other dirty files belonged to preceding uncommitted 14B stages and
were not rewritten by this documentation step.

## Pending outside this gate

Prompt 19 exact-SHA full regression and remote CI/manual workflow, plus
branch-protection administrator review, remain pending. Predictive outcomes,
product-specific response lift, true profile/model retraining, authentication
and multi-node/production hardening are not supplied by this POC. The full-5M
and 20-scenario *local* gates are completed, not pending. No historical
evidence or generated scratch was deleted. Next ordered stage: **Prompt 19**
only on operator direction.
