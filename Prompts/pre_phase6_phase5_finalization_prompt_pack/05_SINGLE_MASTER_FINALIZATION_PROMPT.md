# Single Master Prompt — Pre-Phase-6 Phase 5 Finalization

Repository: https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git
Starting SHA: 0d1425da0bacd020decb79b5d2d7b201b0c894e0

Phase 5 architecture is accepted. Do not redesign training, Bagging PU, the feature contract, chunked scoring, jobs, APIs, or UI. Do not implement Phase 6.

Execute four gated objectives:

STEP 1 — Regenerate the 5M prospect universe as coherent adults age 18..100 from the beginning. Condition state age distributions on adulthood; sample adult age first; generate education/employment/income/family attributes afterward. No post-hoc age mutation. Validate 5M unique rows, no minors, no minor employment, no child-only education. STOP AND TEST.

STEP 2 — Add demographic source provenance using completed demographics data_import_runs. Capture demographic_import_id, source checksum, count, min/max before scoring and recheck before completion. Persist provenance in canonical score_summary_json if possible without schema churn. Require non-empty completion summary. Add a completed-scoring-run provenance validator. Old scoring_run_id=5 remains legacy evidence. STOP AND TEST.

STEP 3 — Reimport the corrected 5M source through the existing import pipeline and rerun actual API scoring with a verified role-policy-v2 BAGGING_PU model. Require exactly 5M demographics, 5M scored, 5M score rows, 0 duplicates/FK errors/nonfinite/out-of-range scores. Record model/job/scoring IDs, provenance, artifact/feature SHA, score stats, chunks, memory, runtime, throughput. Run deterministic 256-row re-score with max_abs_diff approximately 0.0. Verify training/scoring and scoring/scoring conflicts remain 409. STOP AND TEST.

STEP 4 — Update Phase 5 summary, progress tracker, acceptance checklist, and Phase 6 handoff. Preserve historical failed/earlier evidence. Freeze the new canonical scoring run and demographic source provenance. Run full pytest, pip check, compileall, diff check, and data validation. Commit finalization. The actual final HEAD becomes the authoritative Phase 5 baseline for Phase 6. Confirm no Audience Explorer, score bands, audience selection, campaign builder, export, or activation was added.

Final report: starting SHA, final SHA, corrected generator, import/checksum, model/job/scoring IDs, exact 5M reconciliation, score stats, runtime/throughput, re-score result, test results, no Phase 6 scope creep, and final GO/NO-GO.

Then STOP.
