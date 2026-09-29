from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPk


class Customer(Base, UUIDPk, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_org_name", "organization_id", "name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    segment: Mapped[Optional[str]] = mapped_column(String(60))
    region: Mapped[Optional[str]] = mapped_column(String(80))
    employee_count: Mapped[Optional[int]]
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )
    deals: Mapped[list["Deal"]] = relationship(  # noqa: F821
        back_populates="customer", lazy="noload"
    )


class Contact(Base, UUIDPk, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_org", "organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(160))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    is_decision_maker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_procurement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    influence: Mapped[Optional[str]] = mapped_column(String(30))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Competitor(Base, UUIDPk, TimestampMixin):
    __tablename__ = "competitors"
    __table_args__ = (Index("ix_competitors_org_name", "organization_id", "name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(80))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Competitor) and other.name.lower() == self.name.lower()

    def __hash__(self) -> int:
        return hash(self.name.lower())


class Objection(Base, UUIDPk, TimestampMixin):
    __tablename__ = "objections"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Objection) and other.label.lower() == self.label.lower()

    def __hash__(self) -> int:
        return hash(self.label.lower())
