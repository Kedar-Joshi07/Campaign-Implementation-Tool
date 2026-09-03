# Hardening Step 6 — Evidence, Tracker & Documentation Cleanup

Correct the audit trail.

Known required SHAs:
- Phase 6 closure: `0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0`
- Phase 7 Section 1: `dda2ac69540ad96896d379f83da2d338a1292854`
- initial Phase 7 implementation: `4748d9e7aa837ad2e66876c20714d576d3ed1f31`

Fix:
- `Prompts/phase7_two_section_prompt_pack/04_PHASE7_PROGRESS_TRACKER.md`
- `Prompts/phase7_two_section_prompt_pack/03_SECTION_2_PHASE7_ACCEPTANCE_MATRIX.md`
- Phase 7 implementation summary/handoff docs
- FastAPI/app description
- UI labels that still say shell/feature-gated

Section 1 final SHA must be `dda2ac...`, not the old Phase 6 SHA.

Fill every Section 2 tracker item with evidence.
Check acceptance boxes only when actually proven.

Sanitize evidence:
- absolute Windows/Linux paths
- developer usernames
- temp DB full paths
- raw SQL
- tracebacks

Represent drift copy as e.g.:
`temporary_db_copy: true`

Do not mix timing claims from different evidence runs. Each timing must identify the
matching evidence file, generated timestamp, row count, and operation.

Mark older evidence historical/superseded rather than silently rewriting history. STOP.
