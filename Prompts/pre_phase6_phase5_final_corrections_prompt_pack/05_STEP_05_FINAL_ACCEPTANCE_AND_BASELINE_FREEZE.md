# Step 5 — Final Acceptance and Phase 6 Baseline Freeze

Use the HEAD after successful Step 4. Do NOT implement Phase 6.

## Acceptance requirements

All must be true:

### Demographic source
- adult-from-source 18..100 generation remains intact;
- replacement is failure-atomic;
- failed replacement leaves live source unchanged;
- completed provenance is authoritative only after successful live replacement.

### Scoring lifecycle
- multiple historical COMPLETED runs per model are supported when source differs;
- one run is current/canonical for model + current source;
- stale completed runs remain queryable but noncanonical;
- same model can be rescored after source change.

### API
- scoring status checks current source;
- stale history does not disable scoring;
- run detail reports current-source verification accurately;
- current canonical run blocks duplicate scoring;
- no path/PII leakage.

### Existing Phase 5 engine
- exact 11-feature contract unchanged;
- Bagging PRIMARY unchanged;
- keyset chunk scoring unchanged;
- no OFFSET scoring loop;
- shared ProcessPoolExecutor(max_workers=1) unchanged;
- one active heavy job unchanged.

### Scope
No Phase 6 functionality.

## Documentation

Update:

```text
docs/PHASE_5_IMPLEMENTATION_SUMMARY.md
Prompts/phase5_prompt_pack/10_PROGRESS_TRACKER.md
Prompts/phase5_prompt_pack/19_PHASE_5_ACCEPTANCE_CHECKLIST.md
Prompts/phase5_prompt_pack/20_PHASE_6_HANDOFF_CONTRACT.md
```

Document atomic replacement, source-aware canonical scoring, same-model historical coexistence, current-source API semantics, and final validation evidence. Preserve prior historical evidence.

## Phase 6 handoff rule

A score run is usable by Phase 6 only if:

```text
status = COMPLETED
score count reconciled
model/artifact/feature governance valid
demographic import provenance valid
demographic source checksum matches current source
demographic count/min/max match current source
```

Stale completed runs are audit history only.

## Final validation

Run git status, pip check, full pytest, compileall, diff check, and data validation. Verify the sanitized evidence artifact is committed.

## Commit

Create a dedicated final correction commit, e.g.:

```text
Finalize Phase 5 source-aware scoring lifecycle
```

A final docs-only SHA stamp is acceptable if needed. The actual final HEAD becomes the authoritative Phase 6 starting baseline.

## Final report

Include starting SHA `eeed03d052cc75987cc8926b088d906ae0fb7ccc`, final SHA, commits, files changed, atomic design, rollback evidence, canonical rule, schema/index migration, same-model coexistence, current canonical run, API stale/current behavior, tests, evidence artifact, no Phase 6 scope creep, authoritative Phase 6 starting SHA, and GO/NO-GO.

STOP.
