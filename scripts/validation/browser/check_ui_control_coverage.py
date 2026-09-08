from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"NOT_RUN", "PASS", "FAIL", "JUSTIFIED_EXCLUSIVE"}


def evaluate_inventory(inventory_payload: dict[str, Any]) -> dict[str, Any]:
    controls: list[dict[str, Any]] = inventory_payload.get("controls", [])
    errors: list[str] = []
    counts = {
        "NOT_RUN": 0,
        "PASS": 0,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 0,
        "UNJUSTIFIED_EXCLUSIVE": 0,
        "INVALID_STATUS": 0,
    }

    for index, control in enumerate(controls, start=1):
        selector = str(control.get("selector", "")).strip()
        status = str(control.get("status", "")).strip().upper()
        if status not in ALLOWED_STATUSES:
            counts["INVALID_STATUS"] += 1
            errors.append(f"Control #{index} ({selector}) has invalid status: {status!r}")
            continue

        counts[status] += 1
        if status == "JUSTIFIED_EXCLUSIVE":
            group = str(control.get("mutually_exclusive_group", "")).strip()
            justification = str(control.get("justification", "")).strip()
            if not group or not justification:
                counts["UNJUSTIFIED_EXCLUSIVE"] += 1
                errors.append(
                    f"Control #{index} ({selector}) is JUSTIFIED_EXCLUSIVE but missing "
                    "mutually_exclusive_group or justification."
                )

    if counts["NOT_RUN"] > 0:
        errors.append(f"Coverage gate failed: NOT_RUN controls remaining ({counts['NOT_RUN']}).")
    if counts["FAIL"] > 0:
        errors.append(f"Coverage gate failed: FAIL controls present ({counts['FAIL']}).")
    if counts["UNJUSTIFIED_EXCLUSIVE"] > 0:
        errors.append(
            "Coverage gate failed: unjustified JUSTIFIED_EXCLUSIVE entries present "
            f"({counts['UNJUSTIFIED_EXCLUSIVE']})."
        )
    if counts["INVALID_STATUS"] > 0:
        errors.append(f"Coverage gate failed: invalid status entries present ({counts['INVALID_STATUS']}).")

    return {
        "ok": len(errors) == 0,
        "counts": counts,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 8 UI control coverage status contract.")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("docs/evidence/phase8/ui_control_inventory.json"),
        help="Path to UI control inventory JSON.",
    )
    args = parser.parse_args()

    payload = json.loads(args.inventory.read_text(encoding="utf-8"))
    result = evaluate_inventory(payload)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
