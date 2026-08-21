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


def test_phase4_api_surface_excludes_scoring_and_later_navigation_remains_disabled() -> None:
    router_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / "app" / "routers").glob("*.py")
    ).casefold()
    html = (REPOSITORY_ROOT / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "prefix=\"/api\"" in router_source
    assert "\"/models/train\"" in router_source
    assert "\"/models\"" in router_source
    assert "/api/models/{model_run_id}/score" not in router_source
    assert "/api/models/{id}/score" not in router_source
    assert html.count('class="navigation-item is-disabled"') == 2
    assert 'data-view-target="model-training"' in html
    assert '<span class="nav-icon" aria-hidden="true">04</span><span>Model Training</span><small>Phase 4</small>' in html
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


def test_phase3_algorithm_role_policy_v2_is_explicit_and_scope_stays_bounded() -> None:
    roles = (REPOSITORY_ROOT / "app" / "ml" / "model_roles.py").read_text(
        encoding="utf-8"
    )
    training = (REPOSITORY_ROOT / "app" / "ml" / "training.py").read_text(
        encoding="utf-8"
    )
    evaluation = (REPOSITORY_ROOT / "app" / "ml" / "evaluation.py").read_text(
        encoding="utf-8"
    )
    cli = (REPOSITORY_ROOT / "scripts" / "train_pu_model.py").read_text(
        encoding="utf-8"
    )

    assert 'MODEL_ROLE_POLICY_VERSION = "2"' in roles
    assert "PRIMARY_MODEL_NAME = BAGGING_PU_NAME" in roles
    assert "CHALLENGER_1_MODEL_NAME = ELKAN_NOTO_NAME" in roles
    assert "DIAGNOSTIC_CONTROL_NAME = NAIVE_BASELINE_NAME" in roles
    assert 'EVALUATION_CONTRACT_VERSION = "2"' in evaluation
    assert "SKIPPED_RUNTIME" not in training
    assert "run_elkan_challenger" in training
    assert "--run-elkan-challenger" in cli
    assert "--run-challenger" not in cli


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


def test_phase5_scope_scan_confirms_later_phase_scoring_and_activation_absent() -> None:
    app_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in REPOSITORY_ROOT.joinpath("app").rglob("*.py")
    ).casefold()
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in REPOSITORY_ROOT.joinpath("frontend", "js").glob("*.js")
    ).casefold()
    html = (REPOSITORY_ROOT / "frontend" / "index.html").read_text(
        encoding="utf-8"
    ).casefold()

    for forbidden in (
        "propensity_scores",
        "/api/audience",
        "/api/campaigns/export",
        "audience persistence",
        "activation adapter",
        "score band",
        "percentile band",
        "csv export",
        "demographic scoring",
        "/api/models/{model_run_id}/score",
        "/api/models/{id}/score",
    ):
        assert forbidden not in app_source
        assert forbidden not in frontend_source

    assert 'data-view="audience-explorer"' not in html
    assert 'data-view-target="audience-explorer"' not in html
    assert 'data-view="campaigns"' not in html
    assert 'data-view-target="campaigns"' not in html
