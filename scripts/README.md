# Scripts Guide

This folder is split into operational scripts and archived historical helpers.

## Operational scripts (current)

Core runtime and data operations:

- init_db.py
  - Initialize or migrate SQLite schema; optional inspection output.
- import_customers.py
  - Import customer source data.
- import_campaign_sales.py
  - Import campaign-sales source data.
- import_demographics.py
  - Import one or multiple demographic source files.
- validate_data.py
  - Reconcile loaded data and verify required indexes.
- train_pu_model.py
  - Train and persist one governed PU model from a completed historical analysis.

## Validation automation (current)

- validation/phase6/
  - Phase 6 performance and 5M validation helpers.
- validation/phase7/
  - Phase 7 export and 5M hardening validations.

These scripts produce evidence JSON artifacts in docs/evidence.

## Archived scripts (historical)

- archive/phase5/
  - Historical one-off correction/re-run helpers used during Phase 5 stabilization.

Archived scripts are retained for traceability and should not be used for current operational workflows unless reproducing historical evidence.

## General usage expectations

- Run from repository root.
- Prefer explicit virtual environment python executable.
- Treat archive scripts as read-mostly historical assets.
