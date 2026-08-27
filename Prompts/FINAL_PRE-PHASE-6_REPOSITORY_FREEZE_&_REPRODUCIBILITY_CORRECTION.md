
FINAL PRE-PHASE-6 REPOSITORY FREEZE & REPRODUCIBILITY CORRECTION

Repository:
https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git

Required starting HEAD:
c114b8442c3d09585a7ac3094df17c704fc678d9

IMPORTANT:
The Phase 1→5 technical implementation is already accepted.

This pass is NOT a redesign.

DO NOT:
- change PU-learning logic;
- change the Feature Contract;
- change the 11 scoring features;
- change Bagging PU governance;
- change Phase 4 job architecture;
- change Phase 5 scoring architecture;
- regenerate valid data unnecessarily;
- implement Audience Explorer;
- implement Phase 6;
- add audience selection;
- add percentiles/deciles/bands;
- add Campaign Builder;
- add exports;
- add campaign activation.

The purpose of this pass is ONLY to eliminate the remaining repository reproducibility, evidence, documentation, and freeze-consistency blockers.

==================================================
0. FROZEN CURRENT CANONICAL CHAIN
==================================================

Treat the following as the currently validated Phase 1→5 chain unless actual database inspection proves otherwise:

Current source imports:

CUSTOMERS
import_id = 8
source_checksum =
3a3449e64f582aaa17765fae2bb3c44c5352cb7c6ff723797fab322665aa36b8

CAMPAIGN_SALES
import_id = 9
source_checksum =
58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

DEMOGRAPHICS
import_id = 5
source_checksum =
7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db

Current derived chain:

analysis_run_id = 12

training job_id = 20
model_run_id = 8

scoring job_id = 21
scoring_run_id = 8

Selected candidate:

BAGGING_PU

Model Role Policy:

2

Evaluation Contract:

2

Feature Contract:

version = 1

feature SHA =
a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535

Model artifact SHA:

755e8f81bc1238673d17f59fb52044f44b5f00a8810fee82e694b4c4b8709d18

Current canonical score statistics:

score_min =
0.06774103945805435

score_mean =
0.20595671379862576

score_max =
0.9782832402557606

Current score reconciliation:

demographic snapshot = 5,000,000
scored persons = 5,000,000
score rows = 5,000,000
distinct person_ids = 5,000,000
duplicates = 0
invalid FK = 0
nonfinite = 0
below zero = 0
above one = 0

Deterministic verification:

scoring_run_id = 8
sample_size = 256
verified = true
max_abs_diff = 0.0

Historical underage campaign contact evidence:

before correction = 5,453
after correction = 0

==================================================
1. BASELINE GATE
==================================================

Before changing anything run:

git rev-parse HEAD
git status --short

HEAD must be:

c114b8442c3d09585a7ac3094df17c704fc678d9

If there are unexplained local changes:

STOP.

Then run:

python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json

Record:

- pytest result
- pip check
- compileall
- data validation status
- current schema version
- current import IDs/checksums
- current analysis/model/scoring IDs

Do not modify code if the repository is not in the expected starting state.

==================================================
2. CRITICAL BLOCKER — CANONICAL CAMPAIGN SOURCE IS NOT COMMITTED
==================================================

Current repository Git LFS campaign file still points to the OLD campaign source:

data/campaign_sales_570000.csv.gz

old LFS object SHA:

16aace571676765f358ecb3e981ec273ae08653fc9397229856cc4e27dfd500c

But the canonical database was rebuilt using campaign source checksum:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

This means:

fresh clone
→ git lfs pull
→ import tracked campaign source

cannot reproduce:

analysis_run_id 12
model_run_id 8
scoring_run_id 8

This MUST be fixed before Phase 6.

==================================================
3. FIND THE EXACT REGENERATED CAMPAIGN SOURCE
==================================================

Before regenerating anything, locate the exact campaign source that produced:

SHA-256:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

Check:

- current data directory;
- generator output directory;
- Step 7 output directories;
- temporary validation folders;
- archived generated data locations.

Do NOT search outside the project unnecessarily.

For every candidate file compute:

SHA-256
file size
row count

The correct canonical source must satisfy:

SHA256 =
58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

rows =
570,000

plus header row.

Also verify:

underage historical contacts = 0

Do not expose PII in the report.

==================================================
4. DATA REGENERATION DECISION
==================================================

CASE A — exact 58106df... file exists

This is preferred.

DO NOT regenerate campaign sales.

Use that exact existing source.

Move/copy it into:

data/campaign_sales_570000.csv.gz

through the normal repository workflow.

Preserve exact bytes.

Recompute SHA after placement.

It MUST still equal:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

CASE B — exact file no longer exists

Only then regenerate campaign data.

Use:

data_generation_scripts/generate_campaign_sales.py

Use the exact deterministic configuration/seed used by the corrected Step 7 implementation.

Input must remain the existing canonical customer source.

Generate:

campaign_sales_570000.csv.gz
campaign_master.csv
product_master.csv
campaign_sales_sample_10000.csv
campaign_sales_summary.json

Validate:

campaign rows = 570,000
campaigns = 96
underage campaign contact count = 0
invalid customer FK = 0
PU consistency violations = 0
contact date coverage remains within 2024-01-01..2025-12-31

IMPORTANT:

If regenerated output SHA is NOT:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

then the source differs from the one used for the current canonical model/scoring chain.

In that case:

DO NOT pretend model_run_id=8 / scoring_run_id=8 remain canonical.

A different campaign source requires rebuilding:

Phase 2 analysis
→ Phase 3/4 model
→ Phase 5 scoring

Do not automatically perform that expensive rebuild without first reporting the checksum mismatch.

==================================================
5. COMMIT CANONICAL CAMPAIGN DATA THROUGH GIT LFS
==================================================

Ensure:

data/campaign_sales_570000.csv.gz

contains the canonical source.

Verify Git LFS tracking:

git lfs ls-files

Ensure the campaign file is managed by Git LFS.

Stage the canonical source.

After staging, inspect the LFS pointer or Git object representation.

IMPORTANT:

The Git LFS object SHA and the raw source-file SHA may represent the same underlying content SHA but verify carefully using Git LFS metadata.

Record:

canonical source raw SHA-256
Git LFS oid
Git LFS size

Do not rely on README values.

Read the actual committed/staged LFS pointer.

==================================================
6. COMPANION CAMPAIGN ARTIFACTS
==================================================

Inspect whether the corrected campaign regeneration also changed:

data/campaign_master.csv
data/product_master.csv
data/campaign_sales_sample_10000.csv
data/campaign_sales_summary.json

or their actual repository paths.

If the current canonical campaign source was regenerated, companion artifacts must correspond to the same generation run.

Do NOT retain companions from the old campaign source if they no longer correspond to the canonical campaign data.

Validate:

campaign master matches campaign IDs in campaign_sales
product master matches product IDs
sample rows exist in canonical campaign source
summary describes the canonical source
summary reports underage_contact_count = 0
summary row count = 570000
summary campaign count = 96

Commit only coherent companion artifacts.

==================================================
7. README LFS MANIFEST CORRECTION
==================================================

Update README using ACTUAL final Git LFS pointers.

Do not hard-code values from prior documentation.

Read:

customer_master_125000.csv.gz
campaign_sales_570000.csv.gz
usa_demographic_synthetic_5000000_rows.csv.gz

and record their actual:

Git LFS oid SHA256
size

The README manifest must exactly match the committed repository state.

Clearly distinguish:

Git LFS object/source file SHA

from:

database import provenance checksum

if they are conceptually the same source but represented differently.

README must also state that the tracked source files are the authoritative reproducible inputs for the current Phase 1→5 baseline.

==================================================
8. FINAL INTEGRITY JSON SHA SEMANTICS
==================================================

File:

docs/evidence/phase1_to_phase5_final_integrity.json

currently contains:

starting_sha = 5f54c5e...
final_sha = 5f54c5e...

Do NOT simply replace final_sha with the commit that contains the file.

That creates a self-referential Git SHA problem:

changing the file
→ changes commit content
→ changes commit SHA

Instead redesign the fields to have explicit semantics.

Preferred fields:

integrity_pass_start_sha:
5f54c5e7138afaf615984babd32cac3a6bf2a99b

validated_repository_state_sha:
<the SHA against which the validation commands were actually run>

evidence_generated_before_freeze_commit:
true

freeze_commit_sha:
null

OR omit freeze_commit_sha entirely.

Add a note:

"The authoritative final Phase 6 baseline is the Git commit/tag containing this evidence artifact. The commit SHA is intentionally not self-embedded in this file."

Do not introduce misleading `final_sha`.

The actual final SHA will be reported externally after commit.

==================================================
9. FIX PHASE 5 ACCEPTANCE CHECKLIST CANONICAL SCORE VALUES
==================================================

File:

Prompts/phase5_prompt_pack/19_PHASE_5_ACCEPTANCE_CHECKLIST.md

Current identifiers correctly point to:

job_id = 21
model_run_id = 8
scoring_run_id = 8

But score values still refer to the old run.

Replace the CURRENT canonical score statistics with:

min =
0.06774103945805435

mean =
0.20595671379862576

max =
0.9782832402557606

Do not delete old score values if they are useful historical evidence.

If retained, move them under an explicit heading:

Historical / Superseded Phase 5 Scoring Evidence

Current canonical values must appear only in the current/final section.

Also verify any runtime/chunk/throughput values attributed to scoring_run_id=8.

Do NOT copy scoring_run_id=7 performance metrics and label them as run 8 unless actual evidence confirms they are identical.

If current run-8 runtime metrics are unavailable:

say:

"runtime metric not preserved in final integrity evidence"

rather than using stale run-7 values.

==================================================
10. FIX PROGRESS TRACKER HISTORICAL/CURRENT LABELING
==================================================

File:

Prompts/phase5_prompt_pack/10_PROGRESS_TRACKER.md

Do NOT erase historical evidence.

Older sections containing:

model_run_id=6
job_id=18
scoring_run_id=7

were valid at the time.

Change labels such as:

canonical

to:

Historical canonical at that phase
Superseded by Step 8 final canonical chain

Add an explicit note above historical sections:

"This section records the canonical state at that historical checkpoint. It is no longer the current Phase 6 handoff baseline."

Current canonical section must clearly show:

analysis_run_id = 12
training job_id = 20
model_run_id = 8
scoring job_id = 21
scoring_run_id = 8

Current source imports:

customers = 8
campaign_sales = 9
demographics = 5

==================================================
11. FIX PHASE 5 IMPLEMENTATION SUMMARY
==================================================

File:

docs/PHASE_5_IMPLEMENTATION_SUMMARY.md

Preserve the historical story.

Do not remove:

- earlier 5M run;
- old model 7/run 5;
- old model 6/run 7;
- earlier remediation evidence.

But clearly structure the document:

Historical Phase 5 Evidence
→ previous runs

Pre-Phase-6 Corrections
→ source-aware lifecycle

Final Phase 1→5 Integrity Rebuild
→ current canonical chain

At the top or final summary, state unambiguously:

CURRENT CANONICAL PHASE 6 HANDOFF:

analysis_run_id = 12
model_run_id = 8
training job_id = 20
scoring job_id = 21
scoring_run_id = 8

campaign import = 9
demographic import = 5

No reader should mistake scoring_run_id=5 or 7 for the current handoff.

==================================================
12. VERIFY PHASE 6 HANDOFF CONTRACT
==================================================

File:

Prompts/phase5_prompt_pack/20_PHASE_6_HANDOFF_CONTRACT.md

Verify it uses:

model_run_id=8
job_id=21
scoring_run_id=8

artifact SHA:

755e8f81bc1238673d17f59fb52044f44b5f00a8810fee82e694b4c4b8709d18

Feature SHA:

a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535

Demographic import:

5

Historical source provenance must also point through:

analysis_run_id=12
customer import 8
campaign import 9

The Phase 6 handoff rule must require:

completed scoring run
AND
current demographic source
AND
current historical source
AND
valid model governance
AND
valid artifact
AND
exact feature contract
AND
score reconciliation

==================================================
13. FRESH-CLONE / FRESH-DATABASE REPRODUCIBILITY TEST
==================================================

This is REQUIRED after the canonical campaign source is committed/staged correctly.

Do NOT use the populated production POC DB for this proof.

Create a temporary validation database.

Using ONLY files available from the repository working tree as they will exist after clone/LFS pull:

1. initialize schema;
2. import customer source;
3. import campaign source;
4. import demographics source;
5. run reconciliation.

Verify imported checksums equal the canonical expected source checksums.

Expected:

CUSTOMERS:
3a3449e64f582aaa17765fae2bb3c44c5352cb7c6ff723797fab322665aa36b8

CAMPAIGN SALES:
58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

DEMOGRAPHICS:
7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db

Verify:

customers = 125,000
campaign_sales = 570,000
demographics = 5,000,000

underage campaign contacts = 0

invalid customer FK = 0

PU consistency violations = 0

demographic age <18 = 0

demographic age >100 = 0

adult-count violations = 0

overall_status = OK

Delete the temporary DB afterward if repository conventions require it.

Do NOT commit test SQLite databases.

==================================================
14. DO WE NEED TO RETRAIN / RESCORE?
==================================================

Determine from the final campaign source SHA.

CASE 1:

Final tracked campaign source SHA is exactly:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

Then:

DO NOT retrain.
DO NOT rerun 5M scoring.

Existing:

analysis 12
model 8
scoring 8

remain valid because the repository now contains the exact source bytes already used to create them.

Only perform bounded revalidation:

verify analysis provenance
verify model artifact
verify scoring provenance
verify deterministic scoring sample

CASE 2:

Final tracked campaign SHA differs from 58106df...

Then:

STOP.

Do not call the old chain current.

Report that the campaign source changed.

A new Phase 2→5 derived chain would be required:

new analysis
→ new model
→ new 5M scoring

Do not continue freeze documentation using old canonical IDs.

==================================================
15. CURRENT DATABASE REVALIDATION
==================================================

For the existing POC database verify:

latest COMPLETED imports:

customers:
import_id=8
checksum=3a3449...

campaign_sales:
import_id=9
checksum=58106d...

demographics:
import_id=5
checksum=7d57a0...

Verify:

analysis_run_id=12
status=COMPLETED

historical source provenance current=true

model_run_id=8
status=COMPLETED

selected candidate=BAGGING_PU

artifact SHA=
755e8f81bc1238673d17f59fb52044f44b5f00a8810fee82e694b4c4b8709d18

scoring_run_id=8
status=COMPLETED

demographic source verified=true
historical source verified=true
canonical/current=true

Verify:

5M score rows
no duplicates
no invalid FK
no invalid ranges

Run:

verify_scoring_run_sample(
    scoring_run_id=8,
    sample_size=256
)

Expected:

verified=true
max_abs_diff=0.0

==================================================
16. FULL TEST GATES
==================================================

Run:

python -m pip check

python -m pytest -q

python -m compileall -q app scripts tests

git diff --check

python scripts/validate_data.py --json

Also verify:

git status --short

Review all changed documentation for:

model_run_id=6
scoring_run_id=7
scoring_run_id=5
job_id=18

Old references are allowed ONLY when clearly labeled:

Historical
Previous
Superseded
Earlier Phase 5 evidence

No old run may be described as the CURRENT canonical Phase 6 handoff.

==================================================
17. PHASE 6 SCOPE SCAN
==================================================

Confirm no implementation has been introduced for:

Audience Explorer
prospect browsing
person lookup
score bands
score percentiles
score deciles
audience filters
audience selection
saved audiences
Campaign Builder
CSV target export
campaign activation

This is still a Phase 1→5 freeze cleanup.

==================================================
18. COMMIT STRATEGY
==================================================

Create one dedicated cleanup commit, for example:

chore: align final phase1-5 freeze evidence and canonical data

The commit should include:

- canonical campaign LFS source;
- matching companion generated artifacts when required;
- README manifest correction;
- final integrity JSON semantic correction;
- progress tracker cleanup;
- acceptance checklist correction;
- implementation summary cleanup;
- handoff correction if required.

Do NOT try to place this commit's own SHA inside a file in the same commit.

After commit:

git rev-parse HEAD

That resulting SHA is the candidate authoritative Phase 6 baseline.

Optionally create a Git tag such as:

phase5-final
or
pre-phase6-final

only if repository conventions allow it.

A Git tag is a cleaner freeze pointer than self-embedding the SHA in an evidence file.

==================================================
19. POST-COMMIT VERIFICATION
==================================================

After commit run:

git status --short

Expected:

clean

Then verify:

git lfs ls-files

Verify campaign source is the corrected canonical object.

Fetch/read the committed versions of:

README.md

docs/evidence/phase1_to_phase5_final_integrity.json

Prompts/phase5_prompt_pack/10_PROGRESS_TRACKER.md

Prompts/phase5_prompt_pack/19_PHASE_5_ACCEPTANCE_CHECKLIST.md

Prompts/phase5_prompt_pack/20_PHASE_6_HANDOFF_CONTRACT.md

docs/PHASE_5_IMPLEMENTATION_SUMMARY.md

Confirm no current-canonical contradictions remain.

==================================================
20. FINAL REPORT
==================================================

Return a strict report containing:

1. starting SHA:
   c114b8442c3d09585a7ac3094df17c704fc678d9

2. final cleanup SHA

3. files changed

4. whether exact canonical campaign source was found or regenerated

5. canonical campaign raw SHA

6. final Git LFS campaign oid

7. final Git LFS campaign size

8. whether customer data was regenerated
   expected: NO

9. whether demographic data was regenerated
   expected: NO

10. whether campaign data was regenerated
    expected:
    NO if exact 58106df file was found
    YES only if it had been lost

11. customer import/checksum

12. campaign import/checksum

13. demographic import/checksum

14. fresh-database import reconciliation result

15. underage campaign contact count

16. analysis_run_id

17. training job_id

18. model_run_id

19. scoring job_id

20. scoring_run_id

21. feature contract SHA

22. artifact SHA

23. score min/mean/max

24. score row reconciliation

25. deterministic re-score result

26. historical-source verification

27. demographic-source verification

28. pytest result

29. pip check result

30. compileall result

31. git diff check

32. validate_data result

33. Git LFS manifest verification

34. documentation stale-reference scan result

35. confirmation no Phase 6 implementation

36. final candidate Phase 6 baseline SHA

37. FINAL DECISION:
    GO
    CONDITIONAL GO
    NO-GO

==================================================
21. FINAL ACCEPTANCE RULE
==================================================

GO is allowed only if:

- repository contains the exact canonical campaign source used by the current model chain;
- fresh database imports reproduce all three canonical source checksums;
- campaign underage contacts = 0;
- historical source provenance is current;
- demographic source provenance is current;
- model 8/artifact verification passes;
- scoring run 8 remains canonical;
- exact 5M score reconciliation passes;
- deterministic re-score passes;
- tests pass;
- documentation contains no conflicting CURRENT canonical references;
- no Phase 6 functionality has been added.

If the final campaign source checksum differs from:

58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb

then the current analysis/model/scoring chain must be considered superseded and this pass must end:

NO-GO — NEW PHASE 2→5 REBUILD REQUIRED.

Do not begin Phase 6.

STOP after the final report.
