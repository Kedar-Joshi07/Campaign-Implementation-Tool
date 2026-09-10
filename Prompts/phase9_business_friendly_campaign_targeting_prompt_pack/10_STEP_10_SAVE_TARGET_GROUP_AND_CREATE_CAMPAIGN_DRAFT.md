# Step 10 — Save Target Group & Create Campaign Draft

## Objective
Complete the business workflow while preserving the existing immutable Saved Audience and Campaign contracts.

## Save Target Group
Business action:
`Save Target Group`

Under the hood:
- normalize Phase 9 criteria
- convert to supported Audience Filter Contract
- persist immutable Saved Audience
- preserve scoring/model/analysis/source provenance
- preserve resolved count
- preserve filter hash
- store Phase 9 contract/context references

The UI should show “Saved Target Group”, while the internal Phase 6 table/service may remain `saved_audiences`.

## Naming
Default suggested name may derive from campaign name, but user can edit.

## Create Campaign Draft
After successful target-group save:
- create Campaign draft using the saved audience
- preserve campaign name/description/channel/planned launch date
- persist Phase 9 campaign context linkage
- do not finalize automatically

## Review
Show a business-readable summary:

Campaign:
- name
- products
- type/category
- offer
- channel
- launch date

Targeting:
- match strength
- age
- gender
- location
- income
- advanced filters

Target group:
- selected count
- targeting source status
- current/up-to-date status

## PII
No PII during planning/review/save.
Existing Phase 7 PII acknowledgement/export rules remain unchanged.

## Reopen
A saved Phase 9 campaign draft should reopen with:
- business context
- targeting criteria
- saved target-group summary
- currentness status

Do not mutate an immutable Saved Audience when editing campaign criteria.
Create a new Saved Target Group if criteria change after save.

## Tests
Test:
- create
- reopen
- edit-before-save
- criteria change after save
- new saved target group created
- campaign linkage correct
- stale source handling

Create:
`docs/evidence/phase9/10_SAVE_TARGET_GROUP_CAMPAIGN_REPORT.md`

STOP.
