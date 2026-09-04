# CI Freeze Report

Generated on: 2026-09-04

## Scope

Workstream 4 CI freeze implemented for reproducible clean-checkout validation without mandatory 5M runtime on every PR.

## Step 1 - Dependency lock and test classification

- Added pinned lockfile: requirements.lock
- Preserved range-based developer requirements: requirements.txt
- Added pytest marker registration: pytest.ini
- Added automatic marker classification: tests/conftest.py

Registered markers:

- unit
- integration
- cleanroom
- full5m
- browser
- performance

Workflow marker usage:

- CI Tests job: not cleanroom and not full5m and not performance and not browser
- CI Clean-Room Phase1-7 job: dedicated clean-room runner command
- CI Frontend Contract job: browser or integration against frontend/api contract targets
- Full Validation (Manual): pytest not full5m by default, with optional full-fresh runner invocation when available

## Step 2 - Primary GitHub Actions CI

Added workflow: .github/workflows/ci.yml

Checks implemented:

- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract

Design controls:

- Triggers: pull_request and push to main
- Minimal permissions: contents: read
- Concurrency cancellation enabled
- Dependency caching enabled
- CI checkout does not pull LFS objects by default

## Step 3 - Hygiene, LFS and browser smoke gates

Added hygiene validator: scripts/validation/validate_ci_hygiene.py

Gate coverage:

- Reject tracked DB, WAL, SHM files
- Reject tracked cache and runtime debris paths
- Reject tracked .joblib model artifacts
- Validate LFS pointer configuration for data/*.gz without downloading large LFS payloads
- Compileall and diff check included in Python Validation job
- Frontend/API contracts covered by Frontend Contract job

Note: no dedicated Playwright/Selenium smoke suite exists in this repository today.

## Step 4 - Manual full validation workflow

Added workflow: .github/workflows/full-validation.yml

Behavior:

- Trigger: workflow_dispatch
- Checkout with LFS enabled
- Runs pip check, compileall, and pytest not full5m baseline
- Invokes scripts/validation/run_full_fresh_phase1_to_phase7.py only if present
- Uploads only compact evidence artifacts from docs/evidence/*.md and docs/evidence/*.json

## Step 5 - Branch protection and local gates

Added branch protection guide: docs/BRANCH_PROTECTION.md

Local gates executed:

- pytest: PASS (458 passed)
- clean-room phase1-7 runner: PASS
- compileall: PASS
- pip check: PASS
- git diff --check: PASS
- workflow syntax validation: PASS

## Required check names for branch protection

- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract
