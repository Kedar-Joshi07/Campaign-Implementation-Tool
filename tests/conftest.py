from __future__ import annotations

from pathlib import Path


CLEANROOM_FILES = {"test_cleanroom_runner.py"}
BROWSER_FILES = {"test_frontend.py"}


def _item_path_name(item) -> str:
    candidate = getattr(item, "path", None)
    if candidate is None:
        candidate = getattr(item, "fspath", "")
    return Path(str(candidate)).name.lower()


def pytest_collection_modifyitems(config, items) -> None:  # pragma: no cover
    for item in items:
        filename = _item_path_name(item)
        nodeid = item.nodeid.lower()

        if filename in CLEANROOM_FILES:
            item.add_marker("cleanroom")
            item.add_marker("integration")
            continue

        if filename in BROWSER_FILES:
            item.add_marker("browser")
            item.add_marker("integration")
            continue

        if "real_5m" in nodeid or "full5m" in nodeid:
            item.add_marker("full5m")
            item.add_marker("performance")
            item.add_marker("integration")
            continue

        if "performance" in nodeid:
            item.add_marker("performance")

        if filename.endswith("_api.py") or filename.endswith("_ui.py"):
            item.add_marker("integration")
            continue

        item.add_marker("unit")
