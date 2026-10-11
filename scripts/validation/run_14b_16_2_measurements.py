"""Uninterrupted, resource-sampled Prompt 16 full-5M recertification.

Use one phase per invocation in this order: audit, import, profiles, score,
index, preflight, verify, scenario-preflight, scenario-search,
scenario-reuse-export, history. Each phase is resumable in an isolated DB.
Budgets are recorded, not used as execution timeouts or stop conditions.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import get_connection  # noqa: E402
from app.services.buyer_similarity_scoring_service import (  # noqa: E402
    has_current_similarity_attestation,
    run_similarity_generation,
)
from app.services.phase11_results_service import list_result_history  # noqa: E402
from scripts.validation import run_14b_15_1_full5m as prior  # noqa: E402

VERSION = "14B_16_2_UNINTERRUPTED_RESOURCE_MEASUREMENT_V1"
DEFAULT_SCRATCH = ROOT / "output" / "lookalike_stage16_2_measurements"
PHASE_ORDER = (
    "audit", "import", "profiles", "score", "index", "preflight", "verify",
    "scenario-preflight", "scenario-search", "scenario-reuse-export", "history",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ResourceMonitor:
    """Sample this process and the isolated database; never cancel its work."""

    def __init__(self, scratch: Path, label: str) -> None:
        self.scratch = scratch
        self.label = label
        self.process = psutil.Process(os.getpid())
        self.stop_signal = threading.Event()
        self.activity = label
        self.processed_rows = 0
        self.total_rows = 0
        self.last_progress_at = _utc()
        self.started_at = _utc()
        self.started = time.perf_counter()
        self.peak_rss_bytes = 0
        self.peak_db_bytes = 0
        self.peak_wal_bytes = 0
        self.minimum_available_memory_bytes = psutil.virtual_memory().available
        self.minimum_free_disk_bytes = psutil.disk_usage(str(scratch)).free
        self.samples = 0
        self.initial_cpu_seconds = self._cpu_seconds()
        self.initial_io = self.process.io_counters()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _cpu_seconds(self) -> float:
        times = self.process.cpu_times()
        return times.user + times.system

    def progress(self, stage: str, processed: int, total: int, _message: str) -> None:
        if stage != self.activity or processed != self.processed_rows:
            self.last_progress_at = _utc()
        self.activity = stage
        self.processed_rows = processed
        self.total_rows = total

    def _sample(self) -> dict:
        db = self.scratch / "certification.db"
        wal = self.scratch / "certification.db-wal"
        rss = self.process.memory_info().rss
        db_bytes = db.stat().st_size if db.exists() else 0
        wal_bytes = wal.stat().st_size if wal.exists() else 0
        self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
        self.peak_db_bytes = max(self.peak_db_bytes, db_bytes)
        self.peak_wal_bytes = max(self.peak_wal_bytes, wal_bytes)
        self.minimum_available_memory_bytes = min(
            self.minimum_available_memory_bytes, psutil.virtual_memory().available
        )
        self.minimum_free_disk_bytes = min(
            self.minimum_free_disk_bytes, psutil.disk_usage(str(self.scratch)).free
        )
        self.samples += 1
        io = self.process.io_counters()
        return {
            "label": self.label,
            "pid": self.process.pid,
            "heartbeat_at": _utc(),
            "started_at": self.started_at,
            "elapsed_seconds": round(time.perf_counter() - self.started, 3),
            "activity": self.activity,
            "processed_rows": self.processed_rows,
            "total_rows": self.total_rows,
            "last_progress_at": self.last_progress_at,
            "rss_bytes": rss,
            "peak_rss_bytes": self.peak_rss_bytes,
            "cpu_seconds": round(self._cpu_seconds() - self.initial_cpu_seconds, 3),
            "read_bytes": io.read_bytes - self.initial_io.read_bytes,
            "write_bytes": io.write_bytes - self.initial_io.write_bytes,
            "db_bytes": db_bytes,
            "peak_db_bytes": self.peak_db_bytes,
            "wal_bytes": wal_bytes,
            "peak_wal_bytes": self.peak_wal_bytes,
            "minimum_available_memory_bytes": self.minimum_available_memory_bytes,
            "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
            "sample_count": self.samples,
        }

    def _publish(self, sample: dict) -> None:
        # Append-only history survives a process death during live-file replacement.
        with (self.scratch / "measurement_heartbeats.jsonl").open(
            "a", encoding="utf-8"
        ) as journal:
            journal.write(json.dumps(sample, sort_keys=True) + "\n")
        target = self.scratch / "live_measurement.json"
        temporary = self.scratch / "live_measurement.json.tmp"
        temporary.write_text(json.dumps(sample, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)

    def _loop(self) -> None:
        while not self.stop_signal.is_set():
            sample = self._sample()
            self._publish(sample)
            self.stop_signal.wait(5)

    def __enter__(self) -> "ResourceMonitor":
        self.thread.start()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.stop_signal.set()
        self.thread.join()
        self.final = self._sample()
        self.final["completed_at"] = _utc()
        self._publish(self.final)


def score(scratch: Path, state: dict) -> None:
    if state["phases"].get("profiles", {}).get("status") != "PASS":
        raise RuntimeError("The current three-product profiles are required.")
    db = scratch / "certification.db"
    for product in state["recorded_common_context"]["product_ids"]:
        profile_id = int(state["profiles"][product]["profile_id"])
        existing = state.setdefault("scores", {}).get(product)
        if existing and has_current_similarity_attestation(
            db, int(existing["generation_id"]), project_root=scratch
        ):
            prior.prior._log(f"reusing prior uninterrupted generation for {product}")
            continue
        stale_before = None
        with get_connection(db) as connection:
            incomplete = connection.execute(
                "SELECT similarity_generation_id,publication_state,lease_heartbeat_at "
                "FROM buyer_similarity_score_generations WHERE profile_id=? "
                "ORDER BY similarity_generation_id DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
        if incomplete is not None and incomplete["publication_state"] == "BUILDING":
            live_path = scratch / "live_measurement.json"
            try:
                previous = json.loads(live_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                previous = None
            if previous is not None and previous.get("label") != f"score:{product}":
                previous = None
            for process in psutil.process_iter(["name", "cmdline"]):
                try:
                    command = process.info["cmdline"] or []
                    if (process.pid != os.getpid() and "python" in (
                        process.info["name"] or ""
                    ).lower() and "run_14b_16_2_measurements.py" in " ".join(command)
                        and "--phase score" in " ".join(command)):
                        raise RuntimeError(
                            "Another scoring process still exists; do not take its lease."
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            stale_before = (
                datetime.now(timezone.utc) - timedelta(minutes=2)
            ).isoformat()
            heartbeat = str(incomplete["lease_heartbeat_at"])
            if heartbeat >= stale_before:
                raise RuntimeError("The previous generation lease is not stale.")
            with get_connection(db) as connection:
                checkpoint = connection.execute(
                    "SELECT started_at,heartbeat_at,processed_count,checkpoint_person_id "
                    "FROM buyer_similarity_generation_stages "
                    "WHERE similarity_generation_id=? AND stage_code='SCORING_PROSPECTS'",
                    (int(incomplete["similarity_generation_id"]),),
                ).fetchone()
            if checkpoint is None:
                raise RuntimeError("Incomplete generation has no durable checkpoint.")
            started_at = datetime.fromisoformat(str(checkpoint["started_at"]).replace("Z", "+00:00"))
            last_heartbeat = datetime.fromisoformat(
                str(checkpoint["heartbeat_at"]).replace("Z", "+00:00")
            )
            state.setdefault("interrupted_segments", {})[product] = {
                "reason": "previous scoring process absent after session interruption",
                "generation_id": int(incomplete["similarity_generation_id"]),
                "last_observed_process_measurement": previous,
                "durable_processed_rows": int(checkpoint["processed_count"]),
                "durable_checkpoint_person_id": str(checkpoint["checkpoint_person_id"]),
                "durable_active_wall_seconds_to_heartbeat": round(
                    (last_heartbeat - started_at).total_seconds(), 3
                ),
                "prior_peak_rss_certified": previous is not None,
                "observed_at_resume": _utc(),
            }
            prior.save(scratch, state)
        timings: dict[str, float] = {}
        with ResourceMonitor(scratch, f"score:{product}") as monitor:
            started = time.perf_counter()

            def progress(stage: str, processed: int, total: int, message: str) -> None:
                monitor.progress(stage, processed, total, message)
                if stage == "SCORING_PROSPECTS" and processed % 250_000 == 0:
                    prior.prior._log(f"{product} {stage}: {processed}/{total}")
                elif stage in {"DEEP_VERIFY", "PUBLISH"}:
                    prior.prior._log(f"{product} {stage}: {processed}/{total}")

            result = run_similarity_generation(
                db, profile_id, project_root=scratch,
                execution_owner=f"stage16-2-{product}-scorer",
                execution_token=secrets.token_hex(32),
                chunk_size=prior.prior.CHUNK_SIZE,
                stale_before=stale_before,
                progress_callback=progress, timing_sink=timings,
            )
            score_seconds = time.perf_counter() - started
        generation_id = int(result["similarity_generation_id"])
        if result.get("reused") or not has_current_similarity_attestation(
            db, generation_id, project_root=scratch
        ):
            raise RuntimeError("Fresh product generation was not newly published and verified.")
        state["scores"][product] = {
            "generation_id": generation_id,
            "published_person_count": result["published_person_count"],
            "elapsed_seconds": round(score_seconds, 3),
            "stage_timings_seconds": {key: round(value, 3) for key, value in timings.items()},
            "score_claim_and_chunk_loop_seconds": round(
                score_seconds - timings["verify_and_publish_committed_seconds"], 3
            ),
            "resource_measurement": monitor.final,
            "deep_verification_run": bool(result.get("deep_verification_run")),
            "resumed_from_stale_lease": bool(result.get("restarted_from_stale_lease")),
            "db_bytes": db.stat().st_size,
        }
        if product in state.get("interrupted_segments", {}):
            earlier = state["interrupted_segments"][product][
                "last_observed_process_measurement"
            ]
            state["scores"][product]["observed_active_seconds_across_segments"] = round(
                float(earlier["elapsed_seconds"] if earlier is not None else
                      state["interrupted_segments"][product][
                          "durable_active_wall_seconds_to_heartbeat"
                      ]) + score_seconds, 3
            )
            if earlier is not None:
                state["scores"][product]["peak_rss_across_segments_bytes"] = max(
                    int(earlier["peak_rss_bytes"]), monitor.peak_rss_bytes
                )
            else:
                state["scores"][product]["peak_rss_across_segments_bytes"] = None
        prior.save(scratch, state)
        prior.prior._log(
            f"{product} uninterrupted score+verify+publish {score_seconds:.3f}s; "
            f"peak RSS {monitor.peak_rss_bytes / 2**30:.3f} GiB"
        )
    state["phases"]["score"] = {"status": "PASS", "completed_at": _utc()}
    prior.save(scratch, state)


def index(scratch: Path, state: dict) -> None:
    if state["phases"].get("score", {}).get("status") != "PASS":
        raise RuntimeError("Complete scoring before isolated index rebuild measurement.")
    db = scratch / "certification.db"
    with get_connection(db) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_buyer_similarity_score_lookup",),
        ).fetchone()
        if row is None:
            raise RuntimeError("The score lookup index is missing.")
    started = time.perf_counter()
    with get_connection(db, write=True) as connection:
        connection.execute("REINDEX idx_buyer_similarity_score_lookup")
    elapsed = time.perf_counter() - started
    state["phases"]["index"] = {
        "status": "PASS", "elapsed_seconds": round(elapsed, 3),
        "index_name": "idx_buyer_similarity_score_lookup",
        "meaning": "standalone existing-index rebuild; indexed INSERT timing is separate",
    }
    prior.save(scratch, state)
    prior.prior._log(f"standalone full score-lookup index rebuild: {elapsed:.3f}s")


def history(scratch: Path, state: dict) -> None:
    if "scenario_20_reuse_export" not in state:
        raise RuntimeError("Complete the real scenario snapshot and reuse first.")
    db = scratch / "certification.db"
    expected = {
        int(state["scenario_20_search"]["search_run_id"]),
        int(state["scenario_20_reuse_export"]["reuse_run_id"]),
    }
    samples = []
    for sample_number in range(1, 6):
        started = time.perf_counter()
        rows = list_result_history(db, limit=20, project_root=scratch)
        elapsed = time.perf_counter() - started
        if not expected <= {int(row["search_run_id"]) for row in rows}:
            raise RuntimeError("Measured history lost a completed certification run.")
        samples.append(round(elapsed, 3))
        prior.prior._log(f"history sample {sample_number}: {elapsed:.3f}s")
    state["phases"]["history"] = {
        "status": "PASS", "samples_seconds": samples,
        "budget_seconds": prior.prior.BUDGETS_SECONDS["history_projection"],
        "all_within_budget": all(
            value <= prior.prior.BUDGETS_SECONDS["history_projection"]
            for value in samples
        ),
    }
    prior.save(scratch, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASE_ORDER, required=True)
    parser.add_argument("--scratch-dir", type=Path, default=DEFAULT_SCRATCH)
    args = parser.parse_args()
    scratch = args.scratch_dir.resolve()
    output = (ROOT / "output").resolve()
    if not scratch.is_relative_to(output) or scratch == output:
        raise SystemExit("Use a dedicated child of output/ for disposable certification.")
    if scratch in {prior.DEFAULT_SCRATCH.resolve(), prior.PRIOR_SCRATCH.resolve()}:
        raise SystemExit("The two prior certification scratch directories are immutable.")
    scratch.mkdir(parents=True, exist_ok=True)
    manifest = scratch / "run_manifest.json"
    state = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {
        "runner_version": VERSION,
        "candidate": "UNCOMMITTED",
        "starting_sha": "336875c30fc32b00323d916ecc45b232016168a1",
        "created_at": _utc(),
        "budgets_seconds": prior.prior.BUDGETS_SECONDS,
        "phases": {},
        "measurement_policy": "observe to natural completion; budgets do not terminate work",
    }
    if state["runner_version"] != VERSION:
        raise RuntimeError("This scratch directory belongs to a different runner.")
    if args.phase == "scenario-preflight" and state["phases"].get("verify", {}).get(
        "status"
    ) == "PASS":
        # Earlier wrapper revisions flattened the stronger verified-context
        # status after prior.verify had already completed its full SQL check.
        composite = state.get("complete_context_composite") or {}
        preflight = state.get("recorded_context_preflight") or {}
        measured = state.get("phase_resource_measurements", {}).get("verify") or {}
        if (
            measured.get("completed_at")
            and composite.get("total") == 5_000_000
            and composite.get("valid") == 5_000_000
            and preflight.get("selected_count") == composite.get("ge_70")
            and preflight.get("readiness") == "CURRENT"
        ):
            state["phases"]["verify"]["status"] = "PASS_THREE_PRODUCT_CONTEXT"
            prior.save(scratch, state)
    expected_previous = PHASE_ORDER[:PHASE_ORDER.index(args.phase)]
    if expected_previous and not state["phases"].get(expected_previous[-1], {}).get(
        "status", ""
    ).startswith("PASS"):
        raise RuntimeError(f"Complete prior phase {expected_previous[-1]} first.")
    functions = {
        "audit": prior.audit,
        "import": prior.import_copy,
        "profiles": prior.profiles,
        "score": score,
        "index": index,
        "preflight": prior.preflight,
        "verify": prior.verify,
        "scenario-preflight": prior.scenario_preflight,
        "scenario-search": prior.scenario_search,
        "scenario-reuse-export": prior.scenario_reuse_export,
        "history": history,
    }
    prior.prior._log(f"starting uninterrupted measurement phase {args.phase}")
    if args.phase == "score":
        functions[args.phase](scratch, state)
    else:
        with ResourceMonitor(scratch, args.phase) as monitor:
            functions[args.phase](scratch, state)
        state.setdefault("phase_resource_measurements", {})[args.phase] = monitor.final
    if args.phase == "audit":
        state["runner_version"] = VERSION
    state["phases"].setdefault(args.phase, {}).setdefault("status", "PASS")
    prior.save(scratch, state)
    prior.prior._log(f"completed phase {args.phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
