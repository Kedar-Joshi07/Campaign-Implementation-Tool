# Phase 9 Reference Architecture

Recommended shape:

Business Campaign Planner UI
        |
        v
Phase 9 Schemas / View Models
        |
        +--> Campaign Context Service
        |
        +--> Business Targeting Criteria Service
        |
        +--> Targeting Intelligence Resolver Interface
        |        |
        |        +--> Phase 9 explicit linked-source implementation
        |        +--> Phase 10 automatic resolver later
        |
        +--> Existing Audience Estimate/Search/Profile
        |
        +--> Existing Saved Audience Service
        |
        +--> Existing Campaign Service

Recommended new modules:
- `app/schemas/campaign_targeting.py`
- `app/services/campaign_targeting_context_service.py`
- `app/services/business_targeting_service.py`
- `app/services/targeting_intelligence_resolution.py`
- optional `app/repositories/campaign_targeting_context_repository.py`

Frontend:
- `campaign-planner-state.js`
- `campaign-planner-form.js`
- `campaign-context.js`
- `targeting-preferences.js`
- `target-preview.js`
- `campaign-review.js`

Do not turn existing large Audience/Campaign services into larger god services.
