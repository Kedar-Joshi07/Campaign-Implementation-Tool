# 04 — Verify and Freeze Demo Data

After all 20 real searches have finished:

## Database assertions

Assert:
- exactly 20 new intended demo search history events were created by this preload batch (unless an explicit retry was required; list retries separately);
- all intended runs are terminal;
- all demo-ready runs are COMPLETED, progress=100, CURRENT, and selected_count >100;
- no new orphan/stale active run remains;
- snapshots referenced by COMPLETED runs exist and validate;
- snapshot hashes/currentness validate;
- no new model/scoring build occurred for targeting-only changes unless compatibility evidence proves it was required;
- source datasets and checksums are unchanged;
- demographic/customer/campaign row counts are unchanged.

Run `PRAGMA integrity_check` again.

## API reopen assertions

For each run:
- reopen through Results/history API;
- reopen full Result Detail;
- verify displayed criteria equal the submitted normalized criteria;
- verify selected_count is stable;
- verify currentness and download eligibility are stable.

## Browser verification

Using the real application in installed Chrome:
- Home shows recent preloaded searches;
- Results lists the new history newest-first;
- open at least scenarios 20, 1, 2, 7, 9, 10, 13, 18;
- Result Detail correctly shows context, targeting, count, source, score/demographic summary, provenance and progress;
- manual Refresh Progress works;
- no unexplained console errors or critical network failures.

Do not download contact data unless needed for a separate approved demo step.

## Freeze manifest

Create:
`output/demo_preload/DEMO_FREEZE_MANIFEST.json`

Include:
- canonical code SHA;
- schema version;
- database filename and safe database metadata (not DB bytes/checksum if changing run history would make it misleading);
- source import IDs/checksums;
- 20 search run IDs;
- 20 snapshot IDs;
- common context;
- export profile;
- exact result counts;
- preload completion timestamp;
- validation gate results.
