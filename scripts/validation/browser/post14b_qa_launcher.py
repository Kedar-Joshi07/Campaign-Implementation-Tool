"""Prepare and own an isolated, bounded native-browser QA application."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QA_PARENT = REPOSITORY_ROOT / "output" / "post14b_closure"
COPY_DIRECTORIES = ("app", "frontend", "scripts", "tests", "data_generation_scripts")
DEFAULT_MANIFEST = {
    "contract": "POST14B_QA_V1",
    "fixture_kind": "DEFAULT",
    "fixture_version": "sources/qa_v1",
    "max_customers": 1_000,
    "max_campaign_sales": 3_000,
    "max_demographics": 2_000,
    "expected_customers": 230,
    "expected_campaign_sales": 640,
    "expected_demographics": 200,
    "products": ["P1", "P2", "P3"],
    "sparse_product_id": "P4",
    "minimum_support": {"total": 200, "fit": 160, "holdout": 40},
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_retained_navigation_harness(source: Path) -> dict[str, dict[str, str]]:
    """Alter only the disposable copy's presentation routing, never controllers."""
    path = source / "frontend" / "js" / "view-contract.js"
    original_hash = _sha(path)
    content = path.read_text(encoding="utf-8")
    replacements = (
        ("group, domView, title, showInNavigation: false,",
         'group, domView, title, hash: `#${domView}`, '
         'showInNavigation: location.pathname === "/qa-retained",'),
        ("if (definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE) view.hidden = true;",
         "if (definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE && !definition?.showInNavigation) view.hidden = true;"),
        ("control.hidden = definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE\n"
         "      || (inNavigation && !definition.showInNavigation);",
         "control.hidden = (definition?.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE\n"
         "      && !definition?.showInNavigation) || (inNavigation && !definition.showInNavigation);"),
    )
    for old, new in replacements:
        if content.count(old) != 1:
            raise RuntimeError("Retained QA navigation source contract changed; refuse harness rewrite.")
        content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    view_identity = {"original_sha256": original_hash, "qa_harness_sha256": _sha(path)}
    app_path = source / "frontend" / "js" / "app.js"
    app_original_hash = _sha(app_path)
    app_content = app_path.read_text(encoding="utf-8")
    old = "  const title = route.definition.title;\n"
    new = ("  // QA-only retained-component navigation: normal production routing never calls this.\n"
           "  if (location.pathname === \"/qa-retained\"\n"
           "      && route.definition.group !== VIEW_GROUPS.BUSINESS_USER_VISIBLE) {\n"
           "    loadLegacyWorkspace(route.key);\n"
           "  }\n" + old)
    if app_content.count(old) != 1:
        raise RuntimeError("Retained QA loader seam changed; refuse harness rewrite.")
    app_path.write_text(app_content.replace(old, new), encoding="utf-8")
    return {
        "view_contract": view_identity,
        "app_loader": {"original_sha256": app_original_hash,
                       "qa_harness_sha256": _sha(app_path)},
    }


def prepare_qa_root(*, fixture_kind: str = "DEFAULT") -> Path:
    """Copy current executable code and create one never-reused QA root."""
    if fixture_kind not in {"DEFAULT", "NAMED_10K_QUALIFICATION", "LEGACY_TRAINABLE",
                            "PLANNER_TRAINABLE", "PLANNER_CALIBRATABLE",
                            "UI_CATALOG_DIVERSE", "SIMILARITY_THRESHOLDS",
                            "SPARSE_BUYERS", "FAULT_ONCE", "EMPTY"}:
        raise ValueError("Unknown bounded-QA fixture kind.")
    QA_PARENT.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="n", dir=QA_PARENT)).resolve()
    if root.parent != QA_PARENT.resolve():
        raise RuntimeError("QA root escaped its dedicated parent.")
    source = root / "source"
    source.mkdir()
    for name in COPY_DIRECTORIES:
        shutil.copytree(
            REPOSITORY_ROOT / name, source / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    for name in ("state", "browser_profile", "downloads", "logs"):
        (root / name).mkdir()
    harness_identity = _install_retained_navigation_harness(source)
    manifest = dict(DEFAULT_MANIFEST)
    manifest["fixture_kind"] = fixture_kind
    if fixture_kind == "NAMED_10K_QUALIFICATION":
        manifest.update({"fixture_kind": fixture_kind, "max_demographics": 20_000,
                         "expected_demographics": 12_000})
    elif fixture_kind in {"LEGACY_TRAINABLE", "PLANNER_TRAINABLE"}:
        manifest.update({"fixture_kind": fixture_kind, "expected_customers": 430,
                         "expected_campaign_sales": 940})
    elif fixture_kind == "PLANNER_CALIBRATABLE":
        manifest.update({"fixture_kind": fixture_kind, "max_customers": 2_000,
                         "expected_customers": 1_200, "expected_campaign_sales": 1_840})
    elif fixture_kind == "EMPTY":
        manifest.update({"fixture_kind": fixture_kind, "expected_customers": 0,
                         "expected_campaign_sales": 0, "expected_demographics": 0,
                         "products": [], "sparse_product_id": None})
    manifest["source_sha256"] = {
        relative: _sha(REPOSITORY_ROOT / relative)
        for relative in ("app/main.py", "app/qa_guard.py", "frontend/index.html")
    }
    manifest["retained_navigation_harness"] = harness_identity
    manifest_path = root / "qa_fixture_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert all(
        _sha(source / relative) == digest
        for relative, digest in manifest["source_sha256"].items()
    )
    return root


def qa_environment(root: Path) -> dict[str, str]:
    root = root.resolve()
    if root.parent != QA_PARENT.resolve() or not (root / "qa_fixture_manifest.json").is_file():
        raise ValueError("Only a prepared, dedicated Post-14B QA root is allowed.")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["source_sha256"].items():
        if _sha(root / "source" / relative) != digest:
            raise ValueError("The isolated executable copy changed after manifest freeze.")
    for key, relative in (("view_contract", "frontend/js/view-contract.js"),
                          ("app_loader", "frontend/js/app.js")):
        if _sha(root / "source" / relative) != (
            manifest["retained_navigation_harness"][key]["qa_harness_sha256"]
        ):
            raise ValueError("The retained QA navigation harness changed after manifest freeze.")
    env = dict(os.environ)
    env.update({
        "POST14B_QA_MODE": "BOUNDED_NATIVE",
        "POST14B_QA_ROOT": str(root),
        "POST14B_QA_MANIFEST": str(root / "qa_fixture_manifest.json"),
        "DATABASE_PATH": str(root / "state" / "qa.db"),
        "EXPECTED_CUSTOMER_ROWS": str(manifest["expected_customers"]),
        "EXPECTED_CAMPAIGN_SALES_ROWS": str(manifest["expected_campaign_sales"]),
        "EXPECTED_DEMOGRAPHIC_ROWS": str(manifest["expected_demographics"]),
        "APP_ENV": "qa",
        "HOST": "127.0.0.1",
        "PYTHONPATH": str(root / "source"),
    })
    return env


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_qa_server(root: Path, *, timeout_seconds: float = 90.0) -> tuple[subprocess.Popen, int]:
    """Start actual copied app; caller owns and must stop this exact process."""
    env = qa_environment(root)
    port = _free_loopback_port()
    env["PORT"] = str(port)
    log_path = root / "logs" / "server.log"
    log = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.validation.browser.post14b_qa_server"],
            cwd=root / "source", env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        log.close()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"QA app exited during startup; inspect {log_path}.")
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                if response.status == 200:
                    return process, port
        except (URLError, TimeoutError):
            pass
        time.sleep(0.2)
    process.terminate()
    process.wait(timeout=10)
    raise TimeoutError(f"QA app did not become healthy; inspect {log_path}.")


def stop_qa_server(process: subprocess.Popen) -> None:
    """Stop only the process object created by this launcher."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    prepared = prepare_qa_root()
    print(prepared)
