from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import Action, can_edit_deal, ensure_role
from app.models import (
    Competitor,
    Contact,
    Customer,
    Deal,
    DealCompetitor,
    DealObjection,
    Objection,
    Organization,
    User,
)
from app.models.enums import DealEventType, DealStatus, MemoryKind
from app.repositories.deal_repository import DealRepository
from app.schemas.deal import DealCreate, DealOutcomeIn, DealUpdate
from app.services.memory_service import MemoryService


class DealService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = DealRepository(session)
        self.memory = MemoryService(session)

    # --------------------------------------------------------------- reads
    def get(self, organization_id: uuid.UUID, deal_id: uuid.UUID) -> Deal:
        deal = self.repository.get(organization_id, deal_id)
        if deal is None:
            raise NotFoundError("Deal not found.")
        return deal

    def list(self, organization_id: uuid.UUID, **filters: Any):
        return self.repository.list(organization_id, **filters)

    def serialize_summary(self, deal: Deal) -> dict[str, Any]:
        return {
            "id": deal.id,
            "name": deal.name,
            "customer_id": deal.customer_id,
            "owner_id": deal.owner_id,
            "amount": deal.amount,
            "currency": deal.currency,
            "stage": deal.stage,
            "probability": deal.probability,
            "status": deal.status,
            "outcome": deal.outcome,
            "win_reason": deal.win_reason,
            "loss_reason": deal.loss_reason,
            "expected_close_date": deal.expected_close_date,
            "last_activity_at": deal.last_activity_at,
            "next_action": deal.next_action,
            "created_at": deal.created_at,
            "updated_at": deal.updated_at,
            "is_demo": deal.is_demo,
            "customer_name": deal.customer.name if deal.customer else "",
            "owner_name": deal.owner.full_name if deal.owner else "",
            "competitor_names": [dc.competitor.name for dc in deal.deal_competitors],
            "objection_labels": [do.objection.label for do in deal.deal_objections],
            "interaction_count": len(deal.interactions),
        }

    def serialize_detail(self, deal: Deal) -> dict[str, Any]:
        payload = self.serialize_summary(deal)
        payload.update(
            {
                "description": deal.description,
                "competitors": [
                    {
                        "id": dc.competitor.id,
                        "name": dc.competitor.name,
                        "strength": dc.strength,
                        "notes": dc.notes,
                    }
                    for dc in deal.deal_competitors
                ],
                "objections": [
                    {
                        "id": do.objection.id,
                        "label": do.objection.label,
                        "category": do.objection.category,
                        "status": do.status,
                        "resolution": do.resolution,
                        "raised_at": do.raised_at,
                    }
                    for do in deal.deal_objections
                ],
                "contacts": [
                    {
                        "id": c.id,
                        "full_name": c.full_name,
                        "title": c.title,
                        "is_decision_maker": c.is_decision_maker,
                        "is_procurement": c.is_procurement,
                        "influence": c.influence,
                    }
                    for c in (deal.customer.contacts if deal.customer else [])
                ],
            }
        )
        return payload

    # -------------------------------------------------------------- writes
    def create(
        self,
        organization_id: uuid.UUID,
        user: User,
        payload: DealCreate,
    ) -> Deal:
        ensure_role(user.role, Action.WRITE_DEAL)
        customer = self.session.get(Customer, payload.customer_id)
        if customer is None or customer.organization_id != organization_id:
            raise NotFoundError("Customer not found.")

        owner_id = payload.owner_id or user.id
        owner = self.session.get(User, owner_id)
        if owner is None or owner.organization_id != organization_id:
            raise NotFoundError("Owner user not found.")

        deal = Deal(
            organization_id=organization_id,
            customer_id=customer.id,
            owner_id=owner.id,
            name=payload.name,
            description=payload.description,
            amount=payload.amount,
            currency=payload.currency,
            stage=payload.stage.value,
            probability=payload.probability,
            expected_close_date=payload.expected_close_date,
            next_action=payload.next_action,
            status=DealStatus.OPEN.value,
        )
        self.session.add(deal)
        self.session.flush()

        self._apply_competitors(deal, payload.competitors)
        self._apply_objections(deal, payload.objections)

        self.repository.add_event(
            deal,
            event_type=DealEventType.DEAL_CREATED.value,
            title=f"Deal created: {deal.name}",
            detail=deal.description,
            actor_id=user.id,
            payload={"stage": deal.stage, "amount": str(deal.amount)},
        )
        self.memory.retain(
            organization_id,
            content=MemoryService.build_deal_context_memory(deal, customer.name),
            kind=MemoryKind.DEAL_CONTEXT.value,
            deal=deal,
            customer_id=customer.id,
            context="New deal opened",
            tags=["stage:" + deal.stage, f"deal:{deal.id}"],
        )
        self.session.flush()
        return deal

    def update(
        self,
        organization_id: uuid.UUID,
        user: User,
        deal: Deal,
        payload: DealUpdate,
    ) -> Deal:
        if not can_edit_deal(user.role, str(deal.owner_id), str(user.id)):
            raise ForbiddenError("You can only edit deals you own.")

        changes: dict[str, Any] = {}
        data = payload.model_dump(exclude_unset=True)

        if "owner_id" in data and data["owner_id"] and data["owner_id"] != deal.owner_id:
            new_owner = self.session.get(User, data["owner_id"])
            if new_owner is None or new_owner.organization_id != organization_id:
                raise NotFoundError("Owner user not found.")
        if "customer_id" in data and data["customer_id"] and data["customer_id"] != deal.customer_id:
            new_customer = self.session.get(Customer, data["customer_id"])
            if new_customer is None or new_customer.organization_id != organization_id:
                raise NotFoundError("Customer not found.")

        if "stage" in data and data["stage"] is not None:
            new_stage = data["stage"].value if hasattr(data["stage"], "value") else data["stage"]
            if new_stage != deal.stage:
                changes["stage"] = {"from": deal.stage, "to": new_stage}
                if new_stage == "CLOSED_WON":
                    data["status"] = data.get("status") or DealStatus.CLOSED.value
                if new_stage == "CLOSED_LOST":
                    data["status"] = data.get("status") or DealStatus.CLOSED.value
            data["stage"] = new_stage
            if new_stage not in ("CLOSED_WON", "CLOSED_LOST") and data.get("status") in (
                None,
                deal.status,
            ):
                data.pop("status", None)

        for field, value in data.items():
            current = getattr(deal, field)
            if current != value:
                changes[field] = {"from": str(current), "to": str(value)}
            setattr(deal, field, value)

        if changes:
            self.repository.add_event(
                deal,
                event_type=DealEventType.STAGE_CHANGED.value
                if "stage" in changes
                else DealEventType.DEAL_UPDATED.value,
                title=f"Deal updated: {', '.join(changes)}",
                detail=None,
                actor_id=user.id,
                payload=changes,
            )
            self.session.flush()
        return deal

    def record_outcome(
        self,
        organization_id: uuid.UUID,
        user: User,
        deal: Deal,
        payload: DealOutcomeIn,
    ) -> Deal:
        ensure_role(user.role, Action.RECORD_OUTCOME)
        if not can_edit_deal(user.role, str(deal.owner_id), str(user.id)):
            raise ForbiddenError("You can only record outcomes for deals you own.")
        if deal.outcome:
            raise ConflictError(
                "This deal already has a recorded outcome. Create a new deal instead."
            )

        deal.outcome = payload.outcome
        if payload.outcome == "WON":
            deal.win_reason = payload.reason
            deal.stage = "CLOSED_WON"
        else:
            deal.loss_reason = payload.reason
            deal.stage = "CLOSED_LOST"
        deal.status = DealStatus.CLOSED.value
        deal.closed_at = payload.closed_at or datetime.utcnow()
        deal.probability = 100 if payload.outcome == "WON" else 0

        self.repository.add_event(
            deal,
            event_type=DealEventType.OUTCOME_RECORDED.value,
            title=f"Deal {payload.outcome.lower()}",
            detail=payload.reason,
            actor_id=user.id,
            payload={"outcome": payload.outcome, "reason": payload.reason},
        )

        customer_name = deal.customer.name if deal.customer else ""
        self.memory.retain(
            organization_id,
            content=MemoryService.build_outcome_memory(deal, customer_name),
            kind=MemoryKind.OUTCOME.value,
            deal=deal,
            customer_id=deal.customer_id,
            context=f"Deal outcome recorded: {payload.outcome}",
            tags=["outcome:" + payload.outcome, "stage:" + deal.stage, f"deal:{deal.id}"],
            timestamp=deal.closed_at,
        )
        self.session.flush()
        return deal

    def archive(self, organization_id: uuid.UUID, user: User, deal: Deal) -> Deal:
        ensure_role(user.role, Action.DELETE_DEAL)
        deal.status = DealStatus.ARCHIVED.value
        self.repository.add_event(
            deal,
            event_type=DealEventType.DEAL_UPDATED.value,
            title="Deal archived",
            actor_id=user.id,
        )
        self.session.flush()
        return deal

    # ------------------------------------------------------------ sub-entities
    def _apply_competitors(self, deal: Deal, items: list[Any]) -> None:
        for item in items:
            existing = self.repository.find_competitor(deal.organization_id, item.name)
            if existing is None:
                existing = Competitor(organization_id=deal.organization_id, name=item.name.strip())
                self.session.add(existing)
                self.session.flush()
            if any(dc.competitor_id == existing.id for dc in deal.deal_competitors):
                continue
            self.session.add(
                DealCompetitor(
                    deal_id=deal.id,
                    competitor_id=existing.id,
                    strength=item.strength,
                    notes=item.notes,
                )
            )

    def _apply_objections(self, deal: Deal, items: list[Any]) -> None:
        for item in items:
            existing = self.repository.find_objection(deal.organization_id, item.label)
            if existing is None:
                existing = Objection(organization_id=deal.organization_id, label=item.label.strip())
                self.session.add(existing)
                self.session.flush()
            if any(do.objection_id == existing.id for do in deal.deal_objections):
                continue
            self.session.add(
                DealObjection(
                    deal_id=deal.id,
                    objection_id=existing.id,
                    status=item.status,
                    raised_at=datetime.utcnow(),
                    resolution=item.resolution,
                )
            )

    def add_competitor(
        self, deal: Deal, name: str, strength: str | None = None, notes: str | None = None
    ) -> DealCompetitor:
        competitor = self.repository.find_competitor(deal.organization_id, name)
        if competitor is None:
            competitor = Competitor(organization_id=deal.organization_id, name=name.strip())
            self.session.add(competitor)
            self.session.flush()
        existing = next(
            (dc for dc in deal.deal_competitors if dc.competitor_id == competitor.id), None
        )
        if existing:
            return existing
        row = DealCompetitor(
            deal_id=deal.id, competitor_id=competitor.id, strength=strength, notes=notes
        )
        self.session.add(row)
        self.repository.add_event(
            deal,
            event_type=DealEventType.COMPETITOR_ADDED.value,
            title=f"Competitor added: {competitor.name}",
            payload={"competitor": competitor.name},
        )
        self.session.flush()
        return row

    def add_objection(
        self, deal: Deal, label: str, status: str = "OPEN", resolution: str | None = None
    ) -> DealObjection:
        objection = self.repository.find_objection(deal.organization_id, label)
        if objection is None:
            objection = Objection(organization_id=deal.organization_id, label=label.strip())
            self.session.add(objection)
            self.session.flush()
        existing = next(
            (do for do in deal.deal_objections if do.objection_id == objection.id), None
        )
        if existing:
            return existing
        row = DealObjection(
            deal_id=deal.id,
            objection_id=objection.id,
            status=status,
            raised_at=datetime.utcnow(),
            resolution=resolution,
        )
        self.session.add(row)
        self.repository.add_event(
            deal,
            event_type=DealEventType.OBJECTION_ADDED.value,
            title=f"Objection raised: {objection.label}",
            payload={"objection": objection.label},
        )
        self.session.flush()
        return row

    def resolve_objection(self, deal: Deal, objection_id: uuid.UUID, resolution: str) -> DealObjection:
        row = next(
            (do for do in deal.deal_objections if do.objection_id == objection_id), None
        )
        if row is None:
            raise NotFoundError("Objection not found on this deal.")
        row.status = "RESOLVED"
        row.resolution = resolution
        self.repository.add_event(
            deal,
            event_type=DealEventType.OBJECTION_ADDED.value,
            title=f"Objection resolved: {row.objection.label}",
            detail=resolution,
            payload={"objection": row.objection.label},
        )
        self.session.flush()
        return row
