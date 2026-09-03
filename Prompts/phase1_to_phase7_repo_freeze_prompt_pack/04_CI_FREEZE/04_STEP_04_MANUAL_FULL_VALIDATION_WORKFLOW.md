# Step 4 — Manual Full Validation Workflow

Create `.github/workflows/full-validation.yml` triggered by workflow_dispatch.

It may pull LFS and run heavier validation. Design it to invoke the real full-fresh runner created in Workstream 5 once available; do not invent unavailable commands.

Avoid uploading large synthetic-contact datasets, runtime DBs or huge exports as CI artifacts. Retain only useful small reports/failure evidence. STOP.
