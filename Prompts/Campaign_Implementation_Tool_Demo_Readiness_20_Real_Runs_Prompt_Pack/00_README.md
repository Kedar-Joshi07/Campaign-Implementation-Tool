# Campaign Implementation Tool — Demo Readiness & 20 Real-Run Preload Prompt Pack

Canonical repository: `Kedar-Joshi07/Campaign-Implementation-Tool`

Required starting SHA: `f2b98adfcf1a01f23f1c201aa2cf5a2df1521a2d`

This pack has three goals:

1. Audit the entire current repository and canonical runtime before demo preload.
2. Create **20 real Phase 11 production-path potential-customer searches** against the canonical data so completed results are available in the normal Results UI during the POC demo.
3. Perform bounded housekeeping and documentation/current-baseline cleanup without destabilizing the demo.

These are **not tests, fixtures, temporary-DB runs, TestClient runs, synthetic mini-runs, or benchmark-only runs**. They must be durable real application search runs in the canonical POC database, using the same APIs/services and result registry the business UI uses.

Run the steps in numeric order. Do not skip a failed gate. Do not silently alter a scenario to make it pass.
