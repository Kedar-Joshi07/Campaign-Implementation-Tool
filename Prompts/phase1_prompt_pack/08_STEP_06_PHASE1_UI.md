# STEP 6 — Phase 1 UI: Overview and Data Status

## Objective
Turn the static shell into a functional Phase 1 UI backed by real API data.

## Prompt to coding agent
Implement only Step 6 of Phase 1.

### Visual direction
Build a clean analytics/product POC interface:
- professional neutral background
- dark or clearly differentiated navigation area
- generous spacing
- reusable cards
- clear typography
- restrained accent color
- responsive enough for modern desktop/laptop screens

Do not spend excessive time on pixel-perfect mobile behavior.

### Navigation
Functional in Phase 1:
- Overview
- Data Status

Visible but disabled/labeled later phase:
- Historical Analysis
- Model Training
- Audience Explorer
- Campaigns

### Overview page
Fetch `/api/data/summary` and display real values:
1. Historical Customers
2. Campaign Records
3. Prospect Universe
4. Distinct Campaigns
5. Distinct Products
6. Known Positive Records
7. Historical campaign date range
8. Database health indicator

If a dataset is not loaded, display a clear state such as:
`Not loaded`
not `0` if zero would be misleading.

Add a small "Data readiness" section summarizing:
- Customer data: Ready / Not Loaded / Warning / Error
- Campaign Sales: Ready / ...
- Demographics: Ready / ...

### Data Status page
Fetch `/api/data/status` and `/api/data/imports`.

Show dataset cards/table with:
- dataset
- expected rows
- actual rows
- status badge
- last import
- source filename/path display-safe value
- rejected row count

Show recent import history beneath it.

### Frontend architecture
Keep JS modular:
- `api.js` for HTTP
- `app.js` for shell/navigation
- add `overview.js`
- add `data-status.js`

Do not put all behavior into one file.

### UX requirements
- loading indicator/skeleton/simple spinner while fetching
- clear backend-unavailable message
- retry action where reasonable
- error banner component
- format large numbers with thousands separators
- format dates readably
- status badge classes

### No charts requirement
Charts are optional in Phase 1. Do not add Chart.js merely to decorate the page.
The purpose of this step is trustworthy system/data readiness presentation.

### Accessibility basics
- buttons are real buttons
- navigation usable with keyboard
- labels/text contrast reasonable
- status should not rely only on color

### Tests/checks
Automated frontend testing framework is not required.
Perform documented manual checks:
- backend online
- backend offline error state
- empty DB
- loaded fixture DB
- navigation Overview <-> Data Status

Backend tests must still pass.

### Step completion criteria
- UI displays real API values
- no hard-coded dataset KPI values
- data status is understandable
- later-phase features clearly disabled/not implemented
- application remains one-command runnable

Update progress tracker and stop.
