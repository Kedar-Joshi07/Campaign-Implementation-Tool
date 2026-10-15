"""Opt-in, fail-closed Post-14B bounded-QA admission guard.

Production behavior is unchanged when the POST14B_QA_* variables are absent.
When any are present, a partial/malformed configuration is an error. This is an
accidental-scale safety boundary for isolated local QA, not production auth.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_QA_KEYS = ("POST14B_QA_MODE", "POST14B_QA_ROOT", "POST14B_QA_MANIFEST")
_LOG_LOCK = Lock()


class QAGuardRejected(RuntimeError):
    """The requested QA operation is outside its bounded isolated fixture."""


def _enabled() -> bool:
    return any(os.environ.get(key) for key in _QA_KEYS)


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _configuration() -> tuple[Path, dict] | None:
    if not _enabled():
        return None
    if os.environ.get("POST14B_QA_MODE") != "BOUNDED_NATIVE":
        raise QAGuardRejected("Incomplete or invalid bounded-QA mode.")
    raw_root = os.environ.get("POST14B_QA_ROOT")
    raw_manifest = os.environ.get("POST14B_QA_MANIFEST")
    if not raw_root or not raw_manifest:
        raise QAGuardRejected("Bounded-QA root and manifest are required.")
    root = Path(raw_root).resolve()
    if not root.is_dir() or root.parent.name != "post14b_closure" or root.parent.parent.name != "output":
        raise QAGuardRejected("Bounded-QA root is not a dedicated post14b_closure child.")
    if Path(__file__).resolve().parents[1] != root / "source":
        raise QAGuardRejected("Bounded-QA code must execute from the isolated source copy.")
    manifest_path = Path(raw_manifest).resolve()
    if manifest_path != root / "qa_fixture_manifest.json":
        raise QAGuardRejected("Bounded-QA manifest must be inside the dedicated root.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QAGuardRejected("Bounded-QA fixture manifest is missing or invalid.") from exc
    if not isinstance(manifest, dict) or manifest.get("contract") != "POST14B_QA_V1":
        raise QAGuardRejected("Unsupported bounded-QA fixture contract.")
    named = manifest.get("fixture_kind") == "NAMED_10K_QUALIFICATION"
    hard_cap = 20_000 if named else 2_000
    cap = manifest.get("max_demographics")
    if type(cap) is not int or not 1 <= cap <= hard_cap:
        raise QAGuardRejected("Bounded-QA demographic cap exceeds its permitted fixture class.")
    for field in ("max_customers", "max_campaign_sales"):
        value = manifest.get(field)
        if type(value) is not int or not 1 <= value <= 100_000:
            raise QAGuardRejected(f"Invalid bounded-QA {field} cap.")
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise QAGuardRejected("Bounded-QA app must bind to loopback.")
    for field, env in (
        ("max_customers", "EXPECTED_CUSTOMER_ROWS"),
        ("max_campaign_sales", "EXPECTED_CAMPAIGN_SALES_ROWS"),
        ("max_demographics", "EXPECTED_DEMOGRAPHIC_ROWS"),
    ):
        raw = os.environ.get(env)
        if raw is None:
            raise QAGuardRejected(f"{env} must be configured before app import.")
        try:
            expected = int(raw)
        except ValueError as exc:
            raise QAGuardRejected(f"{env} is not an integer.") from exc
        if expected < 0 or expected > manifest[field]:
            raise QAGuardRejected(f"{env} exceeds the bounded-QA manifest cap.")
    return root, manifest


def assert_qa_runtime(
    database_path: str | Path,
    *,
    project_root: str | Path | None = None,
    operation: str = "runtime",
    record_admission: bool = False,
) -> dict[str, int] | None:
    """Reject foreign roots/metadata and independently count real table rows."""
    configured = _configuration()
    if configured is None:
        return None
    root, manifest = configured
    db = Path(database_path).resolve()
    expected_db = root / "state" / "qa.db"
    if db != expected_db:
        raise QAGuardRejected("Bounded-QA database path is not the isolated fixture DB.")
    if project_root is not None and Path(project_root).resolve() != root / "source":
        raise QAGuardRejected("Bounded-QA artifact/source root is not the isolated copy.")
    if not _inside(db, root):
        raise QAGuardRejected("Bounded-QA database escaped the fixture root.")
    counts = {"customers": 0, "campaign_sales": 0, "demographics": 0}
    if db.exists():
        try:
            connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            try:
                for table in counts:
                    exists = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    ).fetchone()
                    if exists:
                        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise QAGuardRejected("Bounded-QA database cannot be counted safely.") from exc
    for table, cap_field in (
        ("customers", "max_customers"),
        ("campaign_sales", "max_campaign_sales"),
        ("demographics", "max_demographics"),
    ):
        if counts[table] > manifest[cap_field]:
            raise QAGuardRejected(f"Actual {table} rows exceed the bounded-QA cap.")
    if record_admission:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "operation": operation,
            "database": "state/qa.db",
            "counts": counts,
            "cap": manifest["max_demographics"],
        }
        with _LOG_LOCK:
            with (root / "guard_admissions.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")
    return counts
