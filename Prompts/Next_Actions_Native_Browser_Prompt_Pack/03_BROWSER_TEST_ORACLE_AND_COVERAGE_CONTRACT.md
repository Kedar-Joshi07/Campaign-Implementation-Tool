# Browser coverage and causal evidence contract

## Denominators

Maintain three inventories: production business controls; retained-component controls; backend workflows/API-only capabilities. Static seeds in STATIC_UI_CONTROL_SEEDS.json include forms/details containers as well as direct controls; classify those instead of claiming every seed is a button. Regenerate runtime controls from real DOM states, JS event bindings, dynamic menus/lists/rows, channel/profile alternatives and hidden view definitions. Static source parsing is only a seed.

Each interactive control/conditional variant needs: stable identity, page/scope, selector or accessible locator, source, label, type, enable/show conditions, fixture, scenario IDs, expected UI result, expected API/worker/DB/file effects, independent oracle, actual observations, status and evidence pointer.

Status: PASS, FAIL, BLOCKED, NOT_RUN, HIDDEN_CONTRACT_VERIFIED, or NOT_IMPLEMENTED_WITH_SOURCE_PROOF. A container can map to tested child/form scenarios. Never use blanket “legacy”, “disabled” or “mutually exclusive” as a PASS. Each alternate mode/channel must be selected and exercised in its valid fixture. A disabled guard gets a negative test plus a positive test where its prerequisites can validly be met. Missing browser/environment is BLOCKED.

Business coverage GO requires no FAIL/BLOCKED/NOT_RUN for implemented business controls or required states. Retained-component GO requires no untested implemented retained controls, even though those views are correctly hidden in normal navigation. A not-implemented placeholder is explicitly listed and is not counted as implemented success. Overall “all UI” GO requires both inventories closed and backend side effects proved; do not report business-only GO as all-UI GO.

## Causal action record

For every functional browser case record:
- UI action and visible enabled/disabled state;
- actual network method/path/status and sanitized payload semantics;
- request/run/attempt/context/job/profile/snapshot IDs as applicable;
- observed durable state progression and bounded timestamps;
- database before/after assertions, actual row counts and currentness;
- created/preserved artifact/file hash and count where relevant;
- independent expected result and actual result;
- console/page error findings and classified network errors;
- screenshot/trace references for private synthetic QA inspection, without PII/secrets.

Pure UI controls (sidebar, disclosures, dropdown search) may have no API/DB side effect; verify none unexpectedly occurs. A backend-only call is not proof that the corresponding UI control works. Browser API setup is allowed to create a scenario prerequisite, but the tested action must be performed through the control. Auxiliary SQL queries inspect outcomes, not replace the action.

## Independent oracles

Freeze fixtures before training/testing. Use row-by-row fixture predicates or independent SQL for eligibility/dedup. A separately written scalar distance calculation may verify sampled similarity scores; do not call production selection/count helpers to compute their own expected output. Verify cumulative thresholds versus v2 discrete bands independently. Check file headers, finite full-precision values, person dedup, count/hash, winning products, versioned provenance and CSV formula protection.

Expected network failures/422s for negative cases are logged and asserted. Unexpected 4xx/5xx, console/page exceptions, lost requests, unhandled promises and false READY remain defects. Do not hide these by emptying error arrays or failing to attach listeners until after action.

## Native and retained-component modes

Primary business run: installed Chrome/Edge, headed desktop, clean isolated profile, actual production frontend/router/API/lifespan/workers on bounded QA DB. Browser binary/path/product version and headless flag are evidence. Linux CI may use the same system browser headless but that is a separate automation result; it cannot substitute for a requested native headed run.

Retained run: test-only isolated harness loads the same retained markup/controllers/event handlers and actual APIs. It may provide test navigation into intentionally hidden components. No production navigation change and no authentication implication. Label it RETAINED_COMPONENT_HARNESS; verify normal production hashes keep those views hidden/fallback. Do not claim setting element.hidden=false proves user accessibility.

## No-5M evidence

Record every source and DB actual row count; each worker's admitted population and scope; pre/post generation/job counts; guard rejections and zero canonical-scale scoring dispatches. Default dataset 2,000; named qualification fixture<=20,000. All resources/paths isolated. This contract excludes 5M scoring and 5M performance from the browser verdict. A small fixture does not replace earlier 5M certification.
