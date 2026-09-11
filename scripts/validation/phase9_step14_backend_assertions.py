"""Read-only backend assertions for Phase 9 system-browser certification."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.database.connection import get_connection
from app.services.campaign_contracts import (
    CAMPAIGN_CONTRACT_VERSION,
    CAMPAIGN_EXPORT_CONTRACT_VERSION,
    CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
    CHANNEL_EXPORT_PROFILE,
    DIRECT_MAIL_EXPORT_COLUMNS,
    EMAIL_EXPORT_COLUMNS,
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
)
from app.services.campaign_targeting_context_service import (
    get_business_targeting_criteria,
    get_campaign_targeting_context,
)
from app.services.targeting_intelligence_service import (
    resolve_targeting_intelligence,
)


DATABASE_PATH = REPOSITORY_ROOT / "data" / "campaign_poc.db"
EXPECTED = {
    1: {"audience_id": 2, "campaign_id": 3, "match_strength": "BROAD", "count": 2248},
    2: {"audience_id": 3, "campaign_id": 4, "match_strength": "GOOD", "count": 457},
}
FORBIDDEN_PII_KEYS = {
    "first_name",
    "last_name",
    "email",
    "phone",
    "phone_number",
    "address",
    "address_line_1",
    "address_line_2",
    "street",
    "street_address",
    "city",
    "postal_code",
    "zip",
    "zip_code",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _assert_no_pii(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_PII_KEYS.intersection(value)
        assert not overlap, f"contact PII keys at {path}: {sorted(overlap)}"
        for key, child in value.items():
            _assert_no_pii(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_pii(child, path=f"{path}[{index}]")


def _row(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...]) -> dict[str, Any]:
    result = connection.execute(query, parameters).fetchone()
    assert result is not None
    return dict(result)


def main() -> None:
    started = time.perf_counter()
    assert DATABASE_PATH.is_file(), f"missing database: {DATABASE_PATH}"

    result: dict[str, Any] = {
        "database_path": str(DATABASE_PATH),
        "checks": {},
        "contexts": {},
        "phase7_export_contract": {},
    }

    inventory_path = (
        REPOSITORY_ROOT
        / "docs"
        / "evidence"
        / "phase9"
        / "final_system_browser"
        / "ui_control_coverage.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    recorded_selectors = {item["selector"] for item in inventory["controls"]}
    html = (REPOSITORY_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    static_planner_ids = set(
        re.findall(
            r'<(?:button|input|select|textarea)\b[^>]*\bid="(planner-[^"]+)"',
            html,
        )
    )
    missing_static_controls = sorted(
        control_id
        for control_id in static_planner_ids
        if f"#{control_id}" not in recorded_selectors
    )
    assert not missing_static_controls, missing_static_controls
    for selector in (
        "#planner-targeting-more > summary",
        "#planner-intelligence-advanced > summary",
        "#planner-review-technical > summary",
        "#planner-targeting-chips .planner-targeting-chip-remove",
    ):
        assert selector in recorded_selectors
    for strength in ("VERY_STRONG", "STRONG", "GOOD", "BROAD"):
        assert (
            f"input[name='match_strength'][value='{strength}']"
            in recorded_selectors
        )
    assert inventory["counts"] == {
        "PASS": 68,
        "FAIL": 0,
        "JUSTIFIED_EXCLUSIVE": 4,
        "NOT_RUN": 0,
        "UNJUSTIFIED_EXCLUSIVE": 0,
        "INVALID_STATUS": 0,
    }
    result["checks"]["phase9_control_inventory_complete"] = True

    with get_connection(DATABASE_PATH) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
        result["checks"]["database_read"] = "ok"

        current_imports = {
            row["dataset_name"]: dict(row)
            for row in connection.execute(
                """
                SELECT dataset_name, import_id, status, rows_inserted, source_checksum
                FROM data_import_runs
                WHERE import_id IN (
                    SELECT MAX(import_id) FROM data_import_runs GROUP BY dataset_name
                )
                ORDER BY dataset_name
                """
            )
        }
        assert current_imports["customers"]["rows_inserted"] == 125_000
        assert current_imports["campaign_sales"]["rows_inserted"] == 570_000
        assert current_imports["demographics"]["rows_inserted"] == 5_000_000
        assert all(item["status"] == "COMPLETED" for item in current_imports.values())
        assert current_imports["demographics"]["source_checksum"] == (
            "e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75"
        )
        result["checks"]["current_imports"] = current_imports

    for context_id, expected in EXPECTED.items():
        context = get_campaign_targeting_context(
            DATABASE_PATH, targeting_context_id=context_id
        )
        criteria = get_business_targeting_criteria(
            DATABASE_PATH, targeting_context_id=context_id
        )
        source = resolve_targeting_intelligence(
            DATABASE_PATH, targeting_context_id=context_id
        )
        context_canonical = json.dumps(
            context["context"],
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        criteria_canonical = json.dumps(
            criteria["criteria"],
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert _sha256(context_canonical) == context["campaign_context_sha256"]
        assert _sha256(criteria_canonical) == criteria["targeting_criteria_sha256"]
        assert criteria["criteria"]["match_strength"] == expected["match_strength"]
        assert source.status == "READY"
        assert source.explicitly_linked is True
        assert source.can_preview is True
        assert source.technical_details is not None
        assert source.technical_details["scoring_run_id"] == 2
        with get_connection(DATABASE_PATH) as connection:
            audience = _row(
                connection,
                "SELECT * FROM saved_audiences WHERE audience_id = ?",
                (expected["audience_id"],),
            )
            immutable_group = _row(
                connection,
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (expected["audience_id"],),
            )
            campaign = _row(
                connection,
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (expected["campaign_id"],),
            )
            source_run = _row(
                connection,
                "SELECT demographic_snapshot_count FROM scoring_runs WHERE scoring_run_id = ?",
                (2,),
            )
            score_min = json.loads(immutable_group["filter_branches_json"])[0][
                "score_min"
            ]
            exact_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores
                WHERE scoring_run_id = ? AND propensity_score >= ?
                """,
                (2, score_min),
            ).fetchone()[0]
            sample_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        p.person_id AS potential_customer_id,
                        p.propensity_score AS targeting_match_score,
                        d.age,
                        d.gender,
                        d.state,
                        d.individual_yearly_income
                    FROM propensity_scores AS p
                    JOIN demographics AS d ON d.person_id = p.person_id
                    WHERE p.scoring_run_id = ? AND p.propensity_score >= ?
                    ORDER BY p.propensity_score DESC, p.person_id ASC
                    LIMIT 25
                    """,
                    (2, score_min),
                )
            ]

        assert source_run["demographic_snapshot_count"] == 5_000_000
        assert exact_count == expected["count"]
        assert len(sample_rows) == 25
        assert len({row["potential_customer_id"] for row in sample_rows}) == 25
        _assert_no_pii(sample_rows)

        assert audience["resolved_count"] == expected["count"]
        assert audience["scoring_run_id"] == 2
        assert immutable_group["targeting_context_id"] == context_id
        assert immutable_group["resolved_count"] == expected["count"]
        assert immutable_group["source_status"] == "READY"
        assert immutable_group["source_scoring_run_id"] == 2
        assert immutable_group["campaign_context_json"] == context_canonical
        assert immutable_group["campaign_context_sha256"] == context["campaign_context_sha256"]
        assert immutable_group["targeting_criteria_json"] == criteria_canonical
        assert immutable_group["targeting_criteria_sha256"] == criteria["targeting_criteria_sha256"]
        assert _sha256(immutable_group["filter_branches_json"]) == immutable_group[
            "filter_branches_sha256"
        ]
        assert campaign["saved_audience_id"] == expected["audience_id"]
        assert campaign["saved_audience_resolved_count"] == expected["count"]
        assert campaign["saved_audience_filter_hash"] == immutable_group[
            "filter_branches_sha256"
        ]
        assert campaign["status"] == "DRAFT"
        assert campaign["channel"] == context["context"]["campaign_channel"]
        assert context["campaign_id"] == expected["campaign_id"]

        result["contexts"][str(context_id)] = {
            "campaign_context_sha256": context["campaign_context_sha256"],
            "targeting_criteria_sha256": criteria["targeting_criteria_sha256"],
            "filter_branches_sha256": immutable_group["filter_branches_sha256"],
            "match_strength": expected["match_strength"],
            "source_status": source.status,
            "source_scoring_run_id": source.technical_details["scoring_run_id"],
            "potential_customers_available": source_run[
                "demographic_snapshot_count"
            ],
            "matching": exact_count,
            "selected": audience["resolved_count"],
            "saved_target_group_id": expected["audience_id"],
            "campaign_id": expected["campaign_id"],
            "preview_rows_checked": len(sample_rows),
            "preview_contact_pii_keys": [],
        }

    assert EXPECTED[1]["audience_id"] != EXPECTED[2]["audience_id"]
    assert result["contexts"]["1"]["targeting_criteria_sha256"] != result[
        "contexts"
    ]["2"]["targeting_criteria_sha256"]
    assert result["contexts"]["1"]["filter_branches_sha256"] != result[
        "contexts"
    ]["2"]["filter_branches_sha256"]
    result["checks"]["distinct_immutable_target_groups"] = True

    expected_email_columns = (
        "person_id",
        "propensity_score",
        "percentile_bucket",
        "decile",
        "rank_band",
        "first_name",
        "last_name",
        "email",
    )
    expected_mail_columns = (
        "person_id",
        "propensity_score",
        "percentile_bucket",
        "decile",
        "rank_band",
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
    )
    assert CAMPAIGN_CONTRACT_VERSION == "1"
    assert CAMPAIGN_EXPORT_CONTRACT_VERSION == "1"
    assert CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION == "1"
    assert CHANNEL_EXPORT_PROFILE == {
        "EMAIL": EXPORT_PROFILE_EMAIL_CONTACT_V1,
        "DIRECT_MAIL": EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    }
    assert EMAIL_EXPORT_COLUMNS == expected_email_columns
    assert DIRECT_MAIL_EXPORT_COLUMNS == expected_mail_columns
    result["phase7_export_contract"] = {
        "campaign_contract_version": CAMPAIGN_CONTRACT_VERSION,
        "campaign_export_contract_version": CAMPAIGN_EXPORT_CONTRACT_VERSION,
        "member_resolution_contract_version": CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
        "channel_export_profile": CHANNEL_EXPORT_PROFILE,
        "email_columns": list(EMAIL_EXPORT_COLUMNS),
        "direct_mail_columns": list(DIRECT_MAIL_EXPORT_COLUMNS),
        "unchanged": True,
    }

    result["checks"]["all_backend_assertions"] = True
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    result["overall_status"] = "PASS"
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
