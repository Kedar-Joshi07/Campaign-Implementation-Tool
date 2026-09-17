# Step 8 — Find Potential Customers: Single Business Form

## Objective
Replace multi-screen technical feeling with one clean business-facing request form while retaining
all Phase 9/10 semantics underneath.

Sections:

### Campaign Details
- Campaign Name
- Description optional
- Planned Launch Date optional

### Campaign Context
- Products multi-select
- Campaign Types multi-select
- Campaign Categories multi-select
- Offer Types multi-select
- Historical Campaign Channels multi-select

### Targeting Preferences
- Match Strength
- Gender
- Age Groups
- State/Region
- Income Groups
- compact “More options” for advanced demographics
- Top Matching % optional
- ALL_MATCHING / TOP_N and target count

### Delivery / Download Profile
- Delivery channel/profile selector
- show AVAILABLE profiles only by default
- unavailable gated profiles may be shown disabled with reason
- explain that delivery choice does not retrain targeting intelligence

Primary action:
`Find Potential Customers`

Submission:
1. validate business form
2. persist/update context/criteria
3. create campaign_search_run
4. execute Phase11 smart reuse workflow
5. navigate to processing/result state
6. result remains discoverable from Results even if user navigates away

Preserve exact OR-within/AND-across targeting semantics.
Do not turn delivery profile into Modeling Context.

Evidence:
`docs/evidence/phase11/08_FIND_POTENTIAL_CUSTOMERS_FORM.md`

STOP.
