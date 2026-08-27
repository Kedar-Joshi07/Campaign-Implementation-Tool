from __future__ import annotations

from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.database.connection import get_connection
from app.database.schema import CUSTOMER_COLUMNS
from app.services.data_import_service import import_campaign_sales, import_customers
from app.services.historical_analysis_service import create_historical_analysis
from app.services.training_cohort_service import reconstruct_training_cohort
from data_generation_scripts import generate_campaign_sales


def _customer_row(customer_id: str, *, dob: str) -> dict[str, object]:
    row = {column: "" for column in CUSTOMER_COLUMNS}
    row.update(
        {
            "customer_id": customer_id,
            "first_name": "First",
            "last_name": "Last",
            "gender": "Female",
            "date_of_birth": dob,
            "state": "California",
            "country": "United States",
            "individual_yearly_income": 65000,
            "family_member_count": 2,
            "resident_status": "Citizen",
            "resident_type": "Owner",
            "education": "Bachelor degree",
            "employment_status": "Employed full-time",
            "type_of_employment": "Private sector",
            "marital_status": "Married",
        }
    )
    return row


def _write_customer_master(path: Path, *, adults: int, boundary_younger: int) -> Path:
    rows: list[dict[str, object]] = []
    for index in range(adults):
        rows.append(_customer_row(f"CUS_A_{index:04d}", dob="1989-06-15"))
    # These customers are 17 at 2024-01-01 and should never be contacted in 2024 campaigns.
    for index in range(boundary_younger):
        rows.append(_customer_row(f"CUS_B_{index:04d}", dob="2006-12-31"))
    frame = pd.DataFrame(rows, columns=CUSTOMER_COLUMNS)
    frame.to_csv(path, index=False)
    return path


def _completed_age_at_contact(dob: pd.Series, contact_date: pd.Series) -> pd.Series:
    contact = pd.to_datetime(contact_date, errors="raise")
    birth = pd.to_datetime(dob, errors="raise")
    before_birthday = (contact.dt.month * 100 + contact.dt.day) < (
        birth.dt.month * 100 + birth.dt.day
    )
    return contact.dt.year - birth.dt.year - before_birthday.astype(int)


def test_completed_age_boundary_helper_is_calendar_accurate() -> None:
    birth_dates = pd.to_datetime(pd.Series(["2007-01-10", "2007-01-11", "1925-12-31"]))

    ages = generate_campaign_sales.customer_completed_age_on(birth_dates, date(2025, 1, 10))

    assert ages.tolist() == [18, 17, 99]


def test_generation_summary_and_output_prove_no_underage_contacts(tmp_path: Path) -> None:
    customer_file = _write_customer_master(
        tmp_path / "customers.csv",
        adults=240,
        boundary_younger=30,
    )
    outdir = tmp_path / "generated"
    args = Namespace(
        customer_file=str(customer_file),
        n_rows=1200,
        n_campaigns=24,
        seed=20260827,
        outdir=str(outdir),
        output="campaign_sales_test.csv.gz",
        sample_output="campaign_sales_sample_10000.csv",
        summary_output="campaign_sales_summary.json",
        campaign_master_output="campaign_master.csv",
        product_master_output="product_master.csv",
        sample_rows=500,
    )

    generate_campaign_sales.generate(args)

    summary = pd.read_json(outdir / "campaign_sales_summary.json", typ="series")
    assert int(summary["rows"]) == 1200
    assert int(summary["underage_contact_count"]) == 0
    assert int(summary["minimum_age_at_contact"]) >= 18

    sales = pd.read_csv(outdir / "campaign_sales_test.csv.gz", compression="infer")
    customers = pd.read_csv(customer_file)
    merged = sales.merge(customers[["customer_id", "date_of_birth"]], on="customer_id", how="inner")
    ages = _completed_age_at_contact(merged["date_of_birth"], merged["contact_date"])
    assert int(ages.min()) >= 18


def test_early_date_training_cohort_respects_age_contract_for_generated_history(
    tmp_path: Path,
) -> None:
    customer_file = _write_customer_master(
        tmp_path / "customers.csv",
        adults=320,
        boundary_younger=40,
    )
    outdir = tmp_path / "generated"
    args = Namespace(
        customer_file=str(customer_file),
        n_rows=1800,
        n_campaigns=30,
        seed=20260827,
        outdir=str(outdir),
        output="campaign_sales_for_training.csv.gz",
        sample_output="campaign_sales_sample_10000.csv",
        summary_output="campaign_sales_summary.json",
        campaign_master_output="campaign_master.csv",
        product_master_output="product_master.csv",
        sample_rows=500,
    )
    generate_campaign_sales.generate(args)

    database_path = tmp_path / "generated_history.db"
    import_customers(customer_file, database_path=database_path)
    import_campaign_sales(outdir / "campaign_sales_for_training.csv.gz", database_path=database_path)

    with get_connection(database_path) as connection:
        available_from, available_to = connection.execute(
            "SELECT MIN(contact_date), MAX(contact_date) FROM campaign_sales"
        ).fetchone()
    start = pd.Timestamp(available_from).date()
    end_cap = start + timedelta(days=45)
    end = min(end_cap, pd.Timestamp(available_to).date())

    analysis = create_historical_analysis(
        database_path,
        {
            "contact_date_from": start.isoformat(),
            "contact_date_to": end.isoformat(),
        },
    )
    cohort = reconstruct_training_cohort(database_path, int(analysis["analysis_run_id"]))

    observed_ages = cohort.frame["age"].dropna().astype(int)
    assert not observed_ages.empty
    assert observed_ages.between(18, 100).all()
