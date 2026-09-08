# Step 10 Reproducibility and LFS Report

Generated at: 2026-09-07T15:26:00Z
Prompt: Prompts/phase8_release_assurance_system_browser_prompt_pack/10_STEP_10_DETERMINISTIC_GENERATION_PATH_HASH_AND_LFS_CLEANUP.md

## Deterministic GZIP Controls
- generate_us_customer_master.py: fixed mtime=0, filename='', compresslevel=9
- generate_campaign_sales.py: fixed mtime=0, filename='', compresslevel=9
- generate_us_demographic_synthetic.py: fixed mtime=0, filename='', compresslevel=3

## Temporary Regeneration Equivalence
| Dataset | Canonical rows | Regenerated rows | Decompressed SHA equal | Raw GZIP SHA equal |
|---|---:|---:|---|---|
| customers | 125000 | 125000 | True | True |
| campaign_sales | 570000 | 570000 | True | True |
| demographics | 5000000 | 5000000 | True | True |

## Canonical Dataset Hashes After Refresh
| File | Bytes | Raw GZIP SHA-256 | Decompressed content SHA-256 | Rows |
|---|---:|---|---|---:|
| data/customer_master_125000.csv.gz | 6145025 | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f | fa0e53b055e0340d0a7cfc6dfdd2fc8bcf18c606e7c8b2b13853ef9a561447bd | 125000 |
| data/campaign_sales_570000.csv.gz | 6466267 | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 | f0a391bbd2ef8262644b1f5c879f3ba1d473476889db8b48e6fde222ea640e0d | 570000 |
| data/usa_demographic_synthetic_5000000_rows.csv.gz | 333670533 | adb33ce1daf92b547171960f69f893fec93296d3d514ac7e1bdffbf5c736ac71 | a664b1a3904079a3c8b5c398de10009d52e8fd2ec6b4751a5caebb4512cb7dba | 5000000 |

## Portable Path Checks
### campaign_sales_summary
- Summary file: data/campaign_sales_summary.json
- Path fields: {'main_output': 'data/campaign_sales_570000.csv.gz', 'campaign_master': 'data/campaign_master.csv', 'product_master': 'data/product_master.csv', 'sample_output': 'data/campaign_sales_sample_10000.csv'}
- Absolute path fields: {}
### customer_master_summary
- Summary file: data/customer_master_summary.json
- Path fields: {'output': 'data/customer_master_125000.csv.gz', 'sample_output': 'data/customer_master_sample_10000.csv'}
- Absolute path fields: {}
### usa_demographic_synthetic_summary
- Summary file: data/usa_demographic_synthetic_summary.json
- Path fields: {'file': 'data/usa_demographic_synthetic_5000000_rows.csv.gz'}
- Absolute path fields: {}

## Git LFS
### git lfs status
```text
On branch main
Objects to be pushed to origin/main:


Objects to be committed:


Objects not staged for commit:

	README.md (Git: 5349455 -> File: 8943801)
	app/schemas/audience.py (Git: 9fb4061 -> File: b94f4da)
	data/README.md (Git: 018f421 -> File: 8ccb0e7)
	data/campaign_sales_570000.csv.gz (LFS: 6d84305 -> File: 89e6f84)
	data/campaign_sales_summary.json (Git: f80735e -> File: 9d4d175)
	data/customer_master_125000.csv.gz (LFS: 0cedbaa -> File: 8a2c560)
	data/customer_master_summary.json (Git: eba370d -> File: 074b03b)
	data/usa_demographic_synthetic_5000000_rows.csv.gz (LFS: abaf511 -> File: adb33ce)
	data/usa_demographic_synthetic_summary.json (Git: 2a2c555 -> File: b957c5f)
	data_generation_scripts/generate_campaign_sales.py (Git: 1cc12ee -> File: ae325ed)
	data_generation_scripts/generate_us_customer_master.py (Git: 97c7258 -> File: 3dc827f)
	data_generation_scripts/generate_us_demographic_synthetic.py (Git: 0807802 -> File: 4ac8524)
	docs/evidence/CLEANROOM_PHASE1_TO_PHASE7_REPORT.md (Git: ff68619 -> File: 09de862)
	docs/evidence/README.md (Git: f234ac4 -> File: acc04ec)
	docs/evidence/cleanroom_phase1_to_phase7.json (Git: 08621c1 -> File: 5d3e95b)
	frontend/index.html (Git: 0a48752 -> File: 33d03f4)
	pytest.ini (Git: 3b7b343 -> File: 8e68b92)
	scripts/validation/system_chrome_campaign_test.py (Git: 853797f -> File: deleted)
	scripts/validation/system_chrome_full_fresh_e2e.py (Git: 9aa78ff -> File: 9d23e1c)
```
### git lfs ls-files
```text
6d84305c09 - data/campaign_sales_570000.csv.gz
0cedbaa5d5 - data/customer_master_125000.csv.gz
abaf51153c - data/usa_demographic_synthetic_5000000_rows.csv.gz
```

## Large File and Duplicate Dataset Scan
- Threshold bytes: 52428800
- Non-LFS large files: 0
- Duplicate nested canonical datasets: 0

## Outcome
- Overall status: PASS
- Notes: Decompressed canonical content remained equivalent across regenerated outputs. Canonical compressed assets were refreshed under deterministic gzip settings and validated against LFS and duplicate-file checks.