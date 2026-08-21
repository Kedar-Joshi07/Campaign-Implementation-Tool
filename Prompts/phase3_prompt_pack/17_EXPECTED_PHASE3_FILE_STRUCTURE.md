# Expected Phase 3 File/Module Shape

Exact names may vary slightly if the existing repository conventions justify it, but responsibilities should remain separated.

```text
app/
  database/
    schema.py                       # schema v3 migration
  ml/
    __init__.py
    feature_contract.py             # frozen raw feature contract/fingerprint
    preprocessing.py                # split + fitted ColumnTransformer
    pu_estimators.py                # Elkan-Noto, naive diagnostic, Bagging PU
    evaluation.py                   # PU-aware ranking/diagnostic metrics
    training.py                     # candidate training/orchestration
    artifact.py                     # atomic save/load/checksum
  repositories/
    model_training_repository.py    # analysis reconstruction + model_runs DB IO
  services/
    model_training_service.py       # governed Phase 3 lifecycle

scripts/
  train_pu_model.py                 # Phase 3 execution surface
  inspect_model_run.py              # optional read-only CLI

artifacts/
  models/                           # runtime only; ignored

tests/
  test_model_schema.py
  test_training_cohort.py
  test_feature_contract.py
  test_preprocessing.py
  test_pu_training.py
  test_model_evaluation.py
  test_model_artifact.py
  test_model_training_cli.py
  test_phase3_hardening.py

docs/
  PHASE_3_IMPLEMENTATION_SUMMARY.md
```

Do not add routers/UI simply to make Phase 3 look more complete. Phase 4 is the correct place for model-training API/job/UI orchestration.
