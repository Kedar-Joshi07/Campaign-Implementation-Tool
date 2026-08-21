"""Customer-grain source reconstruction for Phase 3 model training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.database.connection import get_connection
from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    RAW_TRAINING_COLUMNS,
)
from app.repositories.historical_repository import build_matching_observations_cte


@dataclass(frozen=True)
class ReconstructedTrainingRows:
    """Permitted raw customer rows plus their matching observation count."""

    frame: pd.DataFrame
    observation_count: int


class ModelTrainingRepository:
    """Reconstruct one bounded customer-grain frame from Phase 2 semantics."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def reconstruct_customer_rows(
        self,
        *,
        filters: dict[str, Any],
        reference_date: str,
    ) -> ReconstructedTrainingRows:
        cte, parameters = build_matching_observations_cte(filters)
        query = f"""
            {cte},
            analysis_reference AS (
                SELECT DATE(?) AS reference_date
            )
            SELECT
                labels.customer_id,
                labels.is_positive AS pu_label,
                CASE
                    WHEN DATE(customers.date_of_birth) IS NULL THEN NULL
                    ELSE
                        CAST(STRFTIME('%Y', reference.reference_date) AS INTEGER)
                        - CAST(SUBSTR(customers.date_of_birth, 1, 4) AS INTEGER)
                        - CASE
                            WHEN STRFTIME('%m-%d', reference.reference_date)
                                 < SUBSTR(customers.date_of_birth, 6, 5) THEN 1
                            ELSE 0
                          END
                END AS age,
                customers.gender,
                customers.state,
                customers.individual_yearly_income,
                customers.marital_status,
                customers.education,
                customers.employment_status,
                customers.resident_status,
                customers.resident_type,
                customers.family_member_count,
                customers.type_of_employment,
                labels.matching_observation_count AS _matching_observation_count
            FROM customer_labels AS labels
            JOIN customers ON customers.customer_id = labels.customer_id
            CROSS JOIN analysis_reference AS reference
            ORDER BY labels.customer_id
        """

        with get_connection(self.database_path) as connection:
            frame = pd.read_sql_query(
                query,
                connection,
                params=(*parameters, reference_date),
            )

        observation_count = int(frame.pop("_matching_observation_count").sum())
        frame = frame.loc[:, RAW_TRAINING_COLUMNS]
        frame["customer_id"] = frame["customer_id"].astype("string")
        frame["pu_label"] = frame["pu_label"].astype("Int8")
        frame["age"] = frame["age"].astype("Int64")
        frame["individual_yearly_income"] = frame[
            "individual_yearly_income"
        ].astype("Float64")
        frame["family_member_count"] = frame["family_member_count"].astype("Int64")
        for column in CATEGORICAL_FEATURES:
            frame[column] = frame[column].astype("string")

        return ReconstructedTrainingRows(
            frame=frame,
            observation_count=observation_count,
        )
