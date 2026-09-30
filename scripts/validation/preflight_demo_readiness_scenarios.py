"""Run exact calibrated preflight for the 20 canonical demo scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.potential_customer_preflight_service import (  # noqa: E402
    exact_preflight_many,
)
from app.services.targeting_option_catalog_service import (  # noqa: E402
    get_or_build_targeting_catalog,
)

SCENARIOS_PATH = (
    ROOT
    / "Prompts"
    / "Campaign_Implementation_Tool_Demo_Readiness_20_Real_Runs_Prompt_Pack"
    / "scenarios.json"
)
DEFAULT_CONTEXT_MANIFEST = ROOT / "output" / "demo_preload" / "demo_20_scenario_checkpoint.json"
DEFAULT_OUTPUT = ROOT / "output" / "demo_preload" / "recovery_preflight_20.json"
BUCKET_BY_STRENGTH = {
    "VERY_STRONG": "0.90",
    "STRONG": "0.80",
    "GOOD": "0.70",
    "BROAD": "0.60",
}
CRITERIA_FIELDS = (
    "match_strength",
    "genders",
    "age_groups",
    "states",
    "income_groups",
    "marital_statuses",
    "education_levels",
    "employment_statuses",
    "resident_statuses",
    "resident_types",
    "employment_types",
    "family_member_count_min",
    "family_member_count_max",
)


def _criteria(scenario: dict[str, Any]) -> dict[str, Any]:
    criteria = {field: scenario[field] for field in CRITERIA_FIELDS}
    criteria.update(
        top_matching_percent=None,
        selection_mode="ALL_MATCHING",
        target_count=None,
    )
    return criteria


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/campaign_poc.db")
    parser.add_argument("--context-manifest", type=Path, default=DEFAULT_CONTEXT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    database_path = (ROOT / args.database).resolve()
    context_manifest = args.context_manifest.resolve()
    if not context_manifest.exists():
        raise FileNotFoundError(
            "A recorded common-context manifest is required; scenario context must not be guessed."
        )
    common_context = json.loads(context_manifest.read_text(encoding="utf-8"))["common_context"]
    scenario_pack = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    scenarios = scenario_pack["scenarios"]
    if [item["id"] for item in scenarios] != list(range(1, 21)):
        raise RuntimeError("The canonical scenario pack must contain scenarios 1 through 20.")
    catalog = get_or_build_targeting_catalog(database_path)
    buckets = [BUCKET_BY_STRENGTH[item["match_strength"]] for item in scenarios]
    preflights = exact_preflight_many(
        database_path,
        [
            {
                "context": common_context,
                "criteria": _criteria(scenario),
                "propensity_bucket": bucket,
                "catalog_version": catalog["catalog_version"],
            }
            for scenario, bucket in zip(scenarios, buckets, strict=True)
        ],
    )
    rows: list[dict[str, Any]] = []
    for scenario, bucket, result in zip(
        scenarios,
        buckets,
        preflights,
        strict=True,
    ):
        row = {
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "legacy_match_strength": scenario["match_strength"],
            "propensity_bucket": bucket,
            **result,
        }
        rows.append(row)
        print(
            f"scenario={scenario['id']:02d} demographic={result['demographic_count']} "
            f"bucket={result['bucket_count']} qualifying={result['qualifying_count']} "
            f"selected={result['selected_count']} "
            f"demo_ready={result['demo_ready']}",
            flush=True,
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": str(database_path),
        "catalog_version": catalog["catalog_version"],
        "common_context": common_context,
        "qualification_minimum": 10_000,
        "qualified_count": sum(1 for row in rows if row["demo_ready"]),
        "scenarios": rows,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote={output} qualified={payload['qualified_count']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
