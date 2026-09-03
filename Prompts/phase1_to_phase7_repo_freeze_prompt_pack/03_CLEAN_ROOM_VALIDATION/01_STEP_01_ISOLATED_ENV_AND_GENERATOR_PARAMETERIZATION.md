# Step 1 — Isolated Environment & Bounded Deterministic Data

Create isolated temp DB/artifact/data/output/log paths. Do not reuse canonical DB/model/scoring state.

Use bounded deterministic volumes, approximately 1K–5K historical customers, 5K–25K campaign observations, 10K–50K prospects. Reuse current generators by adding opt-in row-count parameters if needed; production defaults stay unchanged.

Record seeds/Python/dependency versions/content hashes. Generate twice and verify determinism where expected. STOP.
