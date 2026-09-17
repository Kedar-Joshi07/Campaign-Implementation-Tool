# Phase 11 Step 7 — Reusable Searchable Multi-Select

Date: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/07_STEP_07_REUSABLE_SEARCHABLE_MULTISELECT_DROPDOWN.md`

Baseline HEAD: `881b5a652e869af1415547de452b9cccd2c18293`. Local, uncommitted implementation evidence; this is not release freeze or remote CI certification. Earlier Phase 11 worktree changes are preserved.

## Result

`PASS_STEP_07_REUSABLE_SEARCHABLE_MULTISELECT`

One focused Vanilla-JS component, `frontend/js/components/multi-select-dropdown.js`, enhances all 16 required fields. Large native lists remain in source as a progressive-enhancement fallback and form/state bridge, but are hidden from the enhanced interface. Existing legacy/advanced UI components are not deleted or rewritten.

## Component contract

- Caller-supplied options only: strings or `{value, label, disabled}` records. No hardcoded business lists, backend calls, modeling logic, or persistence in the component.
- Public class `MultiSelectDropdown` and helpers `enhanceMultiSelect`, `refreshMultiSelect`, `setMultiSelectState`, `focusMultiSelect`.
- Instance methods `setOptions`, `setValues`, `values`, `setState`, `open`, `close`, `refresh`, `destroy`. Duplicate option values and unknown explicit selections are rejected before mutation. Option refresh preserves selected values still supplied by the caller; it does not emit a persistence event.
- Existing native selects keep names, values, selected options, required/custom validation, FormData participation, and existing change-event/state handlers. Enhancement is idempotent through a WeakMap. Destroy removes external listeners and restores native visibility, label association, tabindex and ARIA-hidden state.
- Associated visible label and collapsed selected-count summary; searchable panel with native checkbox multi-selection; compact chips with individual removal. At most five selection chips plus one remainder summary are rendered; every option can be reviewed/toggled in the panel.
- Case-insensitive search matches labels and raw values. Filtering does not clear hidden selections or trigger form-state updates, saves, preparation, or requests.
- **Select All visible** adds all currently filtered, enabled options to existing selections. It preserves selections outside the filter and skips unavailable options. The button displays the available matching count.
- **Clear All** removes every selection, including those outside the current filter. It does not clear the search query. Individual removal remains available through chips or checkboxes.
- Disabled, loading and error states disable interaction, close the panel, and include explicit readable status, not color alone. Unavailable options are disabled and labelled Unavailable. Empty lists and zero search matches have distinct text.

## Accessibility and focus

- Native labelled checkboxes provide multi-selection semantics; the popup is a labelled non-modal `dialog` with a labelled options `group`, not a listbox containing incompatible interactive descendants.
- Trigger exposes `aria-haspopup`, `aria-expanded`, `aria-controls`, label, selection summary/help/status descriptions. The component group exposes loading/disabled state. Status is live; invalid native selection validation transfers focus/message to the visible trigger.
- Enter/Space activate the trigger. Arrow Down/Up can open at the first/last available option. Search Arrow Down moves to options. Roving checkbox navigation supports Up/Down, Home/End, wraps and skips disabled/filtered choices. Space uses native checkbox toggling; Enter toggles without submitting the form.
- Escape closes and restores trigger focus. Tab leaving the component closes without trapping or stealing focus. An actual outside pointer click closes while preserving the clicked control's focus. Opening another dropdown closes the first.
- Removing a chip restores trigger focus. Becoming blocked while focused transfers focus to the labelled component group, never leaving it inside the hidden popup.
- Visible focus outlines, readable selection counts and status copy supplement checkbox/disabled states. Existing progressive disclosure, wizard accessibility and compact scalar controls remain intact.

## Field integration

| Required field | Retained native selector |
|---|---|
| Products | `#planner-context-products` |
| Campaign Types | `#planner-context-types` |
| Campaign Categories | `#planner-context-categories` |
| Offer Types | `#planner-context-offers` |
| Historical Campaign Channels | `#planner-context-historical-channels` |
| Gender | `#planner-targeting-genders` |
| Age Groups | `#planner-targeting-age-groups` |
| State | `#planner-targeting-states` |
| Region shortcut | `#planner-targeting-regions` |
| Income Groups | `#planner-targeting-income-groups` |
| Marital Status | `#planner-targeting-marital-statuses` |
| Education | `#planner-targeting-education-levels` |
| Employment Status | `#planner-targeting-employment-statuses` |
| Resident Status | `#planner-targeting-resident-statuses` |
| Resident Type | `#planner-targeting-resident-types` |
| Type of Employment | `#planner-targeting-employment-types` |

`campaign-context.js` and `business-targeting.js` explicitly refresh the component after backend options, reopened/saved selection state, Region-added states, individual criterion removal and global clear. Existing backend values, URLs, payloads, additive Region semantics and state-based saved targeting are preserved. Dropdown search/checkbox input events cannot bubble into the business form's generic input handler; selection dispatches one native change event.

Delivery Channel stays a native single select. Family size, Match Strength, Top Percentage and TOP_N stay appropriate existing scalar/radio controls. The five-step planner remains; the Step 8 single-form work is not implemented or claimed here.

## Sequential verification

Final command:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_frontend.py tests/test_phase3_hardening.py tests/test_phase9_campaign_context.py tests/test_phase9_business_targeting.py tests/test_phase9_progressive_disclosure.py tests/test_phase9_accessibility_responsive.py tests/test_phase9_validation_and_states.py tests/test_phase10_business_ui.py tests/test_phase11_business_navigation.py tests/test_phase11_multi_select_dropdown.py
```

Result: **120 passed in 142.24 seconds**. This includes **15 new Step 7 cases** (one source/adapter contract and 14 browser cases), plus the prior Step 6 navigation cases. Intermediate reruns overlap; counts are not additive.

Final hygiene passed: targeted Python compileall, tracked Step 7 textual `git diff --check`, and trailing-whitespace scans of the new component/tests/evidence. The API-router/application-entrypoint diff was empty. Git emitted only its existing README CRLF-to-LF normalization warning.

New coverage verifies:

- all 16 adapters and native fallback source, generic supplied options, safe text-only labels;
- filtered bulk add, preservation of nonmatching selections, clear across the filter, individual chips and raw FormData values;
- keyboard toggle/navigation, Escape, Tab, outside click, label activation, and only one open dropdown;
- disabled/loading/error/recovery, unavailable/empty/no-match states;
- native required validation, programmatic changes, reset, destroy and idempotent enhancement;
- duplicate/unknown rejection and selected-value preservation during option refresh;
- all 16 live field controls against option payloads produced by the real option service over a tiny temporary fixture; browser saves/GET reopen are intercepted, not real persisted campaign/search runs;
- exact unchanged context/criteria request shapes, additive Region-to-State updates, active criterion-chip removal, global clear, save/reopen, and search leaving the complete planner state unchanged;
- load-error/retry recovery without duplicate component creation;
- realistic and stress-count latency, bounded rendering and stable checkbox nodes.

The installed **system Chrome** runs headless through the existing repository launcher with temporary profiles. Every browser request is intercepted, including unrelated intelligence/preparation/result routes, which receive an explicit safe unavailable response. No application server or canonical analytical job is connected. This is component/navigation certification, not the later real-backend full business-flow certification. Browser tests have the existing `browser` marker and are excluded by the ordinary CI non-browser gate; no remote CI-green claim is made.

### Performance evidence

One hundred alternating search events per list, followed by bulk select/clear. Product metadata comes from the existing 48-product catalog builder (no generated rows/files); State names come from the existing 51-state/DC Region mapping. A separate 500-option list stress-tests the generic component, not an expanded backend business contract.

Measured on the same final component revision during the preceding verification; final rerun also passed these budgets:

| List | Options | Setup ms | Search p95 ms | Maximum search ms | Bulk select ms |
|---|---:|---:|---:|---:|---:|
| Products | 48 | 2.7 | 0.3 | 2.9 | 1.5 |
| States/DC | 51 | 2.5 | 0.5 | 0.9 | 0.9 |
| Generic stress | 500 | 12.6 | 1.7 | 4.4 | 5.0 |

Enforced budgets: setup <500 ms, p95 search <50 ms, maximum search <250 ms, bulk select <250 ms. All checkbox nodes stayed identical; **zero checkbox-subtree child-list mutations** occurred during the repeated searches and selections. Searches emitted **zero** form input/change/submit events; bulk select plus clear emitted exactly **two** change events and no input/submit events. No polling, MutationObserver-driven synchronization, or selection-triggered option rebuild loop exists in production. Filtering is linear in option count; collapsed chip rendering is bounded.

### Verification corrections and isolation

The first browser pass exposed two harness defects: its outside target sat underneath the open overlay, and a broad API mock treated an unrelated preparation request as a context save. A genuinely outside target and exact context/criteria route matching corrected both; the focused rerun passed. An added label test initially assumed trigger focus, but native button-label activation correctly opens the panel and focuses Search; the assertion was corrected. No production defect was bypassed or disabled.

An intermediate run also exposed an older validation TestClient fixture still using the runtime database for startup verification. Logs reported schema 17 verified, zero failed stale jobs, zero resumed orchestrations and zero stale export reconciliations. No canonical analytical work started. That fixture, plus the context/targeting API fixtures, now points application startup and request dependencies at the same tiny temporary database. The final passing suite uses those isolated paths. This evidence does not claim the runtime database was byte-for-byte untouched by that intermediate startup verification.

## Scope and stop

Step 7 changes the shared component, its two frontend adapters, component CSS/help/cache labels, scoped tests and documentation. No backend API implementation, schema, repository, analytical contract, canonical source, model, score, rank, result snapshot or export implementation is changed by this step. Existing bounded regression fixtures may exercise their established tiny analytical/service paths; no canonical generation, import, training, scoring, rank build, result build or export was run.

Earlier Phase 11 changes remain preserved and uncommitted. No staging, commit, push or freeze was performed.

`STOP_AFTER_STEP_07`

Step 8 and subsequent prompts have not started.
