from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EvidenceItem(BaseModel):
    deal_id: Optional[uuid.UUID] = None
    deal_name: str
    customer_name: Optional[str] = None
    outcome: Optional[str] = None
    stage: Optional[str] = None
    amount: Optional[Decimal] = None
    why: str
    source: str = "database"


class RiskItem(BaseModel):
    key: str
    title: str
    why_it_matters: str
    evidence: str
    suggested_investigation: str
    level: str = "MEDIUM"


class RecommendationOut(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    kind: str
    title: str
    rationale: str
    summary: Optional[str] = None
    actions: Optional[list[dict[str, Any]]] = None
    evidence: Optional[list[dict[str, Any]]] = None
    unknowns: Optional[list[str]] = None
    risks: Optional[list[dict[str, Any]]] = None
    similar_patterns: Optional[list[str]] = None
    evidence_level: str
    risk_level: Optional[str] = None
    source: str
    model: Optional[str] = None
    status: str
    created_at: datetime


class RecommendationCreateOut(BaseModel):
    recommendation: RecommendationOut
    similar_deals: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    memory_hits: list[dict[str, Any]] = []
    memory_status: dict[str, Any] = {}
    llm_status: dict[str, Any] = {}
    method: str
    warnings: list[str] = []


class FeedbackIn(BaseModel):
    feedback: str = Field(pattern="^(USEFUL|NOT_USEFUL|ACTED_ON|IGNORED)$")
    comment: Optional[str] = Field(default=None, max_length=2000)


class FeedbackOut(ORMModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    feedback: str
    comment: Optional[str] = None
    created_at: datetime


class AnalyzeRequest(BaseModel):
    regenerate: bool = False
    include_memory: bool = True


class CopilotIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    include_history: bool = True


class CopilotOut(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    available: bool = True
    unavailable_reason: Optional[str] = None
    model: Optional[str] = None
    memory_status: dict[str, Any] = {}
