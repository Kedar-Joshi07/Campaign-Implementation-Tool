# Phase 7 Handoff Contract

Phase 6 is accepted and frozen at Step 10. Phase 7 starts from this baseline.

## Authoritative Baseline

- Authoritative baseline is repository HEAD after the dedicated Phase 6 freeze commit.
- This contract must be interpreted together with:
	- `docs/PHASE_6_IMPLEMENTATION_SUMMARY.md`
	- `docs/evidence/phase6_5m_acceptance.json`
	- `docs/evidence/phase6_step8_query_plan_and_timing.json`

## Inherited Frozen Contracts

- `AUDIENCE_FILTER_CONTRACT_VERSION = "1"`
- `AUDIENCE_RANK_CONTRACT_VERSION = "1"`
- `AUDIENCE_SELECTION_CONTRACT_VERSION = "1"`
- Scoring provenance currentness gates remain mandatory.

## Mandatory Preconditions for Phase 7 Consumption

Phase 7 may consume a saved audience only if all checks pass:

1. Saved audience exists and can be loaded.
2. Saved audience currentness check returns current.
3. Referenced scoring run is canonical/current for provenance.
4. Historical and demographic provenance checks are current.
5. Selection definition is valid under supported contract versions.
6. `resolved_count > 0`.
7. Filter/rank/selection contract versions are supported.

Any failed precondition is a hard stop for campaign execution paths.

## Staleness Safety Rule

Phase 7 must never silently consume stale saved audiences.

Required behavior:

- Run currentness/provenance validation before campaign member resolution.
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

