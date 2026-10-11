# Campaign Implementation Tool — approved 14B look-alike implementation pack

Prepared 2026-10-05 against `336875c30fc32b00323d916ecc45b232016168a1`. This is a prompt deliverable, not a completed implementation or fresh model certification.

**2026-10-11 execution-status addendum:** the paragraph above describes this
pack when it was authored. The uncommitted implementation now has a current
schema-33 v3 path; [Prompt 16.2](../../docs/evidence/lookalike_v3/16_2_FULL5M_MEASUREMENTS.md)
records a named isolated `FULL5M_GO`, and [Prompt 17](../../docs/evidence/lookalike_v3/17_SCENARIOS.md)
records 20/20 exact current real scenarios and local `DEMO_GO`. See the
[Prompt 18 documentation gate](../../docs/evidence/lookalike_v3/18_DOCUMENTATION.md)
and [operator guide](../../docs/BUYER_SIMILARITY_OPERATOR_AND_DEMO.md).
The initial “unmeasured” status below remains historical drafting context,
not the current evidence verdict. Product-specific predictive quality and
prospective lift remain unvalidated; Prompt 19 exact-SHA remote CI and final
release decision are still separate. The approved v3 decision supersedes
the older *conditional* 14B choice, without changing v1/v2 contracts.

Kedar's requirement: learn buyer profiles from 125K existing customers and linked historical sales, score the independent 5M prospect population for product-aware resemblance, apply strict campaign criteria, and select prospects at the chosen minimum similarity score. Keep the extensively implemented purchase-probability capability intact.

The reviewed code currently interprets v2 as absolute calibrated purchase probability, with discrete buckets. The new v3 uses an explicitly defined buyer-similarity index and cumulative minimum thresholds. A 90/100 similarity score is neither 90% purchase probability nor the 90th percentile. The measure is a design choice in this pack; canonical score distributions and threshold yields are still unmeasured.

### How to run

1. Extract the ZIP in a prompt folder. Read 00_GUARDRAILS, 01_SEMANTICS, and 02_REVIEW.
2. Use `14B_MASTER_COMPREHENSIVE.md` as the controller prompt. It delegates the work into stages; do not run it alongside a separate controller mutating the same checkout.
3. Run `14B_00` through `14B_09` in numeric order, each passing its own gate. Each staged file is independently usable with the common execution contract embedded.
4. Optional concurrent prompts C1–C4 may run only at their listed waves and with isolated write ownership. They support the staged work; they do not replace it.
5. After 14B_09 passes, run this pack's updated 15 → 16 → 17 → 18 → 19. The older versions are historical references. Do not run both copies.
6. Stop dependent work when a gate fails. Continue independent diagnosis/documentation where useful. Genuine zero similarity selections and unsupported products remain valid outcomes.

### Contents

- Master 14B and ten implementation stages covering baseline, contracts/migrations, buyer cohorts, learned profiles, scoring, search integration, UI, snapshot/export/feedback, model/data assurance, and integration closure.
- Four optional concurrent lanes, an execution DAG, interface contract, acceptance matrix, manual/client guide, and a decisions/risk register.
- Updated companion Prompts 15–19 for faults, full-scale performance, unchanged canonical scenario translation, documentation, and final release.
- Repository review notes and a machine-readable manifest with file hashes.

### Two discoveries that affect implementation

The canonical CSV has 570,000 sales rows, 119,909 distinct customers, and **36** observed products; the product master contains **48**. The existing sales summary's `distinct_products=48` is not an observed sales count. Treat catalogue, observed history, and eligible buyer support separately.

The headphone/mobile-phone example is a requirement illustration. Exact headphone/mobile-phone products are absent from the current catalogue. Do not rename Earbuds/Tablet to satisfy that example. Use exact existing products for canonical runs and an explicitly separate fixture for the example, or report unsupported products.

### First action

Run `14B_00_BASELINE_POLICY_AND_GOLDEN_COMPATIBILITY.md`. The user has already chosen look-alike 14B; do not re-ask 14A versus 14B. Record that decision with its exact score meaning and preserve the previous probability history.
