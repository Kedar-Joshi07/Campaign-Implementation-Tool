# Single Master Prompt — Phase 11

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Frozen Phase10 baseline: `881b5a652e869af1415547de452b9cccd2c18293`

Execute Steps 1–21 sequentially. Obey every STOP/gate.

Mission:
Create a simple business product with only Home, Find Potential Customers and Results visible,
while preserving the full Phase1–10 analytical engine underneath for future role-based analyst/admin access.

Implement:
- searchable checkbox multi-select dropdowns;
- one clean Find Potential Customers form;
- immutable search-run history;
- immutable no-PII analytical result snapshots;
- EXACT_RESULT_REUSE above Phase10 INTELLIGENCE_REUSE;
- NEW_INTELLIGENCE_BUILD only when exact compatibility requires it;
- NO all-permutation precomputation;
- optional atomic segment optimization only after benchmarks;
- Email, Direct Mail, SMS, WhatsApp, Telemarketing, Paid Social, Paid Search;
- Push, Display, Website/On-site only after deterministic governed identifiers/contactability exist;
- profile-specific allowlists and consent/contactability;
- hashed paid-media identifiers;
- result downloads with checksums/audit/currentness;
- future feedback/retraining lineage without claiming RL exists.

Critical proofs:
1. identical request creates new search history but reuses same snapshot;
2. demographic-filter change does not train/rescore;
3. delivery-profile change does not train/rescore;
4. new incompatible Modeling Context can still trigger correct Phase10 full 5M scoring;
5. contact PII never persists in result membership snapshots;
6. paid-media downloads never expose raw identifiers;
7. legacy analyst UI is hidden, not deleted.

Require bounded clean-room, installed Chrome/Edge, clean-head full 5M certification,
Phase1–10 regression, exact-SHA CI and final freeze.
