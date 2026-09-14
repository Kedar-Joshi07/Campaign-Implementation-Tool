# Phase 10 Real System-Browser Business Flow Certification

Generated: 2026-09-14

## Step result

`PASS_STEP_14_REAL_SYSTEM_BROWSER_BUSINESS_FLOW_CERTIFICATION`

All six required business-flow scenarios passed sequentially in the installed
Chrome browser against a disposable Step 14 database and artifact root. No
canonical production database, source, model, scoring, rank or campaign file
was used as a test input or modified by the certification.

## Execution boundary

- Headed business-flow browser: installed Chrome controlled through the live
  system-browser connection.
- Screenshot/independent telemetry browser: installed system Chrome
  `153.0.8010.36` at
  `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- App URL: `http://127.0.0.1:8014/`.
- Isolated runtime: `tmp/phase10-step14/`.
- Fixture size: 40 historical customers, 44 campaign observations and 80
  initial potential customers; two controlled demographic refreshes ended at
  82 potential customers.
- Starting repository commit: `7e54754053bf998e65c59a36c0096d5404bb6479`.

## Required scenario results

| Scenario | Result | Browser evidence |
|---|---|---|
| A. READY reuse | PASS | A business user completed Campaign Details, Campaign Context and Targeting Preferences. The existing complete generation was reused, Step 4 opened automatically, and the exact preview displayed 78 people. No raw technical identifier appeared in the default business surface. |
| B. Preparation required | PASS | A controlled demographic-source change produced `analysis=REUSE`, `model=REUSE`, `scoring=BUILD`, `rank=BUILD`. The UI displayed `Preparing your Target Group`, 0% queued progress and business stage labels. The user navigated to Home, returned to Create Campaign, reconnected to the persisted work, and reached READY with an exact 79-person preview. |
| C. Insufficient history | PASS | P2 Acquisition/Discount reached durable BLOCKED at the history eligibility gate. The browser showed plain `Not enough history` copy, disabled Review & Save, exposed `Back to Campaign Context`, showed no estimated/fabricated preview and performed no fallback or automatic broadening. Back reopened the unchanged P2/Acquisition inputs. |
| D. Deterministic failure/retry | PASS | A one-time controlled submitter failure produced the safe message `We could not finish preparing targeting intelligence. Your campaign inputs are saved.` No stack or filesystem path appeared. `Try again` displayed live progress (observed at 89%, `Potential customers`) and recovered to READY with an exact 80-person preview. |
| E. Delivery-channel reuse | PASS | Delivery changed from Email to Direct Mail with all Modeling Context dimensions unchanged. The exact explanation changed to Direct Mail. Model runs remained 1 and scoring runs remained 3; no second model/scoring build occurred. |
| F. Targeting-filter change | PASS | Match strength changed from Good to Very Strong and demographic criteria were added. The exact preview changed from 80 people to the exact zero state. Model runs remained 1, scoring runs remained 3, generations remained 3 and orchestrations remained 6. |

Only the required controlled Scenario D failure is terminal FAILED. The
insufficient-history branch is terminal BLOCKED. Every certification outcome
uses only PASS, FAIL or JUSTIFIED_EXCLUSIVE; there is no reachable NOT_RUN.

## Durable lineage and no-heavy-work checks

The isolated database ended with:

| Durable object | Count |
|---|---:|
| Campaign Contexts | 2 |
| Historical analysis runs | 2 (one eligible P1 analysis and one blocked P2 analysis) |
| Model runs | 1 |
| Scoring runs | 3 (initial plus two controlled demographic refreshes) |
| READY intelligence generations | 3 |
| Orchestration runs | 6 |

The delivery-channel and targeting-filter scenarios did not change any of
these counts. The P1 READY generations consistently reused analysis run 1 and
model run 1. The required failure stored only technical class `RuntimeError`
server-side and returned stable business-safe copy to the browser.

## Technical-details boundary

`View technical details` was closed by default and no run or generation ID was
present in the normal business surface. It opened only after explicit keyboard
activation and showed status/currentness, analysis/model/scoring provenance,
selected model candidate, contract versions, source checksums, artifact hash
and audience-filter hash. The rendered details contained no email, phone,
address, first-name or last-name field. The privacy-safe preview itself showed
Potential Customer IDs and aggregate attributes but no contact PII.

## Dynamic UI inventory

The live DOM inventory covered 84 controls/states, including 31 form controls.
It covers the five-step shell, context and targeting inputs, four match-strength
choices, advanced targeting disclosure, active-filter chips, loading/progress,
READY/BLOCKED/FAILED states, retry/back actions, technical disclosure, exact
preview metrics, comparison, profile, privacy-safe results and the Phase 9
review/save boundary. Each item has a permitted terminal result in
`docs/evidence/phase10/14_UI_COVERAGE.json`.

## Responsive certification

| Viewport | Result | Horizontal overflow |
|---|---|---:|
| 1920x1080 | PASS | 0 px |
| 1366x768 | PASS | 0 px |
| 1024x768 | PASS | 0 px |
| 768x1024 | PASS | 0 px |
| 390x844 | PASS | 0 px |

The active Target Group Preview remained present at every size. The viewport
override was reset after certification.

## Accessibility certification

- PASS: wizard Back/Next, failure retry, blocked Back action, match-strength
  choice and technical disclosure were operated from the keyboard.
- PASS: focus moved to the active step heading and to BLOCKED/FAILED status
  containers; all four error containers are focusable alerts.
- PASS: all 31 input/select/textarea controls had a native label or ARIA label;
  unlabeled count was zero.
- PASS: planner announcements, intelligence state, empty preview, pagination and
  save success use polite live regions.
- PASS: the progressbar has a business label, minimum 0, maximum 100, current
  value and value text; active preparation uses `aria-busy=true`.
- PASS: loading states use status semantics and errors use alert semantics.

## Telemetry

Application-attributed unexplained JavaScript exceptions: **0**. Page errors:
**0**. Critical network failures: **0**. Failed requests: **0**. Unexplained
console errors: **0**.

Three explained observations are retained rather than hidden:

1. The independent screenshot run observed one handled 404 for the Campaign
   Draft lookup before a draft existed. This is the expected no-draft probe,
   not a critical request, and caused no page error (`JUSTIFIED_EXCLUSIVE`).
2. The connected Chrome controller reported eight identical message-channel
   closure messages at the same millisecond during viewport overrides. They
   had no application stack/module/request and were absent from the independent
   installed-Chrome run (`JUSTIFIED_EXCLUSIVE`).
3. Scenario D intentionally returned one safe preparation failure before retry
   (`JUSTIFIED_EXCLUSIVE`).

The detailed classification is in
`docs/evidence/phase10/14_SYSTEM_BROWSER_TELEMETRY.json`.

## Screenshots

- [1920x1080](system_browser/step14/screenshots/phase10-ready-1920x1080.png)
- [1366x768](system_browser/step14/screenshots/phase10-ready-1366x768.png)
- [1024x768](system_browser/step14/screenshots/phase10-ready-1024x768.png)
- [768x1024](system_browser/step14/screenshots/phase10-ready-768x1024.png)
- [390x844](system_browser/step14/screenshots/phase10-ready-390x844.png)

The headed session additionally captured the READY reuse, insufficient-history
and deterministic-failure states during the live browser run. The five saved
responsive images are independently reproducible with the installed-Chrome
capture harness.

## Machine-readable evidence and reproducibility

- `docs/evidence/phase10/14_UI_COVERAGE.json`
- `docs/evidence/phase10/14_SYSTEM_BROWSER_TELEMETRY.json`
- `docs/evidence/phase10/14_SYSTEM_BROWSER_SCREENSHOTS.json`
- `scripts/validation/browser/phase10_step14_fixture.py`
- `scripts/validation/browser/phase10_step14_server.py`
- `scripts/validation/browser/capture_phase10_step14_screenshots.py`

## Stop boundary

Step 14 stops after real system-browser business-flow, responsive,
accessibility and telemetry certification. Step 15+ full-scale,
observability/performance, CI or freeze work was not started.

`STOP_AFTER_STEP_14`
