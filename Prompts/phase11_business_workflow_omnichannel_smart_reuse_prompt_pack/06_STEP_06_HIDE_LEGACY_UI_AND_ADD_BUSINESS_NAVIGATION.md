# Step 6 — Hide Legacy UI & Add Business Navigation

Implement the frozen Step 2 information architecture.

Normal visible navigation:
- Home
- Find Potential Customers
- Results

Hide old technical/analyst nav controls using centralized configuration/DOM rules.
Do not merely CSS-hide random individual elements without a maintainable contract.

Preserve all advanced components in source and regression tests.

Default startup opens Home.

Browser history/hash routing must support the three business views cleanly.

Add explicit tests that:
- analyst tabs are absent/hidden in normal business navigation;
- old APIs are untouched;
- old frontend modules still build/load under test harness where required;
- no security claim is made.

If old pages remain reachable by direct internal route, visibly label them hidden/advanced or redirect;
choose one consistent strategy and document it.

Evidence:
`docs/evidence/phase11/06_BUSINESS_NAVIGATION.md`

STOP.
