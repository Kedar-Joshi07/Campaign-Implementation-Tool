# Step 3 — Saved Audience Eligibility & Campaign Currentness

Saved audience eligible only if:
exists, current, resolved_count>0, scoring canonical/current, historical and demographic
provenance current, model/artifact/features supported, rank boundaries current,
analytics snapshot current, Filter/Rank/Selection contracts supported.

Stale saved audiences remain historical.

Implement `evaluate_campaign_currentness()` returning bounded:
campaign_id, status, is_current, ready_for_finalize, ready_for_export,
saved_audience_current, scoring_current, historical_source_verified,
demographic_source_verified, model_verified, rank_ready, analytics_ready, issues[].

Use lightweight checks for list/detail.

Finalize only current DRAFT with current eligible audience and valid channel/profile.
At finalize copy immutable audience definition/provenance metadata, not members.

FINALIZED immutable.
If it becomes stale later, export blocked; no force override.

Comprehensive drift tests. STOP.
