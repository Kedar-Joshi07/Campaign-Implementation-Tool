# Phase 11 Business UI and Navigation

Normal navigation is exactly:

1. **Home** — bounded business KPIs, recent searches, and primary actions.
2. **Find Potential Customers** — one validated business form with searchable accessible multi-select controls.
3. **Results** — durable newest-first history and active-only bounded polling.

Result Detail is a child route under Results. It reopens exact context, criteria, branches, selection, counts, currentness, aggregate profile, result-source explanation, and optional collapsed technical lineage. It never renders contact PII or artifact paths.

Smart reuse and automatic Phase 10 preparation run behind the submitted search. They are status/progress behavior, not additional navigation destinations. Runtime ownership and restart behavior are documented in `PHASE_11_RUNTIME_ARCHITECTURE.md`.

`frontend/js/view-contract.js` owns route groups and canonical aliases. Empty/unknown/hidden routes redirect to Home; `#overview` maps to Home and `#campaign-planner` maps to Find Potential Customers without adding redirect history. Legacy views and modules remain in source and DOM behind hidden boundaries for backward compatibility.

The group labels `BUSINESS_USER_VISIBLE`, `ANALYST_HIDDEN`, and `ADMIN_HIDDEN` are presentation metadata and a future RBAC seam only. Phase 11 does not implement authentication, authorization, tenant isolation, or API enforcement based on these labels.

The reusable multi-select supports text search, filtered Select All, global Clear All, chips, mouse and keyboard operation, Escape/outside close, focus restoration, loading/disabled/error/empty states, and native form validity. Backend option values and Region-to-State expansion remain authoritative.

Installed-Chrome certification covered the entire Home → Find Potential Customers → progress → Results → Result Detail → Download flow, exact/intelligence/delivery reuse, all ten downloads, 549 dynamic control/state observations, zero reachable NOT_RUN outcomes, five responsive viewports down to 390×844, visible labels/live status, and zero console/page/request/critical HTTP errors.
