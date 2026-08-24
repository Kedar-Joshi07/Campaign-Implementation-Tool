# Phase 5 Library and License Notes

No new dependency should be required. Use existing Python/sqlite3/pandas/NumPy/scikit-learn/joblib/pulearn/FastAPI/frontend stack.

Phase 5 is inference/orchestration/persistence around an existing artifact. Do not add a commercial or distributed-serving framework merely for chunked scoring.

Do not upgrade artifact-critical `pulearn`/scikit-learn dependencies during Phase 5 unless a verified compatibility defect requires it. First prove the accepted artifact still loads and scores under the existing tested environment.
