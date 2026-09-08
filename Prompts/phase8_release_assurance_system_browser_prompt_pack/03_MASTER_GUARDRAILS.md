# Phase 8 Master Guardrails

## Quality
Correctness, data integrity, business logic, reproducibility, provenance, and analytical usefulness take priority over arbitrary processing-time targets. Never introduce sampling, approximation, truncation, semantic changes, reduced data coverage, weaker validation, or altered business results merely to improve speed. Exact heavy work may take 60 seconds, 120–180 seconds, or longer where justified. Optimize unnecessary work, not necessary work.

## Browser
All Phase 8 certification must use a real operating-system browser: Google Chrome preferred, Microsoft Edge fallback. Playwright may control the installed browser. Do not use VS Code Simple Browser, IDE webviews, mock DOMs, or Playwright-bundled Chromium as the primary certification browser when system Chrome/Edge exists. Evidence must record browser product/version and execution mode. If neither Chrome nor Edge is installed, browser certification is NO-GO.

Additional hard rules:
- no Phase 9/10 targeting functionality;
- do not change Feature Contract v1 or PU semantics;
- do not weaken currentness/provenance;
- do not use direct service/DB writes to substitute for a UI action under certification;
- backend reads are allowed only as independent assertions;
- generic EXCEPTION is forbidden for a reachable control;
- do not sample the 5M scoring run;
- do not fake job state;
- do not certify from a dirty worktree;
- unexplained source/hash drift is NO-GO;
- required CI red = NO-GO.
