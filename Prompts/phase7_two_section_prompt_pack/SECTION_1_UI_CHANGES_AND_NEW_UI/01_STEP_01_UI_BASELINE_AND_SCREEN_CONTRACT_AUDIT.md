# Step 1 — UI Baseline & Screen Contract Audit

Required HEAD: `0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0`

Run full baseline gates:
```powershell
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Audit every visible field/action on:
Overview, Data Status, Historical Analysis, Model Training, Prospect Scoring,
Audience Explorer, Saved Audiences, disabled Campaigns.

For every field record:
label, explanation, API, backend source, data grain, current/historical/derived status,
loading/empty/error behavior, stale/current behavior, privacy/PII behavior,
accessibility and responsive behavior.

Reconfirm known findings:
- Audience Explorer still under "Later phases";
- sidebar footer still Foundation/Phase 1;
- Model Training label does not clearly include Phase 5 scoring;
- FastAPI/app description stale at Phase 1–5;
- Overview "Known positives" is observation-grain but later positives are customer-grain;
- Data Status "Last import" can mean failed attempt while published data remains valid;
- historical analyses lack obvious Current/Stale trainability;
- Recall/Lift @5/@10/@20 does not say percent;
- scoring UI wording is narrower than full provenance;
- Audience Explorer privacy boundary not prominent;
- Phase 2/Phase 6 band definitions can confuse stakeholders;
- Overview waits on deep reconciliation;
- recent model list may cause N+1 detail calls;
- frontend tests are mostly static/source tests rather than browser E2E.

Create `docs/evidence/phase7_section1_ui_baseline_audit.json`.
No PII, raw SQL, paths or tracebacks. STOP.
