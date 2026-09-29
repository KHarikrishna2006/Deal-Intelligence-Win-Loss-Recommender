from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class KPIS(BaseModel):
    active_deals: int
    pipeline_value: Decimal
    won_deals: int
    lost_deals: int
    win_rate: Optional[float]
    average_deal_size: Optional[Decimal]
    average_sales_cycle_days: Optional[int]
    closed_total: int


class ChartPoint(BaseModel):
    label: str
    value: float
    secondary: Optional[float] = None


class WinLossOut(BaseModel):
    kpis: KPIS
    win_loss_distribution: list[ChartPoint]
    pipeline_by_stage: list[ChartPoint]
    common_objections: list[ChartPoint]
    common_competitors: list[ChartPoint]
    loss_reasons: list[ChartPoint]
    win_reasons: list[ChartPoint]
    stage_failure_rates: list[ChartPoint]
    competitor_outcomes: list[dict[str, Any]]
    pricing_related_losses: int
    competitor_related_losses: int
    recurring_requirements: list[ChartPoint]
    sufficient_data: bool
    data_quality: dict[str, Any]
    insufficient_reason: Optional[str] = None


class DashboardOut(BaseModel):
    kpis: KPIS
    pipeline_by_stage: list[ChartPoint]
    win_loss: list[ChartPoint]
    loss_reasons: list[ChartPoint]
    competitor_outcomes: list[ChartPoint]
    objections: list[ChartPoint]
    deal_trend: list[ChartPoint]
    recent_activity: list[dict[str, Any]]
    top_competitors: list[ChartPoint]
    top_objections: list[ChartPoint]


class MemoryReferenceOut(ORMModel):
    id: uuid.UUID
    deal_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    interaction_id: Optional[uuid.UUID] = None
    bank_id: str
    external_id: Optional[str] = None
    kind: str
    content: str
    context: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    occurred_at: Optional[datetime] = None
    sync_status: str
    sync_error: Optional[str] = None
    created_at: datetime


class TimelineItem(BaseModel):
    source: str
    occurred_at: datetime
    title: str
    detail: Optional[str] = None
    kind: str
    reference_id: Optional[uuid.UUID] = None
    meta: dict[str, Any] = {}


class MemoryStatusOut(BaseModel):
    available: bool
    configured_url: str
    enabled: bool
    bank_id: Optional[str] = None
    version: Optional[str] = None
    reason: Optional[str] = None
    code: Optional[str] = None
    local_reference_count: int = 0


class SearchHit(BaseModel):
    entity_type: str
    id: str
    title: str
    subtitle: Optional[str] = None
    score: float = 0.0
    extra: dict[str, Any] = {}


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
    counts: dict[str, int]
    total: int
