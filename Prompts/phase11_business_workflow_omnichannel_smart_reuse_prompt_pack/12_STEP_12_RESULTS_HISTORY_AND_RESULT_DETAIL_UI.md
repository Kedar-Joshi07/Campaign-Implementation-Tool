# Step 12 — Results History & Result Detail UI

## Objective
Make every search discoverable, understandable and downloadable.

Results screen:
- newest first
- pagination/keyset or bounded paging
- all statuses visible: PROCESSING/COMPLETED/BLOCKED/FAILED
- auto-refresh only for active runs, bounded interval
- no duplicate card insertion

Each result card:
- business search/run identifier
- Campaign Name
- created/completed time
- status
- selected Product(s)
- Campaign Type/Category/Offer summary
- Delivery Profile
- Match Strength
- targeting summary
- Potential Customer count
- Result Source:
  “Reused previous exact result”
  “Reused existing targeting intelligence”
  “Prepared new targeting intelligence”
- processing duration
- View Result
- Download Potential Customers when eligible

Result Detail:
- exact saved Campaign Context
- exact targeting criteria
- exact selection mode/count
- result-source explanation
- currentness
- score/demographic summary
- snapshot provenance
- download profile
- optional technical details disclosure
- no contact PII

A repeated identical search must appear as a separate history row even if it references the same snapshot.

Processing survives page refresh because status comes from DB/Phase10 durable state.

Evidence:
`docs/evidence/phase11/12_RESULTS_UI.md`

STOP.
