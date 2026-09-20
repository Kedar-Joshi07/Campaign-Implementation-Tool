# Phase 11 Future Feedback and Retraining Lineage

## Scope and present boundary

Phase 11 preserves enough immutable evidence to support a future closed-loop feedback system. It does not activate campaigns, ingest outcomes, create supervised labels, schedule retraining, select a challenger model, or modify a model from feedback.

This contract is the future feedback/retraining seam referenced by the Phase 11 implementation summary and schema reference. It is intentionally separate from the current Home → Find Potential Customers → Result → Download workflow and from the future RBAC presentation seam in `frontend/js/view-contract.js`.

The intended future vocabulary is:

- closed-loop feedback;
- outcome ingestion;
- scheduled or recommended retraining; and
- champion/challenger refresh.

This is not a reinforcement-learning implementation. That term must not be used for ordinary delayed outcome ingestion or periodic supervised retraining.

## Completed-search lineage retained today

Every completed `campaign_search_runs` record is linked to the following immutable or append-only evidence:

| Requirement | Durable source |
| --- | --- |
| Exact selected people | `campaign_result_snapshots.storage_uri`, `resolved_count`, `snapshot_sha256`, and membership contract version |
| Business/campaign context | `targeting_context_id` and the exact canonical context JSON/hash in `campaign_targeting_contexts` |
| Targeting criteria | Canonical criteria JSON/hash and filter-branch JSON/hash on the search run |
| Delivery profile | `delivery_channel` and `export_profile` on the search run |
| Intelligence generation | `generation_id` and intelligence key on `phase10_intelligence_generations` |
| Analysis/model/scoring lineage | `analysis_run_id`, `model_run_id`, and `scoring_run_id` on both the generation and completed search |
| Model artifact | `artifact_sha256` on the generation, reconciled to `model_runs.artifact_sha256` |
| Source identity | Customer, campaign-sales, and demographic import IDs and source checksums on the generation |
| Result/cache provenance | `result_source`, `result_snapshot_id`, `result_cache_key_sha256`, membership checksum, selection and counts |
| Timing | Search created/started/completed time, snapshot creation/verification/use time, and export start/completion time |
| Download history | Append-only `campaign_result_export_events` rows and their `export_event_id` values |
| Initiating user seam | Nullable `campaign_search_runs.created_by_user_id` |

`get_completed_search_lineage()` in `app/services/phase11_feedback_lineage_service.py` is a read-only audit projection over this chain. It fails closed for a missing, incomplete, non-completed, or artifact-SHA-inconsistent chain. It does not load contact data or perform feedback work.

## Nullable future-link seam

Schema version 18 adds `campaign_search_future_lineage`, with one automatically created row per search run:

- `search_run_id` is the primary key and a real foreign key to the immutable search;
- `activation_id` is reserved for a future governed activation registry;
- `provider_campaign_id` is reserved for the external delivery provider's campaign reference;
- `feedback_batch_id` is reserved for a future ingestion-batch registry;
- `outcome_dataset_id` is reserved for a governed, immutable outcome dataset; and
- `created_at` and `updated_at` preserve the linkage timing.

All four future identifiers are nullable today. There are deliberately no placeholder activation, feedback, outcome, user, or provider tables and no fabricated foreign keys to systems that do not exist. When those registries are implemented, a later migration must validate existing non-null identifiers before adding their real foreign-key constraints.

The seam preserves current immutability:

- a row is created automatically with every search submission;
- existing v17 search runs are backfilled without changing the search record;
- future references may be attached only after the search is completed;
- each non-null future reference is write-once;
- rows cannot be deleted; and
- Phase 11 exposes no application method or API that populates these fields.

These rules allow a later governed integration to attach evidence without reopening or mutating the search, result snapshot, intelligence generation, or export audit.

## Future outcome grain

The minimum future supervised-outcome record grain is:

```text
search_run_id
+ person_id
+ channel
+ delivery_timestamp
+ event_timestamp
+ outcome_timestamp
+ outcome_type
+ outcome_value
```

The future schema should also carry stable event/provider identifiers for idempotent ingestion, `activation_id`, `provider_campaign_id`, `feedback_batch_id`, `outcome_dataset_id`, ingestion time, source checksum, attribution-policy version, observation-window version, and consent/currentness evidence relevant to the channel.

`person_id` must be accepted only when it belongs to the immutable membership snapshot referenced by that `search_run_id`. Contact identifiers belong at the governed delivery boundary and must not become model features or be copied into analytical membership artifacts.

Delivery, event, and outcome times are distinct:

- delivery time records when the provider accepted or attempted the contact;
- event time records the source-system event time;
- outcome time records when the measured business outcome occurred; and
- ingestion time records when the platform received the evidence.

Repeated events must not overwrite history. Corrections should be versioned or superseded with an audit reference.

## Time-aware label and leakage policy

Future supervised learning must be explicitly time-aware:

1. Define a versioned observation window for each outcome type and channel.
2. Do not classify missing or late outcomes as negative before that window closes.
3. Persist `feature_as_of_timestamp`, `observation_window_start`, `observation_window_end`, and `training_cutoff_timestamp` for every derived training dataset.
4. Admit only outcomes whose event/outcome timestamps fall inside the governed window and whose ingestion state is final under the versioned policy.
5. Exclude every event, aggregate, feature, campaign result, or provider signal that occurs after the row's feature-as-of time.
6. Use time-ordered training, validation, and test partitions; never randomly mix later outcomes into earlier feature snapshots.
7. Preserve the exact source checksums, membership snapshot, attribution policy, label derivation version, and analysis/model/scoring lineage for every candidate model.
8. Treat attribution disputes, returns, reversals, opt-outs, delivery failures, and censored observations according to explicit versioned rules rather than silently relabeling them.

A future retraining decision must be a governed recommendation or schedule with eligibility checks, data-quality gates, drift evidence, and champion/challenger evaluation. Feedback arrival alone must never trigger an unreviewed production model replacement.

## Explicitly not implemented in Phase 11

- campaign activation or provider submission;
- provider callback/webhook processing;
- feedback or outcome ingestion APIs;
- outcome/label materialization;
- training-dataset construction from outcomes;
- automatic, scheduled, or recommended retraining;
- champion/challenger execution or promotion;
- model replacement; or
- reinforcement learning.
