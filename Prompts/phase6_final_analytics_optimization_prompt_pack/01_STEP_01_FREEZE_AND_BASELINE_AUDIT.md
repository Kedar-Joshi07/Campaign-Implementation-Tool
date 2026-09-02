# Step 1 — Freeze, Baseline & Fine-Comb Audit

Required starting HEAD: `80c3324f884f448b1eb84e61fafcd1c70415b8b1`

## Objective

Establish an immutable pre-change baseline and verify all known issues before touching runtime code.

## STOP gate

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

HEAD must equal `80c3324f884f448b1eb84e61fafcd1c70415b8b1`. If unexplained tracked changes exist, STOP.

## Record baseline

Capture schema version; latest customer/campaign/demographic import IDs/checksums; current analysis/model/scoring IDs; score count; rank boundary count; saved audience count; test count; DB bytes/page_count/page_size; timings for saved currentness, audience runs, preparation status, options, estimate-all/top1/top-decile, search first/next, profile no-filter/top1/filtered TOP_N 50K, scoring status, scoring detail.

Create `docs/evidence/phase6_final_analytics_optimization_baseline.json` without PII, person/customer IDs, raw SQL, absolute paths, or tracebacks.

## Reconfirm fine-comb findings

Verify whether these remain:

1. Options repeats full-universe numeric/categorical scans.
2. Profile recomputes static universe every request.
3. Profile reconstructs static historical positives every request.
4. Profile materializes universe/matching/selected and expands 11 dimensions.
5. `Unknown/Other` semantics differ between profile/options/filter predicates.
6. Arbitrary categorical strings are accepted without current-vocabulary validation.
7. Save Audience runs estimate and profile separately.
8. Frontend blocks filter completion on profile and auto-runs profile during bootstrap.
9. Ordinary scoring status/detail still use deep score/prospect scans.
10. Lightweight currentness does not enforce every persisted model-governance field.
11. WAL mode is requested on every connection; measure only.
12. Physical demographic CHECKs are broader than app contract; accepted POC residue unless a new measured blocker appears.
13. Root README rewrite remains deferred.
14. No Phase 7 implementation exists.

## Repository residue scan

Search TODO/FIXME/HACK/temporary/debug/print/console.log/traceback/local drive paths/phase7/campaign builder/export/activation and classify each as runtime issue, test-only, historical documentation, acceptable residue, or must-fix.

Update `14_PROGRESS_TRACKER.md`. No runtime code changes in Step 1.
