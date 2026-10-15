# Incomplete, pending and next-action register

Baseline `9bea771940f930504ee8635c7b14fc988a37568c` was audited earlier in this conversation. Re-read actual current code/evidence before applying this register; a newer commit may supersede it.

| ID | Item | Baseline status | Required next action | Owner |
|---|---|---|---|---|
| P01 | PRD001 158/42 split | resolved: 160/40 under split V2 | preserve; regression only | 19_0/19_5 |
| P02 | Prompt 15/16 scale recovery | GO in recorded scopes | preserve prior evidence; don't repeat 5M for UI | 19_0 |
| P03 | current merge CI | all five jobs green; run 38217341713 | new exact-candidate verification after changes | 19_7 |
| P04 | legacy manual full-fresh probability gate | failed at independent campaign-group training | retain block and strict split; separate v3 workflow | 19_1 |
| P05 | standalone fresh v3 gate | not separately certified by failing legacy full-fresh gate | bounded new DB/import/train/score/search/export | 19_1 |
| P06 | exhaustive native UI/background certification at current v3 | broader than earlier business UI screenshots | inventory and execute every implemented control/state | 19_2/19_3 |
| P07 | old browser proof's controlled executor | insufficient alone for real worker proof | primary QA uses actual app lifespan/coordinator | 19_2/19_3 |
| P08 | seven retained analyst/admin views | intentionally hidden, not absent functionality | verify hidden business routes; separate retained UI harness | 19_3 |
| P09 | accidental 5M work from UI/feedback/prepare | must be excluded by user instruction | fail-closed bounded worker/source guard | 19_2 |
| P10 | missing/unknown new UI defects | not asserted as existing bugs | discover/reproduce/fix with exact before/after proof | 19_4 |
| P11 | source invalidation / cache / restart / retry across modes | tested before; preserve and expand to browser traces | real currentness/fencing/rollback proof | 19_5 |
| P12 | downloads/contactability/CSV guards and v3 feedback boundaries | implemented; needs exhaustive control coverage | profile matrix + content/DB audit | 19_3/19_5 |
| P13 | current SHA/PR/branch-protection documentation | historical draft/unprotected references stale | additive current-authority update | 19_6 |
| P14 | protection details | main protected=true observed; detailed endpoint 403 | authenticated read/admin confirmation if available | 19_6/19_7 |
| P15 | local exact dependency pin mismatch | prior host differed from lock | clean isolated pinned venv, record actual versions | 19_0/19_7 |
| P16 | predictive response/lift/product specificity | unvalidated; weak descriptive specificity observed | no claims; prospective evidence plan | 19_6/optional |
| P17 | automatic true profile/feature retraining | not implemented; calibration != retraining | honest boundary; separately versioned future design | optional |
| P18 | production/distributed/auth/activation scope | outside current local single-node POC | retain exclusions, no silent expansion | all |
| P19 | operational handoff/rehearsal | needs updated functional-test evidence | small-data rehearsal and ready-intelligence reuse | 20 |

## Verified recovery counts

PRD001 200 total: old 158 fit/42 holdout → new 160/40.
PRD003 251: old 206/45 → new 201/50.
PRD004 1461: old 1164/297 → new 1169/292.
The union has 1,892 buyers; the new partition changed 11 assignments and is versioned `SIMILARITY_CUSTOMER_SPLIT_V2`. These figures were independently reproduced from the pinned canonical source files during the earlier audit.

## Recorded evidence anchors

- `docs/evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md`
- `docs/evidence/lookalike_v3/16_2_FULL5M_MEASUREMENTS.md`
- `docs/evidence/lookalike_v3/17_SCENARIOS.md` and JSON/checkpoint
- `docs/evidence/lookalike_v3/19_FINAL_RELEASE_GATE.md` and JSON
- `docs/evidence/lookalike_v3/08_MODEL_FACTSHEET.md`

Manual run 38198876255 on executable ec0c289… passed 1,308 baseline tests and source/import gates, then rejected insufficient independent campaign-connected groups. The merge changed prompt/evidence/manifest-test files relative to that executable; its new CI is green, not a new successful manual probability run.

## Current UI/source anchors

`frontend/index.html`, `frontend/js/view-contract.js`, `frontend/js/app.js`, business-search-form/status, historical-analysis, model-training, audience-explorer, data-status, saved-target-groups, campaigns, sidebar, and multi-select-dropdown modules. Backend routers live under `app/routers/`; service and job implementations own actual effects.

Existing helpers: `scripts/validation/browser/system_browser.py`, build_ui_control_inventory.py, check_ui_control_coverage.py and run_phase11_step19_certification.py. The old phase11_step19_server uses a controlled executor; inspect it before deciding which pieces are reusable. A previous fixture browser pass is not comprehensive native QA evidence for all current workers.
