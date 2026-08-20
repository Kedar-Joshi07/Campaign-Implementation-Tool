"""Pydantic response models for bounded reference summaries."""

from __future__ import annotations

from pydantic import BaseModel


class StateReferenceResponse(BaseModel):
    state_name: str
    state_code: str | None
    person_count: int


class CampaignReferenceResponse(BaseModel):
    campaign_id: str
    campaign_name: str | None
    campaign_type: str | None
    campaign_channel: str | None
    campaign_start_date: str
    campaign_end_date: str
    observation_count: int
    positive_count: int


class ProductReferenceResponse(BaseModel):
    product_id: str
    product_name: str | None
    product_category: str | None
    product_subcategory: str | None
    product_tier: str | None
    observation_count: int
    purchase_count: int
