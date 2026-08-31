# Phase 7 Handoff Contract

Phase 6 is accepted and frozen at Step 10. Phase 7 starts from this baseline.

## Authoritative Baseline

- Authoritative baseline is repository HEAD after the dedicated Phase 6 freeze commit.
- This contract must be interpreted together with:
	- `docs/PHASE_6_IMPLEMENTATION_SUMMARY.md`
	- `docs/evidence/phase6_5m_acceptance.json`
	- `docs/evidence/phase6_real_5m_performance.json`
	- `docs/evidence/phase6_performance_finalization_baseline.json`
	- `docs/evidence/phase6_real_5m_service_performance.json`
	- `docs/evidence/phase6_step8_query_plan_and_timing.json`
	- `docs/evidence/phase6_prephase7_finalization_baseline.json`

## Inherited Frozen Contracts

- `AUDIENCE_FILTER_CONTRACT_VERSION = "1"`
- `AUDIENCE_RANK_CONTRACT_VERSION = "1"`
- `AUDIENCE_SELECTION_CONTRACT_VERSION = "1"`
- Scoring provenance currentness gates remain mandatory.

## Focused Pass Governance Clarification

Focused performance finalization preserves governance by explicit two-tier validation:

- Interactive currentness/readiness paths use lightweight metadata/provenance validation only.
- Deep 5M score-table integrity validation remains mandatory for explicit integrity boundaries.

Authoritative helper split:

- `resolve_current_scoring_context_lightweight`
- `find_current_canonical_run_for_model_lightweight`
- `validate_completed_scoring_run_integrity_deep`

Deep integrity validation remains required for:

- scoring completion integrity verification
- audience rank preparation submission/run gate
- explicit audit/integrity verification workflows

Interactive read paths (options/estimate/search/profile/saved audience status/list/detail)
must not automatically trigger repeated full 5M aggregate scans.

## Mandatory Preconditions for Phase 7 Consumption

Phase 7 may consume a saved audience only if all checks pass:

1. Saved audience exists and can be loaded.
2. Saved audience currentness check returns current.
3. Referenced scoring run is canonical/current for provenance.
4. Historical and demographic provenance checks are current.
5. Selection definition is valid under supported contract versions.
6. `resolved_count > 0`.
7. Filter/rank/selection contract versions are supported.
8. Referenced run is `ready_for_current_audience_actions=true` at consumption time.
9. If selection mode is `TOP_N`, enforce `target_count <= scored_person_count` for the current canonical run.
10. Currentness checks must use the lightweight currentness layer; deep integrity checks are invoked only at explicit integrity boundaries.

Any failed precondition is a hard stop for campaign execution paths.

## Staleness Safety Rule

Phase 7 must never silently consume stale saved audiences.

Required behavior:

- Run currentness/provenance validation before campaign member resolution.
- Validate readiness through `ready_for_current_audience_actions` semantics.
- If stale, return explicit blocking status and actionable reason(s).
- Require user/operator acknowledgement and explicit re-resolution path.
- Do not auto-fallback to prior/stale members.

## Permitted Phase 7 Scope (Downstream)

Phase 7 may separately implement:

- Campaign Builder workflow and campaign metadata contract.
- Selection of one saved audience as campaign source.
- Review/approval UX for campaign launch.
- Deterministic member streaming/materialization pipeline.
- Explicit contact-PII contract for export payloads.
- CSV export with explicit governance controls.

## Prohibited in Phase 6 Baseline

The Phase 6 baseline intentionally does not include:

- Campaign activation API.
- Campaign export API.
- Contact-level PII export surface.
- Identity-resolution/linkage behavior.

Phase 7 must introduce these only with explicit schema/API contracts,
tests, security controls, and documentation.

## Contact Export Contract Note

Contact export fields are not frozen in Phase 6.
Phase 7 must define them explicitly and document:

- allowlisted fields and definitions,
- masking/redaction policy,
- retention and access controls,
- auditability requirements.

## Phase 7 Entry Decision

Decision status from Phase 6: GO for Phase 7 planning and implementation,
subject to the mandatory preconditions above.

