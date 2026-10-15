# 19.0 initial control-to-effect map

This is a routing inventory, not an exhaustive PASS matrix. `19_0_STATIC_CONTROL_INVENTORY.json` is selector-based (197 controls); the pack seed is broad markup/container-based (211). Runtime controls and exact states are to be enumerated in 19.3.

| Surface | Main controller / route | Service or durable effect | Certification boundary |
|---|---|---|---|
| Home / overview | `frontend/js/overview.js`, business overview APIs | recent runs/currentness projections | Real app, synthetic DB |
| Find Potential Customers | `business-search-form.js`, `/api/potential-customer-search/options`, `/preflight`, `/runs` | catalog, exact preflight, durable search/attempt, Phase 11 coordinator → Phase 10/v3 worker | Guard source and row caps before create |
| Search progress/history/detail | `business-search-status.js`, run/history/detail/retry routes | polling, attempt fencing, immutable snapshot, failure/retry | Real background worker; not controlled inline executor |
| Result download/feedback | `business-search-status.js`, result download and feedback/template routes | contactability-gated export, feedback records/recalibration trigger | Synthetic contacts, bounded worker, file audit |
| Seven retained views | `view-contract.js` hides tabs; `campaigns.js`, `historical-analysis.js`, `model-training.js`, `audience-explorer.js`, `data-status.js`, `saved-target-groups.js`, `insights.js` remain | Model train/score, audience preparation, targeting intelligence, campaign drafts and data status reachable through supported harness | Retained functionality ≠ business navigation or auth |
| Global/sidebar | `app.js`, sidebar, multi-select dropdown | route selection, responsive layout, form interaction | Headed native Chrome, keyboard/pointer/state matrix |

Direct/indirect heavyweight entry points: v3 search create/retry; legacy v1/v2 create/retry; explicit model train and score; audience run prepare; context targeting-intelligence prepare; feedback ingestion plus recalibration worker; startup recovery/rejoin; import invalidation. Preflight may scan membership/demographics but is not scoring. 19.2 must guard all compute paths and reject canonical/operator sources, not only the primary button. `app.main` lifespan is the required primary worker owner. The old Phase 11 step-19 controlled executor may supply only setup/browser helpers, never primary worker-success proof.
