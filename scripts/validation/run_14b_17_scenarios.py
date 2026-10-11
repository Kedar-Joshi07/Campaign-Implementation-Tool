"""Checkpointed, serial Prompt 17 certification on an existing disposable full-5M DB.

The source scenario JSON and recorded context are read-only. No product,
demographic filter, or minimum is inferred from the outcome counts.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.buyer_similarity_preflight_service import exact_similarity_preflight  # noqa: E402
from app.services.potential_customer_search_submission_service import search_form_options  # noqa: E402
from app.database.connection import get_connection  # noqa: E402

SCENARIOS = (ROOT / "Prompts" /
             "Campaign_Implementation_Tool_Demo_Readiness_20_Real_Runs_Prompt_Pack" /
             "scenarios.json")
CONTEXT = ROOT / "output" / "demo_preload" / "demo_20_scenario_checkpoint.json"
SCRATCH = ROOT / "output" / "lookalike_stage16_2_measurements"
EVIDENCE = ROOT / "docs" / "evidence" / "lookalike_v3"
CHECKPOINT = EVIDENCE / "17_SCENARIO_CHECKPOINT.json"
TRANSLATION = EVIDENCE / "17_V3_TRANSLATION.json"
MINIMUM = 10_000
THRESHOLDS = {"VERY_STRONG": .90, "STRONG": .80, "GOOD": .70, "BROAD": .60}
FIELDS = (
    "genders", "age_groups", "states", "income_groups", "marital_statuses",
    "education_levels", "employment_statuses", "resident_statuses",
    "resident_types", "employment_types", "family_member_count_min",
    "family_member_count_max",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _inputs() -> tuple[dict, list[dict], dict, str, str]:
    if not CONTEXT.is_file():
        raise RuntimeError("Recorded common-context manifest is absent; do not guess a replacement.")
    scenario_bytes = SCENARIOS.read_bytes()
    context_bytes = CONTEXT.read_bytes()
    scenarios = json.loads(scenario_bytes)["scenarios"]
    if [row["id"] for row in scenarios] != list(range(1, 21)):
        raise RuntimeError("Canonical scenario IDs must remain 1 through 20.")
    if Counter(row["match_strength"] for row in scenarios) != Counter(
        {"VERY_STRONG": 1, "STRONG": 2, "GOOD": 7, "BROAD": 10}
    ):
        raise RuntimeError("The canonical strength distribution changed.")
    original = json.loads(context_bytes)
    context = original["common_context"]
    return original, scenarios, context, _sha(scenario_bytes), _sha(context_bytes)


def _init(scratch: Path) -> tuple[dict, list[dict], dict, dict]:
    db = scratch / "certification.db"
    if not db.is_file() or not (scratch / "data" / "product_master.csv").is_file():
        raise RuntimeError("Verified disposable Prompt 16 database/artifacts are unavailable.")
    previous = json.loads((scratch / "run_manifest.json").read_text(encoding="utf-8"))
    if previous.get("phases", {}).get("verify", {}).get("status") != "PASS_THREE_PRODUCT_CONTEXT":
        raise RuntimeError("Prompt 16 exact three-product context is not certified.")
    original, scenarios, context, scenario_sha, context_sha = _inputs()
    if context != previous.get("recorded_common_context"):
        raise RuntimeError("Recorded common context differs from the Prompt 16 certification.")
    if CHECKPOINT.is_file():
        state = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        if (state["scenario_json_sha256"] != scenario_sha
            or state["context_manifest_sha256"] != context_sha
            or state["database"] != str(db.relative_to(ROOT))):
            raise RuntimeError("Checkpoint inputs changed; do not silently reuse old counts/runs.")
    else:
        state = {
            "version": "14B_17_CANONICAL_V3_V1",
            "starting_sha": "336875c30fc32b00323d916ecc45b232016168a1",
            "candidate": "UNCOMMITTED",
            "database": str(db.relative_to(ROOT)),
            "scenario_json_sha256": scenario_sha,
            "context_manifest_sha256": context_sha,
            "recorded_context": context,
            "qualification_minimum": MINIMUM,
            "preflights": {}, "runs": {},
            "created_at": _now(),
        }
        _save(CHECKPOINT, state)
    return state, scenarios, context, original


def preflight(scratch: Path) -> None:
    state, scenarios, context, _ = _init(scratch)
    db = scratch / "certification.db"
    options = search_form_options(db, include_similarity=True)
    email = [p for p in options["profiles"] if p["channel_code"] == "EMAIL"
             and p["selection_contract_version"] == "3"]
    if len(email) != 2:
        raise RuntimeError("Expected two explicit V3 EMAIL export profiles.")
    translation = {
        "version": "CANONICAL_20_LEGACY_STRENGTH_TO_V3_SIMILARITY_V1",
        "source_scenario_json": str(SCENARIOS.relative_to(ROOT)),
        "source_scenario_json_sha256": state["scenario_json_sha256"],
        "historical_json_minimum": 101,
        "current_demo_minimum": MINIMUM,
        "recorded_context_manifest": str(CONTEXT.relative_to(ROOT)),
        "recorded_context_manifest_sha256": state["context_manifest_sha256"],
        "recorded_context": context,
        "catalog_version": options["catalog_version"],
        "selection_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "threshold_predicate": "GREATER_THAN_OR_EQUAL",
        "mapping": THRESHOLDS,
        "scenarios": [
            {"id": s["id"], "match_strength": s["match_strength"],
             "similarity_minimum": THRESHOLDS[s["match_strength"]],
             "criteria": {field: s[field] for field in FIELDS}}
            for s in scenarios
        ],
    }
    for scenario in scenarios:
        key = str(scenario["id"])
        if key in state["preflights"]:
            print(f"scenario={key} checkpointed", flush=True)
            continue
        threshold = THRESHOLDS[scenario["match_strength"]]
        start = time.perf_counter()
        result = exact_similarity_preflight(
            db, context=context, criteria={field: scenario[field] for field in FIELDS},
            similarity_minimum=threshold, selection_mode="ALL_MATCHING", top_n=None,
            catalog_version=options["catalog_version"], project_root=scratch,
        )
        state["preflights"][key] = {
            "scenario_id": scenario["id"], "scenario_name": scenario["name"],
            "legacy_strength": scenario["match_strength"],
            "similarity_minimum": threshold,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "preflight": result,
            "qualifies": (result["similarity_currentness"] == "CURRENT"
                          and result["selected_count"] is not None
                          and result["selected_count"] >= MINIMUM),
            "contact_export_profile_availability": [
                {"export_profile": p["export_profile"],
                 "availability": p["availability"]} for p in email
            ],
            "recorded_at": _now(),
        }
        _save(CHECKPOINT, state)
        print(f"scenario={key} current={result['similarity_currentness']} "
              f"eligible={result['demographic_eligible_count']} "
              f"valid={result['valid_similarity_count']} "
              f"invalid={result['invalid_similarity_count']} "
              f"selected={result['selected_count']} "
              f"qualifies={state['preflights'][key]['qualifies']}", flush=True)
    first = state["preflights"]["1"]["preflight"]
    for key in ("source_identity_sha256", "profile_ids", "profile_set_sha256",
                "similarity_generation_ids", "composite_context_sha256"):
        translation[key] = first[key]
    _save(TRANSLATION, translation)
    print(f"qualified={sum(row['qualifies'] for row in state['preflights'].values())}/20", flush=True)


def _http(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    encoded = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url + path, data=encoded, method=method,
        headers={"Content-Type": "application/json"} if encoded else {},
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.load(response)
    except HTTPError as exc:
        message = exc.read(512).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {path}: {message}") from exc


def _existing_run(database: Path, campaign_name: str) -> int | None:
    with get_connection(database) as connection:
        matches = connection.execute(
            "SELECT search_run_id FROM campaign_search_runs WHERE campaign_name=? "
            "ORDER BY search_run_id", (campaign_name,),
        ).fetchall()
    if len(matches) > 1:
        raise RuntimeError("Checkpoint identity found duplicate saved runs.")
    return int(matches[0][0]) if matches else None


def _file_evidence(scratch: Path, snapshot: dict) -> dict:
    path = scratch / snapshot["storage_uri"]
    if not path.is_file() or not path.resolve().is_relative_to(scratch.resolve()):
        raise RuntimeError("Immutable membership file is absent or outside scratch.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        count = sum(1 for _ in reader)
    if digest.hexdigest() != snapshot["snapshot_sha256"] or count != snapshot["resolved_count"]:
        raise RuntimeError("Membership file count or hash differs from the immutable registry.")
    return {"member_count": count, "membership_sha256": digest.hexdigest(),
            "storage_uri": snapshot["storage_uri"]}


def run(scratch: Path, base_url: str) -> None:
    state, scenarios, context, _ = _init(scratch)
    if len(state["preflights"]) != 20 or not TRANSLATION.is_file():
        raise RuntimeError("All 20 exact preflights and translation must complete first.")
    db = scratch / "certification.db"
    options = _http(base_url, "GET", "/api/potential-customer-search/options?include_similarity=true")
    translation = json.loads(TRANSLATION.read_text(encoding="utf-8"))
    if options["catalog_version"] != translation["catalog_version"]:
        raise RuntimeError("Catalog changed after exact preflight; refresh counts first.")
    profiles = [p for p in options["profiles"] if p["channel_code"] == "EMAIL"
                and p["selection_contract_version"] == "3"
                and p["analytical_fields"] and p["availability"] == "AVAILABLE"]
    if len(profiles) != 1:
        raise RuntimeError("Expected one available V3 EMAIL analytical export profile.")
    for scenario in scenarios:
        key = str(scenario["id"])
        preflight_row = state["preflights"][key]
        if not preflight_row["qualifies"]:
            continue
        if state["runs"].get(key, {}).get("terminal_status") == "COMPLETED":
            print(f"scenario={key} completed checkpoint", flush=True)
            continue
        name = f"14B17 canonical {scenario['id']:02d} {state['scenario_json_sha256'][:10]}"
        record = state["runs"].get(key, {"scenario_id": scenario["id"],
                                           "campaign_name": name})
        run_id = record.get("search_run_id") or _existing_run(db, name)
        if run_id is None:
            request = {
                "selection_contract_version": "3",
                "score_semantics": "PRODUCT_BUYER_SIMILARITY",
                "similarity_minimum": preflight_row["similarity_minimum"],
                "campaign_name": name,
                "description": f"Canonical scenario {scenario['id']}: {scenario['name']}",
                "context": context,
                "criteria": {field: scenario[field] for field in FIELDS},
                "selection_mode": "ALL_MATCHING", "top_n": None,
                "export_profile": profiles[0]["export_profile"],
                "catalog_version": options["catalog_version"],
            }
            start = time.perf_counter()
            try:
                created = _http(base_url, "POST", "/api/potential-customer-search/runs", request)
            except RuntimeError as exc:
                record["submission_error"] = str(exc)
                record["terminal_status"] = "SUBMISSION_ERROR"
                state["runs"][key] = record
                _save(CHECKPOINT, state)
                print(f"scenario={key} submission_error={exc}", flush=True)
                continue
            run_id = int(created["search_run_id"])
            record["submission_seconds"] = round(time.perf_counter() - start, 3)
            record["created_status"] = created["status"]
            record["created_at"] = _now()
        record["search_run_id"] = run_id
        state["runs"][key] = record
        _save(CHECKPOINT, state)
        print(f"scenario={key} run_id={run_id} submitted", flush=True)
        started = time.perf_counter()
        while True:
            status = _http(base_url, "GET", f"/api/potential-customer-search/runs/{run_id}/status")
            record["attempt_number"] = status.get("attempt_number")
            record["last_status"] = status["status"]
            record["last_stage"] = status.get("progress", {}).get("stage_code")
            if status["status"] in {"COMPLETED", "BLOCKED", "FAILED"}:
                break
            time.sleep(5)
        record["terminal_status"] = status["status"]
        record["terminal_at"] = _now()
        record["poll_wait_seconds"] = round(time.perf_counter() - started, 3)
        record["processing_seconds"] = status.get("progress", {}).get("processing_seconds")
        record["total_elapsed_seconds"] = status.get("progress", {}).get("total_elapsed_seconds")
        record["issue"] = status.get("issue")
        with get_connection(db) as connection:
            saved = dict(connection.execute(
                "SELECT * FROM campaign_search_runs WHERE search_run_id=?", (run_id,),
            ).fetchone())
            snapshot_id = saved.get("similarity_result_snapshot_id")
            snapshot = (dict(connection.execute(
                "SELECT * FROM buyer_similarity_result_snapshots "
                "WHERE similarity_result_snapshot_id=?", (snapshot_id,),
            ).fetchone()) if snapshot_id is not None else None)
        record["lineage"] = {field: saved.get(field) for field in (
            "similarity_generation_id", "similarity_result_snapshot_id",
            "similarity_profile_set_sha256", "similarity_composite_context_sha256",
            "phase10_orchestration_id", "result_source", "selected_count",
        )}
        if status["status"] == "COMPLETED" and snapshot is not None:
            try:
                record["membership"] = _file_evidence(scratch, snapshot)
                detail = _http(base_url, "GET", f"/api/potential-customer-search/runs/{run_id}/result")
                provenance = detail.get("snapshot_provenance") or {}
                record["reopen"] = {
                    "currentness": provenance.get("currentness"),
                    "resolved_count": provenance.get("resolved_count"),
                    "download_eligible": detail.get("download_eligible"),
                    "selection_label": detail.get("selection_label"),
                    "export_summary": detail.get("export_summary"),
                }
                expected = preflight_row["preflight"]["selected_count"]
                record["exact_count_match"] = (
                    expected == record["membership"]["member_count"]
                    == provenance.get("resolved_count") == saved.get("selected_count")
                )
            except Exception as exc:
                record["verification_error"] = f"{type(exc).__name__}: {exc}"
        state["runs"][key] = record
        _save(CHECKPOINT, state)
        print(f"scenario={key} terminal={record['terminal_status']} "
              f"members={record.get('membership', {}).get('member_count')} "
              f"exact={record.get('exact_count_match')}", flush=True)


def browser(scratch: Path, base_url: str) -> None:
    from playwright.sync_api import expect, sync_playwright
    from scripts.validation.browser.system_browser import launch_system_browser_session

    state, scenarios, _, _ = _init(scratch)
    completed = [(scenario, state["runs"].get(str(scenario["id"]), {}))
                 for scenario in scenarios]
    completed = [(scenario, row) for scenario, row in completed
                 if row.get("terminal_status") == "COMPLETED"]
    if not completed:
        raise RuntimeError("There are no completed real runs to certify in the browser.")
    screenshot_dir = EVIDENCE / "17_browser_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        with launch_system_browser_session(
            playwright, app_url=base_url + "/", viewport={"width": 1440, "height": 900}
        ) as session:
            page = session.page
            state["browser"] = {"metadata": session.metadata.to_dict(),
                                "screenshots": state.get("browser", {}).get("screenshots", {})}
            for scenario, row in completed:
                key = str(scenario["id"])
                run_id = row["search_run_id"]
                page.goto(base_url + f"/#results/{run_id}", wait_until="domcontentloaded")
                page.locator("#result-detail-content:not([hidden])").wait_for(timeout=120_000)
                expect(page.locator("#result-detail-run-id")).to_have_text(
                    f"Search #{run_id}", timeout=120_000
                )
                disclosure = page.locator("#result-technical-disclosure")
                if disclosure.get_attribute("open") is None:
                    disclosure.locator("summary").click()
                expect(disclosure).to_have_attribute("open", "")
                title = page.locator("#result-detail-title").inner_text()
                selection = page.locator("#result-selection-details").inner_text()
                if title != row["campaign_name"] or "buyer similarity" not in selection.casefold():
                    raise RuntimeError(
                        f"Browser reopened wrong result or score mode for {key}: "
                        f"title={title!r}; expected={row['campaign_name']!r}; "
                        f"selection={selection[:500]!r}"
                    )
                target = screenshot_dir / f"scenario_{scenario['id']:02d}_run_{run_id}.png"
                page.screenshot(path=str(target), full_page=True)
                state["browser"]["screenshots"][key] = {
                    "search_run_id": run_id,
                    "path": str(target.relative_to(ROOT)),
                    "sha256": _sha(target.read_bytes()),
                    "title": title,
                    "buyer_similarity_visible": True,
                    "technical_details_open": disclosure.get_attribute("open") is not None,
                }
                _save(CHECKPOINT, state)
                print(f"scenario={key} browser screenshot={target.name}", flush=True)


def representative_export(scratch: Path, base_url: str) -> None:
    state, scenarios, _, _ = _init(scratch)
    candidates = [s for s in scenarios if state["runs"].get(str(s["id"]), {}).get(
        "terminal_status") == "COMPLETED"]
    if not candidates:
        raise RuntimeError("No completed result can be exported.")
    first = candidates[0]
    key = str(first["id"])
    if state["runs"][key].get("representative_export", {}).get("status") == "PASS":
        print(f"scenario={key} export checkpointed", flush=True)
        return
    run_id = state["runs"][key]["search_run_id"]
    path = f"/api/potential-customer-search/runs/{run_id}/download"
    start = time.perf_counter()
    request = Request(base_url + path, method="GET")
    digest = hashlib.sha256()
    size = 0
    try:
        with urlopen(request, timeout=120) as response:
            first_byte = None
            while chunk := response.read(1024 * 1024):
                if first_byte is None:
                    first_byte = round(time.perf_counter() - start, 3)
                digest.update(chunk)
                size += len(chunk)
        export = {"status": "PASS", "first_byte_seconds": first_byte,
                  "elapsed_seconds": round(time.perf_counter() - start, 3),
                  "bytes": size, "stream_sha256": digest.hexdigest(),
                  "contact_data_saved": False}
    except HTTPError as exc:
        export = {"status": "FAILED", "http_status": exc.code,
                  "safe_error": exc.read(512).decode("utf-8", errors="replace")}
    state["runs"][key]["representative_export"] = export
    _save(CHECKPOINT, state)
    print(f"scenario={key} representative_export={export['status']} bytes={size}", flush=True)


def report(scratch: Path) -> None:
    state, scenarios, context, _ = _init(scratch)
    rows = []
    for scenario in scenarios:
        key = str(scenario["id"])
        p = state["preflights"].get(key, {})
        measured = p.get("preflight", {})
        r = state["runs"].get(key, {})
        shot = state.get("browser", {}).get("screenshots", {}).get(key)
        issue = r.get("issue") or {}
        reason = (
            measured.get("safe_message", "Exact preflight not run")
            if not p.get("qualifies") else
            issue.get("plain_language_cause", "Real run not completed")
            if r.get("terminal_status") != "COMPLETED" else
            r.get("verification_error", "Count/currentness/browser evidence incomplete")
            if not (r.get("exact_count_match") and r.get("reopen", {}).get("currentness") == "CURRENT"
                    and shot and shot.get("technical_details_open") is True)
            else "Current exact membership and browser result verified"
        )
        rows.append({
            "id": scenario["id"], "name": scenario["name"],
            "legacy_match_strength": scenario["match_strength"],
            "similarity_minimum": p.get("similarity_minimum"),
            "demographic_eligible_count": measured.get("demographic_eligible_count"),
            "valid_similarity_count": measured.get("valid_similarity_count"),
            "invalid_similarity_count": measured.get("invalid_similarity_count"),
            "similarity_qualifying_count": measured.get("similarity_qualifying_count"),
            "selected_count": measured.get("selected_count"),
            "currentness": measured.get("similarity_currentness"),
            "profile_ids": measured.get("profile_ids"),
            "generation_ids": measured.get("similarity_generation_ids"),
            "qualifies_10000": p.get("qualifies", False),
            "contact_export_profile_availability": p.get("contact_export_profile_availability"),
            "search_run_id": r.get("search_run_id"),
            "attempt_number": r.get("attempt_number"),
            "terminal_status": r.get("terminal_status"),
            "processing_seconds": r.get("processing_seconds"),
            "total_elapsed_seconds": r.get("total_elapsed_seconds"),
            "run_lineage": r.get("lineage"),
            "membership_count": r.get("membership", {}).get("member_count"),
            "membership_sha256": r.get("membership", {}).get("membership_sha256"),
            "reopen_currentness": r.get("reopen", {}).get("currentness"),
            "export_summary": r.get("reopen", {}).get("export_summary"),
            "browser_screenshot": shot.get("path") if shot else None,
            "browser_screenshot_sha256": shot.get("sha256") if shot else None,
            "technical_details_open": shot.get("technical_details_open") if shot else None,
            "reason": reason,
        })
    representative_export = next((row.get("representative_export") for row in
        state["runs"].values() if row.get("representative_export")), None)
    passed = bool(representative_export and representative_export.get("status") == "PASS") and all(
                 row["qualifies_10000"] and row["terminal_status"] == "COMPLETED"
                 and row["membership_count"] == row["selected_count"]
                 and row["reopen_currentness"] == "CURRENT"
                 and row["browser_screenshot"] and row["browser_screenshot_sha256"]
                 and row["technical_details_open"] is True for row in rows)
    payload = {
        "stage": "14B_PROMPT_17", "verdict": "DEMO_GO" if passed else "DEMO_NO_GO",
        "starting_sha": state["starting_sha"], "candidate": "UNCOMMITTED",
        "database": state["database"], "recorded_context": context,
        "scenario_json_sha256": state["scenario_json_sha256"],
        "context_manifest_sha256": state["context_manifest_sha256"],
        "qualification_minimum": MINIMUM,
        "tested": len(state["preflights"]),
        "current_eligible": sum(row["currentness"] == "CURRENT" for row in rows),
        "qualifying": sum(row["qualifies_10000"] for row in rows),
        "completed": sum(row["terminal_status"] == "COMPLETED" for row in rows),
        "blocked": sum(row["terminal_status"] == "BLOCKED" for row in rows),
        "failed": sum(row["terminal_status"] in {"FAILED", "SUBMISSION_ERROR"} for row in rows),
        "representative_export": representative_export,
        "browser": state.get("browser", {}).get("metadata"),
        "scenarios": rows,
        "generated_at": _now(),
    }
    output = EVIDENCE / "17_SCENARIOS.json"
    _save(output, payload)
    header = (
        "# Prompt 17: unchanged canonical 20 scenarios\n\n"
        f"Verdict: **{payload['verdict']}**. Candidate: UNCOMMITTED at starting SHA "
        f"`{payload['starting_sha']}`. This is demo readiness, separate from "
        "Prompt 16 full-population and model-assurance decisions.\n\n"
        f"Recorded context: `{context}`. Original scenario JSON SHA-256: "
        f"`{state['scenario_json_sha256']}`; recorded context manifest SHA-256: "
        f"`{state['context_manifest_sha256']}`. Historical JSON minimum 101 is "
        "metadata only; the unchanged qualification minimum is 10,000. "
        "V3 cumulative similarity translation is separately recorded in "
        "`17_V3_TRANSLATION.json`; v1/v2 selections were not rewritten.\n\n"
        f"Tested {payload['tested']}/20; current/eligible {payload['current_eligible']}; "
        f"qualifying {payload['qualifying']}; completed {payload['completed']}; "
        f"blocked {payload['blocked']}; failed {payload['failed']}.\n\n"
        "| ID | Original strength → V3 minimum | Eligible | Valid / invalid | "
        "Qualified / selected | ≥10K | Run / attempt | Outcome | Members | Reason |\n"
        "|---:|---|---:|---:|---:|:---:|---|---|---:|---|\n"
    )
    lines = [header]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['legacy_match_strength']} → {row['similarity_minimum']} "
            f"| {row['demographic_eligible_count']} | {row['valid_similarity_count']} / "
            f"{row['invalid_similarity_count']} | {row['similarity_qualifying_count']} / "
            f"{row['selected_count']} | {'yes' if row['qualifies_10000'] else 'no'} | "
            f"{row['search_run_id']} / {row['attempt_number']} | {row['terminal_status']} | "
            f"{row['membership_count']} | {str(row['reason']).replace('|', '/')} |\n"
        )
    lines.append(
        "\nReal runs use the loopback FastAPI create/status/result/download routes and "
        "the production Phase 11 coordinator on a disposable Prompt 16 database. "
        "The browser evidence uses installed system Chrome/Edge and opens the "
        "actual result detail, including technical details; it contains no contact PII. "
        "One representative governed download is streamed only to a digest, never "
        "saved as contact data. Full counts, identities, timings, issues, hashes, "
        "and screenshot paths are in `17_SCENARIOS.json` and the checkpoint.\n\n"
        "No production schema or API was changed by Prompt 17; v1/v2 data and "
        "semantics remain untouched. Scenario 7's reported elapsed time includes "
        "a loopback server/runner interruption and durable restart recovery; "
        "scenario 14's elapsed time includes an observed monitoring/host pause. "
        "Those durations are not pure compute benchmarks. Remote CI is not "
        "claimed. Next: Prompt 18 "
        "may document the honest demo decision.\n"
    )
    (EVIDENCE / "17_SCENARIOS.md").write_text("".join(lines), encoding="utf-8")
    print(f"verdict={payload['verdict']} tested={payload['tested']} "
          f"qualifying={payload['qualifying']} completed={payload['completed']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "run", "browser", "export", "report"), required=True)
    parser.add_argument("--scratch-dir", type=Path, default=SCRATCH)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    args = parser.parse_args()
    if args.phase == "preflight":
        preflight(args.scratch_dir.resolve())
    elif args.phase == "run":
        run(args.scratch_dir.resolve(), args.base_url.rstrip("/"))
    elif args.phase == "browser":
        browser(args.scratch_dir.resolve(), args.base_url.rstrip("/"))
    elif args.phase == "export":
        representative_export(args.scratch_dir.resolve(), args.base_url.rstrip("/"))
    elif args.phase == "report":
        report(args.scratch_dir.resolve())


if __name__ == "__main__":
    main()
