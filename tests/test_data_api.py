from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "private" / "api_fixture.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "EXPECTED_CUSTOMER_ROWS", 1)
    monkeypatch.setattr(config, "EXPECTED_CAMPAIGN_SALES_ROWS", 3)
    monkeypatch.setattr(config, "EXPECTED_DEMOGRAPHIC_ROWS", 3)
    monkeypatch.setattr(config, "CUSTOMER_COUNT_EXACT_REQUIRED", True)
    monkeypatch.setattr(config, "CUSTOMER_COUNT_TOLERANCE_PERCENT", 5.0)
    monkeypatch.setattr(config, "CAMPAIGN_SALES_COUNT_EXACT_REQUIRED", True)
    monkeypatch.setattr(config, "DEMOGRAPHIC_COUNT_EXACT_REQUIRED", True)
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_populated_fixture(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES ('CUS_001', '1990-01-15', 'California', 60000, 3)
            """
        )
        connection.executemany(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                campaign_start_date, campaign_end_date,
                product_name, product_category, product_subcategory, product_tier,
                contact_date, contacted_flag, engagement_flag, response_flag,
                purchase_flag, campaign_attributed_sale_flag, pu_label
            ) VALUES (?, 'CUS_001', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "CS_001", "CMP_001", "PRD_001", "January Email", "Retention",
                    "Email", "2025-01-01", "2025-01-31", "Starter", "Services",
                    "Entry", "Standard", "2025-01-05", 1, 1, 1, 1, 1,
                ),
                (
                    "CS_002", "CMP_001", "PRD_002", "January Email", "Retention",
                    "Email", "2025-01-01", "2025-01-31", "Premium", "Services",
                    "Premium", "Premium", "2025-01-20", 0, 0, 0, 0, 0,
                ),
                (
                    "CS_003", "CMP_002", "PRD_001", "Spring Social", "Acquisition",
                    "Social", "2025-03-01", "2025-03-31", "Starter", "Services",
                    "Entry", "Standard", "2025-03-10", 1, 1, 1, 0, 0,
                ),
            ),
        )
        connection.executemany(
            """
            INSERT INTO demographics (
                person_id, age, state, individual_yearly_income,
                family_member_count, number_of_children_in_family,
                number_of_adults_in_family, family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ("PER_001", 35, "California", 60000, 3, 1, 2, 100000),
                ("PER_002", 42, "California", 70000, 2, 0, 2, 120000),
                ("PER_003", 29, "Texas", 50000, 1, 0, 1, 50000),
            ),
        )
        connection.executemany(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?, 0, ?)
            """,
            (
                (
                    "customers", r"C:\private\inputs\customers.csv.gz",
                    "2026-08-20T10:00:00Z", "2026-08-20T10:01:00Z", 1, 1, "abc",
                ),
                (
                    "campaign_sales", r"C:\private\inputs\campaign.csv.gz",
                    "2026-08-20T10:02:00Z", "2026-08-20T10:03:00Z", 3, 3, "def",
                ),
                (
                    "demographics", r"C:\private\inputs\demographics.csv.gz",
                    "2026-08-20T10:04:00Z", "2026-08-20T10:05:00Z", 3, 3, "ghi",
                ),
            ),
        )


def _record_failed_import(
    database_path: Path,
    *,
    source_path: str,
    error_message: str,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, error_message
            ) VALUES ('customers', ?, '2026-08-20T11:00:00Z',
                      '2026-08-20T11:00:01Z', 'FAILED', 0, 0, 0, ?)
            """,
            (source_path, error_message),
        )


def test_data_summary_empty_database(client: TestClient) -> None:
    response = client.get("/api/data/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["customer_count"] == 0
    assert payload["campaign_sales_count"] == 0
    assert payload["demographic_count"] == 0
    assert payload["campaign_contact_date_min"] is None
    assert payload["campaign_contact_date_max"] is None
    assert payload["database_path"] == "api_fixture.db"
    assert "private" not in payload["database_path"]
    assert payload["schema_version"] == str(CURRENT_SCHEMA_VERSION)


def test_data_summary_populated_fixture(client: TestClient, database_path: Path) -> None:
    _seed_populated_fixture(database_path)

    response = client.get("/api/data/summary")

    assert response.status_code == 200
    assert response.json() == {
        "customer_count": 1,
        "campaign_sales_count": 3,
        "demographic_count": 3,
        "distinct_campaigns": 2,
        "distinct_products": 2,
        "campaign_contact_date_min": "2025-01-05",
        "campaign_contact_date_max": "2025-03-10",
        "known_positive_count": 1,
        "attributed_purchase_count": 1,
        "database_path": "api_fixture.db",
        "schema_version": str(CURRENT_SCHEMA_VERSION),
    }


def test_data_status_reports_reconciliation_and_latest_import(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_populated_fixture(database_path)

    response = client.get("/api/data/status")

    assert response.status_code == 200
    payload = response.json()
    assert [item["dataset_name"] for item in payload] == [
        "customers", "campaign_sales", "demographics"
    ]
    assert all(item["reconciliation_status"] == "OK" for item in payload)
    assert [item["actual_rows"] for item in payload] == [1, 3, 3]
    assert payload[0]["source_path"] == "customers.csv.gz"
    assert "private" not in payload[0]["source_path"]
    assert payload[0]["last_import_status"] == "COMPLETED"
    assert payload[0]["last_import_completed_at"] == "2026-08-20T10:01:00Z"
    assert payload[0]["last_completed_import_at"] == "2026-08-20T10:01:00Z"
    assert payload[0]["rows_inserted"] == 1
    assert payload[0]["rows_rejected"] == 0
    assert payload[0]["published_source_path"] == "customers.csv.gz"
    assert payload[0]["exact_match_required"] is True
    assert payload[0]["count_tolerance_percent"] is None
    assert payload[0]["acceptable_min_rows"] == 1
    assert payload[0]["acceptable_max_rows"] == 1
    assert payload[0]["acceptable_count"] is True


def test_data_status_separates_failed_attempt_from_last_published_source(
    client: TestClient,
    database_path: Path,
    tmp_path: Path,
) -> None:
    _seed_populated_fixture(database_path)
    failed_source = tmp_path / "private" / "customers_retry_failed.csv.gz"
    _record_failed_import(
        database_path,
        source_path=str(failed_source),
        error_message=f"Source file does not exist: {failed_source}",
    )

    customer = client.get("/api/data/status").json()[0]

    assert customer["dataset_name"] == "customers"
    assert customer["last_import_status"] == "FAILED"
    assert customer["source_path"] == "customers_retry_failed.csv.gz"
    assert customer["published_source_path"] == "customers.csv.gz"
    assert customer["last_completed_import_at"] == "2026-08-20T10:01:00Z"


def test_data_status_reports_approximate_customer_policy(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_populated_fixture(database_path)
    monkeypatch.setattr(config, "EXPECTED_CUSTOMER_ROWS", 100)
    monkeypatch.setattr(config, "CUSTOMER_COUNT_EXACT_REQUIRED", False)
    monkeypatch.setattr(config, "CUSTOMER_COUNT_TOLERANCE_PERCENT", 5.0)

    customer = client.get("/api/data/status").json()[0]

    assert customer["reconciliation_status"] == "WARNING"
    assert customer["expected_rows"] == 100
    assert customer["exact_match_required"] is False
    assert customer["count_tolerance_percent"] == 5.0
    assert customer["acceptable_min_rows"] == 95
    assert customer["acceptable_max_rows"] == 105
    assert customer["acceptable_count"] is False


def test_reference_campaigns_are_aggregated_and_searchable(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_populated_fixture(database_path)

    payload = client.get("/api/reference/campaigns").json()
    searched = client.get("/api/reference/campaigns", params={"search": "Spring"}).json()

    assert len(payload) == 2
    assert payload[0] == {
        "campaign_id": "CMP_001",
        "campaign_name": "January Email",
        "campaign_type": "Retention",
        "campaign_channel": "Email",
        "campaign_start_date": "2025-01-01",
        "campaign_end_date": "2025-01-31",
        "observation_count": 2,
        "positive_count": 1,
    }
    assert [item["campaign_id"] for item in searched] == ["CMP_002"]


def test_reference_products_are_aggregated_and_bounded(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_populated_fixture(database_path)

    response = client.get("/api/reference/products", params={"limit": 1})

    assert response.status_code == 200
    assert response.json() == [
        {
            "product_id": "PRD_001",
            "product_name": "Starter",
            "product_category": "Services",
            "product_subcategory": "Entry",
            "product_tier": "Standard",
            "observation_count": 2,
            "purchase_count": 2,
        }
    ]


def test_reference_states_return_codes_and_counts(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_populated_fixture(database_path)

    response = client.get("/api/reference/states")

    assert response.status_code == 200
    assert response.json() == [
        {"state_name": "California", "state_code": "CA", "person_count": 2},
        {"state_name": "Texas", "state_code": "TX", "person_count": 1},
    ]


def test_imports_are_newest_first_sanitized_and_limit_is_validated(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_populated_fixture(database_path)

    response = client.get("/api/data/imports", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["dataset_name"] for item in payload] == ["demographics", "campaign_sales"]
    assert payload[0]["source_path"] == "demographics.csv.gz"
    assert payload[0]["error_message"] is None
    assert payload[1]["error_message"] is None
    assert client.get("/api/data/imports", params={"limit": 0}).status_code == 422
    assert client.get("/api/data/imports", params={"limit": 101}).status_code == 422
    assert client.get("/api/data/imports", params={"offset": -1}).status_code == 422
    assert client.get("/api/reference/campaigns", params={"limit": 101}).status_code == 422


def test_import_api_sanitizes_missing_source_path(
    client: TestClient,
    database_path: Path,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "private" / "missing_customers.csv.gz"
    _record_failed_import(
        database_path,
        source_path=str(source_path),
        error_message=f"Source file does not exist: {source_path}",
    )

    item = client.get("/api/data/imports").json()[0]

    assert item["error_message"] == "Source file is unavailable."
    assert item["source_path"] == "missing_customers.csv.gz"
    assert str(tmp_path) not in str(item)
    assert "private" not in str(item)


def test_import_api_sanitizes_sqlite_integrity_detail(
    client: TestClient,
    database_path: Path,
) -> None:
    _record_failed_import(
        database_path,
        source_path=r"C:\private\duplicates.csv",
        error_message=(
            "C:\\private\\duplicates.csv: database rejected batch: "
            "UNIQUE constraint failed: customers.customer_id; SELECT * FROM customers"
        ),
    )

    item = client.get("/api/data/imports").json()[0]

    assert item["error_message"] == "Database operation failed."
    public_payload = str(item).lower()
    assert "unique constraint failed" not in public_payload
    assert "customers.customer_id" not in public_payload
    assert "select *" not in public_payload
    assert "c:\\private" not in public_payload


def test_import_api_sanitizes_schema_mismatch_detail(
    client: TestClient,
    database_path: Path,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "received_secret_header.csv"
    _record_failed_import(
        database_path,
        source_path=str(source_path),
        error_message=(
            f"Schema mismatch in {source_path}; expected ['customer_id']; "
            "received ['secret_row_value', 'unexpected_column']"
        ),
    )

    item = client.get("/api/data/imports").json()[0]

    assert item["error_message"] == "Source schema is invalid."
    assert str(tmp_path) not in str(item)
    assert "secret_row_value" not in str(item)
    assert "unexpected_column" not in str(item)
