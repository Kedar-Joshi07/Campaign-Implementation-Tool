# Prompt 17: unchanged canonical 20 scenarios

Verdict: **DEMO_GO**. Candidate: UNCOMMITTED at starting SHA `336875c30fc32b00323d916ecc45b232016168a1`. This is demo readiness, separate from Prompt 16 full-population and model-assurance decisions.

Recorded context: `{'campaign_categories': [], 'campaign_channel': 'EMAIL', 'campaign_types': [], 'historical_campaign_channels': [], 'offer_types': [], 'product_ids': ['PRD001', 'PRD003', 'PRD004']}`. Original scenario JSON SHA-256: `d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`; recorded context manifest SHA-256: `a355dbfca4d65e9522a15653a8fe5665e2f99f59646b4eea59e11828455c6e7c`. Historical JSON minimum 101 is metadata only; the unchanged qualification minimum is 10,000. V3 cumulative similarity translation is separately recorded in `17_V3_TRANSLATION.json`; v1/v2 selections were not rewritten.

Tested 20/20; current/eligible 20; qualifying 20; completed 20; blocked 0; failed 0.

| ID | Original strength → V3 minimum | Eligible | Valid / invalid | Qualified / selected | ≥10K | Run / attempt | Outcome | Members | Reason |
|---:|---|---:|---:|---:|:---:|---|---|---:|---|
| 1 | STRONG → 0.8 | 1389349 | 5000000 / 0 | 254233 / 254233 | yes | 3 / 1 | COMPLETED | 254233 | Current exact membership and browser result verified |
| 2 | GOOD → 0.7 | 168533 | 5000000 / 0 | 133886 / 133886 | yes | 4 / 1 | COMPLETED | 133886 | Current exact membership and browser result verified |
| 3 | GOOD → 0.7 | 258616 | 5000000 / 0 | 137516 / 137516 | yes | 5 / 1 | COMPLETED | 137516 | Current exact membership and browser result verified |
| 4 | BROAD → 0.6 | 182172 | 5000000 / 0 | 171988 / 171988 | yes | 6 / 1 | COMPLETED | 171988 | Current exact membership and browser result verified |
| 5 | GOOD → 0.7 | 167301 | 5000000 / 0 | 131247 / 131247 | yes | 7 / 1 | COMPLETED | 131247 | Current exact membership and browser result verified |
| 6 | BROAD → 0.6 | 74514 | 5000000 / 0 | 67625 / 67625 | yes | 8 / 1 | COMPLETED | 67625 | Current exact membership and browser result verified |
| 7 | GOOD → 0.7 | 265247 | 5000000 / 0 | 163260 / 163260 | yes | 9 / 1 | COMPLETED | 163260 | Current exact membership and browser result verified |
| 8 | BROAD → 0.6 | 164862 | 5000000 / 0 | 161368 / 161368 | yes | 10 / 1 | COMPLETED | 161368 | Current exact membership and browser result verified |
| 9 | BROAD → 0.6 | 148110 | 5000000 / 0 | 142089 / 142089 | yes | 11 / 1 | COMPLETED | 142089 | Current exact membership and browser result verified |
| 10 | GOOD → 0.7 | 460423 | 5000000 / 0 | 215443 / 215443 | yes | 12 / 1 | COMPLETED | 215443 | Current exact membership and browser result verified |
| 11 | BROAD → 0.6 | 105496 | 5000000 / 0 | 102246 / 102246 | yes | 13 / 1 | COMPLETED | 102246 | Current exact membership and browser result verified |
| 12 | BROAD → 0.6 | 129595 | 5000000 / 0 | 128122 / 128122 | yes | 14 / 1 | COMPLETED | 128122 | Current exact membership and browser result verified |
| 13 | BROAD → 0.6 | 159164 | 5000000 / 0 | 131253 / 131253 | yes | 15 / 1 | COMPLETED | 131253 | Current exact membership and browser result verified |
| 14 | GOOD → 0.7 | 840022 | 5000000 / 0 | 627218 / 627218 | yes | 16 / 1 | COMPLETED | 627218 | Current exact membership and browser result verified |
| 15 | GOOD → 0.7 | 202805 | 5000000 / 0 | 138667 / 138667 | yes | 17 / 1 | COMPLETED | 138667 | Current exact membership and browser result verified |
| 16 | BROAD → 0.6 | 133497 | 5000000 / 0 | 128120 / 128120 | yes | 18 / 1 | COMPLETED | 128120 | Current exact membership and browser result verified |
| 17 | BROAD → 0.6 | 156188 | 5000000 / 0 | 146363 / 146363 | yes | 19 / 1 | COMPLETED | 146363 | Current exact membership and browser result verified |
| 18 | STRONG → 0.8 | 948268 | 5000000 / 0 | 74630 / 74630 | yes | 20 / 1 | COMPLETED | 74630 | Current exact membership and browser result verified |
| 19 | BROAD → 0.6 | 212846 | 5000000 / 0 | 209751 / 209751 | yes | 21 / 1 | COMPLETED | 209751 | Current exact membership and browser result verified |
| 20 | VERY_STRONG → 0.9 | 2114560 | 5000000 / 0 | 25765 / 25765 | yes | 22 / 1 | COMPLETED | 25765 | Current exact membership and browser result verified |

Real runs use the loopback FastAPI create/status/result/download routes and the production Phase 11 coordinator on a disposable Prompt 16 database. The browser evidence uses installed system Chrome/Edge and opens the actual result detail, including technical details; it contains no contact PII. One representative governed download is streamed only to a digest, never saved as contact data. Full counts, identities, timings, issues, hashes, and screenshot paths are in `17_SCENARIOS.json` and the checkpoint.

No production schema or API was changed by Prompt 17; v1/v2 data and semantics remain untouched. Scenario 7's reported elapsed time includes a loopback server/runner interruption and durable restart recovery; scenario 14's elapsed time includes an observed monitoring/host pause. Those durations are not pure compute benchmarks. Remote CI is not claimed. Next: Prompt 18 may document the honest demo decision.
