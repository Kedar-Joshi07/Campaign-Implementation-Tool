"""Read-only Stage 14B_00 baseline and source-provenance audit.

The only database created by this utility is a disposable fresh schema inside a
temporary directory.  The operator database is opened with SQLite ``mode=ro``.
The command writes its JSON report to stdout; callers decide whether to retain
that output as evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database  # noqa: E402
from app.ml.feature_contract import (  # noqa: E402
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
)


SCENARIO_PATH = ROOT / (
    "Prompts/Campaign_Implementation_Tool_Demo_Readiness_20_Real_Runs_"
    "Prompt_Pack/scenarios.json"
)
SALES_PATH = ROOT / "data/campaign_sales_570000.csv.gz"
PRODUCT_PATH = ROOT / "data/product_master.csv"
CUSTOMER_PATH = ROOT / "data/customer_master_125000.csv.gz"
DEMOGRAPHIC_PATH = ROOT / "data/usa_demographic_synthetic_5000000_rows.csv.gz"
CANONICAL_DATABASE_PATH = ROOT / "data/campaign_poc.db"

MANIFEST_PATHS = (
    "README.md",
    "docs/README.md",
    "app/database/schema.py",
    "app/ml/feature_contract.py",
    "app/selection_contracts.py",
    "app/schemas/potential_customer_search.py",
    "app/services/calibrated_selection_contract_service.py",
    "app/services/potential_customer_preflight_service.py",
    "app/services/potential_customer_search_submission_service.py",
    "app/services/phase11_result_contracts.py",
    "app/services/phase11_result_snapshot_service.py",
    "app/services/phase11_results_service.py",
    "app/services/phase11_export_service.py",
    "frontend/js/business-search-form.js",
    "scripts/validation/preflight_demo_readiness_scenarios.py",
    "tests/test_selection_contract_registry.py",
    "tests/test_preflight_http_contract.py",
    "tests/test_preflight_materialization_parity.py",
    "tests/test_phase11_api_backward_compatibility.py",
    "tests/test_phase11_results_history_detail.py",
    "tests/test_phase11_omnichannel_export_engine.py",
    "docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md",
    "docs/evidence/recovery_hardening/13_5_INTEGRATION_CLOSURE.json",
    "docs/evidence/recovery_hardening/13_6_PRE14_STABILIZATION.json",
    "docs/evidence/recovery_hardening/13_6_1_LEGACY_MAPPING_CLOSURE.json",
    (
        "Prompts/Campaign_Implementation_Tool_Demo_Readiness_20_Real_Runs_"
        "Prompt_Pack/scenarios.json"
    ),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _git_head() -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _scenario_observations() -> dict[str, Any]:
    payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    return {
        "path": SCENARIO_PATH.relative_to(ROOT).as_posix(),
        "file_sha256": _sha256_file(SCENARIO_PATH),
        "count": len(scenarios),
        "strength_distribution": dict(
            sorted(Counter(item["match_strength"] for item in scenarios).items())
        ),
        "scenario_sha256": [
            {"id": int(item["id"]), "sha256": _canonical_sha256(item)}
            for item in scenarios
        ],
    }


def _sales_and_product_observations() -> dict[str, Any]:
    products: dict[str, dict[str, str]] = {}
    with PRODUCT_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            products[str(row["product_id"])] = {
                "name": str(row.get("product_name", "")),
                "category": str(row.get("product_category", "")),
            }

    rows = 0
    customers: set[str] = set()
    observed_products: set[str] = set()
    attributed_buyers: defaultdict[str, set[str]] = defaultdict(set)
    with gzip.open(SALES_PATH, "rt", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            rows += 1
            customer_id = str(row["customer_id"])
            product_id = str(row["product_id"])
            customers.add(customer_id)
            observed_products.add(product_id)
            if str(row["campaign_attributed_sale_flag"]).strip() == "1":
                attributed_buyers[product_id].add(customer_id)

    support = []
    for product_id in sorted(products):
        count = len(attributed_buyers[product_id])
        support.append(
            {
                "product_id": product_id,
                "product_name": products[product_id]["name"],
                "observed_in_sales": product_id in observed_products,
                "distinct_attributed_buyers_unfiltered": count,
                "meets_initial_200_buyer_floor": count >= 200,
            }
        )
    return {
        "sales": {
            "path": SALES_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256_file(SALES_PATH),
            "rows": rows,
            "distinct_customers": len(customers),
            "observed_distinct_products": len(observed_products),
        },
        "product_master": {
            "path": PRODUCT_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256_file(PRODUCT_PATH),
            "catalog_products": len(products),
        },
        "customer_source": {
            "path": CUSTOMER_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256_file(CUSTOMER_PATH),
        },
        "demographic_source": {
            "path": DEMOGRAPHIC_PATH.relative_to(ROOT).as_posix(),
            "size_bytes": DEMOGRAPHIC_PATH.stat().st_size,
            # Hashing this 512 MB source is intentional: Stage 00 pins the
            # current source identity without importing or scoring it.
            "sha256": _sha256_file(DEMOGRAPHIC_PATH),
        },
        "product_support": support,
    }


def _database_objects(connection: sqlite3.Connection) -> dict[str, Any]:
    objects = [
        dict(zip(("type", "name", "table", "sql"), row, strict=True))
        for row in connection.execute(
            """SELECT type,name,tbl_name,COALESCE(sql,'')
               FROM sqlite_master
               WHERE name NOT LIKE 'sqlite_%'
               ORDER BY type,name"""
        )
    ]
    columns: dict[str, list[dict[str, Any]]] = {}
    foreign_keys: dict[str, list[list[Any]]] = {}
    for row in objects:
        if row["type"] != "table":
            continue
        table = str(row["name"])
        quoted = table.replace('"', '""')
        columns[table] = [
            {
                "cid": int(item[0]),
                "name": str(item[1]),
                "type": str(item[2]),
                "notnull": int(item[3]),
                "default": item[4],
                "pk": int(item[5]),
            }
            for item in connection.execute(f'PRAGMA table_info("{quoted}")')
        ]
        foreign_keys[table] = [
            list(item)
            for item in connection.execute(f'PRAGMA foreign_key_list("{quoted}")')
        ]
    return {"objects": objects, "columns": columns, "foreign_keys": foreign_keys}


def _disposable_schema_observations() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="campaign-14b00-") as temporary:
        database_path = Path(temporary) / "baseline.db"
        initialize_database(database_path)
        with closing(sqlite3.connect(database_path)) as connection:
            first = _database_objects(connection)
            stored_version = connection.execute(
                "SELECT value FROM app_metadata WHERE key='schema_version'"
            ).fetchone()[0]
            first_signature = _canonical_sha256(first)
        initialize_database(database_path)
        with closing(sqlite3.connect(database_path)) as connection:
            second = _database_objects(connection)
            second_signature = _canonical_sha256(second)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_violations = len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            )
    return {
        "code_schema_version": CURRENT_SCHEMA_VERSION,
        "stored_schema_version": int(stored_version),
        "schema_identity_sha256": first_signature,
        "second_initialize_schema_identity_sha256": second_signature,
        "initialize_idempotent": first_signature == second_signature,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_key_violations,
        "object_count": len(first["objects"]),
        "table_count": len(first["columns"]),
    }


def _canonical_database_observations() -> dict[str, Any]:
    if not CANONICAL_DATABASE_PATH.is_file():
        return {"available": False}
    uri = "file:" + CANONICAL_DATABASE_PATH.resolve().as_posix() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        stored_version_row = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()
        completed_imports = [
            {
                "dataset_name": str(row[0]),
                "rows_inserted": int(row[1]),
                "source_checksum": row[2],
            }
            for row in connection.execute(
                """SELECT dataset_name,rows_inserted,source_checksum
                   FROM data_import_runs
                   WHERE status='COMPLETED'
                   ORDER BY import_id"""
            )
        ]
    return {
        "available": True,
        "path": CANONICAL_DATABASE_PATH.relative_to(ROOT).as_posix(),
        "size_bytes": CANONICAL_DATABASE_PATH.stat().st_size,
        "stored_schema_version": (
            int(stored_version_row[0]) if stored_version_row is not None else None
        ),
        "opened_read_only": True,
        "completed_imports": completed_imports,
    }


def _file_manifest() -> list[dict[str, Any]]:
    result = []
    for relative in MANIFEST_PATHS:
        path = ROOT / relative
        result.append(
            {
                "path": Path(relative).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return result


def main() -> None:
    report = {
        "evidence_contract": "LOOKALIKE_V3_STAGE_00_SOURCE_AUDIT_V1",
        "repository_head": _git_head(),
        "feature_contract": {
            "version": FEATURE_CONTRACT_VERSION,
            "sha256": FEATURE_CONTRACT_SHA256,
            "ordered_features": list(ORDERED_FEATURES),
        },
        "scenarios": _scenario_observations(),
        "sources": _sales_and_product_observations(),
        "disposable_schema_31": _disposable_schema_observations(),
        "canonical_database_availability": _canonical_database_observations(),
        "baseline_file_manifest": _file_manifest(),
    }
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
