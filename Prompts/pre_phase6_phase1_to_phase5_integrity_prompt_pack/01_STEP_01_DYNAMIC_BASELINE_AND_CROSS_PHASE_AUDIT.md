# Step 1 — Dynamic Baseline and Cross-Phase Audit

Required starting SHA: `5f54c5e7138afaf615984babd32cac3a6bf2a99b`

Do not modify code in this step.

## Baseline

Run:

```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

HEAD must be `5f54c5e7138afaf615984babd32cac3a6bf2a99b` and unexplained worktree changes must stop the pass.

Record schema version, current table counts, latest COMPLETED import IDs/checksums for:

- customers
- campaign_sales
- demographics

Record current completed:
- analysis runs
- model runs
- scoring runs

## Cross-phase integrity checks

### A. Historical adult eligibility

Run an exact SQL query joining `campaign_sales` to `customers` and calculate completed age on each `contact_date`.

Count rows where age at contact is < 18.

Use calendar-aware completed age, not `days / 365`.

Also return:
- minimum age at contact;
- distinct affected customer count;
- first/last affected contact date;
- affected campaign count.

Do not expose customer IDs.

The target invariant is:

```text
underage_campaign_contact_count = 0
```

### B. Training-reference age

For every COMPLETED Phase 2 analysis, or at minimum every analysis referenced by a COMPLETED model run, reconstruct derived age at saved `contact_date_to`.

Count rows outside:

```text
18 <= age <= 100
```

Report analysis IDs and aggregate violation counts only.

### C. Historical source drift

For each COMPLETED analysis, identify the latest COMPLETED customer and campaign-sales imports that existed when that analysis completed.

Compare them to current latest COMPLETED imports.

Report whether the analysis predates a controlled source replacement.

Do not mutate legacy runs.

### D. Current model/scoring chain

For the current Phase 5 canonical score run, record:

```text
analysis_run_id
model_run_id
scoring_run_id
demographic_import_id
demographic checksum
model artifact SHA
feature-contract SHA
score row count
```

Determine whether the model's historical source is still the same historical source used when its Phase 2 analysis was created. If the current schema cannot prove that, explicitly report `historical_source_provenance = UNPROVEN`.

### E. Shared categorical diagnostics

Compare categorical vocabularies used by:
- current customer rows;
- current demographics rows;
- exact model categorical features.

Do not require perfect equality because `OneHotEncoder(handle_unknown="ignore")` is frozen behavior.

Report prospect-only and customer-only categories for diagnostic awareness.

### F. Scope scan

Confirm Phase 6 functionality is still absent.

## Output

Produce a machine-readable sanitized report:

`docs/evidence/phase1_to_phase5_integrity_baseline.json`

No PII, raw IDs, absolute paths, SQL text, or tracebacks.

Report:
1. baseline SHA
2. regression results
3. schema version
4. import provenance
5. underage contact count
6. training-age violations
7. source-drift status
8. current model/scoring chain
9. categorical diagnostics
10. Phase 6 scope scan
11. GO/NO-GO for Step 2

STOP.
