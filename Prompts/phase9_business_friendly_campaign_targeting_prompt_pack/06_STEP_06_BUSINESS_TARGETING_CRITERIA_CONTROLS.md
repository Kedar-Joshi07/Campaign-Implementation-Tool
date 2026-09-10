# Step 6 — Business Targeting Criteria Controls

## Objective
Let business users describe the people they want to reach without requiring technical knowledge of Audience Explorer.

## Primary criteria
Show first:

### Targeting Strength
Business labels:
- Very Strong Match — 0.90+
- Strong Match — 0.80+
- Good Match — 0.70+
- Broad Match — 0.60+

Default/recommendation must be explicit and configurable.

### Gender
Multi-select from current allowed values.

### Age Groups
Multi-select using backend-owned age buckets.

### Location
State multi-select.
Optionally provide coarse Region derived from State.

Do not introduce street/ZIP/city-level targeting in Phase 9.

### Income Groups
Multi-select using backend-owned income groups.

## More targeting options
Progressively disclose:
- marital status
- education
- employment status
- resident status
- resident type
- type of employment
- family size
- top matching %
- optional TOP_N / number of people to target

## Mapping
Convert business bucket selections into valid existing Audience Filter Contract semantics.

For disjoint multi-bucket selections, implement a normalized filter representation safely. Do not incorrectly collapse disjoint buckets into an overly broad min/max range.

## UI behavior
- selected chips/tags
- clear one
- clear all
- accessible multi-selects
- visible selected-count
- sensible defaults
- no hidden filters

## Validation
Backend validates all business targeting criteria.

Create:
`docs/evidence/phase9/06_TARGETING_CRITERIA_REPORT.md`

STOP.
