# Single Master — Final Phase 1–5 Integrity Pass

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Starting HEAD: `5f54c5e7138afaf615984babd32cac3a6bf2a99b`

Do not implement Phase 6.

Audit and correct the Phase 1→5 chain under these frozen rules:
- no customer_id/person_id linkage;
- PU labels remain Positive/Unlabeled;
- feature contract v1 SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`;
- exact 11 features;
- model role policy v2;
- BAGGING_PU PRIMARY;
- evaluation contract v2;
- shared max_workers=1 executor;
- keyset 5M scoring;
- no Audience Explorer/campaign/export work.

Execute these gates in order:

1. Dynamic baseline:
   full tests/data validation; measure underage campaign contacts; measure training age violations; inspect current source import provenance; record current analysis/model/scoring chain.

2. Crash consistency:
   use bounded staging for customers, campaign_sales, and demographics; make each authoritative staging→live publication and successful data_import_runs COMPLETED/checksum transition one `BEGIN IMMEDIATE` transaction. Metadata failure must rollback live mutation. Add crash-boundary and mid-stream failure tests.

3. Historical adult eligibility:
   campaign generator must sample only customers age >=18 at campaign start. Add exact reconciliation `underage_campaign_contact_count`; >0 is structural ERROR.

4. Historical source provenance:
   add additive schema provenance for customer + campaign source to Phase 2 analysis; capture and recheck before completion; Phase 3 refuses stale source; Phase 5 canonical model/scoring chain must include current historical source as well as current demographic source.

5. Demographic import alignment:
   require age 18..100 and number_of_adults_in_family >=1 at import/reconciliation.

6. Current docs:
   fix README schema/phase/import statements and actual Git LFS manifest; rename misleading non-unique scoring index; update current FastAPI description.

7. Data decision:
   if current underage campaign contact count >0, regenerate ONLY campaign-sales outputs using the existing customer master and corrected generator. Do NOT regenerate the adult 5M demographics. Do not regenerate customer master unless a separate measured defect exists.
   If campaign source changes, rebuild the canonical Phase 2→5 derived chain with new analysis/model/scoring runs and preserve old runs as history.

8. Final acceptance:
   full regression, fresh/clean DB validation, source provenance, exact 5M scoring, deterministic sample re-score, no Phase6 scope creep, docs/evidence, final SHA.

Then STOP and report final GO/NO-GO.
