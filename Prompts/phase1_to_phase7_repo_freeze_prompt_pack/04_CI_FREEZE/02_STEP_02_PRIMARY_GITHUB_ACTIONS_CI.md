# Step 2 — Primary GitHub Actions CI

Create `.github/workflows/ci.yml` for pull_request and push to main.

Use least permissions, dependency caching and concurrency cancellation.

CI must not download/run the canonical 5M dataset.

Use stable checks such as:
- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract

CI must succeed from a clean checkout with no local DB/model/.env/browser cache. STOP.
