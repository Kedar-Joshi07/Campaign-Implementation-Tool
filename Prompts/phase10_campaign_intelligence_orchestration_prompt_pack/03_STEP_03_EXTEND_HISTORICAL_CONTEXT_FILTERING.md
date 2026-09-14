# Step 3 — Extend Historical Context Filtering

Backward-compatibly extend Historical Analysis with:
- campaign_categories
- offer_types

Update filter schemas, persisted payload, response/default/options, SQL predicates,
replay/currentness and training-cohort reconstruction.

Old persisted analyses missing these keys MUST normalize to empty lists.

Expose exact available campaign-category/offer values. Advanced Historical UI may expose
them safely, but business Phase 10 flow must not require the advanced page.

Semantics:
OR inside one dimension; AND across dimensions.

Prove multi-product customer-grain behavior:
one customer row in cohort; positive if ANY selected product has governed positive outcome.

Add helper that resolves full current canonical contact-date range and use exact dates for
Phase 10 generated analyses.

Regression tests:
empty new filters preserve old behavior; category only; offer only; category+offer;
multi-product+category+offer; zero-result; old JSON compatibility.

Evidence:
`docs/evidence/phase10/03_HISTORICAL_CONTEXT_EXTENSION.md`

STOP.
