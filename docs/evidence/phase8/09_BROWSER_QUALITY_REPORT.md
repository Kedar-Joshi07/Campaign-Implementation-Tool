# Phase 8 Step 9 Browser Quality Report

Generated at: 2026-09-08T15:09:30Z
Prompt: Prompts/phase8_release_assurance_system_browser_prompt_pack/09_STEP_09_BROWSER_ERROR_ACCESSIBILITY_RESPONSIVE_AND_STATE_TESTS.md

## Browser
- Name: system_chrome
- Executable: C:\Program Files\Google\Chrome\Application\chrome.exe
- Version: 152.0.7977.82
- Mode: headless

## Console and Network
- Total console errors: 1
- Total uncaught/page errors: 0
- Total failed requests: 0
- Total HTTP >=400 responses: 1
- Explained events: 2
- Unexplained console errors: 0
- Unexplained JS errors: 0
- Unexplained critical network failures: 0

## Accessibility Smoke
- Visible keyboard focus: {'focus_visible': True, 'focused_after_tab': 'data-status'}
- Tab and Shift+Tab traversal: {'tab_target': 'data-status', 'shift_tab_target': 'overview', 'changed': True}
- Enter and Space activation: {'enter_activated': True, 'space_activated': True}
- Labels for controls: {'missing': [], 'missing_count': 0}
- Validation focus and error summary: {'error_visible': True, 'error_focused': True, 'error_text': 'Campaign name is required.', 'active_element_id': 'campaign-step-error-summary', 'skipped': False}
- aria-live checks: [{'selector': '#backend-status', 'exists': True, 'ariaLive': 'polite', 'role': ''}, {'selector': '#analysis-run-announcement', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}, {'selector': '#campaigns-status-announcement', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}, {'selector': '#campaign-export-status-note', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}, {'selector': '#audience-announcement', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}, {'selector': '#audience-load-more-status', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}, {'selector': '#audience-save-status', 'exists': True, 'ariaLive': 'polite', 'role': 'status'}]
- Disabled-action explanation: {'finalize_disabled': True, 'export_disabled': True, 'help_text': 'Create or open a campaign to enable finalize and export checks.', 'help_present': True}
- Stepper semantics: [{'id': 'campaign-step-1', 'ariaCurrent': 'false', 'ariaSelected': 'false', 'tabIndex': -1}, {'id': 'campaign-step-2', 'ariaCurrent': 'step', 'ariaSelected': 'true', 'tabIndex': 0}, {'id': 'campaign-step-3', 'ariaCurrent': 'false', 'ariaSelected': 'false', 'tabIndex': -1}, {'id': 'campaign-step-4', 'ariaCurrent': 'false', 'ariaSelected': 'false', 'tabIndex': -1}]
- Table/control reachability: {'open_button_focusable': True, 'open_button_activates': True}
- No color-only status check: {'visible_badges': 5, 'badges_missing_text': 0}
- Reduced motion behavior: {'reduce_media_query_matches': True, 'navigation_still_operational': True}

## Responsive Validation
### 1920x1080
- overview: control=#overview-refresh exists=True within_viewport=True horizontal_overflow_px=0
- data-status: control=#data-status-refresh exists=True within_viewport=True horizontal_overflow_px=0
- historical-analysis: control=#historical-analysis-refresh exists=True within_viewport=True horizontal_overflow_px=0
- model-training: control=#model-training-refresh exists=True within_viewport=True horizontal_overflow_px=0
- audience-explorer: control=#audience-explorer-refresh exists=True within_viewport=True horizontal_overflow_px=0
- campaigns: control=#campaigns-refresh exists=True within_viewport=True horizontal_overflow_px=0
### 1366x768
- overview: control=#overview-refresh exists=True within_viewport=True horizontal_overflow_px=0
- data-status: control=#data-status-refresh exists=True within_viewport=True horizontal_overflow_px=0
- historical-analysis: control=#historical-analysis-refresh exists=True within_viewport=True horizontal_overflow_px=0
- model-training: control=#model-training-refresh exists=True within_viewport=True horizontal_overflow_px=0
- audience-explorer: control=#audience-explorer-refresh exists=True within_viewport=True horizontal_overflow_px=0
- campaigns: control=#campaigns-refresh exists=True within_viewport=True horizontal_overflow_px=0
### 1024x768
- overview: control=#overview-refresh exists=True within_viewport=True horizontal_overflow_px=0
- data-status: control=#data-status-refresh exists=True within_viewport=True horizontal_overflow_px=0
- historical-analysis: control=#historical-analysis-refresh exists=True within_viewport=True horizontal_overflow_px=0
- model-training: control=#model-training-refresh exists=True within_viewport=True horizontal_overflow_px=0
- audience-explorer: control=#audience-explorer-refresh exists=True within_viewport=True horizontal_overflow_px=0
- campaigns: control=#campaigns-refresh exists=True within_viewport=True horizontal_overflow_px=0
### 768x1024
- overview: control=#overview-refresh exists=True within_viewport=True horizontal_overflow_px=0
- data-status: control=#data-status-refresh exists=True within_viewport=True horizontal_overflow_px=0
- historical-analysis: control=#historical-analysis-refresh exists=True within_viewport=True horizontal_overflow_px=0
- model-training: control=#model-training-refresh exists=True within_viewport=True horizontal_overflow_px=0
- audience-explorer: control=#audience-explorer-refresh exists=True within_viewport=True horizontal_overflow_px=0
- campaigns: control=#campaigns-refresh exists=True within_viewport=True horizontal_overflow_px=0
### 390x844
- overview: control=#overview-refresh exists=True within_viewport=True horizontal_overflow_px=0
- data-status: control=#data-status-refresh exists=True within_viewport=True horizontal_overflow_px=0
- historical-analysis: control=#historical-analysis-refresh exists=True within_viewport=True horizontal_overflow_px=0
- model-training: control=#model-training-refresh exists=True within_viewport=True horizontal_overflow_px=0
- audience-explorer: control=#audience-explorer-refresh exists=True within_viewport=True horizontal_overflow_px=0
- campaigns: control=#campaigns-refresh exists=True within_viewport=True horizontal_overflow_px=0

## State Coverage
- Loading state: {'campaigns_loading_seen': True, 'state_after_loading': 'no_eligible'}
- Empty state: {'campaigns_no_eligible_seen': True, 'state_after_empty': 'no_eligible'}
- Retryable error state: {'campaigns_backend_unavailable_seen': True, 'state_after_retry': 'no_eligible'}
- Stale/historical read-only: {'stale_candidate_found': True, 'source': 'injected_response', 'stale_message_seen': True, 'use_in_campaign_disabled': True, 'stale_message': 'Synthetic source/model lineage is stale for Step 9 state coverage.'}
- Long-running/completed/failed/aborted export: {'started_seen': True, 'failed_and_aborted_seen': True, 'completed_seen': True}
- Long-running/failed job states: {'running_seen': True, 'failed_seen': True, 'restored_state': 'workspace'}

## Outcome
- Overall status: PASS
- Browser quality gate: PASS
- Browser quality failures: {'accessibility': [], 'responsive': [], 'state_coverage': []}
- Global inventory controls updated: 7
- Final targets: unexplained_console_errors=0, unexplained_critical_network_failures=0