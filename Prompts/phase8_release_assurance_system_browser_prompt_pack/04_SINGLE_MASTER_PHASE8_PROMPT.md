# Single Master Phase 8 Prompt

Execute Steps 1–12 in exact order.

Phase 8 adds NO new campaign-targeting functionality.

Goals:
- fix CI collection/dependency failure;
- make normal pytest/CI green;
- use installed system Chrome or Edge, never VS Code embedded browser;
- inventory every actionable control;
- replace generic EXCEPTION with PASS/FAIL/JUSTIFIED_EXCLUSIVE;
- submit Historical Analysis through browser;
- submit Model Training through browser;
- initiate and observe the real full 5M scoring run through browser;
- exercise every Audience Explorer control;
- exercise every Campaign Builder control;
- complete Email and Direct Mail browser downloads;
- eliminate unexplained browser errors;
- complete accessibility/responsive/state testing;
- make GZIP generation byte-deterministic where feasible;
- remove absolute machine paths from canonical summaries;
- refresh LFS/hash docs;
- certify from clean committed HEAD;
- get all required GitHub CI checks green;
- enable/document branch protection;
- freeze Phase 8.

Do not mark GO if any required CI check is red, full 5M scoring was backend-initiated instead of browser-initiated, reachable controls remain untested, unexplained browser errors remain, or final certification used dirty_override.
