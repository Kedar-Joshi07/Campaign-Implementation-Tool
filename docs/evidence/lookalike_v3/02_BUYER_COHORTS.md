# Stage 14B_02 — product buyer cohorts and source alignment

## Outcome

Stage 14B_02 is **GO** at the uncommitted candidate on `main`. The trusted and
current HEAD remains `336875c30fc32b00323d916ecc45b232016168a1`, and the
preceding Stage 14B_01 decision is GO. No commit, push, migration, training,
profile build, scoring, scenario run, deployment, or canonical-data write was
performed.

The new descriptive cohort path is separate from PU probability training. It
uses campaign sales only to identify exact, confirmed attributed buyers. A
`pu_label=0` row remains unlabeled and is never promoted to a verified
nonbuyer.

## Implemented behavior

- Exact product, historical context, and fixed date-window selection occurs
  before grouping to one distinct customer per product.
- Repeat attributed orders do not reweight a buyer. A customer may belong to
  several exact product cohorts.
- One deterministic SHA-256 ordering over the selected-products customer union
  assigns the 80/20 fit/holdout split. The seed is `20261005`; a customer cannot
  be fit for one selected product and holdout for another.
- Each selected product needs at least 200 distinct attributed buyers and, after
  the union split, at least 160 fit and 40 holdout buyers.
- Products fail closed as `UNKNOWN_PRODUCT`,
  `NO_ATTRIBUTED_PURCHASE_HISTORY`,
  `INSUFFICIENT_ATTRIBUTED_BUYER_SUPPORT`, or
  `INSUFFICIENT_SPLIT_SUPPORT`. There is no fuzzy alias, category fallback, or
  silently dropped product.
- The manifest binds customer/sales import IDs and operational checksums,
  product-catalog checksum, feature-contract hash, exact context/window, split
  policy, and fit/holdout identity hashes.
- Historical age is completed age at the saved window end. Prospect age remains
  the completed-age value at the demographic source snapshot. Wall-clock time
  is not part of the cohort or later score identity.
- Prospect hard filters and delivery channel are not cohort inputs. Historical
  campaign channel remains an explicit historical-context dimension.

## Canonical read-only audit

The actual operator database was opened in SQLite read-only/query-only mode.
It remained at schema 26 and was not migrated or modified.

| Check | Result |
|---|---:|
| Customers / unique customer PKs | 125,000 / 125,000 |
| Campaign-sales rows | 570,000 |
| Prospect rows | 5,000,000 |
| Sales rows without exact customer join | 0 |
| Invalid contact dates / attributed rows / label-flag mismatches | 0 / 0 / 0 |
| Customer IDs intersecting person IDs | 0 |
| Customer states absent from prospect vocabulary | 0 |
| Customer categorical values absent from prospect vocabularies | 0 |
| Catalog products / products observed in sales | 48 / 36 |
| Distinct attributed-buyer union for all 48 selected products | 25,473 |
| Union fit / holdout | 20,378 / 5,095 |
| Products meeting realized floors in that composite | 31 |

The 48-product composite is deliberately not eligible because 17 selected
products fail exact support. The detailed count-only manifest is
[`02_PRODUCT_SUPPORT_MANIFEST.json`](02_PRODUCT_SUPPORT_MANIFEST.json). It
contains no customer IDs or contact PII.

PRD001 demonstrates why the union split is not reshuffled to force eligibility:

- selected alone: 200 buyers → 160 fit / 40 holdout → eligible;
- selected in the full 48-product union: 200 buyers → 163 fit / 37 holdout →
  `INSUFFICIENT_SPLIT_SUPPORT`.

## Generator reporting correction

The existing raw campaign file and historical
`data/campaign_sales_summary.json` were preserved. That historical summary
reports 48 `distinct_products` because it used the reference-catalog size,
although the file contains 36 product IDs. The generator now reports:

- `distinct_products` and `distinct_products_observed` from the products that
  actually emit rows;
- `catalog_products` separately; and
- the sorted exact `observed_product_ids`.

No 48-product historical training population is claimed or manufactured.

## Verification

| Gate | Result |
|---|---|
| Focused cohort/source/generator/evidence tests | 10 passed in 21.18 s |
| Cohort + PU training + Phase 10 context + feature + v3 registry regression | 65 passed in 67.84 s |
| Canonical read-only source and all-product support audit | PASS |
| Ruff over Stage 14B_02 Python files | PASS |

The tests independently cover wrong customer joins, repeat purchases, one
customer buying two products, historical-context versus prospect-filter
separation, future-window exclusion, unsupported products, exact 199/200
boundaries, missing demographics, unordered product normalization, changed
source checksums, namespace independence, and corrected generator reporting.

Acceptance rows A09–A12 pass. A01–A08 remain inherited GO requirements and
were regression-checked where affected. A13–A45 belong to later stages and are
not claimed here.

## Impact and limitations

No schema or public API changed in this stage. Existing v1/v2 selection,
calibration governance, PU training, historical rows, probability artifacts,
canonical inputs, and scenario definitions remain unchanged.

This stage proves reproducible buyer evidence and split lineage only. It does
not claim learned-profile quality, scoring correctness, prediction, lift,
full-five-million readiness, UI/export readiness, or demo readiness.

The next sequential stage is
`14B_03_LEARNED_BUYER_PROFILES_AND_SCORE_METHOD.md`. It has not been started.
