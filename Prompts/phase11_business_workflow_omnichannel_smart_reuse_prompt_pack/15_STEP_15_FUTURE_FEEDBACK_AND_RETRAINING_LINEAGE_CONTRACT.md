# Step 15 — Future Feedback & Retraining Lineage Contract

## Objective
Ensure today's search/result data can support future delivery feedback, supervised outcome analysis,
retraining and governed continuous-learning work without pretending those features exist now.

For every completed search preserve:
- exact person membership snapshot
- exact campaign/business context
- targeting criteria
- delivery profile
- generation
- analysis/model/scoring IDs
- model artifact SHA
- source checksums
- result/cache provenance
- timestamps
- download/export event IDs

Design nullable/future foreign-key seam for:
- created_by_user_id
- activation_id/provider_campaign_id
- feedback_batch_id/outcome_dataset_id

Do NOT add actual feedback/reinforcement-learning logic in Phase 11.

Document future outcome grain:
search_run_id + person_id + channel + delivery/event/outcome timestamps + outcome type/value.

Prevent future label leakage:
future model training must use outcomes only after governed observation windows and preserve time-aware lineage.

Do not call future auto-retraining “reinforcement learning” unless an actual RL formulation is later implemented.
For this project, likely future terms are:
- closed-loop feedback
- outcome ingestion
- scheduled/recommended retraining
- champion/challenger refresh

Create:
`docs/PHASE_11_FUTURE_FEEDBACK_LINEAGE.md`
and evidence report.

STOP.
