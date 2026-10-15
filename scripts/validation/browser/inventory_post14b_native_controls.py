"""Read-only runtime control discovery in the bounded native QA browser.

This creates a test denominator; observing a control never marks it functional PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    QA_PARENT, REPOSITORY_ROOT, prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture, launch_system_browser_session,
)


BUSINESS = ("home", "find-potential-customers", "results")
RETAINED = (
    "saved-target-groups", "campaigns", "insights", "historical-analysis",
    "audience-explorer", "data-status", "model-training",
)
VIEW_ELEMENT = {
    "home": "overview-view", "find-potential-customers": "campaign-planner-view",
    "results": "results-view", **{name: f"{name}-view" for name in RETAINED},
}
READY_LOADING = {
    "saved-target-groups": "business-target-groups-loading",
    "campaigns": "campaigns-state-loading",
    "historical-analysis": "historical-options-loading",
    "audience-explorer": "audience-explorer-loading",
    "model-training": "model-training-loading",
}
CONTROL_JS = """() => [...document.querySelectorAll(
  'button,a,input,select,textarea,summary,[role="tab"],[role="menuitem"],[role="button"]'
)].filter((element) => {
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== 'hidden';
}).map((element) => {
  const view = element.closest('[data-view]');
  const label = element.getAttribute('aria-label') || element.labels?.[0]?.textContent ||
    element.getAttribute('title') || element.textContent || element.getAttribute('placeholder') || '';
  const selector = (() => {
    if (element.id) return `#${CSS.escape(element.id)}`;
    if (element.dataset.viewTarget) return `[data-view-target="${CSS.escape(element.dataset.viewTarget)}"]`;
    const segments = [];
    for (let current = element; current && current.nodeType === 1; current = current.parentElement) {
      if (current.id) {
        segments.unshift(`#${CSS.escape(current.id)}`);
        break;
      }
      const siblings = [...(current.parentElement?.children || [])]
        .filter(sibling => sibling.tagName === current.tagName);
      const nth = siblings.indexOf(current) + 1;
      segments.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${nth})`);
    }
    return segments.join(' > ');
  })();
  return {
    tag: element.tagName.toLowerCase(), type: element.getAttribute('type') || '',
    id: element.id || null, name: element.getAttribute('name') || null,
    role: element.getAttribute('role') || null, view: view?.dataset.view || 'global',
    label: label.replace(/\\s+/g, ' ').trim().slice(0, 160),
    selector,
    disabled: element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true',
    expanded: element.getAttribute('aria-expanded'),
    value: element.tagName === 'SELECT' ? element.value : null,
    option_count: element.tagName === 'SELECT' ? element.options.length : null,
  };
})"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    parser.add_argument("--include-conditional", action="store_true")
    args = parser.parse_args()
    root = args.qa_root.resolve() if args.qa_root else prepare_qa_root()
    if root.parent != QA_PARENT.resolve():
        raise ValueError("Control discovery requires a dedicated bounded QA root.")
    print(f"Inventory QA root: {root}", flush=True)
    process = None
    report = {
        "scope": "NATIVE_RUNTIME_CONTROL_DISCOVERY_ONLY", "status": "NOT_RUN",
        "qa_root": str(root), "headless": False, "views": [],
        "source_sha256": {
            item: _sha(REPOSITORY_ROOT / item)
            for item in ("frontend/index.html", "frontend/js/view-contract.js")
        },
        "static_seed_count": json.loads((REPOSITORY_ROOT /
            "Prompts/Next_Actions_Native_Browser_Prompt_Pack/STATIC_UI_CONTROL_SEEDS.json"
        ).read_text(encoding="utf-8"))["control_count"],
    }
    try:
        process, port = start_qa_server(root, timeout_seconds=90.0)
        report["loopback_port"] = port
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)
                responses = []

                def on_response(response):
                    parsed = urlsplit(response.url)
                    if parsed.path.startswith("/api/"):
                        responses.append({"method": response.request.method,
                                          "path": parsed.path, "status": response.status})

                page.on("response", on_response)
                try:
                    for scope, path, names in (
                        ("BUSINESS_NATIVE", "/", BUSINESS),
                        ("RETAINED_COMPONENT_HARNESS", "/qa-retained", RETAINED),
                    ):
                        for name in names:
                            page.goto(f"http://127.0.0.1:{port}{path}#{name}",
                                      wait_until="domcontentloaded")
                            page.wait_for_function(
                                "id => { const visible = [...document.querySelectorAll('[data-view]')]"
                                ".filter(v => !v.hidden); return visible.length === 1 && visible[0].id === id; }",
                                arg=VIEW_ELEMENT[name], timeout=20_000,
                            )
                            page.wait_for_load_state("networkidle", timeout=20_000)
                            if name == "find-potential-customers":
                                page.locator("#business-search-form").wait_for(state="visible")
                            if name == "results":
                                page.locator("#results-view").wait_for(state="visible")
                            if name in READY_LOADING:
                                page.locator(f"#{READY_LOADING[name]}").wait_for(
                                    state="hidden", timeout=90_000)
                            controls = page.evaluate(CONTROL_JS)
                            report["views"].append({
                                "scope": scope, "route": name,
                                "url_path": urlsplit(page.url).path,
                                "page_title": page.locator("#page-title").inner_text(),
                                "visible_control_count": len(controls), "controls": controls,
                                "status": "DISCOVERED_NOT_TESTED",
                            })
                    if args.include_conditional:
                        with sqlite3.connect(root / "state" / "qa.db") as connection:
                            rows = connection.execute(
                                "SELECT search_run_id,selection_contract_version,selected_count "
                                "FROM campaign_search_runs WHERE status='COMPLETED' "
                                "ORDER BY selection_contract_version,selected_count DESC,search_run_id"
                            ).fetchall()
                        seen_states = set()
                        for run_id, contract_version, selected_count in rows:
                            state = (contract_version, selected_count == 0)
                            if state in seen_states:
                                continue
                            seen_states.add(state)
                            page.goto(f"http://127.0.0.1:{port}/#results/{run_id}",
                                      wait_until="domcontentloaded", timeout=60_000)
                            page.wait_for_function(
                                "id => document.querySelector('#result-detail-run-id')?.textContent"
                                ".includes(`Search #${id}`) && "
                                "document.querySelector('#result-detail-badge')?.dataset.status === 'COMPLETED'",
                                arg=run_id, timeout=60_000,
                            )
                            controls = page.evaluate(CONTROL_JS)
                            report["views"].append({
                                "scope": "BUSINESS_NATIVE_CONDITIONAL_DISCOVERY",
                                "route": f"results/{run_id}", "state": {
                                    "selection_contract_version": contract_version,
                                    "zero_result": selected_count == 0,
                                },
                                "url_path": urlsplit(page.url).path,
                                "page_title": page.locator("#page-title").inner_text(),
                                "visible_control_count": len(controls), "controls": controls,
                                "status": "DISCOVERED_NOT_TESTED",
                            })
                        report["conditional_result_states"] = sorted(
                            [{"contract_version": version, "zero_result": zero}
                             for version, zero in seen_states],
                            key=lambda item: (item["contract_version"], item["zero_result"]),
                        )
                    report.update({
                        "status": "PASS_DISCOVERY_ONLY", "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "viewport": {"width": 1366, "height": 768},
                        "api_responses": responses,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                        "control_observations": sum(v["visible_control_count"] for v in report["views"]),
                    })
                    if capture.console_errors or capture.page_errors or capture.request_failures:
                        report["status"] = "FINDINGS_DISCOVERY_ONLY"
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_DISCOVERY_ONLY", "error_type": type(exc).__name__,
                       "error": str(exc)[:1000]})
        if "capture" in locals():
            report["failure_console_errors"] = capture.console_errors
            report["failure_page_errors"] = capture.page_errors
            report["failure_request_failures"] = capture.request_failures
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_control_inventory.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] == "PASS_DISCOVERY_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
