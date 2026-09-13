# Phase 9 Implementation Summary

Phase 9 adds a business-friendly Create Campaign workflow above the existing Phase 1–8 analytical and campaign infrastructure. It captures business context, translates explicit targeting preferences into versioned backend filters, requires an explicitly linked current targeting-intelligence source, presents exact Target Group results, and saves an immutable Target Group with a Campaign Draft.

## Delivered workflow

1. A five-step business wizard captures Campaign Details, Campaign Context, Targeting Preferences, Target Group Preview, and Review & Save.
2. Campaign context supports multiple products, types, categories, offers, a delivery channel, and historical-channel context without claiming those choices automatically affect model compatibility.
3. Business targeting supports deterministic Match Strength thresholds, gender, age buckets, states, income groups, advanced demographics, family-size ranges, top percentage, and all-matching/TOP_N selection.
4. Targeting intelligence is fail-closed: exact preview and save require a compatible current scoring source explicitly linked to the context. There is no unrelated “latest scoring run” fallback.
5. Exact preview reports available, matching, and selected counts; average/minimum/maximum scores; score bands; demographic mix; deterministic privacy-safe people pagination; and a non-causal Why these people? explanation.
6. Very Strong, Strong, Good, and Broad comparisons use exact counts. Guidance is deterministic and never silently broadens the user’s selection.
7. Save creates an immutable `saved_audiences` definition plus a `phase9_saved_target_groups` provenance snapshot and links it to a Phase 7-compatible Campaign in `DRAFT` status.
8. Model/scoring identifiers, checksums, hashes, and contract versions remain behind explicit technical-detail disclosures.
9. Validation, loading, empty, unavailable, stale, retryable-error, accessibility, keyboard, and responsive states are covered.

## Information architecture and terminology

The business workspace contains Home / Overview, Create Campaign, Saved Target Groups, Campaigns, and Insights. Saved Target Groups provides a governed business-facing list of immutable groups. Insights routes business users to the existing Past Campaign Insights and Target Group Insights capabilities. Data Status, Historical Analysis, Targeting Intelligence / Model Management, and Audience Explorer remain available as advanced/analyst tools.

The optional Region shortcut expands Northeast, Midwest, South, or West into the exact currently available State selections. Persisted criteria remain state-based, explicit, and auditable; Region does not introduce a new targeting or hash contract.

The default flow uses Campaign Context, Targeting Preferences, Match Strength, Potential Customers, Target Group, Why these people?, and Up to date / Needs refresh. “PU,” model-run IDs, scoring-run IDs, feature hashes, artifact hashes, and raw provenance checksums are not required vocabulary in the default path.

## Schema and contracts

Current SQLite schema version: `14`.

- Version 13 adds `campaign_targeting_contexts` and its source/currentness indexes.
- Version 14 adds `phase9_saved_target_groups` with immutable campaign-context, targeting-criteria, filter-branch, source, hash, count, and contract snapshots.
- Campaign targeting-context contract: `1`
- Targeting-segment contract: `1`
- Business match-strength contract: `1`
- Age-bucket contract: `1`
- Income-group contract: `1`
- Targeting-intelligence resolution contract: `1`
- Match-strength recommendation/rule contracts: `1`
- Target Group preview contract: `1`
- Saved Target Group contract: `1`
- Target Group campaign contract: `1`

Phase 7 campaign, member-resolution, export, audience filter/rank/selection, feature, and model-role contracts remain unchanged.

## API additions

All Phase 9 routes use `/api/campaign-planner`:

- `GET /context-options`
- `POST /contexts`
- `GET|PUT /contexts/{targeting_context_id}`
- `GET /targeting-options`
- `GET|PUT /contexts/{targeting_context_id}/targeting-criteria`
- `GET|PUT|DELETE /contexts/{targeting_context_id}/targeting-intelligence`
- `GET /contexts/{targeting_context_id}/target-group-preview`
- `GET /contexts/{targeting_context_id}/match-strength-recommendation`
- `POST /contexts/{targeting_context_id}/target-group-search`
- `POST /contexts/{targeting_context_id}/save-target-group-and-create-draft`
- `GET /contexts/{targeting_context_id}/campaign-draft`

Validation errors use business-readable 422 responses, unavailable/stale source gates use 409, and unexpected errors retain inputs while returning a stable retry message without leaking database paths or internals.

## Privacy and lineage

Planning and preview expose opaque Potential Customer ID, score/rank descriptions, and approved demographic fields only. They exclude name, email, phone, street, city, postal code, and customer identity. Contact PII remains restricted to an explicitly acknowledged export from a finalized Phase 7 Campaign using `EMAIL_CONTACT_V1` or `DIRECT_MAIL_CONTACT_V1`.

The historical `customer_id` and prospect `person_id` domains remain separate. Phase 9 introduces no identity bridge. Every saved Target Group preserves normalized context and criteria JSON, SHA-256 hashes, exact filter branches, scoring/model/analysis lineage, source checksums, contract versions, and the resolved count.

## Closure interoperability behavior

Audience Explorer can represent one conjunctive filter definition, while a Phase 9 Target Group may preserve multiple disjoint filter branches. Saved-audience detail responses therefore identify whether a definition is Phase 9, report its authoritative branch count, and state whether legacy Audience Explorer reopen is safe.

- Legacy Saved Audiences remain reopenable with their filters and selection restored exactly.
- Single-branch Phase 9 Target Groups remain reopenable in Audience Explorer.
- Multi-branch Phase 9 Target Groups fail closed in the legacy form. Reopen definition is disabled, the user is directed to Saved Target Groups or Campaign Planner, and branch 1 is never populated as though it were the complete definition.
- Campaign creation and governed export continue to resolve members from the authoritative complete branch set. Exact union count, de-duplication, currentness, immutability, lineage, and PII boundaries are unchanged.

## Certification and freeze result

- Original final implementation and browser-candidate SHA: `00e8588b08b15abb1ad7db200d2bc9b88871fd18`
- Original evidence-freeze SHA: `f1fc86b7c25b83a82b530876f675cc9ad530a916`
- Corrected Phase 9 documentation/freeze baseline SHA: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- Closure correction final implementation SHA: `111a9205df79ea160f5929dc25cc84f4e7a1fd19`
- Closure exact-SHA CI: PASS - workflow `CI` run `#10`, ID `34740649936`
- Original certification browser: Google Chrome `152.0.7977.83` (historical Step 14 run)
- Closure recertification browser: installed Google Chrome `153.0.8010.36`
- Current control inventory: 75 controls; 71 `PASS`; 4 individually justified exclusive error-state controls; 0 `FAIL`; 0 `NOT_RUN`; 0 unjustified exclusions
- Main Target Group: `#2`, Broad, 2,248 of 5,000,000
- Changed-criteria Target Group: `#3`, Good, 457 of 5,000,000
- Campaign Drafts: `#3` and `#4`
- Browser telemetry: zero unexplained console, JavaScript, or critical network failures
- Independent backend assertions: `PASS`

The original Step 14 report and manifest under `docs/evidence/phase9/final_system_browser/` remain historically accurate for candidate `00e8588...`. Current closure status, interoperability behavior, browser recertification, and final SHA status are authoritative under `docs/evidence/phase9_closure/`.

## Phase 10 handoff

Phase 9 leaves explicit extension points for Phase 10. Phase 10 owns automatic historical-analysis/model/scoring compatibility, reuse of valid current intelligence, missing/stale build-or-refresh orchestration, long-running progress, context-specific provenance, and scoring lifecycle/retention.

Phase 9 already establishes canonical context JSON and integrity hashes for persistence and audit. The Phase 10 hashing responsibility means compatibility-key/version evolution over those established values; it does not replace or reinterpret existing Phase 9 hashes.

Phase 10 must preserve these Phase 9 boundaries: no fake “latest run wins” compatibility; no silent campaign-context-to-prospect filter claims; exact deterministic counts; immutable saved Target Groups; contact PII excluded before governed export; and progressive disclosure of technical provenance.

## Authoritative references

- `docs/evidence/phase9_closure/PHASE9_CLOSURE_ACCEPTANCE.md`
- `docs/evidence/phase9_closure/README.md`
- `docs/evidence/phase9/PHASE9_FINAL_ACCEPTANCE.md` (historical original freeze)
- `docs/evidence/phase9/final_system_browser/PHASE9_SYSTEM_BROWSER_CERTIFICATION_REPORT.md`
- `docs/evidence/phase9/final_system_browser/phase9_certification_manifest.json`
- `docs/evidence/phase9/final_system_browser/ui_control_coverage.json`
- `Prompts/phase9_business_friendly_campaign_targeting_prompt_pack/05_PHASE10_HANDOFF_CONTRACT.md`
