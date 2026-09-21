# Runtime Closure Test Matrix

Unit:
- coordinator init/submit/dedup/cleanup/shutdown;
- submit after shutdown;
- safe exception handling.

Real lifespan integration:
- no monkeypatch of PHASE11_SEARCH_EXECUTOR;
- options reports workflow_available=true;
- POST transitions QUEUED/PROCESSING/COMPLETED;
- shutdown closes coordinator.

Restart:
- app A leaves QUEUED/PROCESSING;
- app B same DB resumes;
- no duplicate snapshot/heavy orchestration.

Reuse:
- initial run;
- exact repeat;
- targeting-filter change;
- delivery-profile change;
- Modeling Context change.

Failure:
- Phase10 BLOCKED/FAILED;
- materializer error;
- snapshot validation failure;
- coordinator exception;
- export abort/retry.

Browser:
all visible Phase11 flows through real uvicorn.
