from __future__ import annotations

import re
from pathlib import Path


def _sources() -> tuple[str, str, str, str]:
    root = Path(__file__).resolve().parents[1]
    return (
        (root / "frontend" / "index.html").read_text(encoding="utf-8"),
        (root / "frontend" / "css" / "components.css").read_text(
            encoding="utf-8"
        ),
        (root / "frontend" / "js" / "targeting-intelligence.js").read_text(
            encoding="utf-8"
        ),
        (root / "frontend" / "js" / "campaign-planner-form.js").read_text(
            encoding="utf-8"
        ),
    )


def test_targeting_preferences_advance_before_automatic_preparation() -> None:
    _html, _css, intelligence, planner = _sources()
    step_three = planner.split("if (step === 3) {", 1)[1].split("return;", 1)[0]

    assert "validateAndSaveBusinessTargeting" in planner
    assert step_three.index("completePlannerStep(step)") < step_three.index(
        "refreshTargetingIntelligence()"
    )
    assert "Preparing your Target Group now" in step_three
    assert 'if (step === 4) refreshTargetingIntelligence()' in planner
    assert "/intelligence-plan" in intelligence
    assert "/targeting-intelligence/prepare" in intelligence
    assert "/targeting-intelligence/preparation`" in intelligence
    assert "/targeting-intelligence/preparation/retry" in intelligence
    assert "/targeting-intelligence`" in intelligence


def test_durable_preparation_reconnects_polls_and_opens_unchanged_preview() -> None:
    _html, _css, intelligence, _planner = _sources()

    assert "plan.readiness === \"READY\"" in intelligence
    assert '["PREPARING", "BLOCKED", "FAILED"].includes(plan.readiness)' in intelligence
    assert '["QUEUED", "RUNNING"].includes(preparation.status)' in intelligence
    assert "window.setTimeout(() => pollPreparation" in intelligence
    assert "POLL_DELAY_MS" in intelligence
    assert "setInterval" not in intelligence
    assert "loadReadyPhase9" in intelligence
    assert 'new CustomEvent("targeting-intelligence-resolved"' in intelligence
    assert "resolution.can_preview" in intelligence
    assert "requestGeneration" in intelligence
    assert "innerHTML" not in intelligence


def test_business_language_reuse_blocked_and_failed_states_are_exact() -> None:
    html, _css, intelligence, _planner = _sources()

    for message in (
        "Existing verified targeting intelligence matches this campaign and is ready.",
        "Campaign history is still valid; refreshing matches for current potential-customer data.",
        "Preparing new targeting intelligence for this campaign.",
        "There is not enough verified past campaign history for this combination yet.",
        "We could not finish preparing targeting intelligence. Your campaign inputs are saved.",
    ):
        assert message in intelligence

    for label in (
        "Targeting intelligence",
        "Past campaign history",
        "Potential customers",
        "Preparing your Target Group",
        "Verifying results",
        "Up to date",
        "Needs refresh",
        "Not enough past campaign history",
    ):
        assert label in intelligence

    assert 'id="planner-intelligence-retry"' in html
    assert 'id="planner-intelligence-back-context"' in html
    assert "Back to Campaign Context" in html
    assert "Your choices remain unchanged and will never be removed automatically" in intelligence
    assert "preparation/retry" in intelligence


def test_normal_ui_has_no_source_picker_and_technical_details_are_collapsed() -> None:
    html, _css, intelligence, _planner = _sources()
    step_four = html.split('id="planner-step-panel-4"', 1)[1].split(
        'id="planner-step-panel-5"', 1
    )[0]
    normal_markup = re.sub(
        r"<details\b.*?</details>", "", step_four, flags=re.DOTALL
    )

    assert 'name="scoring_run_id"' not in html
    assert '<details id="planner-intelligence-advanced"' in step_four
    assert '<details id="planner-intelligence-advanced" open' not in step_four
    assert "View technical details" in step_four
    for hidden_term in (
        "PU",
        "bagging",
        "model run",
        "scoring run",
        "artifact",
        "feature hash",
    ):
        assert hidden_term.casefold() not in normal_markup.casefold()
    assert "renderPreparationTechnicalDetails" in intelligence
    assert "Modeling Context SHA-256" in intelligence
    assert "Scoring run" in intelligence


def test_progress_accessibility_and_required_responsive_layout_are_present() -> None:
    html, css, intelligence, _planner = _sources()

    for element_id in (
        "planner-intelligence-state",
        "planner-intelligence-progress",
        "planner-intelligence-progressbar",
        "planner-intelligence-progress-fill",
        "planner-intelligence-progress-percent",
        "planner-intelligence-progress-label",
    ):
        assert f'id="{element_id}"' in html
    assert 'role="progressbar"' in html
    assert 'aria-valuemin="0"' in html
    assert 'aria-valuemax="100"' in html
    assert 'aria-valuenow="0"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-atomic="true"' in html
    assert 'tabindex="-1"' in html
    assert "aria-valuetext" in intelligence
    assert 'container.setAttribute("aria-busy", String(active))' in intelligence
    assert "container.focus()" in intelligence
    assert "setCampaignPlannerStep(2)" in intelligence

    for breakpoint in (1100, 780, 520):
        assert f"@media (max-width: {breakpoint}px)" in css
    assert ".planner-intelligence-progress" in css
    assert ".planner-intelligence-progress-track" in css
    assert ".planner-intelligence-progress-copy" in css
    assert ".planner-intelligence-actions" in css


def test_phase10_ui_never_reads_or_renders_pii_fields() -> None:
    _html, _css, intelligence, _planner = _sources()
    for field in (
        "first",
        "first_name",
        "last",
        "last_name",
        "email",
        "phone",
        "address",
        "street",
        "city",
        "postal",
        "postal_code",
    ):
        assert f".{field}" not in intelligence
        assert f'["{field}"]' not in intelligence
        assert f"['{field}']" not in intelligence
