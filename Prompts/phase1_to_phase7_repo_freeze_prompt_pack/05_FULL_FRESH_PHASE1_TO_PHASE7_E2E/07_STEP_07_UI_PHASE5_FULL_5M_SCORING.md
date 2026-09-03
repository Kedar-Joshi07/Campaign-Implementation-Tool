# Step 7 — Browser: Full 5M Scoring

Start scoring from the actual UI on the newly trained model.

MUST score all 5,000,000 freshly imported prospects. No sampling, prebuilt scores or shortcuts.

Use state-aware long-running waits; observe validating/creating/scoring/finalizing/completed UI states.

After completion independently assert: snapshot=5M, score rows=5M, distinct IDs=5M, duplicates=0, invalid FK=0, nonfinite/out-of-range=0, valid min/mean/max and correct model/analysis/source/feature/artifact provenance.

Run deterministic independent rescore of >=256 IDs within frozen tolerance. STOP.
