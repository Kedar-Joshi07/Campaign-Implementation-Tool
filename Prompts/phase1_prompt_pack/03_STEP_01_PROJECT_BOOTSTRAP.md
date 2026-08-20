# STEP 1 — Project Bootstrap and Application Skeleton

## Objective
Create the initial project structure and a minimal runnable FastAPI + HTML/CSS/Vanilla JS application.

## Prompt to coding agent
Implement only Step 1 of Phase 1.

First read:
- `01_PHASE_1_FREEZE_AND_BOUNDARIES.md`
- `02_AGENT_OPERATING_INSTRUCTIONS.md`
- `11_PROGRESS_TRACKER.md`

### Required project structure
Create or align the repository to this POC structure:

```text
campaign_poc/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── schema.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── health.py
│   ├── services/
│   │   └── __init__.py
│   ├── repositories/
│   │   └── __init__.py
│   └── schemas/
│       └── __init__.py
├── frontend/
│   ├── index.html
│   ├── css/
│   │   ├── main.css
│   │   └── components.css
│   └── js/
│       ├── api.js
│       └── app.js
├── scripts/
├── data/
├── logs/
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

If the repository already has a sensible equivalent structure, adapt rather than duplicate.

### Backend requirements
1. Create FastAPI application in `app/main.py`.
2. Add title, version, and description.
3. Create `GET /api/health` returning JSON with at least:
   - status
   - application
   - version
4. Create `GET /api/version`.
5. Serve frontend static assets through FastAPI.
6. Serve `frontend/index.html` at `/`.
7. Add basic structured logging configuration.
8. Add central configuration in `app/config.py` using environment variables with safe defaults.

Minimum config fields:
- APP_NAME
- APP_VERSION
- APP_ENV
- HOST
- PORT
- DATABASE_PATH
- LOG_LEVEL

No secrets are needed.

### Frontend requirements
Build a clean static shell with:
- application title: `Campaign Implementation Intelligence`
- sidebar navigation
- Overview active
- Data Status
- Historical Analysis — disabled / later phase
- Model Training — disabled / later phase
- Audience Explorer — disabled / later phase
- Campaigns — disabled / later phase
- main content area
- placeholder cards that clearly say data will load after Phase 1 database setup; do not invent numbers

Use semantic HTML and reusable CSS classes.
No frontend framework.

### JavaScript requirements
`api.js`:
- generic GET helper using `fetch`
- JSON parsing
- clear error propagation

`app.js`:
- on load, call `/api/health`
- display backend connection state visibly
- do not hard-code API health status

### Requirements file
Include only needed Phase 1 dependencies, such as:
- fastapi
- uvicorn[standard]
- pytest
- httpx for FastAPI tests if required
- python-dotenv only if you choose to use it

The root `requirements.txt` must also include:

```text
-r data_generation_scripts/requirements_campaign_data.txt
```

This ensures one virtual environment and one `pip install -r requirements.txt`
install the application, test, and data-generator dependencies. Do not create a
separate virtual environment for the generator scripts or duplicate their
dependency declarations in the root file.

Do not add ML libraries yet.

### README
Add:
- prerequisite Python version
- virtual environment creation
- a single dependency installation command using the root `requirements.txt`
- start command, e.g. `uvicorn app.main:app --reload`
- browser URL

### Tests
Create at least:
1. `/api/health` returns 200
2. health payload contains expected status/application/version
3. root `/` returns HTML successfully

### Step completion criteria
- `uvicorn app.main:app --reload` starts without error
- `/api/health` works
- `/` displays frontend
- frontend can confirm backend health
- tests pass
- no database import implemented yet

After completion, update `11_PROGRESS_TRACKER.md` and stop.
