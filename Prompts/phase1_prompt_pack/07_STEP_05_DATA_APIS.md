# STEP 5 — Data Status and Reference APIs

## Objective
Expose safe, summary-oriented FastAPI endpoints required by the Phase 1 UI and future phases.

## Prompt to coding agent
Implement only Step 5 of Phase 1.

### Router structure
Add routers such as:

```text
app/routers/data.py
app/routers/reference.py
```

Use repository/service separation:
- repositories contain SQL
- services compose business responses
- routers handle HTTP concerns

Do not put long SQL directly in route functions.

### Required endpoints

#### `GET /api/data/status`
Return per dataset:
- dataset_name
- table_name
- actual_rows
- expected_rows if configured
- reconciliation_status
- last_import_status
- last_import_started_at
- last_import_completed_at
- source_path
- rows_inserted
- rows_rejected

#### `GET /api/data/summary`
Return application-level summary:
- customer_count
- campaign_sales_count
- demographic_count
- distinct_campaigns
- distinct_products
- campaign_contact_date_min
- campaign_contact_date_max
- known_positive_count (`pu_label=1`)
- attributed_purchase_count
- database_path display-safe name, not arbitrary filesystem exposure
- schema_version

#### `GET /api/data/imports`
Return recent import runs.
Support safe pagination/limit, e.g. default 20, max 100.

#### `GET /api/reference/states`
Return state names/codes and counts from demographics, preferably sorted by count descending or state.
Do not return person rows.

#### `GET /api/reference/campaigns`
Return distinct campaign reference summary:
- campaign_id
- campaign_name
- campaign_type
- campaign_channel
- start/end
- observation count
- positive count

Support limit/search if useful, but do not overbuild.

#### `GET /api/reference/products`
Return distinct product reference summary:
- product_id
- product_name
- category/subcategory/tier
- observation count
- purchase count

### API response requirements
- use Pydantic response schemas where helpful
- consistent JSON naming
- appropriate HTTP error codes
- no raw SQLite exceptions in browser responses
- no giant unrestricted query responses

### Health enhancement
Enhance `/api/health` to report:
- application status
- database connectivity status
- schema presence/status

Do not make health query expensive.

### API documentation
FastAPI generated docs should remain available in development:
- `/docs`
- `/redoc` optional/default

### Tests
Create API tests for:
- data summary empty DB
- populated fixture DB
- data status
- reference campaigns
- reference products
- states
- imports limit validation
- health when DB available

### Step completion criteria
- all endpoints work against SQLite
- no fake values
- no oversized data dump endpoints
- tests pass

Update progress tracker and stop.
