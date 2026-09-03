# UI Step 1 — Baseline & Exactness Audit

Required HEAD: `4748d9e7aa837ad2e66876c20714d576d3ed1f31`

Run:
```powershell
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Audit all uses of `formatNumber` and classify each displayed value as:
1. IDENTIFIER — exact integer
2. EXACT_COUNT — full comma-separated integer
3. COMPACT_KPI — K/M/B allowed
4. DECIMAL_METRIC — decimal precision

Inspect campaign_id, audience_id, scoring/model/analysis/import IDs, export_event_id,
target/resolved/selected/deliverable/undeliverable/export counts, reconciliation counts,
population counts and Overview KPIs.

Confirm current issue: shared `formatNumber()` can display IDs/counts as `#8.00`,
`50.00K`, `5.00M`.

Audit browser constraints:
- age 18..100
- family member count >=1
- score 0..1
- percentile 1..100
- TOP_N >=1

Search stale wording:
- Phase 7 shell
- feature-gated until Section 2
- backend not enabled
- any text implying Campaign Builder is incomplete

Create `docs/evidence/phase7_final_ui_baseline.json`.
STOP if baseline gates fail.
