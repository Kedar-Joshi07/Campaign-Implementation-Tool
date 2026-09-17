from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = (
    "saved-target-groups", "campaigns", "insights", "historical-analysis",
    "audience-explorer", "data-status", "model-training",
)


def test_navigation_source_preserves_legacy_views_without_security_claim() -> None:
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    nav = html.split('<nav id="business-navigation"', 1)[1].split("</nav>", 1)[0]
    assert nav.count("data-view-target=") == 3
    for key in HIDDEN:
        assert f'data-view-target="{key}"' not in nav
        tag = html.split(f'<section id="{key}-view"', 1)[1].split(">", 1)[0]
        assert "hidden" in tag
    contract = (ROOT / "frontend/js/view-contract.js").read_text(encoding="utf-8")
    assert "not authentication, authorization, or RBAC" in contract
    assert "Future role-aware navigation" in contract
    app = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
    assert "viewTitles" not in app
    assert 'from "./view-contract.js"' in app
    assert "UI hiding is not security" in app


def test_legacy_api_contracts_remain_registered() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    for path in (
        "/api/health", "/api/data/status", "/api/historical/analyses",
        "/api/models/train", "/api/models/{model_run_id}/score",
        "/api/audience/estimate", "/api/audience/search", "/api/audiences",
        "/api/campaigns", "/api/campaigns/{campaign_id}/finalize",
        "/api/campaigns/{campaign_id}/export.csv",
    ):
        assert path in paths


@pytest.fixture(scope="module")
def browser_session():
    # Static, request-intercepted module harness: no app server/database or heavy work.
    from playwright.sync_api import sync_playwright
    from scripts.validation.browser.system_browser import launch_system_browser_session

    with sync_playwright() as playwright:
        with launch_system_browser_session(playwright, headless=True) as session:
            yield session


@pytest.fixture
def page(browser_session):
    page = browser_session.context.new_page()
    errors: list[str] = []
    requests: list[tuple[str, str]] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def serve(route):
        path = urlsplit(route.request.url).path
        if path.startswith("/api/"):
            requests.append((route.request.method, path))
            # Deliberately exercise existing safe backend-unavailable UI, not fake results.
            route.fulfill(status=503, json={"detail": "Isolated navigation harness: service unavailable"})
            return
        if path == "/":
            asset = ROOT / "frontend/index.html"
        elif path.startswith("/static/"):
            asset = ROOT / "frontend" / path.removeprefix("/static/")
        else:
            route.fulfill(status=404, body="Not found")
            return
        assert asset.resolve().is_relative_to((ROOT / "frontend").resolve())
        content_type = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[asset.suffix]
        route.fulfill(status=200, content_type=content_type, body=asset.read_bytes())

    page.route("**/*", serve)
    yield page, errors, requests
    page.close()


def open_route(page, fragment=""):
    page.goto(f"http://phase11.test/{fragment}", wait_until="networkidle")
    page.wait_for_function("location.hash.length > 1")


def assert_state(page, fragment, dom_view, active, title):
    assert page.evaluate("location.hash") == fragment
    assert page.locator("[data-view]:visible").count() == 1
    assert page.locator(f'[data-view="{dom_view}"]').is_visible()
    assert page.locator("#business-navigation [aria-current=page]").count() == 1
    assert page.locator("#business-navigation .is-active").count() == 1
    assert page.locator("#business-navigation [aria-current=page]").get_attribute("data-view-target") == active
    assert page.locator("#page-title").inner_text() == title
    assert page.title() == f"{title} | Campaign Implementation Intelligence"
    for key in HIDDEN:
        assert page.locator(f'[data-view="{key}"]').is_hidden()


@pytest.mark.browser
@pytest.mark.parametrize("incoming,canonical,dom_view,active,title", [
    ("", "#home", "overview", "home", "Home"),
    ("#", "#home", "overview", "home", "Home"),
    ("#home", "#home", "overview", "home", "Home"),
    ("#overview", "#home", "overview", "home", "Home"),
    ("#campaign-planner", "#find-potential-customers", "campaign-planner", "find-potential-customers", "Find Potential Customers"),
    ("#find-potential-customers", "#find-potential-customers", "campaign-planner", "find-potential-customers", "Find Potential Customers"),
    ("#results", "#results", "results", "results", "Results"),
    ("#results/42", "#results/42", "result-detail", "results", "Result Details"),
    *[(f"#{key}", "#home", "overview", "home", "Home") for key in HIDDEN],
    *[(key, "#home", "overview", "home", "Home") for key in (
        "#unknown", "#toString", "#results/0", "#results/-1", "#results/01",
        "#results/42/extra", "#results/%31", "#results/<script>", "#result-detail",
    )],
])
def test_startup_routes_and_hidden_fragments(page, incoming, canonical, dom_view, active, title):
    browser, errors, requests = page
    open_route(browser, incoming)
    assert_state(browser, canonical, dom_view, active, title)
    assert browser.locator("#business-navigation button:visible span:last-child").all_text_contents() == [
        "Home", "Find Potential Customers", "Results",
    ]
    assert errors == []
    assert all(method == "GET" for method, _ in requests)
    assert not any(path.startswith(("/api/models", "/api/audience", "/api/campaigns", "/api/audiences")) for _, path in requests)


@pytest.mark.browser
def test_click_hash_history_detail_and_redirect_without_extra_history(page):
    browser, errors, _ = page
    open_route(browser)
    browser.locator("#home-find-potential-customers").click()
    browser.wait_for_url("**/#find-potential-customers")
    browser.locator("#nav-results").click()
    browser.wait_for_url("**/#results")
    browser.go_back()
    assert_state(browser, "#find-potential-customers", "campaign-planner", "find-potential-customers", "Find Potential Customers")
    browser.go_back()
    assert_state(browser, "#home", "overview", "home", "Home")
    browser.go_forward()
    browser.go_forward()
    browser.evaluate("location.hash = 'results/42'")
    browser.wait_for_url("**/#results/42")
    assert_state(browser, "#results/42", "result-detail", "results", "Result Details")
    assert browser.locator("#result-detail-view").get_attribute("data-search-run-id") == "42"
    browser.locator("#result-detail-back").click()
    browser.wait_for_url("**/#results")
    before = browser.evaluate("history.length")
    browser.evaluate("location.hash = 'model-training'")
    browser.wait_for_url("**/#home")
    assert browser.evaluate("history.length") == before + 1
    browser.go_back()
    assert_state(browser, "#results", "results", "results", "Results")
    browser.locator(".brand").click()
    browser.wait_for_url("**/#home")
    before = browser.evaluate("history.length")
    browser.locator("#nav-home").click()
    assert browser.evaluate("history.length") == before
    assert browser.locator("#home-find-potential-customers").get_attribute("aria-current") is None
    assert errors == []


@pytest.mark.browser
def test_contract_is_immutable_and_legacy_modules_load_in_harness(page):
    browser, errors, requests = page
    open_route(browser, "#results")
    contract = browser.evaluate("""async () => {
      const module = await import('/static/js/view-contract.js');
      return {navigation: module.BUSINESS_NAVIGATION,
        frozen: Object.isFrozen(module.VIEW_DEFINITIONS) && Object.isFrozen(module.BUSINESS_NAVIGATION)
          && Object.values(module.VIEW_DEFINITIONS).every(Object.isFrozen),
        hidden: [...document.querySelectorAll('[data-view]')]
          .filter(view => view.dataset.viewGroup !== module.VIEW_GROUPS.BUSINESS_USER_VISIBLE)
          .map(view => view.dataset.view)};
    }""")
    assert contract["navigation"] == ["home", "find-potential-customers", "results"]
    assert contract["frozen"] is True
    assert set(contract["hidden"]) == set(HIDDEN)
    exports = browser.evaluate("""async () => {
      const names = ['data-status', 'historical-analysis', 'model-training', 'audience-explorer',
        'campaigns', 'saved-target-groups', 'campaign-planner-form'];
      const exports = {};
      for (const name of names) exports[name] = Object.keys(await import(`/static/js/${name}.js`));
      return exports;
    }""")
    for names in exports.values():
        assert any(name.startswith("initialize") for name in names)
        assert any(name.startswith("load") for name in names)
    # Invoke a retained read-only loader via the explicit module seam, never exposing its view.
    browser.evaluate("""async () => {
      const {loadLegacyWorkspace} = await import('/static/js/app.js');
      try { await loadLegacyWorkspace('saved-target-groups'); } catch (_) {}
    }""")
    assert any(path == "/api/audiences" for _, path in requests)
    assert_state(browser, "#results", "results", "results", "Results")
    assert errors == []
