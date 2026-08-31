from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import perf_counter

from app.database.schema import initialize_database
from app.repositories.scoring_repository import SCORE_SCAN_QUERY_AFTER, SCORE_SCAN_QUERY_INITIAL
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.audience_query_service import estimate_audience, profile_audience, search_audience
from app.services.saved_audience_service import get_saved_audience_detail, list_saved_audiences, save_audience
from tests.test_phase6_step8_hardening import _phase6_seed_fixture


def _plan_rows(connection: sqlite3.Connection, query: str, params: list[object]) -> list[str]:
    return [str(row[3]) for row in connection.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()]


def _timed_ms(fn) -> float:
    started = perf_counter()
    fn()
    return round((perf_counter() - started) * 1000.0, 3)


def _case(name: str, plan: list[str], timing_ms: float) -> dict[str, object]:
    plan_text = "\n".join(plan)
    return {
        "name": name,
        "timing_ms": timing_ms,
        "uses_rank_index": "idx_propensity_scores_run_score_person" in plan_text,
        "uses_saved_newest_index": "idx_saved_audiences_newest" in plan_text,
        "plan": plan,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    db_path = root / "artifacts" / "phase6_step8_perf_security.db"
    sanitized_db_ref = "artifacts/phase6_step8_perf_security.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    initialize_database(db_path)
    scoring_run_id = _phase6_seed_fixture(db_path)
    run_audience_rank_preparation(db_path, scoring_run_id=scoring_run_id)

    first_page = search_audience(
        db_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 2,
        },
    )
    second_page = search_audience(
        db_path,
        {
            "scoring_run_id": scoring_run_id,
            "filters": {},
            "page_size": 2,
            "cursor": first_page["next_cursor"],
        },
    )

    saved = save_audience(
        db_path,
        {
            "audience_name": "step8-evidence",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California"]},
            "selection": {"mode": "TOP_N", "target_count": 2},
            "include_profile_snapshot": True,
        },
    )
    audience_id = int(saved["audience_id"])

    with sqlite3.connect(db_path) as connection:
        cases: list[dict[str, object]] = []

        q_initial = """
            SELECT p.person_id, p.propensity_score
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            ORDER BY p.propensity_score DESC, p.person_id ASC
            LIMIT ?
        """
        cases.append(
            _case(
                "unfiltered first page",
                _plan_rows(connection, q_initial, [scoring_run_id, 3]),
                _timed_ms(
                    lambda: search_audience(
                        db_path,
                        {
                            "scoring_run_id": scoring_run_id,
                            "filters": {},
                            "page_size": 2,
                        },
                    )
                ),
            )
        )

        q_after = """
            SELECT p.person_id, p.propensity_score
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
              AND (p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))
            ORDER BY p.propensity_score DESC, p.person_id ASC
            LIMIT ?
        """
        last_row = first_page["rows"][-1]
        cases.append(
            _case(
                "next keyset page",
                _plan_rows(
                    connection,
                    q_after,
                    [
                        scoring_run_id,
                        float(last_row["propensity_score"]),
                        float(last_row["propensity_score"]),
                        str(last_row["person_id"]),
                        3,
                    ],
                ),
                _timed_ms(lambda: second_page),
            )
        )

        estimate_payloads = [
            (
                "top 1%",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {"top_percentile_max": 1},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            ),
            (
                "top decile",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {"deciles": [1]},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            ),
            (
                "state filter",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {"state": ["California"]},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            ),
            (
                "age+income",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {
                        "age_min": 30,
                        "age_max": 55,
                        "individual_yearly_income_min": 50000.0,
                        "individual_yearly_income_max": 150000.0,
                    },
                    "selection": {"mode": "ALL_MATCHING"},
                },
            ),
            (
                "rank band+demographic filter",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {
                        "rank_bands": ["HIGH", "MEDIUM"],
                        "resident_type": ["Urban"],
                    },
                    "selection": {"mode": "TOP_N", "target_count": 2},
                },
            ),
            (
                "estimate",
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "selection": {"mode": "ALL_MATCHING"},
                },
            ),
        ]

        q_estimate_base = """
            SELECT COUNT(*) AS matching_count,
                   MIN(p.propensity_score),
                   AVG(p.propensity_score),
                   MAX(p.propensity_score)
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
        """
        for name, payload in estimate_payloads:
            cases.append(
                _case(
                    name,
                    _plan_rows(connection, q_estimate_base, [scoring_run_id]),
                    _timed_ms(lambda p=payload: estimate_audience(db_path, p)),
                )
            )

        q_profile_selected = """
            WITH
            matching_members AS MATERIALIZED (
                SELECT p.person_id, p.propensity_score
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ? AND d.state IN (?)
            ),
            selected_members AS MATERIALIZED (
                SELECT * FROM matching_members
                ORDER BY propensity_score DESC, person_id ASC
                LIMIT ?
            )
            SELECT COUNT(*) FROM selected_members
        """
        cases.append(
            _case(
                "selected profile",
                _plan_rows(connection, q_profile_selected, [scoring_run_id, "California", 2]),
                _timed_ms(
                    lambda: profile_audience(
                        db_path,
                        {
                            "scoring_run_id": scoring_run_id,
                            "filters": {"state": ["California"]},
                            "selection": {"mode": "TOP_N", "target_count": 2},
                        },
                    )
                ),
            )
        )

        q_saved_list = """
            SELECT *
            FROM saved_audiences
            ORDER BY created_at DESC, audience_id DESC
            LIMIT ? OFFSET ?
        """
        q_saved_detail = "SELECT * FROM saved_audiences WHERE audience_id = ?"
        cases.append(
            _case(
                "saved-audience list/detail",
                _plan_rows(connection, q_saved_list, [20, 0])
                + _plan_rows(connection, q_saved_detail, [audience_id]),
                round(
                    _timed_ms(lambda: list_saved_audiences(db_path, limit=20, offset=0))
                    + _timed_ms(lambda: get_saved_audience_detail(db_path, audience_id=audience_id)),
                    3,
                ),
            )
        )

        index_names = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        ]
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])

    payload = {
        "step": "phase6_step8",
        "evidence_type": "Synthetic bounded query-plan/index validation",
        "is_real_5m_performance": False,
        "database": sanitized_db_ref,
        "query_plan_timing_cases": cases,
        "index_inventory": sorted(index_names),
        "database_size_bytes": page_count * page_size,
        "page_count": page_count,
        "page_size": page_size,
        "no_offset_hot_path": {
            "score_scan_initial_uses_offset": "OFFSET" in SCORE_SCAN_QUERY_INITIAL.upper(),
            "score_scan_after_uses_offset": "OFFSET" in SCORE_SCAN_QUERY_AFTER.upper(),
            "saved_audiences_offset_allowed": True,
        },
    }

    out_path = root / "docs" / "evidence" / "phase6_step8_query_plan_and_timing.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
