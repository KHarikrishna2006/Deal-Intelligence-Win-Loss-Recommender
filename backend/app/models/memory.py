from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSON, Base, TimestampMixin, UUIDPk, utcnow
from app.models.enums import MemoryKind


class MemoryReference(Base, UUIDPk, TimestampMixin):
    """Local index of a memory stored in Hindsight.

    PostgreSQL stays the source of truth for structured records; this table only
    stores the pointers and metadata needed to inspect, list and re-fetch what
    Hindsight is holding for a deal.
    """

    __tablename__ = "memory_references"
    __table_args__ = (
        Index("ix_memory_ref_org_created", "organization_id", "created_at"),
        Index("ix_memory_ref_deal", "deal_id"),
        Index("ix_memory_ref_external", "external_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    bank_id: Mapped[str] = mapped_column(String(160), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(120))
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE")
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    interaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interactions.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default=MemoryKind.INTERACTION.value)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context: Mapped[Optional[str]] = mapped_column(String(300))
    # `metadata` is reserved by the declarative API, hence the `meta` attribute
    # name mapped onto a `metadata` column.
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default="SYNCED")
    sync_error: Mapped[Optional[str]] = mapped_column(String(400))

    deal: Mapped["Optional[Deal]"] = relationship(back_populates="memory_references")  # noqa: F821
    interaction: Mapped["Optional[Interaction]"] = relationship()  # noqa: F821


class AuditLog(Base, UUIDPk, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(80))
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(60))
    request_id: Mapped[Optional[str]] = mapped_column(String(60))
