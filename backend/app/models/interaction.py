from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSON, Base, TimestampMixin, UUIDPk, utcnow


class Interaction(Base, UUIDPk, TimestampMixin):
    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_org_occurred", "organization_id", "occurred_at"),
        Index("ix_interactions_deal_occurred", "deal_id", "occurred_at"),
        Index("ix_interactions_type", "organization_id", "interaction_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )

    interaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    channel: Mapped[Optional[str]] = mapped_column(String(60))
    direction: Mapped[Optional[str]] = mapped_column(String(20))
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    sentiment: Mapped[Optional[str]] = mapped_column(String(20))
    price_discussed: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    commitments: Mapped[Optional[list[str]]] = mapped_column(JSON)
    requirements: Mapped[Optional[list[str]]] = mapped_column(JSON)
    entities: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    extracted: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")
    external_id: Mapped[Optional[str]] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow, index=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    deal: Mapped["Deal"] = relationship(back_populates="interactions")  # noqa: F821
    participants: Mapped[list["InteractionParticipant"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan", lazy="selectin"
    )


class InteractionParticipant(Base, UUIDPk, TimestampMixin):
    __tablename__ = "interaction_participants"

    interaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interactions.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(40))
    side: Mapped[Optional[str]] = mapped_column(String(20))

    interaction: Mapped[Interaction] = relationship(back_populates="participants")
