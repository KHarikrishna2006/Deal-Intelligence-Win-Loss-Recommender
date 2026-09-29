from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DealStage


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    strength: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = None


class CompetitorOut(ORMModel):
    id: uuid.UUID
    name: str
    strength: Optional[str] = None
    notes: Optional[str] = None


class ObjectionIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    status: str = "OPEN"
    resolution: Optional[str] = None


class ObjectionOut(ORMModel):
    id: uuid.UUID
    label: str
    category: Optional[str] = None
    status: str
    resolution: Optional[str] = None
    raised_at: Optional[datetime] = None


class DealCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    customer_id: uuid.UUID
    owner_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="USD", max_length=8)
    stage: DealStage = DealStage.LEAD
    probability: int = Field(default=10, ge=0, le=100)
    expected_close_date: Optional[date] = None
    next_action: Optional[str] = None
    competitors: list[CompetitorIn] = []
    objections: list[ObjectionIn] = []


class DealUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    amount: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    stage: Optional[DealStage] = None
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    expected_close_date: Optional[date] = None
    owner_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    next_action: Optional[str] = None
    status: Optional[str] = None


class DealOutcomeIn(BaseModel):
    outcome: str = Field(pattern="^(WON|LOST)$")
    reason: Optional[str] = Field(default=None, max_length=2000)
    closed_at: Optional[datetime] = None


class DealOut(ORMModel):
    id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    owner_id: uuid.UUID
    amount: Decimal
    currency: str
    stage: str
    probability: int
    status: str
    outcome: Optional[str] = None
    win_reason: Optional[str] = None
    loss_reason: Optional[str] = None
    expected_close_date: Optional[date] = None
    last_activity_at: Optional[datetime] = None
    next_action: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_demo: bool


class DealSummaryOut(DealOut):
    customer_name: str = ""
    owner_name: str = ""
    competitor_names: list[str] = []
    objection_labels: list[str] = []
    interaction_count: int = 0


class DealDetailOut(DealSummaryOut):
    description: Optional[str] = None
    customer: Any = None
    owner: Any = None
    competitors: list[CompetitorOut] = []
    objections: list[ObjectionOut] = []
    contacts: list[Any] = []


class StageStat(BaseModel):
    stage: str
    count: int
    total_amount: Decimal


class PipelineOut(BaseModel):
    stages: list[StageStat]
    total_open_amount: Decimal
    open_count: int
