# Data Folder Guide

Important: every name, email, phone, address, and other records in this repository is synthetic test data.

Identity boundary:

- customer_id belongs to historical customer/campaign data.
- person_id belongs to the independent demographic prospect universe.
- customer_id != person_id by design.
- No deterministic or inferred linkage between these identifiers is implemented.

## Canonical tracked inputs

These files are the baseline source inputs for reproducible setup.

| File | Purpose | Expected rows |
|---|---|---:|
| customer_master_125000.csv.gz | historical customer foundation | 125000 |
| campaign_sales_570000.csv.gz | historical campaign observations | 570000 |
| usa_demographic_synthetic_5000000_rows.csv.gz | independent prospect universe | 5000000 |

## Canonical checksum and LFS manifest

Raw GZIP SHA-256 identifies the exact compressed artifact. Decompressed content SHA-256 identifies semantic content independent of gzip container metadata.

| File | Bytes | Raw GZIP SHA-256 | Decompressed content SHA-256 | LFS object ref |
|---|---:|---|---|---|
| customer_master_125000.csv.gz | 6145025 | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f | fa0e53b055e0340d0a7cfc6dfdd2fc8bcf18c606e7c8b2b13853ef9a561447bd | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f |
| campaign_sales_570000.csv.gz | 6466267 | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 | f0a391bbd2ef8262644b1f5c879f3ba1d473476889db8b48e6fde222ea640e0d | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 |
| usa_demographic_synthetic_5000000_rows.csv.gz | 512842205 | 27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d | 5694d2048e96b270a3d522e2cc08c1af26561f6fd3c08f104e9957e76653612c | 27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d |

## Phase 11 demographic source contract

Schema 16 appends 12 fields to the frozen first 28 demographic columns:

`email_contactable, direct_mail_contactable, sms_opt_in, whatsapp_opt_in, telemarketing_contactable, do_not_call, push_token, push_opt_in, advertising_id, advertising_targetable, web_visitor_id, onsite_targetable`.

The canonical source has 5,000,000 rows and 40 columns, generated with seed 20260818, chunk size 200000, and ID offset 0. New values are derived from seed/person ID and separate deterministic integer-mixer salts, never the original demographic RNG. All original 28-column content retains SHA-256 `a664b1a3904079a3c8b5c398de10009d52e8fd2ec6b4751a5caebb4512cb7dba` after projecting away the extension.

The following are deliberately varied synthetic POC assumptions, not measured population or platform consent rates. Different channels have independent permission draws. Identifier presence alone does not imply permission.

| Field | Designed rate | Canonical rows true/present | Observed share |
|---|---|---:|---:|
| email_contactable | 88% | 4398985 | 87.9797% |
| direct_mail_contactable | 92% | 4599610 | 91.9922% |
| sms_opt_in | 42% | 2100825 | 42.0165% |
| whatsapp_opt_in | 30% | 1500731 | 30.01462% |
| do_not_call | 18% | 899928 | 17.99856% |
| telemarketing_contactable | 67% of non-DNC rows (~54.94% overall) | 2745904 | 54.91808% |
| push_token | 62% present | 3099544 | 61.99088% |
| push_opt_in | 54% of token-present rows (~33.48% overall) | 1673698 | 33.47396% |
| advertising_id | 74% present | 3699362 | 73.98724% |
| advertising_targetable | 68% of ID-present rows (~50.32% overall) | 2514943 | 50.29886% |
| web_visitor_id | 67% present | 3349299 | 66.98598% |
| onsite_targetable | 72% of visitor-present rows (~48.24% overall) | 2410207 | 48.20414% |

Identifiers are nullable CSV blanks/imported SQL NULLs. Push tokens are `pt_` plus 32 lowercase hexadecimal characters; advertising IDs have deterministic UUID-like v4/variant formatting; web visitor keys are `wv_` plus 32 lowercase hexadecimal characters. These are synthetic opaque keys, never generated at export time.

The importer validates governed email/US phone syntax whenever supplied, strict 0/1 flags, opaque/UUID identifier formats, and flag-to-identifier truthfulness. Email requires email; Direct Mail requires address line 1/city/state/postal code; SMS/WhatsApp/Telemarketing require phone; Telemarketing is blocked by DNC; Push/Display/Website require their respective source identifiers. Reconciliation reports channel totals, identifier availability, and all cross-field violations. Canonical generation and import each produced zero violations/rejections.

All 12 new fields are explicitly excluded from the unchanged 11-feature model contract. Customer and campaign-sales sources are unchanged, so historical/model reuse can remain valid when Phase 10 compatibility permits. Demographic currentness does change: the importer hashes the source filename, NUL, every compressed byte, and NUL. Its new canonical checksum is `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f`; old checksum `e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75` is not current. Old scoring requires a new full scoring generation; Step 4 deliberately does not run it.

See [Step 4 evidence](../docs/evidence/phase11/04_CONTACTABILITY_IDENTIFIER_EXTENSION.md). Historical Phase 8–10 evidence continues to describe its original source hashes; it is not rewritten to imply recertification of the new source.

## Additional tracked references

- customer_master_sample_10000.csv
- campaign_sales_sample_10000.csv
- usa_demographic_synthetic_sample_10000.csv
- customer_master_summary.json
- campaign_sales_summary.json
- usa_demographic_synthetic_summary.json
- product_master.csv
- campaign_master.csv
- usa_demographic_state_reference.csv

## Local runtime file

- campaign_poc.db is the local SQLite runtime database.
- The database is environment/runtime state and should be treated as a local artifact.

## Regeneration notes

- Canonical .csv.gz files are tracked with Git LFS.
- Generators in data_generation_scripts can regenerate synthetic sources when needed.
- Regeneration should preserve schema compatibility and be followed by import + reconciliation validation.
