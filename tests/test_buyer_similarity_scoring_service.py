from __future__ import annotations

import copy
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.repositories.buyer_similarity_profile_repository import (
    publish_buyer_similarity_profile,
)
from app.repositories.buyer_similarity_scoring_repository import (
    BuyerSimilarityGenerationBusy,
    BuyerSimilarityGenerationFenceLost,
    BuyerSimilarityGenerationVerificationError,
    BuyerSimilarityScoringRepository,
    BuyerSimilarityScoringRepositoryError,
)
from app.repositories.prospect_scoring_repository import ProspectScoringRepository
from app.services.buyer_similarity_profile_service import (
    BuyerSimilarityArtifactError,
    _profile_identity,
)
from app.services.buyer_similarity_scoring_service import (
    BuyerSimilarityScoringCancelled,
    composite_similarity_winners,
    estimate_similarity_preparation_work,
    has_current_similarity_attestation,
    run_similarity_generation,
)
from tests.test_buyer_similarity_profile_service import (
    BASE_FEATURES,
    _registry_database,
    _single_profile,
)


NOW = "2026-10-06T03:00:00Z"


def _insert_demographics(path: Path, *, count: int = 12) -> None:
    rows = []
    for index in range(count):
        values = dict(BASE_FEATURES)
        values["gender"] = "Female" if index % 2 == 0 else "Male"
        if index == count - 2:
            # Unknown to both bounded product vocabularies, producing an exact
            # equal-score row used to prove deterministic product-ID tie-breaks.
            values["gender"] = ""
        if index == count - 1:
            values["age"] = 10  # Stored by the source schema, invalid for the model contract.
        rows.append(
            (
                f"P{index:04d}",
                values["gender"],
                values["age"],
                values["state"],
                values["individual_yearly_income"],
                values["marital_status"],
                values["education"],
                values["employment_status"],
                values["resident_status"],
                values["resident_type"],
                values["family_member_count"],
                values["type_of_employment"],
                1,
                2,
                values["individual_yearly_income"] * 2,
            )
        )
    with get_connection(path, write=True) as connection:
        connection.executemany(
            """INSERT INTO demographics (
                person_id,gender,age,state,individual_yearly_income,marital_status,
                education,employment_status,resident_status,resident_type,
                family_member_count,type_of_employment,number_of_children_in_family,
                number_of_adults_in_family,family_yearly_income
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        connection.execute(
            """INSERT INTO data_import_runs (
                import_id,dataset_name,source_path,started_at,completed_at,status,
                rows_read,rows_inserted,rows_rejected,source_checksum
            ) VALUES (3,'demographics','demographics.csv',?,?,'COMPLETED',?,?,0,?)""",
            ("2026-10-06T00:00:00Z", "2026-10-06T00:00:01Z", count, count, "3" * 64),
        )


def _case(tmp_path: Path, *, count: int = 12) -> tuple[Path, int]:
    database = _registry_database(tmp_path)
    _insert_demographics(database, count=count)
    published = publish_buyer_similarity_profile(
        database,
        _single_profile(),
        project_root=tmp_path,
        execution_owner="profile-fixture",
        execution_token="f" * 64,
        now="2026-10-06T01:00:00Z",
    )
    return database, published.profile_id


def _manual_valid_rows(person_ids: list[str], score: float = 0.75) -> list[dict]:
    return [
        {
            "person_id": person_id,
            "is_valid": True,
            "buyer_similarity_score": score,
            "feature_coverage": 1.0,
            "prototype_key": "P001",
            "invalid_reason_code": None,
        }
        for person_id in person_ids
    ]


def test_chunked_generation_deep_verification_publication_and_fast_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, profile_id = _case(tmp_path)
    progress: list[tuple[str, int, int]] = []
    timings: dict[str, float] = {}
    result = run_similarity_generation(
        database,
        profile_id,
        project_root=tmp_path,
        execution_owner="score-worker",
        execution_token="a" * 64,
        chunk_size=3,
        progress_callback=lambda stage, processed, total, _message: progress.append(
            (stage, processed, total)
        ),
        clock=lambda: NOW,
        timing_sink=timings,
    )
    generation_id = result["similarity_generation_id"]
    assert result["status"] == "PUBLISHED"
    assert result["deep_verification_run"] is True
    assert all(timings[key] >= 0 for key in (
        "deep_verification_seconds", "indexed_score_insert_seconds",
        "publication_transaction_body_seconds", "verify_and_publish_committed_seconds",
    ))
    assert timings["indexed_score_insert_seconds"] <= timings["publication_transaction_body_seconds"]
    assert timings["deep_verification_seconds"] <= timings["verify_and_publish_committed_seconds"]
    assert progress[0][0] == "QUEUE_WAIT"
    assert ("SCORING_PROSPECTS", 12, 12) in progress
    with get_connection(database) as connection:
        generation = dict(connection.execute(
            "SELECT * FROM buyer_similarity_score_generations WHERE similarity_generation_id=?",
            (generation_id,),
        ).fetchone())
        counts = tuple(connection.execute(
            """SELECT COUNT(*),SUM(is_valid),SUM(CASE WHEN is_valid=0 THEN 1 ELSE 0 END)
               FROM buyer_similarity_scores WHERE similarity_generation_id=?""",
            (generation_id,),
        ).fetchone())
        stage_count = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage WHERE similarity_generation_id=?",
            (generation_id,),
        ).fetchone()[0]
        attestation = dict(connection.execute(
            "SELECT * FROM buyer_similarity_generation_attestations WHERE similarity_generation_id=?",
            (generation_id,),
        ).fetchone())
    assert generation["publication_state"] == "PUBLISHED"
    assert counts == (12, 11, 1)
    assert stage_count == 0
    assert attestation["verification_status"] == "VERIFIED"
    assert has_current_similarity_attestation(
        database, generation_id, project_root=tmp_path
    )

    monkeypatch.setattr(
        BuyerSimilarityScoringRepository,
        "verify_and_publish",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fast reuse must not deep verify")
        ),
    )
    reused = run_similarity_generation(
        database,
        profile_id,
        project_root=tmp_path,
        execution_owner="score-worker-2",
        execution_token="b" * 64,
        chunk_size=5,
        clock=lambda: NOW,
    )
    assert reused["reused"] is True
    assert reused["deep_verification_run"] is False
    assert reused["similarity_generation_id"] == generation_id


def test_chunk_size_independence(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_db, first_profile = _case(first_root)
    second_db, second_profile = _case(second_root)
    first = run_similarity_generation(
        first_db,
        first_profile,
        project_root=first_root,
        execution_owner="first",
        execution_token="1" * 64,
        chunk_size=2,
        clock=lambda: NOW,
    )
    second = run_similarity_generation(
        second_db,
        second_profile,
        project_root=second_root,
        execution_owner="second",
        execution_token="2" * 64,
        chunk_size=7,
        clock=lambda: NOW,
    )
    def scores(path: Path, generation_id: int) -> list[tuple]:
        with get_connection(path) as connection:
            return [tuple(row) for row in connection.execute(
                """SELECT person_id,is_valid,buyer_similarity_score,feature_coverage,
                          prototype_key,invalid_reason_code
                   FROM buyer_similarity_scores WHERE similarity_generation_id=?
                   ORDER BY person_id""",
                (generation_id,),
            )]
    assert scores(first_db, first["similarity_generation_id"]) == scores(
        second_db, second["similarity_generation_id"]
    )


def test_same_token_resumes_transactional_checkpoint_after_staged_crash(tmp_path: Path) -> None:
    database, profile_id = _case(tmp_path)
    repository = BuyerSimilarityScoringRepository(database)
    provenance = ProspectScoringRepository(database).fetch_completed_demographic_import_provenance()
    claim = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    person_ids, _frame = ProspectScoringRepository(database).fetch_scoring_chunk(
        after_person_id=None, limit=4
    )
    repository.persist_score_chunk(
        claim.similarity_generation_id,
        _manual_valid_rows(person_ids),
        expected_checkpoint_person_id=None,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    completed = run_similarity_generation(
        database,
        profile_id,
        project_root=tmp_path,
        execution_owner="worker",
        execution_token="a" * 64,
        chunk_size=4,
        clock=lambda: NOW,
    )
    assert completed["status"] == "PUBLISHED"
    assert completed["published_person_count"] == 12


def test_concurrent_claim_stale_recovery_restarts_and_old_writer_is_fenced(
    tmp_path: Path,
) -> None:
    database, profile_id = _case(tmp_path)
    repository = BuyerSimilarityScoringRepository(database)
    provenance = ProspectScoringRepository(database).fetch_completed_demographic_import_provenance()
    first = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker-a",
        execution_token="a" * 64,
        now="2026-10-06T01:00:00Z",
    )
    ids, _ = ProspectScoringRepository(database).fetch_scoring_chunk(
        after_person_id=None, limit=3
    )
    repository.persist_score_chunk(
        first.similarity_generation_id,
        _manual_valid_rows(ids),
        expected_checkpoint_person_id=None,
        execution_owner="worker-a",
        execution_token="a" * 64,
        now="2026-10-06T01:00:01Z",
    )
    with pytest.raises(BuyerSimilarityGenerationBusy):
        repository.claim_generation(
            profile_id,
            provenance,
            execution_owner="worker-b",
            execution_token="b" * 64,
            now="2026-10-06T01:01:00Z",
            stale_before="2026-10-06T00:59:00Z",
        )
    recovered = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker-b",
        execution_token="b" * 64,
        now="2026-10-06T02:00:00Z",
        stale_before="2026-10-06T01:30:00Z",
    )
    assert recovered.restarted_from_stale_lease
    assert recovered.processed_count == 0
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 0
    with pytest.raises(BuyerSimilarityGenerationFenceLost):
        repository.persist_score_chunk(
            first.similarity_generation_id,
            _manual_valid_rows(ids),
            expected_checkpoint_person_id=None,
            execution_owner="worker-a",
            execution_token="a" * 64,
            now="2026-10-06T02:00:01Z",
        )
    completed = run_similarity_generation(
        database,
        profile_id,
        project_root=tmp_path,
        execution_owner="worker-b",
        execution_token="b" * 64,
        chunk_size=4,
        clock=lambda: "2026-10-06T02:00:02Z",
    )
    assert completed["status"] == "PUBLISHED"


@pytest.mark.parametrize("mode", ["missing", "extra"])
def test_failed_population_verification_never_publishes(tmp_path: Path, mode: str) -> None:
    database, profile_id = _case(tmp_path)
    repository = BuyerSimilarityScoringRepository(database)
    provenance = ProspectScoringRepository(database).fetch_completed_demographic_import_provenance()
    claim = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    with get_connection(database) as connection:
        person_ids = [str(row[0]) for row in connection.execute(
            "SELECT person_id FROM demographics ORDER BY person_id"
        )]
    staged_ids = person_ids[:-1] if mode == "missing" else [*person_ids[:-1], "PXTRA"]
    repository.persist_score_chunk(
        claim.similarity_generation_id,
        _manual_valid_rows(staged_ids),
        expected_checkpoint_person_id=None,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    with pytest.raises(BuyerSimilarityGenerationVerificationError):
        repository.verify_and_publish(
            claim.similarity_generation_id,
            allowed_prototype_keys=["P001"],
            profile_artifact_sha256=repository.fetch_profile_for_scoring(profile_id)[
                "artifact_sha256"
            ],
            execution_owner="worker",
            execution_token="a" * 64,
            now=NOW,
        )
    with get_connection(database) as connection:
        state = connection.execute(
            "SELECT publication_state FROM buyer_similarity_score_generations"
        ).fetchone()[0]
        published = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0]
        status = connection.execute(
            "SELECT verification_status FROM buyer_similarity_generation_attestations"
        ).fetchone()[0]
    assert state == "FAILED"
    assert published == 0
    assert status == "FAILED"


def test_duplicate_chunk_is_rejected_atomically(tmp_path: Path) -> None:
    database, profile_id = _case(tmp_path)
    repository = BuyerSimilarityScoringRepository(database)
    provenance = ProspectScoringRepository(database).fetch_completed_demographic_import_provenance()
    claim = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    rows = _manual_valid_rows(["P0000", "P0000"])
    with pytest.raises(Exception, match="unique ascending"):
        repository.persist_score_chunk(
            claim.similarity_generation_id,
            rows,
            expected_checkpoint_person_id=None,
            execution_owner="worker",
            execution_token="a" * 64,
            now=NOW,
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 0


def test_valid_row_below_required_coverage_is_rejected_atomically(tmp_path: Path) -> None:
    database, profile_id = _case(tmp_path)
    repository = BuyerSimilarityScoringRepository(database)
    provenance = ProspectScoringRepository(database).fetch_completed_demographic_import_provenance()
    claim = repository.claim_generation(
        profile_id,
        provenance,
        execution_owner="worker",
        execution_token="a" * 64,
        now=NOW,
    )
    rows = _manual_valid_rows(["P0000"])
    rows[0]["feature_coverage"] = 0.79
    with pytest.raises(BuyerSimilarityScoringRepositoryError, match="inconsistent"):
        repository.persist_score_chunk(
            claim.similarity_generation_id,
            rows,
            expected_checkpoint_person_id=None,
            execution_owner="worker",
            execution_token="a" * 64,
            now=NOW,
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0] == 0


def test_source_replacement_mid_score_marks_stale_and_publishes_nothing(tmp_path: Path) -> None:
    database, profile_id = _case(tmp_path)
    replaced = False

    def progress(stage: str, processed: int, _total: int, _message: str) -> None:
        nonlocal replaced
        if stage == "SCORING_PROSPECTS" and processed == 4 and not replaced:
            with get_connection(database, write=True) as connection:
                connection.execute(
                    """INSERT INTO data_import_runs (
                        import_id,dataset_name,source_path,started_at,completed_at,status,
                        rows_read,rows_inserted,rows_rejected,source_checksum
                    ) VALUES (4,'demographics','replacement.csv',?,?,'COMPLETED',12,12,0,?)""",
                    (NOW, NOW, "4" * 64),
                )
            replaced = True

    with pytest.raises(Exception, match="changed during similarity scoring"):
        run_similarity_generation(
            database,
            profile_id,
            project_root=tmp_path,
            execution_owner="worker",
            execution_token="a" * 64,
            chunk_size=4,
            progress_callback=progress,
            clock=lambda: NOW,
        )
    with get_connection(database) as connection:
        generation = connection.execute(
            "SELECT publication_state,safe_error_code FROM buyer_similarity_score_generations"
        ).fetchone()
        published = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0]
    assert tuple(generation) == ("STALE", "SOURCE_REPLACED")
    assert published == 0


def test_corrupt_profile_artifact_refuses_scoring(tmp_path: Path) -> None:
    database, profile_id = _case(tmp_path)
    with get_connection(database) as connection:
        uri = connection.execute(
            "SELECT storage_uri FROM buyer_similarity_profile_artifacts WHERE profile_id=?",
            (profile_id,),
        ).fetchone()[0]
    (tmp_path / uri).write_bytes(b"corrupt")
    with pytest.raises(BuyerSimilarityArtifactError):
        run_similarity_generation(
            database,
            profile_id,
            project_root=tmp_path,
            execution_owner="worker",
            execution_token="a" * 64,
            chunk_size=4,
            clock=lambda: NOW,
        )
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_generations"
        ).fetchone()[0] == 0


def test_two_product_max_winner_and_product_id_tie(tmp_path: Path) -> None:
    database, first_profile_id = _case(tmp_path)
    second_artifact = copy.deepcopy(_single_profile())
    second_artifact["product_id"] = "PRD002"
    second_artifact["categorical_vocabulary"]["gender"] = ["Female", "Male"]
    second_artifact["prototypes"][0]["values"]["gender"] = "Male"
    second_artifact["immutable_identity_sha256"] = _profile_identity(
        second_artifact, include_existing=False
    )
    second_profile = publish_buyer_similarity_profile(
        database,
        second_artifact,
        project_root=tmp_path,
        execution_owner="profile-two",
        execution_token="e" * 64,
        now="2026-10-06T01:01:00Z",
    )
    estimate_before = estimate_similarity_preparation_work(
        database,
        [first_profile_id, second_profile.profile_id],
        project_root=tmp_path,
    )
    assert estimate_before["estimated_new_score_rows"] == 24
    assert estimate_before["operator_confirmation_recommended"] is True
    first = run_similarity_generation(
        database,
        first_profile_id,
        project_root=tmp_path,
        execution_owner="score-one",
        execution_token="1" * 64,
        chunk_size=5,
        clock=lambda: NOW,
    )
    second = run_similarity_generation(
        database,
        second_profile.profile_id,
        project_root=tmp_path,
        execution_owner="score-two",
        execution_token="2" * 64,
        chunk_size=5,
        clock=lambda: NOW,
    )
    winners = composite_similarity_winners(
        database,
        [second["similarity_generation_id"], first["similarity_generation_id"]],
        project_root=tmp_path,
    )
    by_person = {row["person_id"]: row for row in winners}
    assert by_person["P0000"]["matched_product_id"] == "PRD001"
    assert by_person["P0001"]["matched_product_id"] == "PRD002"
    assert by_person["P0010"]["matched_product_id"] == "PRD001"

    # Force one exact equal-score fixture through a fresh bounded database row;
    # the SQL winner must choose product_id ascending, independent of input order.
    with get_connection(database) as connection:
        left = connection.execute(
            """SELECT buyer_similarity_score FROM buyer_similarity_scores
               WHERE similarity_generation_id=? AND person_id='P0000'""",
            (first["similarity_generation_id"],),
        ).fetchone()[0]
        right = connection.execute(
            """SELECT buyer_similarity_score FROM buyer_similarity_scores
               WHERE similarity_generation_id=? AND person_id='P0000'""",
            (second["similarity_generation_id"],),
        ).fetchone()[0]
        tie_left = connection.execute(
            """SELECT buyer_similarity_score FROM buyer_similarity_scores
               WHERE similarity_generation_id=? AND person_id='P0010'""",
            (first["similarity_generation_id"],),
        ).fetchone()[0]
        tie_right = connection.execute(
            """SELECT buyer_similarity_score FROM buyer_similarity_scores
               WHERE similarity_generation_id=? AND person_id='P0010'""",
            (second["similarity_generation_id"],),
        ).fetchone()[0]
    assert left > right
    assert tie_left == tie_right
    estimate = estimate_similarity_preparation_work(
        database,
        [first_profile_id, second_profile.profile_id],
        project_root=tmp_path,
    )
    assert estimate["estimated_new_score_rows"] == 0
    assert estimate["reusable_profile_ids"] == sorted(
        [first_profile_id, second_profile.profile_id]
    )


def test_cancellation_after_first_chunk_removes_stage_and_never_publishes(
    tmp_path: Path,
) -> None:
    database, profile_id = _case(tmp_path)
    processed = 0

    def progress(stage: str, current: int, _total: int, _message: str) -> None:
        nonlocal processed
        if stage == "SCORING_PROSPECTS":
            processed = current

    with pytest.raises(BuyerSimilarityScoringCancelled):
        run_similarity_generation(
            database,
            profile_id,
            project_root=tmp_path,
            execution_owner="worker",
            execution_token="a" * 64,
            chunk_size=4,
            progress_callback=progress,
            cancellation_check=lambda: processed >= 4,
            clock=lambda: NOW,
        )
    with get_connection(database) as connection:
        generation = connection.execute(
            """SELECT publication_state,safe_error_code,published_person_count
               FROM buyer_similarity_score_generations"""
        ).fetchone()
        staged = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_score_stage"
        ).fetchone()[0]
        published = connection.execute(
            "SELECT COUNT(*) FROM buyer_similarity_scores"
        ).fetchone()[0]
    assert tuple(generation) == ("FAILED", "CANCELLED", None)
    assert staged == 0
    assert published == 0


def test_fast_reuse_never_consults_v2_calibration_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, profile_id = _case(tmp_path)
    result = run_similarity_generation(
        database,
        profile_id,
        project_root=tmp_path,
        execution_owner="worker",
        execution_token="a" * 64,
        chunk_size=4,
        clock=lambda: NOW,
    )
    statements: list[str] = []
    original = get_connection

    @contextmanager
    def traced(path, *, write=False):
        with original(path, write=write) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    monkeypatch.setattr(
        "app.services.buyer_similarity_scoring_service.get_connection", traced
    )
    assert has_current_similarity_attestation(
        database, result["similarity_generation_id"], project_root=tmp_path
    )
    assert not any("calibrat" in statement.lower() for statement in statements)
