# Step 1 — Phase 7 Scope, Baseline & Contract Freeze

Run full gates from Section 1 SHA.
Revalidate Phase 6 canonical chain and 5M score/rank/analytics state.

Add:
`CAMPAIGN_CONTRACT_VERSION = "1"`
`CAMPAIGN_EXPORT_CONTRACT_VERSION = "1"`
`CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION = "1"`

Persist campaign states only:
DRAFT, FINALIZED

No ACTIVE/SENT/LAUNCHED.

Channels v1:
EMAIL, DIRECT_MAIL

Profiles:
EMAIL_CONTACT_V1, DIRECT_MAIL_CONTACT_V1

No activation, external platform, member table, customer/person linkage, approximate
counts, arbitrary PII picker.

Create `docs/evidence/phase7_baseline_and_contracts.json`. STOP.
