from __future__ import annotations

from copy import deepcopy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.repositories.phase10_intelligence_repository import Phase10IntelligenceRepository
from app.services.phase11_result_contracts import RESULT_MEMBERSHIP_COLUMNS
from app.services.phase11_result_snapshot_service import RESULT_MEMBERSHIP_SCHEMA
from app.services.phase11_search_orchestration_service import (
    build_generation_fingerprint,
    build_result_cache_key,
    execute_phase11_search,
    execute_phase11_search_safely,
    resume_phase11_searches,
    iter_selected_members,
    validate_persisted_search_identity,
    validate_exact_snapshot,
)
from tests.test_phase11_search_result_registry import case, _search


def ready_response(generation, *, build=False):
    return {
        "status": "READY", "is_ready": True,
        "reuse_summary": {
            "analysis": "BUILD" if build else "REUSE",
            "model": "BUILD" if build else "REUSE",
            "scoring": "BUILD" if build else "REUSE",
            "rank": "BUILD" if build else "REUSE",
        },
        "technical_details": {
            "generation_id": generation["generation_id"],
            "modeling_context_sha256": generation["modeling_context_sha256"],
            "analysis_run_id": generation["analysis_run_id"],
            "model_run_id": generation["model_run_id"],
            "scoring_run_id": generation["scoring_run_id"],
        },
    }


def fixed_reader(response, calls=None):
    def read(path, context_id, **kwargs):
        if calls is not None: calls.append(("read", context_id))
        return deepcopy(response)
    return read


def membership_bytes(rows=2):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RESULT_MEMBERSHIP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for index in range(rows):
        writer.writerow({
            "person_id": f"P{index + 1}", "propensity_score": f"{0.9 - index * 0.1:.1f}",
            "percentile_bucket": index + 1, "decile": 1, "rank_band": "ELITE" if index == 0 else "VERY_HIGH",
        })
    return gzip.compress(stream.getvalue().encode("utf-8"), mtime=0)


class DeterministicMaterializer:
    def __init__(self, root: Path, repository: CampaignResultRegistryRepository):
        self.root, self.repository, self.calls = root, repository, []

    def __call__(self, path, run, generation, cache_key, existing, members):
        self.calls.append({"search_run_id": run["search_run_id"], "existing": existing})
        selected = list(members)
        assert [row["person_id"] for row in selected] == ["P1", "P2"]
        if existing is None:
            number = len(self.calls)
            uri = f"artifacts/results/result_snapshot_{number:06d}/members.csv.gz"
        else:
            uri = existing["storage_uri"]
        artifact = self.root / uri
        artifact.parent.mkdir(parents=True, exist_ok=True)
        payload = membership_bytes(len(selected))
        artifact.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if existing is not None:
            assert digest == existing["snapshot_sha256"]
            self.repository.update_snapshot_currentness(existing["result_snapshot_id"], state="CURRENT")
            snapshot_id = int(existing["result_snapshot_id"])
        else:
            snapshot_id = self.repository.register_snapshot(
                generation_id=generation["generation_id"],
                targeting_criteria_sha256=run["targeting_criteria_sha256"],
                filter_branches_sha256=run["filter_branches_sha256"],
                result_cache_key_sha256=cache_key, resolved_count=len(selected),
                storage_format="CSV_GZIP", storage_uri=uri, snapshot_sha256=digest,
                selection_mode=run["selection_mode"], target_count=run["target_count"],
            )
        snapshot = self.repository.fetch_snapshot(snapshot_id)
        manifest = {
            "result_snapshot_manifest_contract_version": "1",
            "snapshot_id": snapshot_id,
            "result_membership_contract_version": "1",
            "row_count": len(selected),
            "file_sha256": digest,
            "generation_id": generation["generation_id"],
            "scoring_run_id": generation["scoring_run_id"],
            "model_run_id": generation["model_run_id"],
            "analysis_run_id": generation["analysis_run_id"],
            "targeting_criteria_sha256": run["targeting_criteria_sha256"],
            "filter_branches_sha256": run["filter_branches_sha256"],
            "result_cache_key_sha256": cache_key,
            "selection_mode": run["selection_mode"],
            "target_count": run["target_count"],
            "created_at": snapshot["created_at"],
            "storage_format": "CSV_GZIP",
            "storage_schema": list(RESULT_MEMBERSHIP_SCHEMA),
        }
        (artifact.parent / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return snapshot_id


def generation(case):
    return Phase10IntelligenceRepository(case[0]).fetch_generation(case[1]["generation_id"])


def fixed_membership_source(*args):
    return iter((
        {"person_id": "P1", "propensity_score": 0.9, "percentile_bucket": 1, "decile": 1, "rank_band": "ELITE"},
        {"person_id": "P2", "propensity_score": 0.8, "percentile_bucket": 2, "decile": 1, "rank_band": "VERY_HIGH"},
    ))


_execute_engine = execute_phase11_search


def execute_phase11_search(*args, **kwargs):
    kwargs.setdefault("membership_source", fixed_membership_source)
    return _execute_engine(*args, **kwargs)


def table_counts(path):
    with get_connection(path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("historical_analysis_runs", "model_runs", "scoring_runs", "propensity_scores")
        }


def test_cache_key_is_exact_canonical_and_excludes_delivery_or_campaign_copy(case):
    repository = case[3]
    first = repository.fetch_search_run(_search(case))
    current = generation(case)
    key = build_result_cache_key(first, current)
    presentation = dict(first, campaign_name="Other", description="Other", delivery_channel="SMS",
                        export_profile="SMS_CONTACT_V1", planned_launch_date="2030-01-01")
    assert build_result_cache_key(presentation, current) == key
    assert len(key) == 64
    assert build_generation_fingerprint(current) == build_generation_fingerprint(dict(reversed(list(current.items()))))
    changed = dict(first, targeting_criteria_sha256="a" * 64)
    assert build_result_cache_key(changed, current) != key
    changed = dict(first, filter_branches_sha256="b" * 64)
    assert build_result_cache_key(changed, current) != key
    changed = dict(first, selection_mode="TOP_N", target_count=1)
    assert build_result_cache_key(changed, current) != key
    drifted = dict(current, demographic_source_checksum="d" * 64)
    assert build_result_cache_key(first, drifted) != key


def test_identical_request_reuses_snapshot_but_creates_second_history_and_profile_does_not_rescore(case):
    path, _, _, repository = case
    current = generation(case)
    materializer = DeterministicMaterializer(path.parent, repository)
    reader_calls = []
    before = table_counts(path)
    first = _search(case)
    outcome = execute_phase11_search(
        path, first, materializer=materializer, project_root=path.parent,
        phase10_reader=fixed_reader(ready_response(current), reader_calls),
    )
    assert outcome.status == "COMPLETED" and outcome.result_source == "INTELLIGENCE_REUSE"
    second = _search(case, campaign_name="SMS version", delivery_channel="SMS")
    def forbidden_membership_scan(*args):
        raise AssertionError("exact reuse must not scan Audience Engine membership")
    outcome = _execute_engine(
        path, second, materializer=materializer, project_root=path.parent,
        phase10_reader=fixed_reader(ready_response(current), reader_calls),
        membership_source=forbidden_membership_scan,
    )
    assert outcome.status == "COMPLETED" and outcome.result_source == "EXACT_RESULT_REUSE"
    one, two = repository.fetch_search_run(first), repository.fetch_search_run(second)
    assert one["result_snapshot_id"] == two["result_snapshot_id"]
    assert one["search_run_id"] != two["search_run_id"]
    assert len(materializer.calls) == 1
    assert table_counts(path) == before
    assert len(reader_calls) == 2


@pytest.mark.parametrize(
    ("targeting_criteria", "filter_branches"),
    (
        ({"states": ["Texas"]}, [{"state": ["Texas"]}]),
        ({"genders": ["Female"]}, [{"gender": ["Female"]}]),
        ({"age_groups": ["25-34"]}, [{"age_min": 25, "age_max": 34}]),
        (
            {"income_groups": ["50K-74,999"]},
            [{"individual_yearly_income_min": 50_000,
              "individual_yearly_income_max": 74_999}],
        ),
    ),
)
def test_changed_demographic_filters_reuse_intelligence_without_training_or_scoring(
    case, targeting_criteria, filter_branches,
):
    path, _, _, repository = case
    current = generation(case)
    writer = DeterministicMaterializer(path.parent, repository)
    before = table_counts(path)
    first = _search(case)
    execute_phase11_search(path, first, materializer=writer, project_root=path.parent,
                           phase10_reader=fixed_reader(ready_response(current)))
    second = _search(
        case,
        targeting_criteria=targeting_criteria,
        filter_branches=filter_branches,
    )
    outcome = execute_phase11_search(path, second, materializer=writer, project_root=path.parent,
                                     phase10_reader=fixed_reader(ready_response(current)))
    assert outcome.result_source == "INTELLIGENCE_REUSE"
    assert repository.fetch_search_run(first)["result_snapshot_id"] != outcome.result_snapshot_id
    assert len(writer.calls) == 2 and table_counts(path) == before


def test_waiting_phase10_is_durable_and_resume_records_new_build_source(case):
    path, _, _, repository = case
    current = generation(case)
    writer = DeterministicMaterializer(path.parent, repository)
    search = _search(case)
    initial = {"status": "NOT_STARTED", "is_ready": False}
    queued = {"status": "QUEUED", "is_ready": False,
              "reuse_summary": {name: "BUILD" for name in ("analysis", "model", "scoring", "rank")}}
    calls = []
    outcome = execute_phase11_search(
        path, search, materializer=writer, project_root=path.parent,
        phase10_reader=fixed_reader(initial, calls),
        phase10_preparer=fixed_reader(queued, calls),
    )
    assert outcome.status == "PROCESSING" and outcome.waiting_on == "PHASE10_INTELLIGENCE"
    assert repository.fetch_search_run(search)["status"] == "PROCESSING"
    assert repository.fetch_search_run(search)["result_snapshot_id"] is None
    outcomes = resume_phase11_searches(
        path, materializer=writer, project_root=path.parent,
        phase10_reader=fixed_reader(ready_response(current, build=True), calls),
        membership_source=fixed_membership_source,
    )
    assert len(outcomes) == 1 and outcomes[0].result_source == "NEW_INTELLIGENCE_BUILD"
    assert repository.fetch_search_run(search)["status"] == "COMPLETED"


def test_missing_step11_materializer_waits_without_fake_result(case):
    path, _, _, repository = case
    search = _search(case)
    outcome = execute_phase11_search(
        path, search, materializer=None,
        phase10_reader=fixed_reader(ready_response(generation(case))),
    )
    assert outcome.status == "PROCESSING" and outcome.waiting_on == "RESULT_MATERIALIZER"
    run = repository.fetch_search_run(search)
    assert run["status"] == "PROCESSING" and run["result_snapshot_id"] is None
    assert repository.find_snapshot_by_cache_key(build_result_cache_key(run, generation(case))) is None


def test_stale_generation_rejects_exact_cache_without_materialization(case):
    path, ids, _, repository = case
    current = generation(case)
    writer = DeterministicMaterializer(path.parent, repository)
    first = _search(case)
    execute_phase11_search(path, first, materializer=writer, project_root=path.parent,
                           phase10_reader=fixed_reader(ready_response(current)))
    snapshot = repository.fetch_search_run(first)["result_snapshot_id"]
    with get_connection(path, write=True) as connection:
        connection.execute("UPDATE phase10_intelligence_generations SET lifecycle_state='STALE' WHERE generation_id=?",
                           (ids["generation_id"],))
    second = _search(case)
    stale = {"status": "STALE", "is_ready": False}
    blocked = {"status": "BLOCKED", "is_ready": False}
    outcome = execute_phase11_search(
        path, second, materializer=writer, project_root=path.parent,
        phase10_reader=fixed_reader(stale), phase10_preparer=fixed_reader(blocked),
    )
    assert outcome.status == "BLOCKED"
    assert repository.fetch_search_run(second)["result_snapshot_id"] is None
    assert repository.fetch_search_run(second)["status"] == "BLOCKED"
    assert len(writer.calls) == 1
    assert repository.fetch_snapshot(snapshot)["currentness_state"] == "CURRENT"


def test_bad_checksum_or_count_is_not_exact_reuse_and_deterministic_repair_is_revalidated(case):
    path, _, _, repository = case
    current = generation(case)
    writer = DeterministicMaterializer(path.parent, repository)
    first = _search(case)
    execute_phase11_search(path, first, materializer=writer, project_root=path.parent,
                           phase10_reader=fixed_reader(ready_response(current)))
    original = repository.fetch_search_run(first)
    snapshot = repository.fetch_snapshot(original["result_snapshot_id"])
    artifact = path.parent / snapshot["storage_uri"]
    artifact.write_bytes(membership_bytes(rows=1))
    second = _search(case)
    outcome = execute_phase11_search(path, second, materializer=writer, project_root=path.parent,
                                     phase10_reader=fixed_reader(ready_response(current)))
    assert outcome.result_source == "INTELLIGENCE_REUSE"
    assert outcome.result_snapshot_id == original["result_snapshot_id"]
    assert len(writer.calls) == 2 and writer.calls[-1]["existing"] is not None
    repaired = repository.fetch_snapshot(outcome.result_snapshot_id)
    assert repaired["currentness_state"] == "CURRENT"
    assert validate_exact_snapshot(repaired, repository.fetch_search_run(second), current,
                                   repaired["result_cache_key_sha256"], project_root=path.parent)


@pytest.mark.parametrize("change", [
    {"generation_id": 999}, {"targeting_criteria_sha256": "c" * 64},
    {"filter_branches_sha256": "d" * 64}, {"selection_mode": "TOP_N", "target_count": 1},
    {"result_membership_contract_version": "2"}, {"resolved_count": 3},
    {"storage_uri": "artifacts/results/result_snapshot_999999/members.csv.gz"},
])
def test_exact_hit_rejects_every_required_metadata_or_artifact_mismatch(case, change):
    path, _, _, repository = case
    current = generation(case)
    writer = DeterministicMaterializer(path.parent, repository)
    search = _search(case)
    execute_phase11_search(path, search, materializer=writer, project_root=path.parent,
                           phase10_reader=fixed_reader(ready_response(current)))
    run = repository.fetch_search_run(search)
    snapshot = repository.fetch_snapshot(run["result_snapshot_id"])
    cache_key = snapshot["result_cache_key_sha256"]
    assert not validate_exact_snapshot(snapshot | change, run, current, cache_key, project_root=path.parent)


def test_safe_wrapper_never_persists_collaborator_exception_text(case):
    path, _, _, repository = case
    search = _search(case)
    def unsafe(*args, **kwargs):
        raise RuntimeError("person@example.test C:/private/secret")
    outcome = execute_phase11_search_safely(
        path, search, materializer=None, phase10_reader=unsafe,
    )
    assert outcome.status == "FAILED"
    run = repository.fetch_search_run(search)
    assert run["status"] == "FAILED"
    assert "example" not in run["safe_error_message"] and "private" not in run["safe_error_message"]


def test_audience_engine_branches_are_or_merged_in_global_rank_order_and_top_n_stops(case):
    current = generation(case)
    run = case[3].fetch_search_run(_search(
        case, selection_mode="TOP_N", target_count=2,
        filter_branches=[{"state": ["Ohio"]}, {"state": ["Texas"]}],
    ))
    pages = {
        ("Ohio", None): ([member("P1", .95)], "oh-2", True),
        ("Ohio", "oh-2"): ([member("P3", .70)], None, False),
        ("Texas", None): ([member("P2", .90), member("P3", .70)], None, False),
    }
    calls = []
    def audience_search(path, request):
        key = (request["filters"]["state"][0], request["cursor"])
        calls.append(key)
        rows, cursor, more = pages[key]
        return {"scoring_run_id": current["scoring_run_id"], "rows": rows,
                "next_cursor": cursor, "has_more": more}
    selected = list(iter_selected_members(case[0], run, current, audience_search=audience_search))
    assert [row["person_id"] for row in selected] == ["P1", "P2"]
    assert calls == [("Ohio", None), ("Texas", None), ("Ohio", "oh-2")]


def member(person_id, score):
    return {"person_id": person_id, "propensity_score": score,
            "percentile_bucket": max(1, int((1 - score) * 100)),
            "decile": 1, "rank_band": "HIGH"}


def test_audience_engine_overlapping_branches_deduplicate_without_population_set(case):
    current = generation(case)
    run = case[3].fetch_search_run(_search(
        case, filter_branches=[{"state": ["Ohio"]}, {"state": ["Texas"]}],
    ))
    def audience_search(path, request):
        state = request["filters"]["state"][0]
        rows = [member("P1", .9), member("P3", .7)] if state == "Ohio" else [member("P2", .8), member("P3", .7)]
        return {"scoring_run_id": current["scoring_run_id"], "rows": rows,
                "next_cursor": None, "has_more": False}
    assert [row["person_id"] for row in iter_selected_members(
        case[0], run, current, audience_search=audience_search
    )] == ["P1", "P2", "P3"]


def test_persisted_identity_reopens_canonical_hashes_and_selection(case):
    run = case[3].fetch_search_run(_search(case))
    validate_persisted_search_identity(run)
    with pytest.raises(Exception):
        validate_persisted_search_identity(run | {"targeting_criteria_sha256": "f" * 64})
    criteria = json.loads(run["targeting_criteria_json"])
    criteria.update(selection_mode="ALL_MATCHING", target_count=None)
    encoded = json.dumps(criteria, sort_keys=True, separators=(",", ":"))
    with pytest.raises(Exception):
        validate_persisted_search_identity(run | {
            "targeting_criteria_json": encoded,
            "targeting_criteria_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "selection_mode": "TOP_N", "target_count": 1,
        })


def test_engine_source_has_no_permutation_precompute_or_score_count_proof():
    source = (Path(__file__).parents[1] / "app/services/phase11_search_orchestration_service.py").read_text("utf-8")
    assert "product(" not in source and "permutation" not in source.lower()
    assert "propensity_scores" not in source
    assert "count_generation_score_rows" not in source
