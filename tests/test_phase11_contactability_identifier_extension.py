from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION, DEMOGRAPHIC_COLUMNS, initialize_database
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, ORDERED_FEATURES
from app.services.data_import_service import _compute_source_checksum
from app.services.data_validation_service import validate_demographic_row


CONTACTABILITY_COLUMNS = (
    "email_contactable",
    "direct_mail_contactable",
    "sms_opt_in",
    "whatsapp_opt_in",
    "telemarketing_contactable",
    "do_not_call",
    "push_token",
    "push_opt_in",
    "advertising_id",
    "advertising_targetable",
    "web_visitor_id",
    "onsite_targetable",
)
FLAG_COLUMNS = (
    "email_contactable",
    "direct_mail_contactable",
    "sms_opt_in",
    "whatsapp_opt_in",
    "telemarketing_contactable",
    "do_not_call",
    "push_opt_in",
    "advertising_targetable",
    "onsite_targetable",
)
FROZEN_FEATURE_CONTRACT_SHA256 = (
    "a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535"
)


def _run_generator(output_dir: Path, *, chunk: int, stem: str) -> tuple[Path, dict]:
    output_path = output_dir / f"{stem}.csv.gz"
    summary_path = output_dir / f"{stem}_summary.json"
    environment = os.environ.copy()
    environment.update(
        {
            "SEED": "20260818",
            "N_ROWS": "257",
            "CHUNK": str(chunk),
            "OUTDIR": str(output_dir),
            "OUT_NAME": output_path.name,
            "SUMMARY_NAME": summary_path.name,
            "SAMPLE_NAME": f"{stem}_sample.csv",
        }
    )
    subprocess.run(
        [sys.executable, "data_generation_scripts/generate_us_demographic_synthetic.py"],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )
    return output_path, json.loads(summary_path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_generator_is_deterministic_and_emits_truthful_contactability(tmp_path: Path) -> None:
    first_path, first_summary = _run_generator(tmp_path, chunk=73, stem="first")
    repeat_path, repeat_summary = _run_generator(tmp_path, chunk=73, stem="repeat")

    assert hashlib.sha256(first_path.read_bytes()).hexdigest() == hashlib.sha256(
        repeat_path.read_bytes()
    ).hexdigest()
    assert first_summary["file_sha256"] == hashlib.sha256(first_path.read_bytes()).hexdigest()
    assert repeat_summary["file_sha256"] == hashlib.sha256(repeat_path.read_bytes()).hexdigest()

    rows = _read_rows(first_path)
    assert len(rows) == 257
    assert tuple(rows[0]) == DEMOGRAPHIC_COLUMNS
    assert first_summary["columns"] == len(DEMOGRAPHIC_COLUMNS) == 40
    assert tuple(first_summary["source_columns"]) == DEMOGRAPHIC_COLUMNS
    assert tuple(first_summary["model_feature_exclusion"]) == CONTACTABILITY_COLUMNS
    assert first_summary["contactability_contract_violation_count"] == 0

    for row in rows:
        validate_demographic_row(row)
        assert all(row[column] in {"0", "1"} for column in FLAG_COLUMNS)
        assert not (row["push_opt_in"] == "1" and not row["push_token"])
        assert not (
            row["advertising_targetable"] == "1" and not row["advertising_id"]
        )
        assert not (row["onsite_targetable"] == "1" and not row["web_visitor_id"])
        assert not (
            row["telemarketing_contactable"] == "1" and row["do_not_call"] == "1"
        )

    for column, metrics in first_summary["contactability_distribution"].items():
        observed = sum(row[column] == "1" for row in rows)
        assert metrics["rows"] == observed
        assert metrics["share"] == observed / len(rows)
    for column, metrics in first_summary["identifier_availability"].items():
        observed = sum(bool(row[column]) for row in rows)
        assert metrics["rows_present"] == observed
        assert metrics["rows_missing"] == len(rows) - observed


def test_contactability_identifiers_are_independent_of_generator_chunk_size(
    tmp_path: Path,
) -> None:
    first_path, _ = _run_generator(tmp_path, chunk=73, stem="chunk_73")
    second_path, _ = _run_generator(tmp_path, chunk=97, stem="chunk_97")
    first = {
        row["person_id"]: tuple(row[column] for column in CONTACTABILITY_COLUMNS)
        for row in _read_rows(first_path)
    }
    second = {
        row["person_id"]: tuple(row[column] for column in CONTACTABILITY_COLUMNS)
        for row in _read_rows(second_path)
    }

    assert first == second


def test_schema_version_16_migration_preserves_version_15_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "phase11_migration.db"
    legacy_columns = DEMOGRAPHIC_COLUMNS[: -len(CONTACTABILITY_COLUMNS)]
    definitions = ", ".join(
        f'"{column}" {"TEXT PRIMARY KEY" if column == "person_id" else "TEXT"}'
        for column in legacy_columns
    )
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            (
                ("schema_version", "15", "2026-09-16T00:00:00Z"),
                ("application_version", "0.1.0", "2026-09-16T00:00:00Z"),
                ("database_initialized_at", "2026-09-16T00:00:00Z", "2026-09-16T00:00:00Z"),
            ),
        )
        connection.execute(f"CREATE TABLE demographics ({definitions})")
        connection.execute(
            "INSERT INTO demographics (person_id, first_name) VALUES (?, ?)",
            ("US000000001", "Preserved"),
        )
        connection.commit()
    finally:
        connection.close()

    initialize_database(database_path)

    with get_connection(database_path) as migrated:
        version = migrated.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()["value"]
        columns = tuple(
            row["name"] for row in migrated.execute("PRAGMA table_info(demographics)")
        )
        row = migrated.execute(
            "SELECT * FROM demographics WHERE person_id = ?", ("US000000001",)
        ).fetchone()
    assert version == str(CURRENT_SCHEMA_VERSION)
    assert columns == DEMOGRAPHIC_COLUMNS
    assert row["first_name"] == "Preserved"
    assert all(row[column] == 0 for column in FLAG_COLUMNS)
    assert row["push_token"] is None
    assert row["advertising_id"] is None
    assert row["web_visitor_id"] is None


def test_new_source_fields_are_part_of_import_provenance(tmp_path: Path) -> None:
    source_path = tmp_path / "demographics.csv"
    source_path.write_text("person_id,email_contactable\nUS000000001,0\n", encoding="utf-8")
    original = _compute_source_checksum((source_path,))
    source_path.write_text("person_id,email_contactable\nUS000000001,1\n", encoding="utf-8")

    assert _compute_source_checksum((source_path,)) != original


def test_contactability_fields_do_not_change_frozen_model_features() -> None:
    assert ORDERED_FEATURES == (
        "age",
        "gender",
        "state",
        "individual_yearly_income",
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "family_member_count",
        "type_of_employment",
    )
    assert FEATURE_CONTRACT_SHA256 == FROZEN_FEATURE_CONTRACT_SHA256
    assert not set(CONTACTABILITY_COLUMNS).intersection(ORDERED_FEATURES)
