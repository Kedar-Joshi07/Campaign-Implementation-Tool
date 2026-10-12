"""Keep the 14B execution manifest aligned with the reviewed prompt files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PACK_ROOT = (
    Path(__file__).resolve().parents[1]
    / "Prompts"
    / "Campaign_Implementation_Tool_14B_Lookalike_Prompt_Pack"
)


def test_pack_manifest_covers_every_prompt_and_its_current_bytes() -> None:
    manifest = json.loads((PACK_ROOT / "PACK_MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest["files"]
    names = [entry["name"] for entry in entries]

    assert manifest["stage_count"] == 10
    assert manifest["companion_count"] == 6
    assert manifest["concurrent_lane_count"] == 4
    assert manifest["status"].startswith("IMPLEMENTED_")
    assert len(names) == len(set(names))
    assert set(names) == {
        path.name for path in PACK_ROOT.iterdir() if path.is_file()
    } - {"PACK_MANIFEST.json"}

    for entry in entries:
        payload = (PACK_ROOT / entry["name"]).read_bytes()
        assert len(payload) == entry["bytes"], entry["name"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], entry["name"]


def test_release_report_reconciles_its_latest_exact_sha_checkpoint() -> None:
    root = Path(__file__).resolve().parents[1]
    report = json.loads(
        (root / "docs/evidence/lookalike_v3/19_FINAL_RELEASE_GATE.json").read_text(
            encoding="utf-8"
        )
    )
    latest = report["latest_exact_sha_checkpoint"]

    assert report["candidate"] == latest["validated_executable_sha"]
    assert report["current_head"] == latest["validated_executable_sha"]
    assert report["remote"]["candidate_ci_head_sha"] == latest["validated_executable_sha"]
    assert report["remote"]["candidate_ci_run_id"] == latest["pr_ci_run_id"]
    assert report["remote"]["candidate_manual_run_id"] == latest["manual_run_id"]
    assert latest["pr_ci_conclusion"] == "success_all_five_jobs"
    assert latest["manual_conclusion"] == "failure"
    assert report["verdict"] == "FINAL_RELEASE_NO_GO_MANUAL_FULL_FRESH_GOVERNED_SPLIT"
