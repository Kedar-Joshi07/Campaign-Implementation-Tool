# Step 3 — Add Interoperability Regression Tests

Add explicit tests for:

## Legacy single-branch audience
- detail remains compatible
- reopen remains allowed
- filters/selection restore exactly

## Phase 9 single-branch Target Group
- Phase 9 metadata detected
- correct reopen behavior

## Phase 9 multi-branch Target Group
- branch count > 1
- branch SHA validates
- resolved count equals exact union
- Audience Explorer can never present branch #1 as the full definition

If full replay:
- assert all branches are represented faithfully

If safe block:
- assert reopen is blocked/redirected
- assert correct guidance exists
- assert no incomplete form population occurs

## Campaign/export exact-membership regression
For the same multi-branch group:
- resolve selected members
- assert exact expected IDs
- assert no duplicates
- assert count equals stored resolved count

## Additional protections
- previous Target Group immutable after criteria changes
- stale source blocks new save
- no contact PII in target-group/detail interoperability responses
- idempotent retry still works

Use explicit test names containing:
`phase9_multi_branch`
`legacy_audience_reopen`
`saved_target_group_interoperability`

Create:
`docs/evidence/phase9_closure/03_INTEROPERABILITY_TEST_REPORT.md`

STOP.
