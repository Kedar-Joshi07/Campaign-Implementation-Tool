# Single Master Prompt — Phase 6 Audience Explorer

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Starting HEAD: `2d90fc1c77d7e332e789d2b0b233e8044148977d`

Implement Phase6 only. Do NOT implement Phase7 Campaign Builder/export/activation.

1. Baseline: run full gates and validate current Phase5 scoring/historical/demographic provenance dynamically.

2. Contracts: non-PII prospect rows = person_id + score/rank metadata + exact 11 model features only. Ranking = score DESC/person_id ASC. Percentile1 top1%; decile1 top10%; bands ELITE=1, VERY_HIGH=2..5, HIGH=6..10, MEDIUM=11..25, LOW=26..50, VERY_LOW=51..100. Selection = ALL_MATCHING/TOP_N. Saved audiences are immutable definitions, not member copies.

3. Schema v9: extend jobs with AUDIENCE_PREPARATION; add `audience_rank_boundaries` (100 rows/run) and `saved_audiences`; no audience_members/rank-5M table; preserve v8 transactionally.

4. Rank preparation: shared max_workers=1 executor/global compute exclusion; keyset scan score DESC/person_id ASC; no OFFSET/no 5M memory; compute 100 boundary tuples; revalidate provenance; publish transactionally.

5. APIs:
- GET /api/audience/runs
- POST /api/audience/runs/{id}/prepare
- GET /api/audience/runs/{id}/preparation-status
- GET /api/audience/options
- POST /api/audience/estimate
- POST /api/audience/search
- POST /api/audience/profile
- POST /api/audiences
- GET /api/audiences
- GET /api/audiences/{id}

6. Filters: score, top percentile, decile, rank band, age, income, family size, gender, state, marital, education, employment, resident status/type, employment type. Strict canonical normalizer, parameterized SQL, filter hash.

7. Search: fixed score order; page max100; opaque versioned keyset cursor bound to run+filter hash; explicit non-PII projection; enrich rows with percentile/decile/band.

8. Profile: universe/matching/selected/historical positives; exact shared feature space; aggregate only; selected-vs-universe and selected-vs-historical-positive indexes; no customer/person linkage.

9. Save: persist normalized definition, selection, resolved count, profile snapshot, full source/model/feature/artifact provenance. No update/member table/export.

10. UI: enable Audience Explorer; Campaigns stays disabled; preparation, filters, estimate, ranked table, profiles, save/reopen; score/no-linkage disclaimers; no PII/export.

11. Hardening: EXPLAIN/timings; no OFFSET hot path; bounded memory; PII scan; source drift/currentness tests; concurrency and malformed input tests.

12. Real 5M acceptance: prepare current scoring run; verify 100 boundaries and exact counts for N=5M: top1=50k, decile1=500k, ELITE=50k, VERY_HIGH=200k, HIGH=250k, MEDIUM=750k, LOW=1.25M, VERY_LOW=2.5M. Validate filters/pages/profiles. Save/reopen one validation audience. Create sanitized `docs/evidence/phase6_5m_acceptance.json`.

13. Freeze: full gates, Phase6 docs + Phase7 handoff, no root README rewrite, dedicated Phase6 commit, actual final HEAD = Phase7 baseline. STOP with GO/NO-GO report.
