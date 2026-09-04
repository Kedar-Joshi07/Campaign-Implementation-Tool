from __future__ import annotations

import sys
from pathlib import Path

import yaml


WORKFLOWS = (
    Path('.github/workflows/ci.yml'),
    Path('.github/workflows/full-validation.yml'),
)


def main() -> int:
    failures: list[str] = []
    for workflow in WORKFLOWS:
        if not workflow.is_file():
            failures.append(f"Missing workflow file: {workflow.as_posix()}")
            continue
        try:
            yaml.safe_load(workflow.read_text(encoding='utf-8'))
        except Exception as exc:
            failures.append(f"Invalid YAML syntax in {workflow.as_posix()}: {exc}")

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print('Workflow YAML syntax validation passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
