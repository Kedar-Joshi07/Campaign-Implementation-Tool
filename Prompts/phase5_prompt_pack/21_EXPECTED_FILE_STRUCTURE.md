# Expected Phase 5 File/Module Shape

Recommended, adapted to existing conventions:

```text
app/jobs/prospect_scoring_worker.py
app/repositories/scoring_repository.py
app/services/model_scoring_compatibility.py
app/services/prospect_scoring_service.py
app/services/scoring_job_service.py
app/services/scoring_api_service.py
app/routers/scoring.py
app/schemas/scoring.py
frontend/js/prospect-scoring.js   # if separation helps

tests/test_phase5_schema.py
tests/test_scoring_repository.py
tests/test_scoring_compatibility.py
tests/test_prospect_scoring_service.py
tests/test_scoring_job_orchestration.py
tests/test_scoring_api.py
tests/test_scoring_frontend.py
tests/test_phase5_hardening.py

docs/PHASE_5_IMPLEMENTATION_SUMMARY.md
```

Existing executor/job/model modules may be extended backward-compatibly. Do not add Audience Explorer/audience/campaign/export modules in this phase.
