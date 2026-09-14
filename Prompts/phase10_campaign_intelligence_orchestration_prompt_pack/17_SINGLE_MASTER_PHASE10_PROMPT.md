# Single Master Prompt — Phase 10

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Frozen Phase 9 baseline: `7e54754053bf998e65c59a36c0096d5404bb6479`

Execute Steps 1–16 sequentially and obey every STOP gate.

Mission:
make Campaign Planner automatically resolve/reuse/build/verify the correct targeting intelligence
without requiring business users to understand Historical Analysis, PU/ML, model runs,
scoring runs or artifacts.

Mandatory:
- separate full Campaign Context from exact Modeling Context
- Modeling Context uses products, campaign types/categories, offers, historical channels and governed policies
- delivery channel/campaign details/prospect filters excluded
- never latest-run fallback
- exact compatibility analysis→model→scoring→rank
- reuse most advanced valid stage
- missing path builds Historical Analysis→eligibility→governed PRIMARY→full 5M scoring→rank
- multi-product = one combined context/model; positive if ANY selected product converts
- no score fusion
- persistent idempotent orchestration
- no nested single-worker executor deadlock
- business-language UI with progressive technical disclosure
- no PII before governed export
- non-destructive lifecycle classification
- bounded clean-room, real Chrome/Edge, one clean-head full 5M UI-initiated certification
- exact-SHA CI and final freeze

Never weaken correctness for runtime.
