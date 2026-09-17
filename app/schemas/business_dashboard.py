"""Business-safe Phase 11 Home dashboard response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessOverviewResponse(BaseModel):
    """Bounded aggregate counts shown on the business Home screen."""

    model_config = ConfigDict(extra="forbid")

    potential_customers_available: int = Field(ge=0)
    search_runs: int = Field(ge=0)
    completed_results: int = Field(ge=0)
    latest_result_count: int | None = Field(default=None, ge=0)


class BusinessRecentResult(BaseModel):
    """Minimal business projection for the bounded Home result list."""

    model_config = ConfigDict(extra="forbid")

    search_run_id: int = Field(gt=0)
    campaign_name: str
    created_at: str
    completed_at: str | None
    status: Literal["QUEUED", "PROCESSING", "COMPLETED", "BLOCKED", "FAILED"]
    selected_count: int | None = Field(default=None, ge=0)
    delivery_profile_label: str
    safe_message: str
