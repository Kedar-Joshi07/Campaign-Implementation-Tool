from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"(^|/)\.pytest_cache/"),
    re.compile(r"(^|/)\.mypy_cache/"),
    re.compile(r"(^|/)\.ruff_cache/"),
    re.compile(r"(^|/)htmlcov/"),
    re.compile(r"(^|/)(output|source|downloads|traces|videos|playwright-report|test-results)/"),
    re.compile(r"(^|/)artifacts/cleanroom-runtime/"),
    re.compile(r"\.db$"),
    re.compile(r"\.db-wal$"),
    re.compile(r"\.db-shm$"),
    re.compile(r"\.joblib$"),
)

LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1"
LFS_TRACKED_GLOB = "data/*.gz"


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _check_forbidden_paths(paths: list[str]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(path):
                failures.append(path)
                break
    return sorted(set(failures))


def _lfs_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if path.startswith("data/") and path.endswith(".gz")]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _read_tracked_blob_text(relative_path: str) -> str:
    """Read tracked blob contents from HEAD, independent of local LFS smudge state."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _check_lfs_configuration(repo_root: Path, lfs_files: list[str]) -> list[str]:
    failures: list[str] = []
    gitattributes_path = repo_root / ".gitattributes"
    if not gitattributes_path.is_file():
        return ["Missing .gitattributes file."]

    gitattributes = _read_text(gitattributes_path)
    if "data/*.gz filter=lfs diff=lfs merge=lfs -text" not in gitattributes:
        failures.append(".gitattributes is missing required LFS rule for data/*.gz")

    for relative in lfs_files:
        try:
            blob_text = _read_tracked_blob_text(relative)
        except subprocess.CalledProcessError:
            failures.append(f"Unable to read tracked blob from git for: {relative}")
            continue

        if not blob_text.startswith(LFS_POINTER_PREFIX):
            failures.append(f"Tracked LFS path is not a pointer blob: {relative}")
            continue
        if "oid sha256:" not in blob_text or "\nsize " not in blob_text:
            failures.append(f"Tracked LFS pointer blob is malformed: {relative}")

    return failures


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    tracked = _tracked_files()

    forbidden_failures = _check_forbidden_paths(tracked)
    lfs_failures = _check_lfs_configuration(repo_root, _lfs_paths(tracked))

    if forbidden_failures or lfs_failures:
        print("CI hygiene validation failed.")
        if forbidden_failures:
            print("Forbidden tracked paths:")
            for path in forbidden_failures:
                print(f" - {path}")
        if lfs_failures:
            print("LFS configuration failures:")
            for message in lfs_failures:
                print(f" - {message}")
        return 1

    print("CI hygiene validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
