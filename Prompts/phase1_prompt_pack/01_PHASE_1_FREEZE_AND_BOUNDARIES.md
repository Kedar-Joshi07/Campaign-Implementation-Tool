# Phase 1 Freeze, Requirements, and Boundaries

## 1. Product context
This project is a proof of concept for a Campaign Implementation Tool.

The eventual product will allow users to:
1. Analyze historical campaign/customer behavior.
2. Define positive and unlabeled populations.
3. Train a PU-learning look-alike model using historical customer attributes and campaign/sales outcomes.
4. Apply the trained model to an independent approximately 5-million-person demographic prospect universe.
5. Calculate propensity scores.
6. Explore, filter, rank, analyze, select, and export potential campaign audiences.

Phase 1 does NOT implement the PU model or audience scoring. It establishes the application and data foundation required for later phases.

---

## 2. Frozen technology stack

### Frontend
- HTML5
- CSS3
- Vanilla JavaScript only
- No React
- No Vue
- No Angular
- No jQuery
- No frontend build system unless absolutely necessary
- No TypeScript

### Backend
- Python 3.11+ preferred
- FastAPI
- Uvicorn
- Python standard library where practical
- Pydantic through FastAPI

### Database
- SQLite
- Use Python `sqlite3` directly for Phase 1
- No SQLAlchemy unless explicitly approved later
- No PostgreSQL
- No MySQL
- No Redis

### Deployment/runtime style
- One local application
- FastAPI serves API endpoints and static frontend assets
- One SQLite database file
- No Docker requirement in Phase 1
- No cloud requirement

---

## 3. POC philosophy
The application must be functional end-to-end for the implemented Phase 1 scope, but it is not intended to be production complete.

Priorities:
1. Correctness
2. Reproducibility
3. Understandable architecture
4. Fast enough local performance
5. Easy demonstration
6. Clear extension seams for later phases

Do not spend Phase 1 effort on enterprise concerns that do not strengthen the POC demonstration.

---

## 4. Explicitly in scope for Phase 1

1. Project folder structure
2. Python environment/requirements
3. FastAPI application bootstrapping
4. Static HTML/CSS/JS application shell
5. Sidebar/top-level navigation shell
6. SQLite database creation
7. Database schema creation
8. Import of customer data
9. Import of campaign-sales data
10. Import of approximately 5M demographic records, including multi-part compressed CSV support
11. Data validation during import
12. Required SQLite indexes
13. Data summary/reconciliation APIs
14. Application health/status APIs
15. Data status UI page/cards
16. Server-side repository/service separation
17. Logging
18. Configuration through environment variables/default config
19. Basic automated tests
20. Phase 1 documentation and run instructions

---

## 5. Explicitly out of scope for Phase 1

Do NOT implement any of the following:
- PU learning
- look-alike training
- propensity scoring
- model artifact persistence
- feature engineering pipeline
- model evaluation metrics
- audience filtering by propensity
- campaign creation workflow
- campaign audience persistence
- CSV audience export
- login/authentication
- RBAC
- user management
- SSO/OAuth
- multi-tenancy
- Redis
- Celery
- RabbitMQ
- Kafka
- microservices
- Kubernetes
- cloud deployment
- CRM activation
- email/SMS sending
- Salesforce integration
- HubSpot integration
- Meta/Google Ads integration
- production audit framework

Do not create placeholder implementations that falsely imply these features work. Navigation entries for future features may exist visually as disabled/non-functional placeholders only if clearly labeled "Coming in later phase".

---

## 6. Dataset architecture

### Table A: `customers`
Historical customer master.
Approximate rows: 125,000.
Primary key: `customer_id`.

Frozen columns:
1. customer_id
2. first_name
3. last_name
4. gender
5. date_of_birth
6. address_line_1
7. address_line_2
8. street
9. postal_code
10. city
11. state
12. country
13. phone_number
14. email
15. individual_yearly_income
16. family_member_count
17. resident_status
18. resident_type
19. education
20. employment_status
21. type_of_employment
22. marital_status

### Table B: `campaign_sales`
Historical campaign/customer/product/sales observations.
Approximate rows: 570,000.
Foreign key: `customer_id` -> `customers.customer_id`.

Frozen columns:
1. campaign_sales_id
2. customer_id
3. campaign_id
4. product_id
5. order_id
6. campaign_name
7. campaign_type
8. campaign_channel
9. campaign_start_date
10. campaign_end_date
11. campaign_category
12. offer_type
13. offer_value
14. creative_id
15. target_segment
16. product_name
17. product_category
18. product_subcategory
19. product_price
20. product_cost
21. product_tier
22. product_launch_date
23. contact_date
24. contacted_flag
25. delivery_status
26. engagement_flag
27. engagement_type
28. response_flag
29. purchase_flag
30. purchase_date
31. quantity
32. gross_sales_amount
33. discount_amount
34. net_sales_amount
35. gross_margin_amount
36. days_to_purchase
37. campaign_attributed_sale_flag
38. pu_label

### Table C: `demographics`
Independent prospect/scoring universe.
Approximate rows: 5,000,000.
Primary key: `person_id`.
Must have NO row-level linkage to historical customer/campaign tables.

Frozen columns:
1. person_id
2. first_name
3. last_name
4. gender
5. age
6. address_line_1
7. address_line_2
8. street
9. postal_code
10. city
11. state
12. country
13. phone_number
14. email
15. individual_yearly_income
16. marital_status
17. education
18. employment_status
19. resident_status
20. resident_type
21. family_member_count
22. number_of_children_in_family
23. number_of_adults_in_family
24. ethnicity
25. type_of_employment
26. occupation_industry
27. family_yearly_income
28. religion

---

## 7. Data separation rules
1. `customer_id` exists only in historical customer/campaign data.
2. `person_id` exists only in the demographic universe.
3. Never infer or create a mapping between `customer_id` and `person_id`.
4. Names, addresses, phone numbers, emails, and other PII-like synthetic fields must not be used to create a linkage.
5. Customer and demographic populations are intentionally independent synthetic populations.
6. Shared feature vocabularies are allowed and desired for later model compatibility.

---

## 8. SQLite design principles
- Enable foreign keys: `PRAGMA foreign_keys = ON`.
- Consider WAL mode for smoother local reads: `PRAGMA journal_mode = WAL`.
- Use transactions for imports.
- Use chunked/batched inserts.
- Never load the entire 5M-row dataset into Python memory.
- Build heavy indexes after bulk load where advantageous.
- Use parameterized SQL only.
- Create a schema version metadata table.
- Create import/run metadata tables.

Required support tables:
- `app_metadata`
- `data_import_runs`

`app_metadata` should include at least:
- key
- value
- updated_at

`data_import_runs` should include at least:
- import_id
- dataset_name
- source_path
- started_at
- completed_at
- status
- rows_read
- rows_inserted
- rows_rejected
- error_message
- source_checksum if practical

---

## 9. Required indexes
At minimum:

### Customers
- primary key on `customer_id`
- index on `state`
- index on `date_of_birth`
- index on `individual_yearly_income`

### Campaign sales
- primary key on `campaign_sales_id`
- index on `customer_id`
- index on `campaign_id`
- index on `product_id`
- index on `contact_date`
- index on `purchase_flag`
- index on `pu_label`
- useful composite index such as `(campaign_id, product_id, pu_label)`

### Demographics
- primary key on `person_id`
- index on `state`
- index on `age`
- index on `individual_yearly_income`
- index on `education`
- index on `employment_status`
- index on `resident_status`
- index on `type_of_employment`

Do not create dozens of speculative indexes. Add only those justified by Phase 1 and future audience filters.

---

## 10. Data import requirements
The import system must:
1. Accept `.csv`, `.csv.gz`, and multiple demographic part files.
2. Use streaming/chunked reads.
3. Validate column names before insertion.
4. Validate primary key non-nullness.
5. Validate campaign `customer_id` references.
6. Validate basic types and dates.
7. Record import metadata.
8. Fail clearly on schema mismatch.
9. Be restartable without silently duplicating data.
10. Support explicit `--replace` or equivalent behavior.
11. Never truncate existing data implicitly.
12. Log progress periodically for large files.

For the 5M demographic import, display progress based on rows processed if known; otherwise emit periodic row counters.

---

## 11. API scope for Phase 1
Required endpoints:

### Health
- `GET /api/health`
- `GET /api/version`

### Data status
- `GET /api/data/status`
- `GET /api/data/summary`
- `GET /api/data/imports`

### Basic reference summaries
- `GET /api/reference/states`
- `GET /api/reference/campaigns`
- `GET /api/reference/products`

Do not expose raw 5M-row dump endpoints.

---

## 12. Frontend scope for Phase 1
Create a clean application shell with:
- Brand/project title
- Left sidebar or top navigation
- Overview page
- Data Status page
- Disabled/later-phase navigation entries for:
  - Historical Analysis
  - Model Training
  - Audience Explorer
  - Campaigns

The Overview page should show only real Phase 1 values fetched from the backend:
- customer row count
- campaign-sales row count
- demographic row count
- distinct campaigns
- distinct products
- date range of campaign-sales data
- database status

The Data Status page should show:
- dataset name
- expected rows if configured
- actual rows
- last import status
- last import time
- source path/file
- validation/reconciliation status

No hard-coded fake KPI values.

---

## 13. Non-functional expectations
- App should start with one documented command.
- Code should be readable and modular.
- Functions/modules should have clear responsibilities.
- Errors should return meaningful API messages.
- UI should show backend errors gracefully.
- Avoid unnecessary abstraction.
- Avoid framework creep.
- Keep local startup simple.

---

## 14. Definition of Phase 1 complete
Phase 1 is complete only when:
1. Fresh environment setup works.
2. Database can be initialized from scratch.
3. All three datasets can be imported.
4. Row counts reconcile.
5. Customer foreign keys in campaign sales are valid.
6. FastAPI starts successfully.
7. Frontend loads through FastAPI.
8. UI fetches real summary data.
9. Health/status endpoints pass.
10. Automated Phase 1 tests pass.
11. README contains exact run/import steps.
12. No Phase 2 functionality has been implemented accidentally.
