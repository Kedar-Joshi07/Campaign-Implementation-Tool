from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
TEMP_DIR = PROJECT_ROOT / "artifacts" / "phase8_step10_regen_tmp"
REPORT_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "10_REPRODUCIBILITY_AND_LFS_REPORT.md"
EVIDENCE_JSON_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase8" / "10_reproducibility_and_lfs_evidence.json"

PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)


class Step10ValidationError(RuntimeError):
    """Raised when Step 10 reproducibility checks fail."""


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    canonical_name: str
    expected_rows: int


DATASETS = [
    DatasetSpec("customers", "customer_master_125000.csv.gz", 125_000),
    DatasetSpec("campaign_sales", "campaign_sales_570000.csv.gz", 570_000),
    DatasetSpec("demographics", "usa_demographic_synthetic_5000000_rows.csv.gz", 5_000_000),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(message: str) -> None:
    print(f"[step10] {message}", flush=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Step10ValidationError(message)


def _portable(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_decompressed_gzip(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_csv_rows_in_gzip(path: Path) -> int:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        # Skip header line and count remaining records.
        next(handle)
        return sum(1 for _ in handle)


def _run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    process = subprocess.Popen(
        command,
        cwd=str(cwd or PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip("\n")
        print(clean, flush=True)
        lines.append(clean)

    code = process.wait()
    output = "\n".join(lines)
    if code != 0:
        raise Step10ValidationError(
            "Subprocess failed with non-zero exit code.\n"
            f"command={' '.join(command)}\n"
            f"exit_code={code}\n"
            f"output_tail={' '.join(lines[-40:])}"
        )
    return output


def _run_git_command(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return (completed.stdout + "\n" + completed.stderr).strip()
    return completed.stdout.strip()


def _parse_lfs_paths(ls_files_output: str) -> set[str]:
    tracked: set[str] = set()
    for raw in ls_files_output.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Accept common git-lfs formats, including short hashes.
        match = re.match(r"^[0-9a-f]+\s+(?:-|\*)\s*(?P<path>.+)$", line, flags=re.IGNORECASE)
        if match:
            tracked.add(match.group("path").strip().replace("\\", "/"))
    return tracked


def _dataset_metrics(path: Path) -> dict[str, Any]:
    return {
        "path": _portable(path),
        "size_bytes": path.stat().st_size,
        "rows": _count_csv_rows_in_gzip(path),
        "compressed_sha256": _sha256_file(path),
        "decompressed_sha256": _sha256_decompressed_gzip(path),
    }


def _replace_canonical_from_temp() -> list[str]:
    names = [
        "customer_master_125000.csv.gz",
        "customer_master_sample_10000.csv",
        "customer_master_summary.json",
        "campaign_sales_570000.csv.gz",
        "campaign_sales_sample_10000.csv",
        "campaign_sales_summary.json",
        "campaign_master.csv",
        "product_master.csv",
        "usa_demographic_synthetic_5000000_rows.csv.gz",
        "usa_demographic_synthetic_summary.json",
        "usa_demographic_synthetic_sample_10000.csv",
        "usa_demographic_state_reference.csv",
    ]

    copied: list[str] = []
    for name in names:
        source = TEMP_DIR / name
        target = DATA_DIR / name
        _require(source.is_file(), f"Regenerated file missing: {_portable(source)}")
        shutil.copy2(source, target)
        copied.append(_portable(target))

    _normalize_canonical_summary_paths()
    return copied


def _normalize_canonical_summary_paths() -> None:
    replacements: dict[str, dict[str, str]] = {
        "customer_master_summary.json": {
            "output": "data/customer_master_125000.csv.gz",
            "sample_output": "data/customer_master_sample_10000.csv",
        },
        "campaign_sales_summary.json": {
            "main_output": "data/campaign_sales_570000.csv.gz",
            "campaign_master": "data/campaign_master.csv",
            "product_master": "data/product_master.csv",
            "sample_output": "data/campaign_sales_sample_10000.csv",
        },
        "usa_demographic_synthetic_summary.json": {
            "file": "data/usa_demographic_synthetic_5000000_rows.csv.gz",
        },
    }

    for summary_name, updates in replacements.items():
        summary_path = DATA_DIR / summary_name
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        payload.update(updates)
        summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _collect_path_portability_checks() -> dict[str, Any]:
    summaries = {
        "campaign_sales_summary": DATA_DIR / "campaign_sales_summary.json",
        "customer_master_summary": DATA_DIR / "customer_master_summary.json",
        "usa_demographic_synthetic_summary": DATA_DIR / "usa_demographic_synthetic_summary.json",
    }

    checks: dict[str, Any] = {}
    absolute_pattern = re.compile(r"^[A-Za-z]:\\|^/[A-Za-z]|^\\\\")

    for key, path in summaries.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        path_fields = {
            k: v
            for k, v in payload.items()
            if isinstance(v, str) and (k.endswith("output") or k in {"file", "campaign_master", "product_master"})
        }
        checks[key] = {
            "file": _portable(path),
            "path_fields": path_fields,
            "absolute_paths": {
                k: v
                for k, v in path_fields.items()
                if absolute_pattern.search(v.replace("/", "\\"))
            },
        }
    return checks


def _scan_large_non_lfs_files(lfs_paths: set[str]) -> dict[str, Any]:
    threshold = 50 * 1024 * 1024
    large_files: list[dict[str, Any]] = []
    non_lfs_large: list[dict[str, Any]] = []

    for path in DATA_DIR.rglob("*.gz"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size < threshold:
            continue
        relative = _portable(path)
        entry = {"path": relative, "size_bytes": size}
        large_files.append(entry)
        if relative.replace("\\", "/") not in lfs_paths:
            non_lfs_large.append(entry)

    canonical_names = {spec.canonical_name for spec in DATASETS}
    duplicate_nested: list[dict[str, Any]] = []
    for name in canonical_names:
        matches = [p for p in PROJECT_ROOT.rglob(name) if p.is_file()]
        canonical_path = (DATA_DIR / name).resolve()
        extras = [
            _portable(p)
            for p in matches
            if p.resolve() != canonical_path
        ]
        if extras:
            duplicate_nested.append({"name": name, "extra_locations": extras})

    return {
        "threshold_bytes": threshold,
        "large_files": sorted(large_files, key=lambda item: item["path"]),
        "non_lfs_large_files": sorted(non_lfs_large, key=lambda item: item["path"]),
        "duplicate_nested_full_datasets": sorted(duplicate_nested, key=lambda item: item["name"]),
    }


def _write_outputs(payload: dict[str, Any]) -> None:
    EVIDENCE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Step 10 Reproducibility and LFS Report")
    lines.append("")
    lines.append(f"Generated at: {payload['generated_at']}")
    lines.append(f"Prompt: {payload['prompt']}")
    lines.append("")

    lines.append("## Deterministic GZIP Controls")
    lines.append("- generate_us_customer_master.py: fixed mtime=0, filename='', compresslevel=9")
    lines.append("- generate_campaign_sales.py: fixed mtime=0, filename='', compresslevel=9")
    lines.append("- generate_us_demographic_synthetic.py: fixed mtime=0, filename='', compresslevel=3")
    lines.append("")

    lines.append("## Temporary Regeneration Equivalence")
    lines.append("| Dataset | Canonical rows | Regenerated rows | Decompressed SHA equal | Raw GZIP SHA equal |")
    lines.append("|---|---:|---:|---|---|")
    for item in payload["equivalence_checks"]:
        lines.append(
            "| "
            f"{item['dataset']} | "
            f"{item['canonical']['rows']} | "
            f"{item['regenerated']['rows']} | "
            f"{item['decompressed_sha_equal']} | "
            f"{item['raw_gzip_sha_equal']} |"
        )
    lines.append("")

    lines.append("## Canonical Dataset Hashes After Refresh")
    lines.append("| File | Bytes | Raw GZIP SHA-256 | Decompressed content SHA-256 | Rows |")
    lines.append("|---|---:|---|---|---:|")
    for item in payload["final_canonical_hashes"]:
        lines.append(
            "| "
            f"{item['path']} | "
            f"{item['size_bytes']} | "
            f"{item['compressed_sha256']} | "
            f"{item['decompressed_sha256']} | "
            f"{item['rows']} |"
        )
    lines.append("")

    lines.append("## Portable Path Checks")
    portability = payload["portability_checks"]
    for key, item in portability.items():
        lines.append(f"### {key}")
        lines.append(f"- Summary file: {item['file']}")
        lines.append(f"- Path fields: {item['path_fields']}")
        lines.append(f"- Absolute path fields: {item['absolute_paths']}")
    lines.append("")

    lines.append("## Git LFS")
    lines.append("### git lfs status")
    lines.append("```text")
    lines.append(payload["git_lfs"]["status_output"])
    lines.append("```")
    lines.append("### git lfs ls-files")
    lines.append("```text")
    lines.append(payload["git_lfs"]["ls_files_output"])
    lines.append("```")
    lines.append("")

    scan = payload["large_file_scan"]
    lines.append("## Large File and Duplicate Dataset Scan")
    lines.append(f"- Threshold bytes: {scan['threshold_bytes']}")
    lines.append(f"- Non-LFS large files: {len(scan['non_lfs_large_files'])}")
    lines.append(f"- Duplicate nested canonical datasets: {len(scan['duplicate_nested_full_datasets'])}")
    if scan["non_lfs_large_files"]:
        lines.append(f"- Non-LFS large file details: {scan['non_lfs_large_files']}")
    if scan["duplicate_nested_full_datasets"]:
        lines.append(f"- Duplicate dataset details: {scan['duplicate_nested_full_datasets']}")
    lines.append("")

    lines.append("## Outcome")
    lines.append(f"- Overall status: {payload['overall_status']}")
    lines.append(f"- Notes: {payload['notes']}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _run_step10() -> dict[str, Any]:
    _log("Starting Step 10 reproducibility and LFS validation.")

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    _log("Regenerating customer master in temporary validation location.")
    _run_command(
        [
            str(PYTHON_EXE),
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_customer_master.py"),
            "--n-customers",
            "125000",
            "--seed",
            "20260819",
            "--outdir",
            str(TEMP_DIR),
            "--output",
            "customer_master_125000.csv.gz",
            "--sample-output",
            "customer_master_sample_10000.csv",
            "--summary-output",
            "customer_master_summary.json",
            "--sample-rows",
            "10000",
        ]
    )

    _log("Regenerating campaign sales in temporary validation location.")
    _run_command(
        [
            str(PYTHON_EXE),
            str(PROJECT_ROOT / "data_generation_scripts" / "generate_campaign_sales.py"),
            "--customer-file",
            str(TEMP_DIR / "customer_master_125000.csv.gz"),
            "--n-rows",
            "570000",
            "--n-campaigns",
            "96",
            "--seed",
            "20260820",
            "--outdir",
            str(TEMP_DIR),
            "--output",
            "campaign_sales_570000.csv.gz",
            "--sample-output",
            "campaign_sales_sample_10000.csv",
            "--summary-output",
            "campaign_sales_summary.json",
            "--campaign-master-output",
            "campaign_master.csv",
            "--product-master-output",
            "product_master.csv",
            "--sample-rows",
            "10000",
        ]
    )

    _log("Regenerating 5M demographic universe in temporary validation location.")
    env = os.environ.copy()
    env.update(
        {
            "SEED": "20260818",
            "ID_OFFSET": "0",
            "N_ROWS": "5000000",
            "CHUNK": "200000",
            "OUTDIR": str(TEMP_DIR),
            "OUT_NAME": "usa_demographic_synthetic_5000000_rows.csv.gz",
            "SUMMARY_NAME": "usa_demographic_synthetic_summary.json",
            "SAMPLE_NAME": "usa_demographic_synthetic_sample_10000.csv",
        }
    )
    _run_command([str(PYTHON_EXE), str(PROJECT_ROOT / "data_generation_scripts" / "generate_us_demographic_synthetic.py")], env=env)

    _log("Comparing canonical and regenerated datasets.")
    equivalence_checks: list[dict[str, Any]] = []
    decompressed_mismatches: list[str] = []

    for spec in DATASETS:
        canonical_path = DATA_DIR / spec.canonical_name
        regenerated_path = TEMP_DIR / spec.canonical_name

        _require(canonical_path.is_file(), f"Canonical file missing: {_portable(canonical_path)}")
        _require(regenerated_path.is_file(), f"Regenerated file missing: {_portable(regenerated_path)}")

        canonical_metrics = _dataset_metrics(canonical_path)
        regenerated_metrics = _dataset_metrics(regenerated_path)

        _require(canonical_metrics["rows"] == spec.expected_rows, f"Unexpected canonical row count for {spec.key}.")
        _require(regenerated_metrics["rows"] == spec.expected_rows, f"Unexpected regenerated row count for {spec.key}.")

        decompressed_equal = canonical_metrics["decompressed_sha256"] == regenerated_metrics["decompressed_sha256"]
        raw_equal = canonical_metrics["compressed_sha256"] == regenerated_metrics["compressed_sha256"]

        if not decompressed_equal:
            decompressed_mismatches.append(spec.key)

        equivalence_checks.append(
            {
                "dataset": spec.key,
                "canonical": canonical_metrics,
                "regenerated": regenerated_metrics,
                "decompressed_sha_equal": decompressed_equal,
                "raw_gzip_sha_equal": raw_equal,
            }
        )

    _require(
        not decompressed_mismatches,
        "Unexpected decompressed content drift detected for datasets: " + ", ".join(decompressed_mismatches),
    )

    _log("Equivalence checks passed. Refreshing canonical data outputs from temporary generation.")
    copied_files = _replace_canonical_from_temp()

    # Remove the temporary regeneration directory before duplicate-file scanning.
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    final_hashes = [_dataset_metrics(DATA_DIR / spec.canonical_name) for spec in DATASETS]
    portability_checks = _collect_path_portability_checks()

    _log("Collecting Git LFS status and inventory.")
    lfs_status_output = _run_git_command(["lfs", "status"])
    lfs_ls_files_output = _run_git_command(["lfs", "ls-files"])
    lfs_paths = _parse_lfs_paths(lfs_ls_files_output)

    large_file_scan = _scan_large_non_lfs_files(lfs_paths)

    _require(
        not large_file_scan["duplicate_nested_full_datasets"],
        "Duplicate nested full datasets were detected.",
    )
    _require(
        not large_file_scan["non_lfs_large_files"],
        "Large non-LFS files were detected.",
    )

    absolute_path_violations = []
    for key, check in portability_checks.items():
        if check["absolute_paths"]:
            absolute_path_violations.append(key)
    _require(
        not absolute_path_violations,
        "Absolute path fields remain in summary files: " + ", ".join(absolute_path_violations),
    )

    return {
        "generated_at": _now_iso(),
        "prompt": "Prompts/phase8_release_assurance_system_browser_prompt_pack/10_STEP_10_DETERMINISTIC_GENERATION_PATH_HASH_AND_LFS_CLEANUP.md",
        "python_executable": str(PYTHON_EXE),
        "equivalence_checks": equivalence_checks,
        "copied_files": copied_files,
        "final_canonical_hashes": final_hashes,
        "portability_checks": portability_checks,
        "git_lfs": {
            "status_output": lfs_status_output,
            "ls_files_output": lfs_ls_files_output,
        },
        "large_file_scan": large_file_scan,
        "overall_status": "PASS",
        "notes": (
            "Decompressed canonical content remained equivalent across regenerated outputs. "
            "Canonical compressed assets were refreshed under deterministic gzip settings and validated against LFS and duplicate-file checks."
        ),
    }


def main() -> int:
    payload = _run_step10()
    _write_outputs(payload)
    print(f"Wrote evidence JSON: {EVIDENCE_JSON_PATH}")
    print(f"Wrote report: {REPORT_PATH}")
    print(f"Status: {payload['overall_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
