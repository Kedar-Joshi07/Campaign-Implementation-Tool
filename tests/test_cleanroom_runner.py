from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cleanroom_runner_smoke_integration(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "scripts" / "validation" / "run_cleanroom_phase1_to_phase7.py"

    runtime_root = tmp_path / "cleanroom-runtime"
    report_path = tmp_path / "CLEANROOM_PHASE1_TO_PHASE7_REPORT.md"
    json_path = tmp_path / "cleanroom_phase1_to_phase7.json"

    command = [
        sys.executable,
        str(script_path),
        "--customers",
        "500",
        "--campaign-sales",
        "3500",
        "--demographics",
        "4000",
        "--seed-base",
        "20260903",
        "--runtime-root",
        str(runtime_root),
        "--report-path",
        str(report_path),
        "--json-path",
        str(json_path),
    ]

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        "Clean-room runner failed.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )

    assert report_path.is_file()
    assert json_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "PASS"
    assert payload["stages"]["cleanup"]["runtime_removed"] is True
    assert not runtime_root.exists()

    campaigns = payload["stages"]["step5"]["campaigns"]
    assert "EMAIL" in campaigns
    assert "DIRECT_MAIL" in campaigns
