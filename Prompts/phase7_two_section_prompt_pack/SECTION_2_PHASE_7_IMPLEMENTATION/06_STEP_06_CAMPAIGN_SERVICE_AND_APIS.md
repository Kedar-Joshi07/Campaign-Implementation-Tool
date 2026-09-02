# Step 6 — Campaign Services & APIs

Implement:

GET  /api/campaigns/options
POST /api/campaigns
GET  /api/campaigns?limit=&offset=
GET  /api/campaigns/{id}
PATCH /api/campaigns/{id}          # DRAFT only
GET  /api/campaigns/{id}/currentness
POST /api/campaigns/{id}/finalize
GET  /api/campaigns/{id}/exports
GET  /api/campaigns/{id}/export.csv

Export requires:
FINALIZED, current, acknowledge_pii=true, channel-derived profile.

Campaign list/detail contain no raw contact PII.

DRAFT fields:
name, description, channel, planned date, saved audience.

FINALIZED immutable.

Validation:
bounded nonblank name, bounded description, ISO date, exact channel,
current eligible saved audience, supported contracts.

Safe 404/409/422/503 mapping.
No raw SQL/paths/tracebacks. STOP.
