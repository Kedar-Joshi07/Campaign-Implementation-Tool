# Step 10 Reproducibility and LFS Report

Generated at: 2026-09-08T20:28:18Z
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


Failed to run `git update-index`: error running C:\Users\Kedar.Joshi\AppData\Local\Programs\Git\mingw64\libexec\git-core\git.exe 'update-index' '-q' '--refresh': '0 [main] sh (14500) C:\Users\Kedar.Joshi\AppData\Local\Programs\Git\usr\bin\sh.exe: *** fatal error - couldn't create signal pipe, Win32 error 5
fatal: the remote end hung up unexpectedly' 'exit status 128'
```
### git lfs ls-files
```text
89e6f846a9 * data/campaign_sales_570000.csv.gz
8a2c5601a9 * data/customer_master_125000.csv.gz
adb33ce1da * data/usa_demographic_synthetic_5000000_rows.csv.gz
```

## Large File and Duplicate Dataset Scan
- Threshold bytes: 52428800
- Non-LFS large files: 0
- Duplicate nested canonical datasets: 0

## Outcome
- Overall status: PASS
- Notes: Decompressed canonical content remained equivalent across regenerated outputs. Canonical compressed assets were refreshed under deterministic gzip settings and validated against LFS and duplicate-file checks.