# UI Step 3 — Form Contract & Currentness Cleanup

Align Audience Explorer HTML controls with frozen backend contracts:
- age_min/max: min=18, max=100
- family_member_count_min/max: min=1
- score: 0..1
- top percentile: 1..100
- TOP_N: min=1

Campaign Builder currentness must clearly show:
- Saved audience current
- Scoring current
- Historical source current
- Demographic source current
- Model/artifact verified
- Rank prepared
- Analytics prepared
- Ready for finalize/export

Regression-check earlier UI fixes:
- Historical analyses CURRENT/STALE
- stale analyses not trainable
- Lift/Recall labeled Top X%
- score not described as purchase probability
- no full filesystem paths in ordinary UI
- Last import attempt vs current published source

Use exact IDs/counts throughout. STOP after tests.
