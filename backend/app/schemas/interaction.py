from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InteractionType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ParticipantIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: Optional[str] = Field(default=None, max_length=40)
    side: Optional[str] = Field(default=None, max_length=20)
    contact_id: Optional[uuid.UUID] = None


class InteractionCreate(BaseModel):
    interaction_type: InteractionType = InteractionType.NOTE
    title: str = Field(default="", max_length=240)
    body: str = Field(min_length=1, max_length=40000)
    channel: Optional[str] = Field(default=None, max_length=60)
    direction: Optional[str] = Field(default=None, max_length=20)
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    price_discussed: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    occurred_at: Optional[datetime] = None
    participants: list[ParticipantIn] = []
    requirements: list[str] = []
    commitments: list[str] = []


class InteractionOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    interaction_type: str
    title: str
    body: str
    channel: Optional[str] = None
    direction: Optional[str] = None
    duration_minutes: Optional[int] = None
    sentiment: Optional[str] = None
    price_discussed: Optional[Decimal] = None
    currency: Optional[str] = None
    commitments: Optional[list[str]] = None
    requirements: Optional[list[str]] = None
    extracted: Optional[dict[str, Any]] = None
    occurred_at: datetime
    created_at: datetime
    is_demo: bool


class ParticipantOut(ORMModel):
    id: uuid.UUID
    name: str
    role: Optional[str] = None
    side: Optional[str] = None


class InteractionDetailOut(InteractionOut):
    participants: list[ParticipantOut] = []
    author_name: Optional[str] = None
