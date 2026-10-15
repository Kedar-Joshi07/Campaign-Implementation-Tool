# Next actions and native-browser functionality prompt pack

Prepared 2026-10-12 against `9bea771940f930504ee8635c7b14fc988a37568c`. This ZIP contains prompts, contracts and inventory seeds. It does not implement the next changes or claim that the new browser certification has run.

The earlier audit independently reproduced the repaired buyer splits, passed 97 focused tests and 20 exhaustive small solver-oracle cases, and verified five-job CI at this merge SHA. Prompt 15.1 is GO; Prompt 16.2 records full-5M GO on named hardware; Prompt 17 records 20/20 local demo GO. These are baseline facts, not the output of this new pack.

What remains: an explicit independent fresh v3 validation path; exhaustive current UI/background coverage; precise scoped release decisions; current documentation; exact-candidate CI/manual evidence; readable governance evidence; and truthful treatment of unsupported predictive/learning claims.

## Run sequence

1. Run `19_0_CURRENT_BASELINE_AND_PENDING_RECONCILIATION.md`.
2. Run `19_1_FRESH_V3_VALIDATION_AND_RELEASE_SCOPE.md`.
3. Run `19_2_BOUNDED_QA_FIXTURES_AND_NO_5M_GUARD.md`.
4. Run **`19_3_NATIVE_BROWSER_ALL_UI_AND_BACKGROUND_E2E_NO_5M.md`**. This is the comprehensive native browser prompt requested by the user.
5. Run `19_4_UI_DEFECT_REPAIR_AND_RETEST.md` only for genuine findings; resume/rerun affected browser checks until coverage closes.
6. Run `19_5_BACKGROUND_INTEGRITY_EXPORT_FEEDBACK_AND_REGRESSION.md`.
7. Run `19_6_DOCUMENTATION_GOVERNANCE_AND_OPERATOR_HANDOFF.md`.
8. Run `19_7_EXACT_CANDIDATE_CI_AND_SCOPED_FINAL_GATE.md` when authorized remote actions are available; otherwise finish local gates and record remote pending.
9. Run `20_POC_REHEARSAL_AND_MAINTENANCE_RUNBOOK.md` using the completed functional test evidence and existing certified intelligence.

`MASTER_EXECUTION_PROMPT.md` controls this sequence. Do not run two controllers against one checkout/DB. Stages 19_1 and 19_2 may be developed in isolation after 19_0, but integrate sequentially before 19_3. No agent delegation is required.

Two **optional, non-default** prompts cover real outcome validation/true learning and future canonical 5M recertification. They are not prerequisites for UI functionality and are never silently started by the master.

## Browser scope in plain language

Use installed Chrome or Edge, headed on the user's local desktop. Click/type/select through real UI controls. Correlate each action to its real API, worker/state changes, SQLite records and output files. Test failure, retry, restart, currentness, exports, feedback, modes, accessibility and responsive behavior.

There are 11 view containers in the pinned HTML and 211 static interactive/container seeds in this pack. This is not a final control count: many widgets are dynamically generated, and forms/details are containers. Runtime discovery must add controls and states. Three main business tabs plus result detail are public business surfaces. Seven analyst/admin views remain intentionally hidden; test their hidden-route behavior and their retained controls separately through a labeled test-only harness, without adding them to production navigation.

Use a default 2,000-prospect synthetic QA fixture. A separate genuine bounded fixture may use up to 20,000 prospects to exercise the unchanged 10K demo qualification branch. Neither is the canonical 5M population. Bounded scoring is allowed only when needed to exercise a real scoring/prepare control; five-million-row scoring is excluded and must be prevented by the guard.

## Important release distinction

An independent v3 bounded fresh-workflow GO does not erase the existing legacy probability full-fresh NO-GO or independently validated predictive limitations. Keep the legacy workflow and evidence. Produce a concrete scope decision record for a local v3 POC; do not redefine an all-capability release approval silently.

First prompt: `19_0_CURRENT_BASELINE_AND_PENDING_RECONCILIATION.md`.
