from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import ORDERED_FEATURES
from app.repositories.prospect_scoring_repository import (
    ProspectScoringRepository,
    ProspectScoringValidationError,
    SCORING_CHUNK_QUERY_AFTER,
    SCORING_CHUNK_QUERY_INITIAL,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "prospect-scoring-repository.db"
    initialize_database(path)
    return path


def _insert_demographic_row(
    database_path: Path,
    *,
    person_id: str,
    age: int,
    gender: str,
    state: str,
    income: float,
    marital_status: str,
    education: str,
    employment_status: str,
    resident_status: str,
    resident_type: str,
    family_member_count: int,
    type_of_employment: str,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id,
                age,
                gender,
                state,
                individual_yearly_income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                number_of_children_in_family,
                number_of_adults_in_family,
                type_of_employment,
                family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                age,
                gender,
                state,
                income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                0,
                max(family_member_count - 1, 1),
                type_of_employment,
                float(income * 1.25),
            ),
        )


def _seed_three_rows(database_path: Path) -> None:
    _insert_demographic_row(
        database_path,
        person_id="PER_003",
        age=41,
        gender="Female",
        state="Ohio",
        income=80_000,
        marital_status="Single",
        education="Bachelors",
        employment_status="Employed",
        resident_status="Citizen",
        resident_type="Owner",
        family_member_count=2,
        type_of_employment="Salaried",
    )
    _insert_demographic_row(
        database_path,
        person_id="PER_001",
        age=34,
        gender="Male",
        state="Texas",
        income=65_000,
        marital_status="Married",
        education="High School",
        employment_status="Employed",
        resident_status="Citizen",
        resident_type="Renter",
        family_member_count=3,
        type_of_employment="Hourly",
    )
    _insert_demographic_row(
        database_path,
        person_id="PER_002",
        age=29,
        gender="Female",
        state="Nevada",
        income=52_000,
        marital_status="Single",
        education="Associates",
        employment_status="Self-Employed",
        resident_status="Permanent Resident",
        resident_type="Owner",
        family_member_count=1,
        type_of_employment="Contract",
    )


def test_fetch_scoring_chunk_returns_exact_twelve_selected_columns(database_path: Path) -> None:
    _seed_three_rows(database_path)
    repository = ProspectScoringRepository(database_path)

    person_ids, features = repository.fetch_scoring_chunk(after_person_id=None, limit=2)

    assert person_ids == ["PER_001", "PER_002"]
    assert tuple(features.columns) == ORDERED_FEATURES
    assert 1 + len(features.columns) == 12
    forbidden_columns = {
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "street",
        "postal_code",
        "city",
        "phone_number",
        "email",
        "ethnicity",
        "religion",
        "occupation_industry",
        "family_yearly_income",
        "number_of_children_in_family",
        "number_of_adults_in_family",
        "country",
    }
    assert forbidden_columns.isdisjoint(set(features.columns))


def test_keyset_chunking_is_deterministic_and_uses_no_offset(database_path: Path) -> None:
    _seed_three_rows(database_path)
    repository = ProspectScoringRepository(database_path)

    first_ids, _ = repository.fetch_scoring_chunk(after_person_id=None, limit=2)
    second_ids, _ = repository.fetch_scoring_chunk(
        after_person_id=first_ids[-1],
        limit=2,
    )

    assert first_ids == ["PER_001", "PER_002"]
    assert second_ids == ["PER_003"]
    assert first_ids + second_ids == ["PER_001", "PER_002", "PER_003"]

    assert "offset" not in SCORING_CHUNK_QUERY_INITIAL.casefold()
    assert "offset" not in SCORING_CHUNK_QUERY_AFTER.casefold()
    assert "order by person_id" in SCORING_CHUNK_QUERY_INITIAL.casefold()
    assert "order by person_id" in SCORING_CHUNK_QUERY_AFTER.casefold()


def test_population_snapshot_is_bounded_and_dynamic(database_path: Path) -> None:
    _seed_three_rows(database_path)
    repository = ProspectScoringRepository(database_path)

    snapshot = repository.fetch_prospect_snapshot()

    assert snapshot.demographic_snapshot_count == 3
    assert snapshot.demographic_min_person_id == "PER_001"
    assert snapshot.demographic_max_person_id == "PER_003"


@pytest.mark.parametrize("invalid_limit", [0, -1, 100_001])
def test_fetch_scoring_chunk_rejects_invalid_limit(database_path: Path, invalid_limit: int) -> None:
    repository = ProspectScoringRepository(database_path)

    with pytest.raises(ProspectScoringValidationError):
        repository.fetch_scoring_chunk(after_person_id=None, limit=invalid_limit)
