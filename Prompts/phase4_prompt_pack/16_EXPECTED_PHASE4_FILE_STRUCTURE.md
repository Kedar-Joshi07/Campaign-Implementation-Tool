# Expected Phase 4 File/Module Shape

Adapt naming to repository conventions while preserving responsibilities.

```text
app/
  jobs/
    __init__.py
    executor.py
    model_training_worker.py
  repositories/
    job_repository.py
  services/
    model_job_service.py
    model_query_service.py
  routers/
    models.py
    jobs.py            # optional if cleanly combined
  schemas/
    models.py
    jobs.py

frontend/
  js/
    model-training.js
  css/
    ...

tests/
  test_phase4_schema.py
  test_job_repository.py
  test_model_job_service.py
  test_model_api.py
  test_model_training_ui.py
  test_phase4_hardening.py

docs/
  PHASE_4_IMPLEMENTATION_SUMMARY.md
```

Do not create scoring, propensity, audience, or campaign-builder modules in Phase 4.
