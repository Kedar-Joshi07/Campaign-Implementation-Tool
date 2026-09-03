# Master Guardrails

Correctness, data integrity, business logic, reproducibility, provenance, and analytical usefulness take priority over arbitrary processing-time targets.

Never introduce sampling, approximation, truncation, semantic changes, reduced data coverage, weaker validation, or altered business results merely to improve speed.

Interactive lightweight operations should remain responsive. Exact heavy work may take 60 seconds, 120–180 seconds, or longer where justified. Improve architecture and progress visibility before compromising data/process/logic quality.

Optimize unnecessary work, not necessary work.

Additional hard rules:
- never discard uncommitted user changes;
- never delete `.git`;
- never fake run IDs/models/scores/audiences/campaigns;
- do not use direct DB/service writes to substitute for UI actions in final browser E2E;
- backend reads may be used as independent assertions;
- do not reuse prior DB/model/scoring/audience/campaign state in the full fresh run;
- no post-hoc source repair;
- no sampling of the 5M scoring run;
- no permanent 5M member table;
- no persistent server-side PII export artifact;
- unexplained fresh-data hash drift = NO-GO;
- untested reachable UI control requires explicit justification;
- final GO requires evidence.
