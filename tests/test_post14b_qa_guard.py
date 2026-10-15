"""Fail-closed admission and real isolated-app startup for native QA."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, qa_environment, start_qa_server, stop_qa_server,
)


def _child(root: Path, source: str, *, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = qa_environment(root)
    env.update(env_override or {})
    return subprocess.run(
        [sys.executable, "-c", source], cwd=root / "source", env=env,
        capture_output=True, text=True, check=False, timeout=20,
    )


def test_copied_real_app_starts_on_bounded_fixture_and_owned_process_stops() -> None:
    root = prepare_qa_root()
    process, port = start_qa_server(root)
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            assert response.status == 200
        with urlopen(f"http://127.0.0.1:{port}/qa-retained", timeout=5) as response:
            assert response.status == 200
            assert b"business-navigation" in response.read()
        manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
        for identity in manifest["retained_navigation_harness"].values():
            assert identity["original_sha256"] != identity["qa_harness_sha256"]
        copied_contract = (root / "source" / "frontend" / "js" / "view-contract.js").read_text(
            encoding="utf-8")
        production_contract = Path("frontend/js/view-contract.js").read_text(encoding="utf-8")
        assert "hash: `#${domView}`" in copied_contract
        assert "hash: `#${domView}`" not in production_contract
        from sqlite3 import connect
        with connect(root / "state" / "qa.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 230
            assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 640
            assert connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0] == 200
        admissions = [json.loads(line) for line in (root / "guard_admissions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()]
        assert {entry["operation"] for entry in admissions} >= {"server_preimport", "startup"}
        assert all(entry["counts"]["demographics"] <= 2_000 for entry in admissions)
    finally:
        stop_qa_server(process)
    assert process.poll() is not None


def test_named_qualification_fixture_has_separate_twenty_thousand_hard_cap() -> None:
    root = prepare_qa_root(fixture_kind="NAMED_10K_QUALIFICATION")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_kind"] == "NAMED_10K_QUALIFICATION"
    assert manifest["expected_demographics"] == 12_000
    assert manifest["max_demographics"] == 20_000
    assert qa_environment(root)["EXPECTED_DEMOGRAPHIC_ROWS"] == "12000"


def test_ui_catalog_fixture_is_explicitly_named_and_stays_under_default_cap() -> None:
    root = prepare_qa_root(fixture_kind="UI_CATALOG_DIVERSE")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_kind"] == "UI_CATALOG_DIVERSE"
    assert manifest["expected_demographics"] == 200
    assert manifest["max_demographics"] == 2_000


def test_similarity_threshold_fixture_is_named_and_stays_under_default_cap() -> None:
    root = prepare_qa_root(fixture_kind="SIMILARITY_THRESHOLDS")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_kind"] == "SIMILARITY_THRESHOLDS"
    assert manifest["expected_demographics"] == 200
    assert manifest["max_demographics"] == 2_000


def test_legacy_trainable_fixture_stays_under_default_cap_and_has_independent_groups() -> None:
    from sqlite3 import connect

    root = prepare_qa_root(fixture_kind="LEGACY_TRAINABLE")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["max_demographics"] == 2_000
    assert manifest["expected_demographics"] == 200
    assert manifest["expected_customers"] == 430
    assert manifest["expected_campaign_sales"] == 940
    process, _ = start_qa_server(root)
    try:
        with connect(root / "state" / "qa.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 430
            assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 940
            groups = connection.execute(
                "SELECT COUNT(DISTINCT campaign_id) FROM campaign_sales "
                "WHERE campaign_id LIKE 'CMP_TRAIN_%'"
            ).fetchone()[0]
            assert groups == 10
            counts = connection.execute(
                "SELECT SUM(CASE WHEN pu_label=1 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN pu_label=0 THEN 1 ELSE 0 END) "
                "FROM campaign_sales WHERE campaign_id LIKE 'CMP_TRAIN_%'"
            ).fetchone()
            assert counts == (100, 200)
            from app.services.historical_service import get_historical_options
            options = get_historical_options(root / "state" / "qa.db")
            assert len([item for item in options["campaigns"]
                        if item["campaign_id"].startswith("CMP_TRAIN_")]) == 10
    finally:
        stop_qa_server(process)


def test_calibratable_planner_fixture_keeps_independent_groups_and_bounded_prospects() -> None:
    from sqlite3 import connect

    root = prepare_qa_root(fixture_kind="PLANNER_CALIBRATABLE")
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["max_demographics"] == 2_000
    assert (manifest["expected_customers"], manifest["expected_campaign_sales"],
            manifest["expected_demographics"]) == (1_200, 1_840, 200)
    process, _ = start_qa_server(root)
    try:
        with connect(root / "state" / "qa.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0] == 200
            assert connection.execute(
                "SELECT COUNT(DISTINCT campaign_id) FROM campaign_sales "
                "WHERE campaign_type='Training Fixture'"
            ).fetchone()[0] == 10
            assert connection.execute(
                "SELECT COUNT(*),SUM(CASE WHEN pu_label=1 THEN 1 ELSE 0 END) "
                "FROM campaign_sales WHERE campaign_type='Training Fixture'"
            ).fetchone() == (1_200, 400)
    finally:
        stop_qa_server(process)


def test_empty_fixture_starts_real_app_without_fabricating_readiness() -> None:
    from sqlite3 import connect

    root = prepare_qa_root(fixture_kind="EMPTY")
    process, port = start_qa_server(root)
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            assert response.status == 200
        with connect(root / "state" / "qa.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles").fetchone()[0] == 0
    finally:
        stop_qa_server(process)


def test_sparse_buyer_fixture_is_catalog_visible_but_below_support() -> None:
    from sqlite3 import connect

    root = prepare_qa_root(fixture_kind="SPARSE_BUYERS")
    process, _ = start_qa_server(root)
    try:
        with connect(root / "state" / "qa.db") as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_sales WHERE product_id='P4'"
            ).fetchone()[0] == 8
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_sales WHERE product_id='P3'"
            ).fetchone()[0] == 202
            assert connection.execute(
                "SELECT COUNT(*) FROM demographics"
            ).fetchone()[0] == 200
    finally:
        stop_qa_server(process)


def test_five_million_metadata_and_foreign_paths_reject_before_body() -> None:
    root = prepare_qa_root()
    marker = root / "body_started"
    body = (
        "from pathlib import Path; "
        "from app.qa_guard import assert_qa_runtime; "
        "assert_qa_runtime(Path('" + str(root / "state" / "qa.db").replace("\\", "\\\\") + "'), "
        "project_root=Path('" + str(root / "source").replace("\\", "\\\\") + "'), "
        "operation='metadata_five_million',record_admission=True); "
        "Path('" + str(marker).replace("\\", "\\\\") + "').write_text('unsafe')"
    )
    denied = _child(root, body, env_override={"EXPECTED_DEMOGRAPHIC_ROWS": "5000000"})
    assert denied.returncode != 0
    assert "exceeds the bounded-QA manifest cap" in denied.stderr
    assert not marker.exists()
    wrong_db = _child(root, body.replace(str(root / "state" / "qa.db").replace("\\", "\\\\"),
                                         str(root / "operator.db").replace("\\", "\\\\")))
    assert wrong_db.returncode != 0
    assert "database path is not the isolated fixture DB" in wrong_db.stderr
    assert not (root / "operator.db").exists()
    wrong_source = _child(root, body.replace(str(root / "source").replace("\\", "\\\\"),
                                             str(root / "foreign_source").replace("\\", "\\\\")))
    assert wrong_source.returncode != 0
    assert "artifact/source root is not the isolated copy" in wrong_source.stderr
    assert not marker.exists()


def test_actual_rows_over_manifest_cap_reject_worker_before_body() -> None:
    root = prepare_qa_root()
    process, _ = start_qa_server(root)
    stop_qa_server(process)
    manifest_path = root / "qa_fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["max_demographics"] = 100
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    denied = _child(
        root,
        "from app.services.buyer_similarity_scoring_service import run_similarity_generation; "
        "run_similarity_generation('" + str(root / "state" / "qa.db").replace("\\", "\\\\")
        + "', 1, project_root='" + str(root / "source").replace("\\", "\\\\")
        + "', execution_owner='qa', execution_token='bounded')",
        env_override={"EXPECTED_DEMOGRAPHIC_ROWS": "100"},
    )
    assert denied.returncode != 0
    assert "Actual demographics rows exceed the bounded-QA cap" in denied.stderr
    assert not (root / "guard_admissions.jsonl").read_text(encoding="utf-8").endswith(
        '"operation": "v3_score_generation"}\n'
    )


def test_queued_forbidden_job_is_not_resumed_at_startup() -> None:
    from sqlite3 import connect

    root = prepare_qa_root()
    process, _ = start_qa_server(root)
    stop_qa_server(process)
    database = root / "state" / "qa.db"
    with connect(database) as connection:
        # This is an admission-only startup fixture. The dummy model reference
        # is deliberately not executable; the guard must reject even before
        # recovery can inspect a queued work item.
        connection.execute("PRAGMA foreign_keys=OFF")
        cursor = connection.execute(
            """INSERT INTO jobs (job_type,status,progress_percent,stage,model_run_id,created_at,request_json)
               VALUES ('PROSPECT_SCORING','QUEUED',0,'QUEUED',1,
                       '2026-10-13T00:00:00Z','{}')"""
        )
        job_id = cursor.lastrowid
    manifest_path = root / "qa_fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["max_demographics"] = 100
    manifest["expected_demographics"] = 100
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeError, match="exited during startup"):
        start_qa_server(root, timeout_seconds=60)
    with connect(database) as connection:
        assert connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0] == "QUEUED"
