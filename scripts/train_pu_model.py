#!/usr/bin/env python3
"""Train and persist one governed Phase 3 positive-unlabeled model."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logging_config import configure_logging  # noqa: E402
from app.services.model_training_service import (  # noqa: E402
    ModelTrainingExecutionError,
    ModelTrainingServiceError,
    train_and_persist_model,
)


logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train, evaluate, persist, and reload-verify one governed Phase 3 PU model."
        )
    )
    parser.add_argument(
        "--analysis-run-id",
        type=int,
        required=True,
        help="Completed Phase 2 historical analysis run ID.",
    )
    parser.add_argument(
        "--model-name",
        help="Optional display name for the model run.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Deterministic split and estimator seed (default: 42).",
    )
    parser.add_argument(
        "--validation-fraction",
        type=float,
        default=0.20,
        help="Validation fraction strictly between 0 and 1 (default: 0.20).",
    )
    parser.add_argument(
        "--run-challenger",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the bounded Bagging PU challenger (default: enabled).",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help="SQLite database path (defaults to DATABASE_PATH).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one machine-readable bounded JSON object.",
    )
    return parser.parse_args(argv)


def _format_summary(summary: dict[str, object]) -> str:
    return "\n".join(
        (
            f"Model run: {summary['model_run_id']}",
            f"Analysis run: {summary['analysis_run_id']}",
            f"Status: {summary['status']}",
            f"Selected candidate: {summary['selected_candidate']}",
            f"Customers: {summary['selected_customer_count']}",
            f"Known positives: {summary['positive_customer_count']}",
            f"Unlabeled: {summary['unlabeled_customer_count']}",
            (
                "Validation lift@10%: "
                f"{float(summary['validation_lift_at_10_percent']):.6f}"
            ),
            f"Artifact: {summary['artifact_path']}",
            f"SHA-256: {summary['artifact_sha256']}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    try:
        summary = train_and_persist_model(
            args.database_path,
            args.analysis_run_id,
            model_name=args.model_name,
            random_seed=args.random_seed,
            validation_fraction=args.validation_fraction,
            run_challenger=args.run_challenger,
        )
    except ModelTrainingServiceError as exc:
        failure: dict[str, object] = {
            "status": "FAILED",
            "error": str(exc),
        }
        if isinstance(exc, ModelTrainingExecutionError):
            failure["model_run_id"] = exc.model_run_id
        if args.json:
            print(json.dumps(failure, allow_nan=False, sort_keys=True))
        else:
            print(f"Status: FAILED\nError: {exc}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Unexpected PU model CLI failure")
        failure = {
            "status": "FAILED",
            "error": "The PU model command could not be completed.",
        }
        if args.json:
            print(json.dumps(failure, allow_nan=False, sort_keys=True))
        else:
            print(
                "Status: FAILED\nError: The PU model command could not be completed.",
                file=sys.stderr,
            )
        return 1

    if args.json:
        print(json.dumps(summary, allow_nan=False, sort_keys=True))
    else:
        print(_format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
