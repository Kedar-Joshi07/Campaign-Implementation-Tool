"""Run the independent bounded fresh-v3 gate in a disposable local root.

This intentionally does not call the canonical full-fresh probability runner,
import canonical sources, or dispatch remote CI. The pytest gate uses actual
production import, app lifespan, coordinator, scoring, export and feedback.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Keep this path short on Windows: immutable profile artifact names are long.
QA_PARENT = PROJECT_ROOT / "output" / "post14b_closure" / "q"
TEST = PROJECT_ROOT / "tests" / "test_post14b_fresh_v3_gate.py"
REQUIRED_LOCKS = (PROJECT_ROOT / "requirements.lock", PROJECT_ROOT / "requirements-browser.lock")


def validate_qa_root(root: Path) -> Path:
    resolved = root.resolve()
    if not resolved.is_relative_to(QA_PARENT.resolve()) or resolved == QA_PARENT.resolve():
        raise ValueError("Fresh-v3 work must stay under the dedicated disposable QA tree.")
    return resolved


def main() -> int:
    if not TEST.is_file():
        raise SystemExit("The bounded fresh-v3 test is missing; no gate was run.")
    if any(not lock.is_file() for lock in REQUIRED_LOCKS):
        raise SystemExit("A pinned dependency lock is missing; no gate was run.")
    QA_PARENT.mkdir(parents=True, exist_ok=True)
    root = validate_qa_root(Path(tempfile.mkdtemp(prefix="q", dir=QA_PARENT)))
    print(f"Fresh-v3 disposable root: {root}", flush=True)
    print("Fixture cap: 200 prospects; three synthetic products; no canonical sources.", flush=True)
    return subprocess.call([
        sys.executable, "-m", "pytest", "-q", str(TEST), "--maxfail=1",
        "--tb=short", "--basetemp", str(root / "t"),
    ], cwd=PROJECT_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
