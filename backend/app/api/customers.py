from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models import Contact, Customer, Deal, Interaction, Recommendation
from app.models.enums import DealStatus
from app.repositories.deal_repository import DealRepository
from app.schemas.customer import (
    ContactIn,
    ContactOut,
    CustomerCreate,
    CustomerDetailOut,
    CustomerOut,
    CustomerUpdate,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/customers", tags=["customers"])


def _get_customer(db, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise NotFoundError("Customer not found.")
    return customer


@router.get("", response_model=dict)
def list_customers(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(Customer).where(Customer.organization_id == organization.id)
    count = select(func.count(Customer.id)).where(Customer.organization_id == organization.id)
    if search:
        like = f"%{search.lower()}%"
        condition = or_(
            func.lower(Customer.name).like(like),
            func.lower(func.coalesce(Customer.industry, "")).like(like),
        )
        stmt = stmt.where(condition)
        count = count.where(condition)
    rows = list(db.execute(stmt.order_by(Customer.name).limit(limit).offset(offset)).scalars())
    total = int(db.execute(count).scalar_one() or 0)
    return {
        "items": [CustomerOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    customer = Customer(
        organization_id=organization.id,
        name=payload.name,
        domain=payload.domain,
        industry=payload.industry,
        segment=payload.segment,
        region=payload.region,
        employee_count=payload.employee_count,
        notes=payload.notes,
    )
    db.add(customer)
    db.flush()
    for contact in payload.contacts:
        db.add(
            Contact(
                organization_id=organization.id,
                customer_id=customer.id,
                **contact.model_dump(),
            )
        )
    db.flush()
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}", response_model=dict)
def customer_detail(
    customer_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    customer = _get_customer(db, organization.id, customer_id)
    repo = DealRepository(db)

    deals = list(
        db.execute(
            repo.base().where(
                Deal.organization_id == organization.id,
                Deal.customer_id == customer.id,
            )
        )
        .unique()
        .scalars()
    )
    active = [d for d in deals if d.status == DealStatus.OPEN.value and d.outcome is None]
    past = [d for d in deals if d.outcome is not None or d.status != DealStatus.OPEN.value]

    interactions = list(
        db.execute(
            select(Interaction)
            .where(Interaction.customer_id == customer.id)
            .order_by(Interaction.occurred_at.desc())
            .limit(200)
        ).scalars()
    )

    objections: dict[str, dict[str, Any]] = {}
    competitors: dict[str, dict[str, Any]] = {}
    for deal in deals:
        for do in deal.deal_objections:
            bucket = objections.setdefault(
                do.objection.label, {"label": do.objection.label, "total": 0, "open": 0}
            )
            bucket["total"] += 1
            if (do.status or "OPEN").upper() == "OPEN":
                bucket["open"] += 1
        for dc in deal.deal_competitors:
            bucket = competitors.setdefault(
                dc.competitor.name, {"name": dc.competitor.name, "total": 0}
            )
            bucket["total"] += 1

    pricing_history = [
        {
            "interaction_id": str(i.id),
            "occurred_at": i.occurred_at.isoformat(),
            "amount": float(i.price_discussed) if i.price_discussed else None,
            "currency": i.currency,
            "type": i.interaction_type,
        }
        for i in interactions
        if i.price_discussed is not None
    ]

    recommendations = list(
        db.execute(
            select(Recommendation)
            .join(Deal, Deal.id == Recommendation.deal_id)
            .where(
                Recommendation.organization_id == organization.id,
                Deal.customer_id == customer.id,
            )
            .order_by(Recommendation.created_at.desc())
            .limit(10)
        ).scalars()
    )

    memory_service = MemoryService(db)
    timeline: list[dict[str, Any]] = []
    for deal in deals[:10]:
        timeline.extend(memory_service.deal_timeline(deal.id, limit=60))
    timeline.sort(key=lambda item: item["occurred_at"] or datetime.min)

    detail = CustomerDetailOut.model_validate(customer).model_dump()
    detail["contacts"] = [
        ContactOut.model_validate(c).model_dump(mode="json") for c in customer.contacts
    ]
    detail["active_deals"] = [
        {
            "id": str(d.id),
            "name": d.name,
            "stage": d.stage,
            "amount": float(d.amount or 0),
            "currency": d.currency,
        }
        for d in active
    ]
    detail["past_deals"] = [
        {
            "id": str(d.id),
            "name": d.name,
            "stage": d.stage,
            "amount": float(d.amount or 0),
            "currency": d.currency,
            "outcome": d.outcome,
            "loss_reason": d.loss_reason,
            "win_reason": d.win_reason,
        }
        for d in past
    ]
    detail["interaction_count"] = len(interactions)
    detail["objections"] = list(objections.values())
    detail["competitors"] = list(competitors.values())
    detail["pricing_history"] = pricing_history
    detail["recommendations"] = [
        {
            "id": str(r.id),
            "deal_id": str(r.deal_id),
            "title": r.title,
            "evidence_level": r.evidence_level,
            "created_at": r.created_at.isoformat(),
        }
        for r in recommendations
    ]
    detail["memory_timeline"] = timeline[:80]
    return detail


@router.post("/{customer_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(
    customer_id: uuid.UUID,
    payload: ContactIn,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    customer = _get_customer(db, organization.id, customer_id)
    contact = Contact(
        organization_id=organization.id, customer_id=customer.id, **payload.model_dump()
    )
    db.add(contact)
    db.flush()
    return ContactOut.model_validate(contact)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    customer = _get_customer(db, organization.id, customer_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.flush()
    return CustomerOut.model_validate(customer)
