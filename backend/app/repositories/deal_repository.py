from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Competitor,
    Contact,
    Customer,
    Deal,
    DealCompetitor,
    DealObjection,
    DealEvent,
    Interaction,
    Objection,
    Recommendation,
    User,
)
from app.models.enums import DealStage


def _stage_rank(stage: str) -> int:
    order = [s.value for s in DealStage]
    return order.index(stage) if stage in order else len(order)


class DealRepository:
    def __init__(self, session: Session):
        self.session = session

    def base(self) -> Select:
        return select(Deal).options(
            selectinload(Deal.customer),
            selectinload(Deal.owner),
            selectinload(Deal.deal_competitors).selectinload(DealCompetitor.competitor),
            selectinload(Deal.deal_objections).selectinload(DealObjection.objection),
        )

    def get(self, organization_id: uuid.UUID, deal_id: uuid.UUID) -> Optional[Deal]:
        stmt = self.base().where(
            Deal.id == deal_id, Deal.organization_id == organization_id
        )
        return self.session.execute(stmt).unique().scalar_one_or_none()

    def list(
        self,
        organization_id: uuid.UUID,
        *,
        owner_id: uuid.UUID | None = None,
        stage: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
        customer_id: uuid.UUID | None = None,
        competitor: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        risk: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "updated_at",
        direction: str = "desc",
    ) -> tuple[list[Deal], int]:
        stmt = self.base().where(Deal.organization_id == organization_id)
        count_stmt = select(func.count(Deal.id)).where(Deal.organization_id == organization_id)

        if owner_id:
            stmt = stmt.where(Deal.owner_id == owner_id)
            count_stmt = count_stmt.where(Deal.owner_id == owner_id)
        if stage:
            stmt = stmt.where(Deal.stage == stage)
            count_stmt = count_stmt.where(Deal.stage == stage)
        if status:
            stmt = stmt.where(Deal.status == status)
            count_stmt = count_stmt.where(Deal.status == status)
        if outcome:
            stmt = stmt.where(Deal.outcome == outcome)
            count_stmt = count_stmt.where(Deal.outcome == outcome)
        if customer_id:
            stmt = stmt.where(Deal.customer_id == customer_id)
            count_stmt = count_stmt.where(Deal.customer_id == customer_id)
        if min_amount is not None:
            stmt = stmt.where(Deal.amount >= min_amount)
            count_stmt = count_stmt.where(Deal.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Deal.amount <= max_amount)
            count_stmt = count_stmt.where(Deal.amount <= max_amount)
        if from_date:
            stmt = stmt.where(Deal.created_at >= datetime.combine(from_date, datetime.min.time()))
            count_stmt = count_stmt.where(
                Deal.created_at >= datetime.combine(from_date, datetime.min.time())
            )
        if to_date:
            stmt = stmt.where(Deal.created_at < datetime.combine(to_date, datetime.min.time()))
            count_stmt = count_stmt.where(
                Deal.created_at < datetime.combine(to_date, datetime.min.time())
            )
        if competitor:
            stmt = stmt.join(DealCompetitor).join(Competitor).where(
                func.lower(Competitor.name).like(f"%{competitor.lower()}%")
            )
            count_stmt = count_stmt.join(DealCompetitor).join(Competitor).where(
                func.lower(Competitor.name).like(f"%{competitor.lower()}%")
            )
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.join(Customer, Deal.customer_id == Customer.id).where(
                or_(func.lower(Deal.name).like(like), func.lower(Customer.name).like(like))
            )
            count_stmt = count_stmt.join(Customer, Deal.customer_id == Customer.id).where(
                or_(func.lower(Deal.name).like(like), func.lower(Customer.name).like(like))
            )

        sort_map = {
            "updated_at": Deal.updated_at,
            "created_at": Deal.created_at,
            "amount": Deal.amount,
            "close_date": Deal.expected_close_date,
            "name": Deal.name,
            "stage": Deal.stage,
        }
        column = sort_map.get(sort, Deal.updated_at)
        order = column.desc() if direction == "desc" else column.asc()

        rows = list(
            self.session.execute(
                stmt.order_by(order).limit(limit).offset(offset)
            )
            .unique()
            .scalars()
            .all()
        )
        if risk == "STALLED":
            cutoff = datetime.utcnow() - timedelta(days=21)
            rows = [
                d
                for d in rows
                if d.status == "OPEN"
                and (d.last_activity_at is None or d.last_activity_at < cutoff)
            ]
        total = int(self.session.execute(count_stmt).scalar_one() or 0)
        return rows, total

    def similar(
        self,
        organization_id: uuid.UUID,
        *,
        exclude_id: uuid.UUID,
        customer_id: uuid.UUID,
        stage: str,
        amount: Decimal,
        competitor_ids: Sequence[uuid.UUID],
        objection_ids: Sequence[uuid.UUID],
        limit: int = 8,
    ) -> list[Deal]:
        """Candidate retrieval from structured data.

        Only closed deals with a recorded outcome are considered: an open deal
        cannot tell us whether a pattern worked.
        """
        stmt = (
            self.base()
            .where(
                Deal.organization_id == organization_id,
                Deal.id != exclude_id,
                Deal.outcome.is_not(None),
            )
            .order_by(func.abs(Deal.amount - amount).asc())
            .limit(60)
        )
        candidates: list[Deal] = list(self.session.execute(stmt).unique().scalars().all())

        closed_won = {DealStage.CLOSED_WON.value, DealStage.CLOSED_LOST.value}
        scored: list[tuple[float, Deal]] = []
        for deal in candidates:
            if deal.stage not in closed_won:
                continue
            score = 0.0
            if deal.customer_id == customer_id:
                score += 25
            deal_competitor_ids = {dc.competitor_id for dc in deal.deal_competitors}
            shared_competitors = deal_competitor_ids & set(competitor_ids)
            if shared_competitors:
                score += 20 + 5 * min(len(shared_competitors), 3)
            deal_objection_ids = {do.objection_id for do in deal.deal_objections}
            shared_objections = deal_objection_ids & set(objection_ids)
            if shared_objections:
                score += 18 + 5 * min(len(shared_objections), 3)
            if deal.stage == stage:
                score += 10
            if amount > 0 and deal.amount > 0:
                delta = abs(float(deal.amount) - float(amount)) / max(float(amount), 1.0)
                score += max(0.0, 20.0 * (1.0 - min(delta, 1.0)))
            else:
                score += 8
            scored.append((score, deal))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [deal for _, deal in scored[:limit]]

    def add_event(
        self,
        deal: Deal,
        *,
        event_type: str,
        title: str,
        detail: str | None = None,
        actor_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> DealEvent:
        event = DealEvent(
            deal_id=deal.id,
            organization_id=deal.organization_id,
            actor_id=actor_id,
            event_type=event_type,
            title=title,
            detail=detail,
            payload=payload,
            occurred_at=occurred_at or datetime.utcnow(),
        )
        self.session.add(event)
        return event

    def events(self, deal_id: uuid.UUID, limit: int = 200) -> list[DealEvent]:
        stmt = (
            select(DealEvent)
            .where(DealEvent.deal_id == deal_id)
            .order_by(DealEvent.occurred_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def competitors_for(self, deal: Deal) -> list[Competitor]:
        return [dc.competitor for dc in deal.deal_competitors]

    def objections_for(self, deal: Deal) -> list[Objection]:
        return [do.objection for do in deal.deal_objections]

    def find_competitor(self, organization_id: uuid.UUID, name: str) -> Optional[Competitor]:
        return self.session.execute(
            select(Competitor).where(
                Competitor.organization_id == organization_id,
                func.lower(Competitor.name) == name.strip().lower(),
            )
        ).scalar_one_or_none()

    def find_objection(self, organization_id: uuid.UUID, label: str) -> Optional[Objection]:
        return self.session.execute(
            select(Objection).where(
                Objection.organization_id == organization_id,
                func.lower(Objection.label) == label.strip().lower(),
            )
        ).scalar_one_or_none()

    def all_competitors(self, organization_id: uuid.UUID) -> list[Competitor]:
        return list(
            self.session.execute(
                select(Competitor)
                .where(Competitor.organization_id == organization_id)
                .order_by(Competitor.name)
            ).scalars()
        )

    def all_objections(self, organization_id: uuid.UUID) -> list[Objection]:
        return list(
            self.session.execute(
                select(Objection)
                .where(Objection.organization_id == organization_id)
                .order_by(Objection.label)
            ).scalars()
        )

    def closed_deals(self, organization_id: uuid.UUID) -> list[Deal]:
        return list(
            self.session.execute(
                select(Deal)
                .options(
                    selectinload(Deal.customer),
                    selectinload(Deal.deal_competitors).selectinload(DealCompetitor.competitor),
                    selectinload(Deal.deal_objections).selectinload(DealObjection.objection),
                )
                .where(
                    Deal.organization_id == organization_id,
                    Deal.outcome.is_not(None),
                )
            )
            .unique()
            .scalars()
            .all()
        )

    def open_deals(self, organization_id: uuid.UUID) -> list[Deal]:
        return list(
            self.session.execute(
                self.base().where(
                    Deal.organization_id == organization_id,
                    Deal.status == "OPEN",
                    Deal.outcome.is_(None),
                )
            )
            .unique()
            .scalars()
            .all()
        )

    def interactions_for(self, deal_id: uuid.UUID) -> list[Interaction]:
        return list(
            self.session.execute(
                select(Interaction)
                .where(Interaction.deal_id == deal_id)
                .order_by(Interaction.occurred_at.asc())
            ).scalars()
        )

    def contacts_for(self, customer_id: uuid.UUID) -> list[Contact]:
        return list(
            self.session.execute(
                select(Contact).where(Contact.customer_id == customer_id)
            ).scalars()
        )

    def recommendations_for(self, deal_id: uuid.UUID) -> list[Recommendation]:
        return list(
            self.session.execute(
                select(Recommendation)
                .where(Recommendation.deal_id == deal_id)
                .order_by(Recommendation.created_at.desc())
            ).scalars()
        )
