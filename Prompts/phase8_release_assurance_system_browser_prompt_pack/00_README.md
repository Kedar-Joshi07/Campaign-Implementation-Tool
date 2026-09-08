# Phase 8 — Release Assurance & System-Browser Certification

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Starting baseline: `47a93d0a44c4df8ab12ff58157fbc204ec43a51d`

Phase 8 adds no new campaign-targeting business functionality. It exists only to close the remaining release-certification gaps from Phase 1–7.

Goals:
- fix the red GitHub CI Tests job;
- prevent validation scripts from accidental pytest collection;
- create a reusable system Chrome/Edge harness;
- test every reachable control on every page through real browser interactions;
- submit Historical Analysis through the UI;
- submit Model Training through the UI;
- start and observe full 5M scoring through the UI;
- fully test Audience Explorer and Campaign Builder;
- validate browser Email/Direct Mail downloads;
- eliminate unexplained browser errors;
- make canonical GZIP output byte-deterministic where feasible;
- remove machine-specific paths from canonical summary files;
- refresh hashes/LFS documentation;
- rerun final certification from a clean committed HEAD;
- get all required CI checks green;
- prepare/enforce branch protection;
- freeze Phase 8.

## Quality-first rule
Correctness, data integrity, business logic, reproducibility, provenance, and analytical usefulness take priority over arbitrary processing-time targets. Never introduce sampling, approximation, truncation, semantic changes, reduced data coverage, weaker validation, or altered business results merely to improve speed. Exact heavy work may take 60 seconds, 120–180 seconds, or longer where justified. Optimize unnecessary work, not necessary work.

## System-browser rule
All Phase 8 certification must use a real operating-system browser: Google Chrome preferred, Microsoft Edge fallback. Playwright may control the installed browser. Do not use VS Code Simple Browser, IDE webviews, mock DOMs, or Playwright-bundled Chromium as the primary certification browser when system Chrome/Edge exists. Evidence must record browser product/version and execution mode. If neither Chrome nor Edge is installed, browser certification is NO-GO.

Run Steps 1–12 in order and obey every STOP gate.
