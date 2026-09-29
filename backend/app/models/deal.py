from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSON, Base, TimestampMixin, UUIDPk, utcnow
from app.models.enums import DealStage


class DealStageCatalog(Base, UUIDPk, TimestampMixin):
    """Reference table describing the pipeline stages an organization uses."""

    __tablename__ = "deal_stages"
    __table_args__ = (UniqueConstraint("key", name="uq_deal_stages_key"),)

    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)


class Deal(Base, UUIDPk, TimestampMixin):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_org_stage", "organization_id", "stage"),
        Index("ix_deals_org_owner", "organization_id", "owner_id"),
        Index("ix_deals_org_close_date", "organization_id", "expected_close_date"),
        Index("ix_deals_org_outcome", "organization_id", "outcome"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default=DealStage.LEAD.value)
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    win_reason: Mapped[Optional[str]] = mapped_column(Text)
    loss_reason: Mapped[Optional[str]] = mapped_column(Text)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    next_action: Mapped[Optional[str]] = mapped_column(Text)
    source_notes: Mapped[Optional[str]] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer: Mapped["Customer"] = relationship(lazy="joined", back_populates="deals")  # noqa: F821
    owner: Mapped["User"] = relationship(lazy="joined")  # noqa: F821

    interactions: Mapped[list["Interaction"]] = relationship(  # noqa: F821
        back_populates="deal",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Interaction.occurred_at",
    )
    deal_events: Mapped[list[DealEvent]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", lazy="noload"
    )
    deal_competitors: Mapped[list[DealCompetitor]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", lazy="selectin"
    )
    deal_objections: Mapped[list[DealObjection]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", lazy="selectin"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(  # noqa: F821
        back_populates="deal", cascade="all, delete-orphan", lazy="noload"
    )
    memory_references: Mapped[list["MemoryReference"]] = relationship(  # noqa: F821
        back_populates="deal", cascade="all, delete-orphan", lazy="selectin"
    )


class DealCompetitor(Base, UUIDPk, TimestampMixin):
    __tablename__ = "deal_competitors"
    __table_args__ = (UniqueConstraint("deal_id", "competitor_id", name="uq_deal_competitor"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False
    )
    strength: Mapped[Optional[str]] = mapped_column(String(30))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    deal: Mapped[Deal] = relationship(back_populates="deal_competitors")
    competitor: Mapped["Competitor"] = relationship(lazy="joined")  # noqa: F821


class DealObjection(Base, UUIDPk, TimestampMixin):
    __tablename__ = "deal_objections"
    __table_args__ = (UniqueConstraint("deal_id", "objection_id", name="uq_deal_objection"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    objection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("objections.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    raised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    resolution: Mapped[Optional[str]] = mapped_column(Text)

    deal: Mapped[Deal] = relationship(back_populates="deal_objections")
    objection: Mapped["Objection"] = relationship(lazy="joined")  # noqa: F821


class DealEvent(Base, UUIDPk, TimestampMixin):
    __tablename__ = "deal_events"
    __table_args__ = (Index("ix_deal_events_deal_created", "deal_id", "created_at"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow
    )

    deal: Mapped[Deal] = relationship(back_populates="deal_events")
