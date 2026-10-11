# Buyer Similarity: operator runbook and client demonstration

Current as of 2026-10-11; uncommitted 14B candidate at HEAD
`336875c30fc32b00323d916ecc45b232016168a1`. The canonical 20-scenario
proof used an **isolated disposable** full-5M SQLite database, not an
operator's live database. See [architecture](BUYER_SIMILARITY_ARCHITECTURE.md)
and [Prompt 17 evidence](evidence/lookalike_v3/17_SCENARIOS.md).

## What to say to a client

“We use attributed purchases to learn supported demographic profiles of
historical buyers for the exact selected products. We score an independent
prospect population for resemblance to those profiles, apply your audience
criteria as strict filters, and keep people at or above the similarity minimum
you choose. You can inspect the immutable result and download eligible
contacts under the selected channel's consent rules. The number is a
**descriptive similarity index**, not the chance someone will buy.”

Do not say “guaranteed buyers,” “90% likely,” “90% accuracy,” “validated
lift,” “confidence,” “90th percentile,” or “production ready.” In this
method, **90** means weighted distance no greater than **0.10** from the
nearest learned buyer profile. A minimum of 80 includes everyone with a
valid 80–100 similarity score; it is not the legacy probability 80–<90 band.

The current catalog has 48 products, but only 36 exact IDs appear in the
canonical sales file. That observed 36 is source-specific, not a permanent
catalog rule. A product without enough exact attributed buyers is
unsupported and cannot be silently replaced by a category. “Mobile Phone”
and “Headphones” are not exact current catalog names; Tablet and Earbuds are
different products. The demo context uses PRD001 Earbuds, PRD003 Tablet,
and PRD004 Laptop because the recorded context and support-aware profiles
for those exact IDs are certified—not as aliases for absent products.

## Demonstration script (existing evidence, no new run required)

1. Open **Home → Find Potential Customers**. Show **Buyer Similarity** and
   the separate advanced **Purchase Probability** mode. Explain that
   probability is implemented but its current calibration/validation
   limitations remain; no v3 score is a probability.
2. Select the recorded Email context with exact product IDs PRD001, PRD003,
   PRD004. Show the selected audience criteria and **Minimum Buyer
   Similarity**. Use Scenario 20's unchanged `VERY_STRONG → 0.90`
   translation as the high-minimum example; do not edit filters to force a
   count. The 2026-10-10/11 full-5M evidence shows its exact preflight and
   immutable result both selected **25,765** people. This is analytical
   membership, not the number of deliverable contacts.
3. Explain the result order: learn relevant historical buyer patterns →
   score prospects → apply strict audience criteria → select by inclusive
   resemblance minimum → inspect immutable membership → governed download.
4. Open saved **Results → Search #22** in the disposable certification
   evidence. Show **Buyer Similarity Summary**, **Current** provenance,
   25,765 selected, the score-method label, and technical details. The
   [full-page Scenario 20 screenshot](evidence/lookalike_v3/17_browser_screenshots/scenario_20_run_22.png)
   records this state; the [20-scenario report](evidence/lookalike_v3/17_SCENARIOS.md)
   gives every exact count, with a range from **25,765 to 627,218**. All
   20 unchanged scenarios exceeded the existing 10,000 demo minimum.
5. Show the **Download Potential Customers** control. A separate governed
   representative Scenario 1 export passed (26,709,301 streamed bytes);
   contact contents were not saved in evidence. Explain that contactability
   and consent are checked at export, so deliverable rows can be fewer than
   the analytical selection. Download is not campaign sending.
6. Close with the boundaries: full-5M and 20-run **demo** gates passed on
   the named disposable environment, while independent purchase-response,
   product-specific predictive power and lift remain unvalidated. Prompt 19
   exact-SHA remote CI/release certification is not claimed.

Screenshots are evidence of the disposable local run, not permission to
represent the operator's current database as having those same counts. The
recorded original scenario JSON SHA-256 is
`d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`;
the 20-run profile-set SHA-256 is
`b754deaacf04a6b2781c9b090ed2b476a24c33fa2cb770c7a6c2c7be972e1def`;
score generations are **3/4/5** for PRD001/PRD003/PRD004 in that
disposable database. They are not universal identifiers.

## Operator preparation and currentness

1. Verify Git LFS inputs and the [canonical source manifest](../README.md#canonical-synthetic-source-manifest).
   Use the existing approved database/import workflow; do **not** migrate or
   replace an operator database merely to reproduce this demo. The current
   code initializes schema **33** on an authorized database path.
2. Start the single local app with
   `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
   Do not run multiple independent SQLite writers.
   Open `/docs` to inspect the live OpenAPI contract or the three-tab UI.
3. In **Find Potential Customers**, load the catalog. Product support shown
   across all history is preliminary; exact historical context is checked
   before a profile can be used. Choose Buyer Similarity, exact products,
   campaign context, audience criteria, and a version-3 export profile.
4. Run exact preflight. `CURRENT` plus `ELIGIBLE` gives separate demographic,
   valid/invalid scored, similarity-qualified and final intersection counts.
   `NOT_AVAILABLE`/`BUILDING` is **not zero**. If not prepared but build is
   available, submit a durable run and monitor preparation. If stale, verify
   import/source lineage and rebuild via the normal authorized path; do not
   reuse a stale generation. Unsupported-product or unresolved split reasons
   need operator review, not threshold manipulation.
5. Submit once; the acknowledgement is durable and the run appears in
   **Results**. Watch stage, heartbeat, processed count (when measurable),
   queue position and confidence-qualified ETA. A long indivisible stage may
   remain at one percentage while its heartbeat advances. Reloading the
   browser does not cancel the run. If polling pauses, use **Resume Updates**.
6. For `FAILED`, retryable `BLOCKED`, or stale `PROCESSING`, read the safe
   issue guidance and use **Retry Search** only when eligible. Retry adds a
   fenced immutable attempt under the same search ID; repeated clicks use an
   idempotency key. Permanent support/data failures require fixing the cause.
   **Run Again With These Choices** creates a new search from a completed one.
   On restart the coordinator reconciles durable unfinished searches.
7. Open the result and check currentness, selected count, score method,
   source/profile/generation lineage and download eligibility. A past result
   remains historical if its source becomes stale. Choose a governed export
   profile; export rechecks membership, source, contactability and consent,
   then records an aggregate audit. Do not store contact CSVs in evidence.
8. Optional outcome feedback accepts only the downloadable CSV/JSON template
   schema and members of that exact immutable result. V3 feedback is retained
   with score/product lineage but does **not** automatically retrain buyer
   profiles or recalibrate probability. Governed v1/v2 feedback may trigger
   **calibration-only** updates under its separate gate; true model/feature
   retraining is not implemented. See [feedback boundary](FEEDBACK_LEARNING_BOUNDARY.md).

### API/OpenAPI example

`GET /api/potential-customer-search/options?include_similarity=true` returns
the current `catalog_version` and v3 export-profile choices. Replace the
catalog token and profile below with values from **that same response**;
the values shown are the frozen disposable Prompt 17 context, not a default
for a different database. Preflight uses the illustrated body; submission
also needs campaign name and export profile.

```json
{
  "selection_contract_version": "3",
  "score_semantics": "PRODUCT_BUYER_SIMILARITY",
  "similarity_minimum": 0.9,
  "context": {
    "campaign_channel": "EMAIL",
    "product_ids": ["PRD001", "PRD003", "PRD004"],
    "campaign_types": [], "campaign_categories": [],
    "offer_types": [], "historical_campaign_channels": []
  },
  "criteria": {
    "age_groups": ["25-34", "35-44", "45-54", "55-64"],
    "income_groups": ["25K-49,999", "50K-74,999", "75K-99,999", "100K-149,999"],
    "genders": [], "states": [], "marital_statuses": [],
    "education_levels": [], "employment_statuses": [],
    "resident_statuses": [], "resident_types": [],
    "employment_types": [], "family_member_count_min": null,
    "family_member_count_max": null
  },
  "selection_mode": "ALL_MATCHING",
  "top_n": null,
  "catalog_version": "0e40a88ad6a43c9d808dcc21533bc5466eeafe804cb3f0d4a1378b1d2420f26d"
}
```

POST this body to `/api/potential-customer-search/preflight`. Only when
current/eligible and appropriate for the user's purpose, POST the same body
plus `campaign_name` and a returned v3 `export_profile` to
`/api/potential-customer-search/runs`. GET `/runs/{id}/status`,
`/runs/{id}/result`, and `/runs/{id}/download` as appropriate. For eligible
retry, POST `/runs/{id}/retry` with an 8–200-character `Idempotency-Key`.
The result is versioned; never reinterpret a v2 propensity band as v3.

## Monitoring, retention and resources

- Watch stage/heartbeat, queue and issue reason, source/profile/generation
  currentness, snapshot hash/count, export audit, SQLite busy/WAL growth,
  disk headroom and process RSS. A heartbeat older than two minutes is
  recoverably stale; avoid a parallel manual worker on the same run.
- Prompt 16.2 observed successful full-5M per-product scoring processes of
  **3,984.540 / 1,750.860 / 2,088.605 seconds** for PRD001/003/004 and
  sampled peak RSS of **346,927,104 / 337,780,736 / 347,992,064 bytes**.
  The PRD004 aborted segment and retry are separately disclosed in the
  [measurement report](evidence/lookalike_v3/16_2_FULL5M_MEASUREMENTS.md).
  These are hardware/source-specific observations, not timeout rules or SLOs.
- The disposable database grew to **8,560,308,224 bytes** after the three
  generations, with peak observed WAL around **1.6 GB** during scoring.
  Budget ample disk before starting a new generation. Result-history six
  fresh observations met the unchanged two-second budget, but an earlier
  **2.053-second** miss remains historical; do not promise universal latency.
- Historical runs, probability scores, profile/generation lineage, feedback
  and immutable results are retained for audit even when stale. Do not delete
  them to make a gate pass. Apply only the existing controlled retention
  policy to generated scratch/artifacts after verifying target paths and
  current references; this Prompt 18 deletes nothing.

Future validation requires independently observed, governed outcome labels,
leakage-controlled campaign/time splits or a suitable prospective experiment,
product-specific discrimination and calibration/lift checks, and a separately
authorized versioned challenger for any true profile or probability-model
retraining. No such future result is inferred from the descriptive 20-run
demo.
