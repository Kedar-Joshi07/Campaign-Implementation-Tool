# Step 12 — Branch Governance & Release Readiness

Check current GitHub branch protection.

If authorized and supported, configure `main` protection according to repository policy:
- pull request required;
- at least one approval if appropriate;
- required CI checks;
- branch must be up to date;
- prevent direct bypass where appropriate.

If the automation/user lacks GitHub administration permission:
- do not pretend protection is enabled;
- keep/update exact documented settings;
- record current `protected=false`;
- mark this as repository-governance follow-up, not a runtime correctness blocker.

Also verify:
- no runtime DB/artifacts accidentally staged;
- LFS files correct;
- result snapshots/evidence placement respects repo hygiene;
- no secrets or private identifiers.

Create:
`docs/evidence/phase11_runtime_closure/12_RELEASE_GOVERNANCE.md`

STOP.
