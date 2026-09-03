# Step 1 — Dependency Lock & Test Classification

Create a reproducible dependency lock/constraints set from a clean environment containing only repository dependencies. Record exact Python/runtime/ML/generator/test/browser-tool versions.

Keep developer-friendly ranges if desired, but CI should install the accepted lock.

Introduce/register useful pytest markers such as unit, integration, cleanroom, full5m, browser and performance. Document which workflows run each marker. Run pip check. STOP.
