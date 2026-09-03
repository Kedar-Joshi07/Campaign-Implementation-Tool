# Hardening Step 8 — Final Phase 1–7 Regression & Freeze

Run:
```powershell
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```
Run real browser E2E.

## Phase 1–6 invariants
- customers 125K
- campaign sales 570K
- demographics 5M
- current source provenance
- Feature Contract v1 / SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- Model Role Policy v2
- Evaluation Contract v2
- BAGGING_PU
- score count 5M
- deterministic 256-row rescore max diff 0
- 100 rank boundaries
- analytics snapshot current
- Audience Explorer non-PII
- saved audiences immutable/currentness-governed

## Phase 7 invariants
- additive schema only
- no persistent member table
- DRAFT/FINALIZED and finalized immutable
- exact deterministic resolution
- exact EMAIL/DIRECT_MAIL contracts
- deliverability reconciliation
- CSV injection protection
- long-running status/recovery
- true mid-export drift test
- no mixed provenance under chosen snapshot contract
- future stale export blocked
- no PII outside stream
- no persistent server PII CSV
- no activation/send

Commit:
`fix: finalize phase7 export integrity and ui exactness`

Optionally add a documentation-only closure commit recording the implementation SHA.

Final report must include:
starting SHA, UI SHA, hardening SHA, optional closure SHA, schema version, files changed,
formatter changes, input fixes, wording cleanup, polling/status redesign, 416K before/after,
throughput before/after, dominant cost, architecture after, index changes, output-equivalence,
checksums, deliverability tests, CSV injection tests, mid-export drift result, snapshot
contract, stale-future-export block, PII scan, stale STARTED recovery, evidence cleanup,
pytest/pip/compile/diff/validate/browser results, no regeneration/retrain/rescore/activation,
and GO/CONDITIONAL GO/NO-GO.

GO only if data/process/logic quality is at least as strong as baseline. STOP.
