# Step 12 — Comprehensive Phase 10 Test Matrix

A. Modeling Context identity:
ordering/dedup; delivery/details/target filters excluded; modeling dimensions/policies included.

B. Historical extension:
old JSON; category/offer/combined filters; options/defaults/replay; cohort reconstruction.

C. Multi-product:
A positive, B positive, neither U, both once, no score fusion.

D. Historical compatibility:
exact reuse; context/source/date/policy mismatch; failed/incomplete.

E. Eligibility:
exact threshold, one below, zero P/U, split viability, eligible.

F. Model:
exact reuse; wrong feature/role/evaluation/analysis; failed; missing/corrupt artifact;
challenger never selected; fresh model.

G. Scoring:
full reuse; demographic drift; incomplete count; duplicate/nonfinite/out-of-range;
artifact mismatch; failed run.

H. Rank:
100 boundaries; missing boundary; stale analytics; rank-only rebuild.

I. Orchestration:
READY reuse; rank-only; score+rank; model+score+rank; full build; BLOCKED; model/scoring failure;
retry highest valid stage.

J. Change matrix:
campaign name/description/date, delivery channel and target filters = no heavy work.
products/type/category/offer/historical-channel = new compatibility identity.

K. Concurrency/idempotency:
double click; simultaneous exact context; two delivery channels; refresh while running;
repeated retry; no duplicate active full scoring.

L. Restart recovery:
persist RUNNING and simulate startup/reconciliation.

M. Privacy:
recursively prohibit first/last/email/phone/address/street/city/postal in Phase10 APIs/UI.

N. Full Phase1–9 existing suite.

Evidence:
`docs/evidence/phase10/12_TEST_MATRIX.md`

STOP.
