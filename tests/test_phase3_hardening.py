from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRAINING_BOUNDARY_FILES = (
    REPOSITORY_ROOT / "app" / "repositories" / "model_training_repository.py",
    REPOSITORY_ROOT / "app" / "repositories" / "model_run_repository.py",
    REPOSITORY_ROOT / "app" / "services" / "training_cohort_service.py",
    REPOSITORY_ROOT / "app" / "services" / "model_training_service.py",
    *(REPOSITORY_ROOT / "app" / "ml").glob("*.py"),
)


def test_phase3_training_boundary_contains_no_later_phase_scoring_or_prospect_query() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in TRAINING_BOUNDARY_FILES)
    lowered = source.casefold()

    assert "from demographics" not in lowered
    assert "join demographics" not in lowered
    assert "propensity_scores" not in lowered
    assert "person_id" not in lowered
    assert "audience explorer" not in lowered
    assert "campaign export" not in lowered


def test_no_model_training_http_surface_and_later_navigation_remains_disabled() -> None:
    router_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / "app" / "routers").glob("*.py")
    ).casefold()
    html = (REPOSITORY_ROOT / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "train_pu_model" not in router_source
    assert "/api/models" not in router_source
    assert html.count('class="navigation-item is-disabled"') == 3
    assert '<span>Model Training</span><small>Later phase</small>' in html
    assert '<span>Audience Explorer</span><small>Later phase</small>' in html
    assert '<span>Campaigns</span><small>Later phase</small>' in html


def test_phase3_documentation_records_contract_cli_caveat_and_phase4_boundary() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    summary = (
        REPOSITORY_ROOT / "docs" / "PHASE_3_IMPLEMENTATION_SUMMARY.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Schema version 3",
        "scripts\\train_pu_model.py",
        "unlabeled, not a confirmed negative",
        "observed-label diagnostics",
        "artifacts/models/model_run_000001/pu_model.joblib",
        "Phase 4 handoff",
    ):
        assert required in readme
    assert "52396010f945b0328b84453ce25c587b11ed7fd7" in summary
    assert "a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535" in summary
    assert "OBSERVED_LABEL_METRICS_ONLY" in summary
    assert "No customer ID values were persisted" in summary
    assert "Go for Phase 4" in summary


def test_prohibited_ml_infrastructure_dependencies_are_absent() -> None:
    requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
        encoding="utf-8"
    ).casefold()
    for prohibited in (
        "tensorflow",
        "torch",
        "xgboost",
        "lightgbm",
        "mlflow",
        "airflow",
        "celery",
        "redis",
        "kafka",
        "spark",
    ):
        assert prohibited not in requirements
