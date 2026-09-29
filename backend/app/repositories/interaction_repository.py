from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Interaction, InteractionParticipant


class InteractionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, organization_id: uuid.UUID, interaction_id: uuid.UUID) -> Optional[Interaction]:
        return self.session.execute(
            select(Interaction).where(
                Interaction.id == interaction_id,
                Interaction.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def list_for_deal(
        self, deal_id: uuid.UUID, *, limit: int = 200, offset: int = 0
    ) -> list[Interaction]:
        return list(
            self.session.execute(
                select(Interaction)
                .where(Interaction.deal_id == deal_id)
                .order_by(Interaction.occurred_at.desc())
                .limit(limit)
                .offset(offset)
            ).scalars()
        )

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        type_: str | None = None,
        search: str | None = None,
        customer_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Interaction], int]:
        stmt = select(Interaction).where(Interaction.organization_id == organization_id)
        count = select(func.count(Interaction.id)).where(
            Interaction.organization_id == organization_id
        )
        if customer_id:
            stmt = stmt.where(Interaction.customer_id == customer_id)
            count = count.where(Interaction.customer_id == customer_id)
        if type_:
            stmt = stmt.where(Interaction.interaction_type == type_)
            count = count.where(Interaction.interaction_type == type_)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Interaction.body).like(like))
            count = count.where(func.lower(Interaction.body).like(like))
        rows = list(
            self.session.execute(
                stmt.order_by(Interaction.occurred_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        total = int(self.session.execute(count).scalar_one() or 0)
        return rows, total

    def add_participant(self, participant: InteractionParticipant) -> InteractionParticipant:
        self.session.add(participant)
        return participant

    def count_for_deal(self, deal_id: uuid.UUID) -> int:
        return int(
            self.session.execute(
                select(func.count(Interaction.id)).where(Interaction.deal_id == deal_id)
            ).scalar_one()
            or 0
        )
