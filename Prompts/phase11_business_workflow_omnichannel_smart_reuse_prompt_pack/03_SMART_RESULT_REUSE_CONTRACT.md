# Smart Result Reuse Contract

## Layer 1 — EXACT_RESULT_REUSE
Canonical result-cache key includes:
- current compatible generation_id
- generation/currentness fingerprint
- targeting_criteria_sha256
- filter_branches_sha256
- selection_mode
- target_count where relevant
- result/selection/filter contract versions
- result-membership contract version

On exact hit:
- create a NEW search-run event;
- reuse existing immutable membership snapshot;
- do not rescan/filter 5M scores;
- result_source=EXACT_RESULT_REUSE.

## Layer 2 — INTELLIGENCE_REUSE
If no exact snapshot but compatible Phase 10 generation is READY:
- no retraining;
- no 5M rescoring;
- run exact Audience Engine filtering/selection only;
- materialize new result snapshot;
- result_source=INTELLIGENCE_REUSE.

## Layer 3 — NEW_INTELLIGENCE_BUILD
If no compatible generation:
- invoke Phase 10 prepare/reuse-build;
- wait durably until READY/BLOCKED/FAILED;
- then exact filter/materialize;
- result_source=NEW_INTELLIGENCE_BUILD.

Never reuse stale/superseded generation results for a current request.
Repeated identical user actions may share one result snapshot but always retain separate search-run history.

Explicitly reject “precompute every combination”.
