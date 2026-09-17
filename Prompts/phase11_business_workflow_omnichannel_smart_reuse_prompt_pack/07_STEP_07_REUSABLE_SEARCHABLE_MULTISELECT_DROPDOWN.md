# Step 7 — Reusable Searchable Multi-Select Dropdown

## Objective
Replace large checkbox blocks with one reusable accessible Vanilla-JS component.

Create focused module, e.g.:
`frontend/js/components/multi-select-dropdown.js`

Required behavior:
- label
- collapsed selected-count summary
- dropdown panel
- search/filter
- checkbox multi-select
- Select All visible/filtered behavior clearly defined
- Clear All
- selected chips or compact selection summary
- remove individual selection
- keyboard navigation
- Space/Enter toggle
- Escape close
- click-outside close
- focus restoration
- disabled/loading/error states
- ARIA roles/labels
- no color-only state

Backend values remain authoritative; component accepts options, never hardcodes business lists.

Use component for:
- Products
- Campaign Types
- Campaign Categories
- Offer Types
- Historical Campaign Channels
- Gender
- Age Groups
- State
- Region if retained
- Income Groups
- Marital Status
- Education
- Employment Status
- Resident Status
- Resident Type
- Type of Employment

Family size / Match Strength / Top% / TOP_N may use compact appropriate controls, not forced multi-select.

Performance:
test with realistic Products and State option counts and ensure no laggy re-render loops.

Evidence:
`docs/evidence/phase11/07_MULTISELECT_COMPONENT.md`

STOP.
