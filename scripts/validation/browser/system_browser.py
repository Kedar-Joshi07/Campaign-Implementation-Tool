from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright


DEFAULT_CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class SystemBrowserResolutionError(RuntimeError):
    """Raised when a system browser cannot be resolved under configured rules."""


@dataclass(frozen=True)
class BrowserTarget:
    name: str
    executable_path: Path
    source: str


@dataclass(frozen=True)
class BrowserMetadata:
    name: str
    executable_path: str
    product_version: str
    execution_mode: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "executable_path": self.executable_path,
            "product_version": self.product_version,
            "execution_mode": self.execution_mode,
        }


@dataclass
class SystemBrowserSession:
    target: BrowserTarget
    metadata: BrowserMetadata
    browser: Browser | None
    context: BrowserContext
    page: Page
    profile_dir: Path
    downloads_dir: Path


@dataclass
class PageEventCapture:
    console_errors: list[str]
    page_errors: list[str]
    request_failures: list[dict[str, str]]


def _normalize_browser_name(raw_name: str) -> str:
    name = (raw_name or "auto").strip().casefold()
    if name not in {"auto", "chrome", "edge"}:
        raise SystemBrowserResolutionError(
            "SYSTEM_BROWSER must be one of auto, chrome, edge. "
            f"Received: {raw_name!r}"
        )
    return name


def resolve_system_browser(
    *,
    system_browser: str | None = None,
    system_browser_path: str | None = None,
    environ: dict[str, str] | None = None,
    path_exists: Callable[[Path], bool] | None = None,
    chrome_path: Path = DEFAULT_CHROME_PATH,
    edge_path: Path = DEFAULT_EDGE_PATH,
) -> BrowserTarget:
    env = os.environ if environ is None else environ
    exists = path_exists if path_exists is not None else (lambda p: p.is_file())

    configured_browser = system_browser if system_browser is not None else env.get("SYSTEM_BROWSER", "auto")
    browser_name = _normalize_browser_name(configured_browser)

    configured_path = (
        system_browser_path
        if system_browser_path is not None
        else env.get("SYSTEM_BROWSER_PATH", "")
    )
    explicit_path = Path(configured_path).expanduser() if configured_path and configured_path.strip() else None

    # Rule 1: explicit path override has highest priority.
    if explicit_path is not None:
        if not exists(explicit_path):
            raise SystemBrowserResolutionError(
                "SYSTEM_BROWSER_PATH was provided but executable was not found: "
                f"{explicit_path}"
            )
        resolved_name = browser_name if browser_name in {"chrome", "edge"} else "explicit"
        return BrowserTarget(name=resolved_name, executable_path=explicit_path, source="explicit_path")

    # Rule 2/3: explicit browser preference when requested.
    if browser_name == "chrome":
        if exists(chrome_path):
            return BrowserTarget(name="chrome", executable_path=chrome_path, source="system_default")
        raise SystemBrowserResolutionError(f"SYSTEM_BROWSER=chrome requested, but executable not found: {chrome_path}")

    if browser_name == "edge":
        if exists(edge_path):
            return BrowserTarget(name="edge", executable_path=edge_path, source="system_default")
        raise SystemBrowserResolutionError(f"SYSTEM_BROWSER=edge requested, but executable not found: {edge_path}")

    # Rule 2 then 3 under auto mode.
    if exists(chrome_path):
        return BrowserTarget(name="chrome", executable_path=chrome_path, source="system_default")
    if exists(edge_path):
        return BrowserTarget(name="edge", executable_path=edge_path, source="system_default")

    # Rule 4: fail clearly.
    raise SystemBrowserResolutionError(
        "No supported system browser found. Checked Chrome and Edge defaults. "
        "Install Chrome or Edge, or set SYSTEM_BROWSER_PATH to a valid executable."
    )


def _read_browser_version(browser: Browser) -> str:
    version_attr = getattr(browser, "version", None)
    if callable(version_attr):
        try:
            return str(version_attr())
        except Exception:
            return "unknown"
    if isinstance(version_attr, str) and version_attr.strip():
        return version_attr.strip()
    return "unknown"


def _launch_browser_context(
    playwright: Playwright,
    *,
    executable_path: Path,
    headless: bool,
    profile_dir: Path,
    downloads_dir: Path,
    launch_args: list[str],
    ignore_https_errors: bool,
    viewport: dict[str, int] | None,
) -> BrowserContext:
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "executable_path": str(executable_path),
        "headless": headless,
        "args": launch_args,
        "ignore_https_errors": ignore_https_errors,
        "accept_downloads": True,
        "viewport": viewport,
        "downloads_path": str(downloads_dir),
    }
    try:
        return playwright.chromium.launch_persistent_context(**launch_kwargs)
    except TypeError:
        launch_kwargs.pop("downloads_path", None)
        return playwright.chromium.launch_persistent_context(**launch_kwargs)


@contextmanager
def launch_system_browser_session(
    playwright: Playwright,
    *,
    system_browser: str | None = None,
    system_browser_path: str | None = None,
    headless: bool = True,
    headed_debug: bool = False,
    viewport: dict[str, int] | None = None,
    app_url: str | None = None,
    ignore_https_errors: bool = True,
    extra_args: list[str] | None = None,
) -> Iterator[SystemBrowserSession]:
    target = resolve_system_browser(system_browser=system_browser, system_browser_path=system_browser_path)
    launch_headless = False if headed_debug else headless
    profile_tmp = tempfile.TemporaryDirectory(prefix="phase8-browser-profile-")
    downloads_tmp = tempfile.TemporaryDirectory(prefix="phase8-browser-downloads-")
    profile_dir = Path(profile_tmp.name)
    downloads_dir = Path(downloads_tmp.name)
    context: BrowserContext | None = None
    try:
        launch_args = ["--disable-popup-blocking", *(extra_args or [])]
        context = _launch_browser_context(
            playwright,
            executable_path=target.executable_path,
            headless=launch_headless,
            profile_dir=profile_dir,
            downloads_dir=downloads_dir,
            launch_args=launch_args,
            ignore_https_errors=ignore_https_errors,
            viewport=viewport,
        )
        page = context.pages[0] if context.pages else context.new_page()
        if app_url:
            page.goto(app_url, wait_until="domcontentloaded")
        browser = context.browser
        metadata = BrowserMetadata(
            name=f"system_{target.name}",
            executable_path=str(target.executable_path),
            product_version=_read_browser_version(browser) if browser is not None else "unknown",
            execution_mode="headless" if launch_headless else "headed",
        )
        yield SystemBrowserSession(
            target=target,
            metadata=metadata,
            browser=browser,
            context=context,
            page=page,
            profile_dir=profile_dir,
            downloads_dir=downloads_dir,
        )
    finally:
        if context is not None:
            context.close()
        downloads_tmp.cleanup()
        profile_tmp.cleanup()


def attach_page_event_capture(page: Page) -> tuple[PageEventCapture, dict[str, Any]]:
    capture = PageEventCapture(console_errors=[], page_errors=[], request_failures=[])

    def on_console(message: Any) -> None:
        try:
            if message.type == "error":
                capture.console_errors.append(message.text)
        except Exception:
            capture.console_errors.append(str(message))

    def on_page_error(error: Any) -> None:
        capture.page_errors.append(str(error))

    def on_request_failed(request: Any) -> None:
        failure = getattr(request, "failure", None)
        error_text = "unknown"
        if failure is not None:
            error_text = getattr(failure, "error_text", None) or str(failure)
        capture.request_failures.append(
            {
                "method": str(getattr(request, "method", "")),
                "url": str(getattr(request, "url", "")),
                "failure": str(error_text),
            }
        )

    listeners = {
        "console": on_console,
        "pageerror": on_page_error,
        "requestfailed": on_request_failed,
    }
    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    return capture, listeners


def detach_page_event_capture(page: Page, listeners: dict[str, Any]) -> None:
    for event_name, callback in listeners.items():
        page.remove_listener(event_name, callback)


@contextmanager
def capture_page_events(page: Page) -> Iterator[PageEventCapture]:
    capture, listeners = attach_page_event_capture(page)
    try:
        yield capture
    finally:
        detach_page_event_capture(page, listeners)


def save_screenshot(page: Page, output_path: Path, *, full_page: bool = True) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output_path), full_page=full_page)
    return str(output_path)
