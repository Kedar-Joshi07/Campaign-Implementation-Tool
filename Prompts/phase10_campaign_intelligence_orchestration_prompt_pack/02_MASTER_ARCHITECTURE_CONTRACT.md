# Phase 10 Master Architecture Contract

## Preserve architecture
Router → Pydantic schema → Service → Repository → SQLite.

Phase 10 orchestrates the existing pipeline; it does not duplicate it:
Historical Analysis → training cohort → governed PU model → full prospect scoring
→ Audience rank/analytics → Audience Engine → Saved Audience → Campaign/export.

## Recommended modules
- app/schemas/phase10_intelligence.py
- app/routers/phase10_intelligence.py
- app/services/phase10_context_identity_service.py
- app/services/phase10_compatibility_service.py
- app/services/phase10_historical_resolution_service.py
- app/services/phase10_model_resolution_service.py
- app/services/phase10_scoring_resolution_service.py
- app/services/phase10_orchestration_service.py
- app/services/phase10_lifecycle_service.py
- app/repositories/phase10_intelligence_repository.py
- app/workers/phase10_orchestration_worker.py

Do not stuff Phase 10 into audience_query_service.py, audience_preparation_service.py,
campaign_service.py or one giant frontend file.

## Compatibility layers
Historical compatible = exact Modeling Context + historical policy + current customer
and campaign-sales checksums + completed exact analysis.

Model compatible = historical compatible + exact analysis linkage + frozen feature
contract + model-role/evaluation/training policies + PRIMARY + verified artifact.

Scoring compatible = model compatible + exact model/artifact + current demographic
checksum/count + complete finite 0..1 full-universe scores + canonical currentness.

Targeting-ready = scoring compatible + exactly 100 current rank boundaries + current
analytics snapshot + ready_for_current_audience_actions.

## Reuse hierarchy
1. reuse fully targeting-ready generation
2. reuse scoring, rebuild rank/analytics
3. reuse model, rescore demographics
4. reuse analysis, retrain model
5. build analysis→model→score→rank
6. block if historical cohort is ineligible

## Phase 9 bridge
When READY, bind verified scoring_run_id into Phase 9 source_scoring_run_id so the
existing Phase 9 preview/search/save flow continues unchanged.
