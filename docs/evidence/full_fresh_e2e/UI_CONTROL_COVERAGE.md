# UI Control Coverage (System Chrome)

- Generated at: 2026-09-04T12:42:59Z
- Browser: system Chrome
- Method: Playwright automation launched with system Chrome executable

## Summary

- Inventory controls: 107
- PASS: 20
- FAIL: 0
- EXCEPTION: 87

## Browser Errors

- Console errors: 1
- Unhandled page errors: 0
- Failed network requests: 0

Console error samples:
- Failed to load resource: the server responded with a status of 404 (Not Found)

## Accessibility Smoke

- Campaign name label present: True
- Campaign channel label present: True
- Audience save label present: True
- aria-live audience announcement: polite
- aria-live campaign status: polite
- aria-live export status: polite

## Responsive

- desktop_1920x1080: PASS (1920x1080)
- laptop_1366x768: PASS (1366x768)
- tablet_768x1024: PASS (768x1024)
- mobile_390x844: PASS (390x844)

## Curated Screenshots

- docs/evidence/full_fresh_e2e/screenshots/step5_overview.png
- docs/evidence/full_fresh_e2e/screenshots/step5_data_status.png
- docs/evidence/full_fresh_e2e/screenshots/step6_historical_analysis.png
- docs/evidence/full_fresh_e2e/screenshots/step7_model_training.png
- docs/evidence/full_fresh_e2e/screenshots/step9_audience_explorer.png
- docs/evidence/full_fresh_e2e/screenshots/step10_12_campaigns.png
- docs/evidence/full_fresh_e2e/screenshots/responsive_desktop_1920x1080.png
- docs/evidence/full_fresh_e2e/screenshots/responsive_laptop_1366x768.png
- docs/evidence/full_fresh_e2e/screenshots/responsive_tablet_768x1024.png
- docs/evidence/full_fresh_e2e/screenshots/responsive_mobile_390x844.png

## Control Map

| Selector | Label | Status |
|---|---|---|
| [data-view-target='overview'] | OV | EXCEPTION: not visible/reachable in current state |
| [data-view-target='data-status'] | DS | EXCEPTION: not visible/reachable in current state |
| [data-view-target='historical-analysis'] | HA | EXCEPTION: not visible/reachable in current state |
| [data-view-target='model-training'] | MT | EXCEPTION: not visible/reachable in current state |
| [data-view-target='audience-explorer'] | AE | EXCEPTION: not visible/reachable in current state |
| [data-view-target='campaigns'] | P7 | EXCEPTION: not visible/reachable in current state |
| #backend-status | Check backend connection | EXCEPTION: reachable but not explicitly exercised in this run |
| #overview-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #overview-refresh | Refresh data | PASS |
| #historical-analysis-cta | Analyze historical campaigns | EXCEPTION: reachable but not explicitly exercised in this run |
| #historical-analysis-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #historical-analysis-refresh | Refresh options and runs | PASS |
| #historical-analysis-reset | Reset to defaults | EXCEPTION: reachable but not explicitly exercised in this run |
| #analysis-name |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #contact-date-from |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #contact-date-to |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-filter |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #product-filter |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #product-category-filter |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #channel-filter |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-type-filter |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #contacted-only |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #analyze-population | Analyze Population | EXCEPTION: reachable but not explicitly exercised in this run |
| #recent-analyses-refresh | Refresh | EXCEPTION: reachable but not explicitly exercised in this run |
| button | Channels | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Categories | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Campaigns | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Products | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| #profile-dimension |  | EXCEPTION: reachable but not explicitly exercised in this run |
| button | Selected | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Known positive | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Unlabeled | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Historical baseline | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| #model-training-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #model-training-refresh | Refresh training workspace | PASS |
| #source-analysis-select |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #model-name-input |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #random-seed-input |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #validation-fraction-input |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #run-elkan-challenger-input |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #train-model-submit | Train Look-alike Model | EXCEPTION: reachable but not explicitly exercised in this run |
| #recent-model-runs-refresh | Refresh | EXCEPTION: reachable but not explicitly exercised in this run |
| #score-prospect-submit | Score Prospect Universe | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-explorer-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-explorer-refresh | Refresh audience workspace | PASS |
| #audience-prepare-submit | Prepare Audience Explorer | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-prepare-retry | Retry preparation | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-filter-reset | Reset filters | PASS |
| #audience-score-min |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-score-max |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-top-percentile |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-deciles |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-rank-bands |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-age-min |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-age-max |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-income-min |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-income-max |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-family-min |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-family-max |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-gender |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-state |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-marital-status |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-education |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-employment-status |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-resident-status |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-resident-type |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-type-of-employment |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-selection-all |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-selection-topn |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-target-count |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-apply-filters | Apply filters | PASS |
| #audience-clear-filter-chips | Clear active chips | EXCEPTION: reachable but not explicitly exercised in this run |
| #saved-audiences-refresh | Refresh | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-save-name |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-save-description |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-save-submit | Save audience | PASS |
| #saved-audience-reopen | Reopen definition | EXCEPTION: reachable but not explicitly exercised in this run |
| #saved-audience-use-campaign | Use in Campaign Builder | PASS |
| #audience-load-more | Load more | EXCEPTION: reachable but not explicitly exercised in this run |
| #audience-profile-dimension |  | EXCEPTION: reachable but not explicitly exercised in this run |
| button | Selected vs Universe | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| button | Selected vs Historical Positives | EXCEPTION: generic selector in inventory, covered via specific ID controls |
| #data-status-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #data-status-refresh | Run checks again | PASS |
| #campaigns-retry | Try again | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaigns-refresh | Refresh campaign workspace | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-1 | 1 | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-2 | 2 | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-3 | 3 | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-4 | 4 | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-audience-select |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-next-1 | Continue to Campaign Details | PASS |
| #campaign-name |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-description |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-channel |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-launch-date |  | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-step-back-2 | Back | PASS |
| #campaign-step-next-2 | Continue to Review | PASS |
| #campaign-step-back-3 | Back | PASS |
| #campaign-step-next-3 | Continue to Finalize / Export | PASS |
| #campaign-pii-ack |  | PASS |
| #campaign-step-back-4 | Back | PASS |
| #campaign-create-draft | Create Draft | PASS |
| #campaign-review-draft | Review | EXCEPTION: reachable but not explicitly exercised in this run |
| #campaign-finalize | Finalize Campaign | PASS |
| #campaign-export | Export Target List | PASS |
| #campaign-export-history-refresh | Refresh Export Status | PASS |
