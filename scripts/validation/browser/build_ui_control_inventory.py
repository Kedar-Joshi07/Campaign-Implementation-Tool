from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_HTML = PROJECT_ROOT / "frontend" / "index.html"
FRONTEND_JS_DIR = PROJECT_ROOT / "frontend" / "js"

DEFAULT_INVENTORY_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "ui_control_inventory.json"
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "UI_CONTROL_COVERAGE_CONTRACT.md"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _infer_page_from_selector(selector: str) -> str:
    lowered = selector.casefold()
    if "data-view-target" in lowered:
        return "global"
    if "overview" in lowered:
        return "overview"
    if "data-status" in lowered:
        return "data-status"
    if "historical" in lowered or "analysis" in lowered:
        return "historical-analysis"
    if "model" in lowered or "score" in lowered:
        return "model-training"
    if "audience" in lowered:
        return "audience-explorer"
    if "campaign" in lowered or "export" in lowered:
        return "campaigns"
    return "global"


def _scenario_for_page(page: str) -> str:
    return f"Exercise {page} control in system browser and assert observable UI/API state transition."


def _default_control_record(
    *,
    page: str,
    selector: str,
    label: str,
    control_type: str,
    mutually_exclusive_group: str = "",
    source: str,
) -> dict[str, Any]:
    return {
        "page": page,
        "selector": selector,
        "label": label,
        "type": control_type,
        "enable_conditions": "Visible in active view and enabled by currentness/job-state guards.",
        "mutually_exclusive_group": mutually_exclusive_group,
        "expected_behavior": "Control is reachable and performs its documented action without unexplained errors.",
        "required_scenario": _scenario_for_page(page),
        "status": "NOT_RUN",
        "justification": "",
        "source": source,
    }


class _ActionableHtmlParser(HTMLParser):
    ACTIONABLE_TAGS = {"button", "input", "select", "textarea", "a"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[dict[str, Any]] = []
        self.label_map: dict[str, str] = {}
        self._view_stack: list[str] = []
        self._tag_is_view_scope: list[bool] = []
        self._active_text_control_index: int | None = None
        self._active_label_for: str | None = None
        self._active_label_text: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: (value or "") for key, value in attrs_list}
        has_view_scope = "data-view" in attrs and bool(attrs["data-view"].strip())
        if has_view_scope:
            self._view_stack.append(attrs["data-view"].strip())
        self._tag_is_view_scope.append(has_view_scope)

        if tag == "label" and attrs.get("for", "").strip():
            self._active_label_for = attrs["for"].strip()
            self._active_label_text = []

        if tag not in self.ACTIONABLE_TAGS:
            return

        selector = self._selector_for(tag, attrs)
        if not selector:
            return

        page = self._current_view() or _infer_page_from_selector(selector)
        control_type = self._control_type(tag, attrs)
        label = attrs.get("aria-label", "").strip() or attrs.get("title", "").strip() or attrs.get("value", "").strip()
        group = attrs.get("name", "").strip() if control_type in {"input:radio", "input:checkbox"} else ""

        self.controls.append(
            _default_control_record(
                page=page,
                selector=selector,
                label=label,
                control_type=control_type,
                mutually_exclusive_group=group,
                source="dom",
            )
        )
        if tag in {"button", "a"} and not label:
            self._active_text_control_index = len(self.controls) - 1

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._active_text_control_index is not None:
            control = self.controls[self._active_text_control_index]
            control["label"] = f"{control['label']} {text}".strip()
        if self._active_label_for is not None:
            self._active_label_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._active_label_for is not None:
            text = " ".join(self._active_label_text).strip()
            if text:
                self.label_map[self._active_label_for] = text
            self._active_label_for = None
            self._active_label_text = []

        if tag in {"button", "a"}:
            self._active_text_control_index = None

        if self._tag_is_view_scope:
            had_view_scope = self._tag_is_view_scope.pop()
            if had_view_scope and self._view_stack:
                self._view_stack.pop()

    def _current_view(self) -> str:
        return self._view_stack[-1] if self._view_stack else ""

    @staticmethod
    def _selector_for(tag: str, attrs: dict[str, str]) -> str:
        element_id = attrs.get("id", "").strip()
        if element_id:
            return f"#{element_id}"
        data_breakdown = attrs.get("data-breakdown", "").strip()
        if data_breakdown:
            return f"[data-breakdown='{data_breakdown}']"
        data_profile_group = attrs.get("data-profile-group", "").strip()
        if data_profile_group:
            return f"[data-profile-group='{data_profile_group}']"
        data_testid = attrs.get("data-testid", "").strip()
        if data_testid:
            return f"[data-testid='{data_testid}']"
        view_target = attrs.get("data-view-target", "").strip()
        if view_target:
            return f"[data-view-target='{view_target}']"
        if tag == "input" and attrs.get("name", "").strip():
            return f"input[name='{attrs['name'].strip()}']"
        return ""

    @staticmethod
    def _control_type(tag: str, attrs: dict[str, str]) -> str:
        if tag == "input":
            return f"input:{attrs.get('type', 'text').strip() or 'text'}"
        return tag


def _discover_dom_controls(index_html: Path) -> list[dict[str, Any]]:
    parser = _ActionableHtmlParser()
    parser.feed(index_html.read_text(encoding="utf-8"))
    controls = parser.controls
    for control in controls:
        if not control["label"] and control["selector"].startswith("#"):
            element_id = control["selector"][1:]
            control["label"] = parser.label_map.get(element_id, "")
    return controls


_JS_PAGE_BY_FILE = {
    "app.js": "global",
    "overview.js": "overview",
    "data-status.js": "data-status",
    "historical-analysis.js": "historical-analysis",
    "historical-overview.js": "overview",
    "model-training.js": "model-training",
    "audience-explorer.js": "audience-explorer",
    "campaigns.js": "campaigns",
}

_PRESENTATION_ONLY_CLASSES = {
    "button",
    "button-primary",
    "button-secondary",
    "button-danger",
}


def _dynamic_selector(*, tag: str, body: str, variable: str) -> tuple[str, str, str] | None:
    """Return selector, label and type for a created actionable element.

    General ``querySelector`` usage is deliberately not inventory input: most such
    selectors point at output/status containers. Static actionable elements are
    already discovered from HTML. JavaScript discovery is reserved for controls
    that are actually created at runtime.
    """

    id_match = re.search(rf"\b{re.escape(variable)}\.id\s*=\s*['\"]([^'\"]+)['\"]", body)
    name_match = re.search(rf"\b{re.escape(variable)}\.name\s*=\s*['\"]([^'\"]+)['\"]", body)
    type_match = re.search(rf"\b{re.escape(variable)}\.type\s*=\s*['\"]([^'\"]+)['\"]", body)
    class_match = re.search(rf"\b{re.escape(variable)}\.className\s*=\s*['\"]([^'\"]+)['\"]", body)
    label_match = re.search(rf"\b{re.escape(variable)}\.textContent\s*=\s*['\"]([^'\"]+)['\"]", body)
    has_listener = re.search(rf"\b{re.escape(variable)}\.addEventListener\(", body) is not None

    if tag in {"button", "a"} and not has_listener:
        return None

    selector = ""
    if id_match:
        selector = f"#{id_match.group(1)}"
    elif tag == "input" and name_match:
        selector = f"input[name='{name_match.group(1)}']"
    elif class_match:
        stable_classes = [
            item
            for item in class_match.group(1).split()
            if item and item not in _PRESENTATION_ONLY_CLASSES
        ]
        if stable_classes:
            selector = f".{stable_classes[0]}"

    if not selector:
        return None

    input_type = type_match.group(1) if type_match else "text"
    control_type = f"input:{input_type}" if tag == "input" else f"dynamic:{tag}"
    label = label_match.group(1).strip() if label_match else ""
    return selector, label, control_type


def _discover_js_selectors(frontend_js_dir: Path) -> list[dict[str, Any]]:
    controls: dict[tuple[str, str], dict[str, Any]] = {}
    create_pattern = re.compile(
        r"const\s+(?P<variable>[A-Za-z_$][\w$]*)\s*=\s*document\.createElement\("
        r"\s*['\"](?P<tag>button|a|input|select|textarea)['\"]\s*\)\s*;"
    )

    for js_file in sorted(frontend_js_dir.glob("*.js")):
        text = js_file.read_text(encoding="utf-8")
        page = _JS_PAGE_BY_FILE.get(js_file.name, "global")
        matches = list(create_pattern.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            # Limit the body to the local construction block so later assignments
            # to a same-named variable cannot be attributed to this element.
            body = text[match.end() : min(end, match.end() + 1_500)]
            discovered = _dynamic_selector(
                tag=match.group("tag"),
                body=body,
                variable=match.group("variable"),
            )
            if discovered is None:
                continue
            selector, label, control_type = discovered
            key = (page, selector)
            controls.setdefault(
                key,
                _default_control_record(
                    page=page,
                    selector=selector,
                    label=label,
                    control_type=control_type,
                    source=f"js-created:{js_file.name}",
                ),
            )

    return list(controls.values())


def build_inventory_payload(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    index_html = project_root / "frontend" / "index.html"
    frontend_js_dir = project_root / "frontend" / "js"

    dom_controls = _discover_dom_controls(index_html)
    js_controls = _discover_js_selectors(frontend_js_dir)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for control in dom_controls + js_controls:
        key = (control["page"], control["selector"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = control
            continue
        source_parts = {existing.get("source", ""), control.get("source", "")}
        existing["source"] = "+".join(sorted(part for part in source_parts if part))
        if not existing.get("label") and control.get("label"):
            existing["label"] = control["label"]

    controls = sorted(merged.values(), key=lambda item: (item["page"], item["selector"]))
    status_summary = {
        "NOT_RUN": sum(1 for control in controls if control["status"] == "NOT_RUN"),
        "PASS": 0,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
    }

    return {
        "generated_at": _now_iso(),
        "source": {
            "frontend_index": str(index_html.relative_to(project_root)).replace("\\", "/"),
            "frontend_js_glob": "frontend/js/*.js",
        },
        "controls": controls,
        "status_summary": status_summary,
    }


def _render_contract_markdown(inventory_payload: dict[str, Any]) -> str:
    controls: list[dict[str, Any]] = inventory_payload["controls"]
    page_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for control in controls:
        page_counts[control["page"]] = page_counts.get(control["page"], 0) + 1
        type_counts[control["type"]] = type_counts.get(control["type"], 0) + 1

    lines: list[str] = []
    lines.append("# Phase 8 UI Control Coverage Contract")
    lines.append("")
    lines.append(f"Generated at: {inventory_payload['generated_at']}")
    lines.append("")
    lines.append("## Contract Rules")
    lines.append("- Allowed statuses: `NOT_RUN`, `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.")
    lines.append("- Terminal statuses allowed for certification: `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.")
    lines.append("- Generic `EXCEPTION` is forbidden.")
    lines.append("- `JUSTIFIED_EXCLUSIVE` requires both `mutually_exclusive_group` and `justification`.")
    lines.append("- Coverage gate fails if any control is `NOT_RUN`.")
    lines.append("- Coverage gate fails if any control is `FAIL`.")
    lines.append("- Coverage gate fails if any `JUSTIFIED_EXCLUSIVE` is unjustified.")
    lines.append("")
    lines.append("## Discovery Summary")
    lines.append(f"- Total controls: {len(controls)}")
    lines.append("")
    lines.append("By page:")
    for page, count in sorted(page_counts.items()):
        lines.append(f"- {page}: {count}")
    lines.append("")
    lines.append("By type:")
    for control_type, count in sorted(type_counts.items()):
        lines.append(f"- {control_type}: {count}")
    lines.append("")
    lines.append("## Checker")
    lines.append("Run:")
    lines.append("- `python scripts/validation/browser/check_ui_control_coverage.py --inventory docs/evidence/phase8/ui_control_inventory.json`")
    lines.append("")
    lines.append("Expected current state after Step 4:")
    lines.append("- Inventory is intentionally initialized with `NOT_RUN` status for all controls.")
    lines.append("- Gate should fail until execution steps update statuses to terminal values.")
    return "\n".join(lines)


def write_inventory_and_contract(
    inventory_payload: dict[str, Any],
    *,
    inventory_path: Path,
    contract_path: Path,
) -> None:
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps(inventory_payload, indent=2), encoding="utf-8")
    contract_path.write_text(_render_contract_markdown(inventory_payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 8 UI control inventory and coverage contract.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY_PATH)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    args = parser.parse_args()

    payload = build_inventory_payload(PROJECT_ROOT)
    write_inventory_and_contract(payload, inventory_path=args.inventory, contract_path=args.contract)
    print(f"Wrote inventory: {args.inventory}")
    print(f"Wrote contract: {args.contract}")
    print(f"Discovered controls: {len(payload['controls'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
