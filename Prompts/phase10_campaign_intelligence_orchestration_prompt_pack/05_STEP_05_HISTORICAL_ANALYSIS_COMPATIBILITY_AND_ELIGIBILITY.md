# Step 5 — Historical Compatibility & Training Eligibility

Map Phase 10 Modeling Context into exact Historical Analysis filters:
- product_ids
- campaign_types
- campaign_categories
- offer_types
- historical_campaign_channels -> campaign_channels
- full canonical contact date range
- contacted_only=true
- ATTRIBUTED_PURCHASE

Do NOT map delivery channel.

Reusable Historical Analysis requires:
COMPLETED + exact normalized filters + exact current customer import/checksum +
exact current campaign-sales import/checksum + internally reconciled counts/currentness.
No subset/superset compatibility in v1.

Discover exact-compatible pre-Phase10 analyses by normalizing their stored filters.

## Freeze training eligibility policy v1
Inspect existing training constraints and run deterministic diagnostics on representative
canonical contexts (narrow single-product, multi-product, broad, restrictive category/offer).
Choose and document exact selected/P/U and split-viability thresholds based on evidence,
not intuition. Freeze as versioned constants and boundary tests.

Ineligible:
status BLOCKED; no model/scoring; no silent broadening.
Business message:
“There is not enough verified past campaign history for this combination yet.”

If no reusable analysis exists, create one through existing governed service and persist ID.

Tests: exact reuse, source drift, one filter mismatch, delivery channel no effect,
prospect target no effect, zero history, P/U threshold boundaries, old analysis discovery.

Evidence:
`docs/evidence/phase10/05_HISTORICAL_COMPATIBILITY_AND_ELIGIBILITY.md`

STOP.
