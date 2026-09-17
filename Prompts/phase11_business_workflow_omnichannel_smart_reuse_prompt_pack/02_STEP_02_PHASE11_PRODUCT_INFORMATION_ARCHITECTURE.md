# Step 2 — Phase 11 Product Information Architecture

## Objective
Freeze the normal-user product flow before backend changes.

Visible top navigation only:
1. Home
2. Find Potential Customers
3. Results

Remove/hide normal navigation links and business-route entry points for:
- Data Status
- Historical Analysis
- Model Training & Prospect Scoring
- Audience Explorer
- legacy Campaigns
- analyst Insights
- technical saved-audience views

Do NOT delete code, APIs, tests or analyst functionality.

Add a centralized view-group contract such as:
BUSINESS_USER_VISIBLE
ANALYST_HIDDEN
ADMIN_HIDDEN
so a future RBAC phase can map roles cleanly.

Define business routes/states:
HOME
FIND_POTENTIAL_CUSTOMERS
RESULTS
RESULT_DETAIL

Direct old-fragment/navigation behavior:
- existing bookmarked analyst route may remain technically addressable in POC OR redirect to Home;
- whichever is chosen, document that UI hiding is not authorization.

Freeze copy:
- “Potential Customers”, not “prospects” in default UI;
- “Find Potential Customers” primary action;
- “Results” for run history;
- “Targeting intelligence” only in progress/help, not ML jargon.

Create wireflow and DOM/control inventory.

Evidence:
`docs/evidence/phase11/02_PRODUCT_INFORMATION_ARCHITECTURE.md`

STOP.
