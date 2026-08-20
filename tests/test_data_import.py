from __future__ import annotations

import csv
import gzip
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database import connection as connection_module
from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    initialize_database,
)
from app.services.data_import_service import (
    DataImportError,
    import_campaign_sales,
    import_customers,
    import_demographics,
    resolve_demographic_sources,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "imports.db"


def _write_source(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, str]],
) -> Path:
    opener = gzip.open if path.name.endswith(".gz") else path.open
    if path.name.endswith(".gz"):
        handle = opener(path, "wt", encoding="utf-8", newline="")
    else:
        handle = opener("w", encoding="utf-8", newline="")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _customer_row(customer_id: str = "CUS_TEST_001") -> dict[str, str]:
    row = {column: "" for column in CUSTOMER_COLUMNS}
    row.update(
        {
            "customer_id": customer_id,
            "first_name": "Test",
            "last_name": "Customer",
            "gender": "Female",
            "date_of_birth": "1990-05-15",
            "state": "California",
            "country": "United States",
            "individual_yearly_income": "65000",
            "family_member_count": "2",
        }
    )
    return row


def _campaign_row(
    campaign_sales_id: str = "CS_TEST_001",
    customer_id: str = "CUS_TEST_001",
) -> dict[str, str]:
    row = {column: "" for column in CAMPAIGN_SALES_COLUMNS}
    row.update(
        {
            "campaign_sales_id": campaign_sales_id,
            "customer_id": customer_id,
            "campaign_id": "CMP_TEST_001",
            "product_id": "PRD_TEST_001",
            "campaign_start_date": "2025-01-01",
            "campaign_end_date": "2025-01-10",
            "contact_date": "2025-01-02",
            "contacted_flag": "1",
            "engagement_flag": "0",
            "response_flag": "0",
            "purchase_flag": "0",
            "quantity": "0",
            "gross_sales_amount": "0",
            "discount_amount": "0",
            "net_sales_amount": "0",
            "gross_margin_amount": "0",
            "campaign_attributed_sale_flag": "0",
            "pu_label": "0",
        }
    )
    return row


def _demographic_row(person_id: str = "US_TEST_001") -> dict[str, str]:
    row = {column: "" for column in DEMOGRAPHIC_COLUMNS}
    row.update(
        {
            "person_id": person_id,
            "age": "35",
            "state": "California",
            "country": "United States",
            "individual_yearly_income": "55000",
            "family_member_count": "3",
            "number_of_children_in_family": "1",
            "number_of_adults_in_family": "2",
            "family_yearly_income": "95000",
        }
    )
    return row


def _seed_history(tmp_path: Path, database_path: Path) -> None:
    customer_file = _write_source(
        tmp_path / "seed_customers.csv",
        CUSTOMER_COLUMNS,
        [_customer_row()],
    )
    campaign_file = _write_source(
        tmp_path / "seed_campaign.csv",
        CAMPAIGN_SALES_COLUMNS,
        [_campaign_row()],
    )
    import_customers(customer_file, database_path=database_path, batch_size=2)
    import_campaign_sales(campaign_file, database_path=database_path, batch_size=2)


def _latest_import(database_path: Path, dataset_name: str):
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM data_import_runs
            WHERE dataset_name = ?
            ORDER BY import_id DESC
            LIMIT 1
            """,
            (dataset_name,),
        ).fetchone()


def test_successful_customer_gzip_import(tmp_path: Path, database_path: Path) -> None:
    source = _write_source(
        tmp_path / "customers.csv.gz",
        CUSTOMER_COLUMNS,
        [_customer_row(), _customer_row("CUS_TEST_002")],
    )

    result = import_customers(source, database_path=database_path, batch_size=1)

    assert result.status == "COMPLETED"
    assert result.rows_read == 2
    assert result.rows_inserted == 2
    assert result.rows_rejected == 0
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 2


def test_campaign_import_with_valid_customer(tmp_path: Path, database_path: Path) -> None:
    customer_file = _write_source(
        tmp_path / "customers.csv", CUSTOMER_COLUMNS, [_customer_row()]
    )
    campaign_file = _write_source(
        tmp_path / "campaign.csv", CAMPAIGN_SALES_COLUMNS, [_campaign_row()]
    )
    import_customers(customer_file, database_path=database_path)

    result = import_campaign_sales(campaign_file, database_path=database_path)

    assert result.rows_inserted == 1
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 1


def test_campaign_import_rejects_invalid_customer_fk(
    tmp_path: Path, database_path: Path
) -> None:
    customer_file = _write_source(
        tmp_path / "customers.csv", CUSTOMER_COLUMNS, [_customer_row()]
    )
    campaign_file = _write_source(
        tmp_path / "campaign.csv",
        CAMPAIGN_SALES_COLUMNS,
        [_campaign_row(customer_id="CUS_UNKNOWN")],
    )
    import_customers(customer_file, database_path=database_path)

    with pytest.raises(DataImportError, match="FOREIGN KEY constraint failed"):
        import_campaign_sales(campaign_file, database_path=database_path)

    latest = _latest_import(database_path, "campaign_sales")
    assert latest["status"] == "FAILED"
    assert latest["rows_rejected"] == 1
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 0


def test_demographic_multi_file_import(tmp_path: Path, database_path: Path) -> None:
    _seed_history(tmp_path, database_path)
    parts = tmp_path / "parts"
    parts.mkdir()
    _write_source(
        parts / "demo_part_01.csv",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_TEST_001")],
    )
    _write_source(
        parts / "demo_part_02.csv.gz",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_TEST_002")],
    )
    sources = resolve_demographic_sources(
        input_dir=parts,
        pattern="demo_part_*.csv*",
    )

    result = import_demographics(sources, database_path=database_path, batch_size=1)

    assert [Path(path).name for path in result.source_paths] == [
        "demo_part_01.csv",
        "demo_part_02.csv.gz",
    ]
    assert result.rows_inserted == 2


def test_schema_mismatch_is_recorded_as_failed(
    tmp_path: Path, database_path: Path
) -> None:
    source = _write_source(tmp_path / "wrong.csv", ("wrong_column",), [{"wrong_column": "x"}])

    with pytest.raises(DataImportError, match="Schema mismatch"):
        import_customers(source, database_path=database_path)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert latest["error_message"]


def test_malformed_demographic_family_arithmetic_is_rejected(
    tmp_path: Path, database_path: Path
) -> None:
    _seed_history(tmp_path, database_path)
    malformed = _demographic_row()
    malformed["family_member_count"] = "4"
    source = _write_source(
        tmp_path / "bad_demo.csv", DEMOGRAPHIC_COLUMNS, [malformed]
    )

    with pytest.raises(DataImportError, match="must equal family_member_count"):
        import_demographics((source,), database_path=database_path)

    latest = _latest_import(database_path, "demographics")
    assert latest["status"] == "FAILED"
    assert latest["rows_read"] == 1
    assert latest["rows_rejected"] == 1


def test_duplicate_primary_key_fails_without_silent_skip(
    tmp_path: Path, database_path: Path
) -> None:
    source = _write_source(
        tmp_path / "duplicates.csv",
        CUSTOMER_COLUMNS,
        [_customer_row(), _customer_row()],
    )

    with pytest.raises(DataImportError, match="UNIQUE constraint failed"):
        import_customers(source, database_path=database_path, batch_size=10)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert latest["rows_rejected"] == 1
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0


def test_completed_import_metadata_contains_counts(
    tmp_path: Path, database_path: Path
) -> None:
    source = _write_source(
        tmp_path / "customers.csv", CUSTOMER_COLUMNS, [_customer_row()]
    )

    result = import_customers(source, database_path=database_path)
    latest = _latest_import(database_path, "customers")

    assert latest["import_id"] == result.import_id
    assert latest["status"] == "COMPLETED"
    assert latest["completed_at"]
    assert latest["rows_read"] == 1
    assert latest["rows_inserted"] == 1
    assert latest["rows_rejected"] == 0


def test_customer_replace_is_explicit_and_replaces_rows(
    tmp_path: Path, database_path: Path
) -> None:
    first = _write_source(
        tmp_path / "first.csv", CUSTOMER_COLUMNS, [_customer_row("CUS_OLD")]
    )
    second = _write_source(
        tmp_path / "second.csv", CUSTOMER_COLUMNS, [_customer_row("CUS_NEW")]
    )
    import_customers(first, database_path=database_path)

    import_customers(second, database_path=database_path, replace=True)

    with get_connection(database_path) as connection:
        customer_ids = [row[0] for row in connection.execute("SELECT customer_id FROM customers")]
    assert customer_ids == ["CUS_NEW"]


def test_customer_replace_wrong_header_preserves_existing_rows(
    tmp_path: Path,
    database_path: Path,
) -> None:
    original = _write_source(
        tmp_path / "original_customers.csv",
        CUSTOMER_COLUMNS,
        [_customer_row("CUS_OLD")],
    )
    wrong_header = _write_source(
        tmp_path / "wrong_customers.csv",
        ("wrong_column",),
        [{"wrong_column": "not-a-customer"}],
    )
    import_customers(original, database_path=database_path)

    with pytest.raises(DataImportError, match="Schema mismatch"):
        import_customers(wrong_header, database_path=database_path, replace=True)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert latest["rows_read"] == 0
    assert latest["rows_inserted"] == 0
    assert latest["rows_rejected"] == 0
    with get_connection(database_path) as connection:
        customer_ids = [
            row[0] for row in connection.execute("SELECT customer_id FROM customers")
        ]
    assert customer_ids == ["CUS_OLD"]


def test_default_import_refuses_nonempty_target(
    tmp_path: Path, database_path: Path
) -> None:
    first = _write_source(
        tmp_path / "first.csv", CUSTOMER_COLUMNS, [_customer_row("CUS_OLD")]
    )
    second = _write_source(
        tmp_path / "second.csv", CUSTOMER_COLUMNS, [_customer_row("CUS_NEW")]
    )
    import_customers(first, database_path=database_path)

    with pytest.raises(DataImportError, match="already contains 1 rows"):
        import_customers(second, database_path=database_path)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    with get_connection(database_path) as connection:
        customer_ids = [row[0] for row in connection.execute("SELECT customer_id FROM customers")]
    assert customer_ids == ["CUS_OLD"]


def test_customer_replace_refuses_when_campaign_rows_exist(
    tmp_path: Path, database_path: Path
) -> None:
    _seed_history(tmp_path, database_path)
    replacement = _write_source(
        tmp_path / "replacement.csv", CUSTOMER_COLUMNS, [_customer_row("CUS_NEW")]
    )

    with pytest.raises(DataImportError, match="Cannot replace customers"):
        import_customers(replacement, database_path=database_path, replace=True)

    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 1


def test_import_order_is_enforced(tmp_path: Path, database_path: Path) -> None:
    campaign_file = _write_source(
        tmp_path / "campaign.csv", CAMPAIGN_SALES_COLUMNS, [_campaign_row()]
    )

    with pytest.raises(DataImportError, match="Import customers before campaign_sales"):
        import_campaign_sales(campaign_file, database_path=database_path)


def test_missing_source_is_recorded_as_failed(tmp_path: Path, database_path: Path) -> None:
    missing_source = tmp_path / "missing_customers.csv.gz"

    with pytest.raises(DataImportError, match="does not exist"):
        import_customers(missing_source, database_path=database_path)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert str(missing_source) in latest["error_message"]


def test_malformed_date_is_recorded_as_failed(tmp_path: Path, database_path: Path) -> None:
    malformed = _customer_row()
    malformed["date_of_birth"] = "not-a-date"
    source = _write_source(
        tmp_path / "malformed_date.csv",
        CUSTOMER_COLUMNS,
        [malformed],
    )

    with pytest.raises(DataImportError, match="date_of_birth"):
        import_customers(source, database_path=database_path)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert latest["rows_read"] == 1
    assert latest["rows_rejected"] == 1


def test_corrupted_gzip_is_recorded_as_failed(tmp_path: Path, database_path: Path) -> None:
    source = tmp_path / "corrupted.csv.gz"
    source.write_bytes(b"this is not a gzip stream")

    with pytest.raises(DataImportError, match="Unable to read"):
        import_customers(source, database_path=database_path)

    latest = _latest_import(database_path, "customers")
    assert latest["status"] == "FAILED"
    assert "Not a gzipped file" in latest["error_message"]


def test_locked_database_returns_useful_import_error(
    tmp_path: Path,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(
        tmp_path / "customers.csv",
        CUSTOMER_COLUMNS,
        [_customer_row()],
    )
    initialize_database(database_path)
    monkeypatch.setattr(connection_module, "DATABASE_BUSY_TIMEOUT_MS", 25)
    locker = sqlite3.connect(database_path, timeout=0.025)
    try:
        locker.execute("BEGIN IMMEDIATE")

        with pytest.raises(DataImportError, match="SQLite database.*database is locked"):
            import_customers(source, database_path=database_path)
    finally:
        locker.rollback()
        locker.close()


def test_campaign_and_demographic_replace_modes_are_explicit(
    tmp_path: Path,
    database_path: Path,
) -> None:
    _seed_history(tmp_path, database_path)
    first_demographic = _write_source(
        tmp_path / "first_demo.csv",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_OLD")],
    )
    import_demographics((first_demographic,), database_path=database_path)

    replacement_campaign = _write_source(
        tmp_path / "replacement_campaign.csv",
        CAMPAIGN_SALES_COLUMNS,
        [_campaign_row("CS_NEW")],
    )
    replacement_demographic = _write_source(
        tmp_path / "replacement_demo.csv",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_NEW")],
    )
    import_campaign_sales(
        replacement_campaign,
        database_path=database_path,
        replace=True,
    )
    import_demographics(
        (replacement_demographic,),
        database_path=database_path,
        replace=True,
    )

    with get_connection(database_path) as connection:
        campaign_ids = [
            row[0]
            for row in connection.execute(
                "SELECT campaign_sales_id FROM campaign_sales"
            )
        ]
        person_ids = [
            row[0] for row in connection.execute("SELECT person_id FROM demographics")
        ]
    assert campaign_ids == ["CS_NEW"]
    assert person_ids == ["US_NEW"]


def test_campaign_replace_corrupt_gzip_preserves_existing_rows(
    tmp_path: Path,
    database_path: Path,
) -> None:
    _seed_history(tmp_path, database_path)
    replacement = _write_source(
        tmp_path / "replacement_campaign.csv.gz",
        CAMPAIGN_SALES_COLUMNS,
        [_campaign_row("CS_NEW")],
    )
    replacement.write_bytes(replacement.read_bytes()[:-8])

    with pytest.raises(DataImportError, match="Unable to read"):
        import_campaign_sales(replacement, database_path=database_path, replace=True)

    latest = _latest_import(database_path, "campaign_sales")
    assert latest["status"] == "FAILED"
    assert latest["rows_read"] == 0
    assert latest["rows_inserted"] == 0
    assert latest["rows_rejected"] == 0
    with get_connection(database_path) as connection:
        campaign_ids = [
            row[0]
            for row in connection.execute(
                "SELECT campaign_sales_id FROM campaign_sales"
            )
        ]
    assert campaign_ids == ["CS_TEST_001"]


def test_demographic_replace_preflights_every_part_before_deletion(
    tmp_path: Path,
    database_path: Path,
) -> None:
    _seed_history(tmp_path, database_path)
    original = _write_source(
        tmp_path / "original_demo.csv",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_OLD")],
    )
    import_demographics((original,), database_path=database_path)
    valid_part = _write_source(
        tmp_path / "replacement_demo_01.csv",
        DEMOGRAPHIC_COLUMNS,
        [_demographic_row("US_NEW_01")],
    )
    invalid_part = _write_source(
        tmp_path / "replacement_demo_02.csv",
        ("wrong_column",),
        [{"wrong_column": "not-a-person"}],
    )

    with pytest.raises(DataImportError, match="Schema mismatch"):
        import_demographics(
            (valid_part, invalid_part),
            database_path=database_path,
            replace=True,
        )

    latest = _latest_import(database_path, "demographics")
    assert latest["status"] == "FAILED"
    assert latest["rows_read"] == 0
    assert latest["rows_inserted"] == 0
    assert latest["rows_rejected"] == 0
    with get_connection(database_path) as connection:
        person_ids = [
            row[0] for row in connection.execute("SELECT person_id FROM demographics")
        ]
    assert person_ids == ["US_OLD"]
