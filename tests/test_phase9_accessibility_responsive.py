from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


class _PlannerFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_planner = False
        self.controls: dict[str, dict[str, str | None]] = {}
        self.label_fors: set[str] = set()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "section" and attributes.get("id") == "campaign-planner-view":
            self.in_planner = True
        if not self.in_planner:
            return
        if tag == "label" and attributes.get("for"):
            self.label_fors.add(str(attributes["for"]))
        if tag in {"input", "select", "textarea"} and attributes.get("id"):
            self.controls[str(attributes["id"])] = attributes


def _sources() -> tuple[str, str, str, str, str]:
    root = Path(__file__).resolve().parents[1]
    return (
        (root / "frontend" / "index.html").read_text(encoding="utf-8"),
        (root / "frontend" / "css" / "components.css").read_text(encoding="utf-8"),
        (root / "frontend" / "css" / "main.css").read_text(encoding="utf-8"),
        (root / "frontend" / "js" / "campaign-planner-form.js").read_text(
            encoding="utf-8"
        ),
        (root / "frontend" / "js" / "business-targeting.js").read_text(
            encoding="utf-8"
        ),
    )


def test_every_static_planner_form_control_has_an_accessible_name() -> None:
    html, *_ = _sources()
    planner_html = html.split('id="campaign-planner-view"', 1)[1].split(
        'id="campaigns-view"', 1
    )[0]
    parser = _PlannerFormParser()
    parser.feed('<section id="campaign-planner-view"' + planner_html)

    unnamed = [
        control_id
        for control_id, attributes in parser.controls.items()
        if control_id not in parser.label_fors and not attributes.get("aria-label")
    ]
    assert unnamed == []


def test_keyboard_stepper_validation_multiselect_and_chip_contracts() -> None:
    html, components, _main, form_script, targeting_script = _sources()
    planner_html = html.split('id="campaign-planner-view"', 1)[1].split(
        'id="campaigns-view"', 1
    )[0]

    assert 'aria-label="Create Campaign steps"' in planner_html
    assert 'aria-describedby="planner-stepper-help"' in planner_html
    assert planner_html.count('aria-controls="planner-step-panel-') == 5
    assert 'aria-current="step"' in planner_html
    assert 'button.setAttribute("aria-current", "step")' in form_script
    assert (
        'document.querySelector(`[data-planner-panel="${target}"] h3`).focus?.();'
        in form_script
    )
    assert "reportValidity()" in form_script

    assert "planner-multiselect-help" in planner_html
    assert "hold Ctrl (or Command)" in planner_html
    assert planner_html.count('multiple size="') == 15
    assert planner_html.count("planner-multiselect-help") >= 16
    assert 'id="planner-targeting-chips"' in planner_html
    assert 'role="list"' in planner_html
    assert 'chip.setAttribute("role", "listitem")' in targeting_script
    assert "button.type = \"button\"" in targeting_script
    assert "button.setAttribute(\"aria-label\", `Remove ${text}`)" in targeting_script
    assert "document.querySelector(focusSelector)?.focus()" in targeting_script

    for selector in (
        ".planner-step:focus-visible",
        ".planner-targeting-chip button:focus-visible",
        ".planner-targeting-more summary:focus-visible",
        ".planner-panel h3:focus-visible",
        ".error-state:focus-visible",
    ):
        assert selector in components


def test_live_status_table_reduced_motion_and_non_color_status_contracts() -> None:
    html, components, main, _form_script, _targeting_script = _sources()
    planner_html = html.split('id="campaign-planner-view"', 1)[1].split(
        'id="campaigns-view"', 1
    )[0]

    assert 'id="planner-status-announcement"' in planner_html
    assert 'aria-live="polite"' in planner_html
    assert 'aria-atomic="true"' in planner_html
    assert 'role="alert" tabindex="-1"' in planner_html
    assert 'role="status" aria-live="polite"' in planner_html
    assert '<caption class="visually-hidden">Potential customers' in planner_html
    assert planner_html.count('th scope="col"') == 8
    assert 'id="planner-preview-page-status"' in planner_html
    assert "Current" in planner_html
    assert "Not started" in planner_html
    assert "Up to date" in planner_html
    assert "Not checked" in planner_html
    assert "@media (prefers-reduced-motion: reduce)" in main
    assert "transition-duration: 0.01ms !important" in main
    assert ".planner-save-success:focus-visible" in components


def test_required_viewports_have_explicit_responsive_layout_coverage() -> None:
    _html, components, main, _form_script, _targeting_script = _sources()
    css = main + components

    for breakpoint in (1100, 780, 520):
        assert f"@media (max-width: {breakpoint}px)" in css
    assert re.search(
        r"@media \(max-width: 1100px\).*?\.planner-workspace.*?grid-template-columns: 1fr",
        components,
        re.DOTALL,
    )
    assert re.search(
        r"@media \(max-width: 780px\).*?\.planner-stepper.*?grid-template-columns: 1fr",
        components,
        re.DOTALL,
    )
    assert ".planner-preview-table-panel table" in components
    assert "min-width: 980px" in components
    assert ".table-scroll" in components
    assert "overflow-x: auto" in components


def test_normal_business_path_answers_key_questions_without_model_jargon() -> None:
    html, *_ = _sources()
    planner_html = html.split('id="campaign-planner-view"', 1)[1].split(
        'id="campaigns-view"', 1
    )[0]
    normal_path = re.sub(r"<details.*?</details>", "", planner_html, flags=re.DOTALL)

    for expected in (
        "Campaign Name",
        "What are you promoting?",
        "Describe the people you would like to reach",
        "How selective should targeting be?",
        "Selected for Target Group",
        "Why these people?",
        "Up to date",
        "This saves an immutable, privacy-safe Target Group",
    ):
        assert expected in normal_path
    for forbidden in (
        "analysis_run_id",
        "model_run_id",
        "scoring_run_id",
        "model artifacts",
        "algorithm",
    ):
        assert forbidden not in normal_path.lower()
