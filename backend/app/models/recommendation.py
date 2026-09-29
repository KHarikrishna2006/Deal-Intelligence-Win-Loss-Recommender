from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSON, Base, TimestampMixin, UUIDPk, utcnow
from app.models.enums import (
    EvidenceLevel,
    FeedbackType,
    RecommendationKind,
    RecommendationSource,
    RiskLevel,
)


class Recommendation(Base, UUIDPk, TimestampMixin):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_deal_created", "deal_id", "created_at"),
        Index("ix_recommendations_org_kind", "organization_id", "kind"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default=RecommendationKind.NEXT_ACTION.value)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    evidence: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    unknowns: Mapped[Optional[list[str]]] = mapped_column(JSON)
    risks: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    similar_patterns: Mapped[Optional[list[str]]] = mapped_column(JSON)
    evidence_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EvidenceLevel.LIMITED_EVIDENCE.value
    )
    risk_level: Mapped[Optional[str]] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=RecommendationSource.DETERMINISTIC.value
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    summary: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    is_stale: Mapped[bool] = mapped_column(default=False, nullable=False)

    deal: Mapped["Deal"] = relationship(back_populates="recommendations")  # noqa: F821
    feedback: Mapped[list["RecommendationFeedback"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan", lazy="selectin"
    )


class RecommendationFeedback(Base, UUIDPk, TimestampMixin):
    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "user_id", name="uq_feedback_rec_user"),
    )

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feedback: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)

    recommendation: Mapped[Recommendation] = relationship(back_populates="feedback")


class CopilotMessage(Base, UUIDPk, TimestampMixin):
    __tablename__ = "copilot_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    tool_trace: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    unavailable_reason: Mapped[Optional[str]] = mapped_column(String(200))
    created_at_model: Mapped[Optional[str]] = mapped_column(String(120))
