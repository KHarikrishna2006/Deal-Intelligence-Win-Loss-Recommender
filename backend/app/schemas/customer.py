from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ContactIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    title: Optional[str] = Field(default=None, max_length=160)
    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=50)
    is_decision_maker: bool = False
    is_procurement: bool = False
    influence: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = None


class ContactOut(ORMModel):
    id: uuid.UUID
    full_name: str
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_decision_maker: bool
    is_procurement: bool
    influence: Optional[str] = None
    notes: Optional[str] = None


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: Optional[str] = Field(default=None, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=120)
    segment: Optional[str] = Field(default=None, max_length=60)
    region: Optional[str] = Field(default=None, max_length=80)
    employee_count: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    contacts: list[ContactIn] = []


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    domain: Optional[str] = None
    industry: Optional[str] = None
    segment: Optional[str] = None
    region: Optional[str] = None
    employee_count: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


class CustomerOut(ORMModel):
    id: uuid.UUID
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    segment: Optional[str] = None
    region: Optional[str] = None
    employee_count: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    is_demo: bool


class CustomerDetailOut(CustomerOut):
    contacts: list[ContactOut] = []
    active_deals: list[dict] = []
    past_deals: list[dict] = []
    interaction_count: int = 0
    objections: list[dict] = []
    competitors: list[dict] = []
    pricing_history: list[dict] = []
    recommendations: list[dict] = []
    memory_timeline: list[dict] = []
