from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models import (
    Competitor,
    Contact,
    Customer,
    Deal,
    DealCompetitor,
    DealObjection,
    Interaction,
    InteractionParticipant,
    Objection,
)
from app.models.enums import DealEventType, MemoryKind
from app.repositories.deal_repository import DealRepository
from app.repositories.interaction_repository import InteractionRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.schemas.interaction import InteractionCreate
from app.services.extraction_service import ExtractionService
from app.services.memory_service import MemoryService

logger = get_logger(__name__)


class InteractionService:
    """Ingests one customer interaction end to end.

    Order matters: validate -> persist structured rows -> extract entities ->
    retain contextual memory -> update the timeline.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repository = InteractionRepository(session)
        self.deals = DealRepository(session)
        self.memory = MemoryService(session)
        self.extraction = ExtractionService(session)
        self.recommendations = RecommendationRepository(session)

    def ingest(
        self,
        organization_id: uuid.UUID,
        deal: Deal,
        payload: InteractionCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Interaction:
        if payload.occurred_at and payload.occurred_at > datetime.utcnow().replace(microsecond=0):
            raise ValidationAppError("occurred_at cannot be in the future.")

        occurred_at = payload.occurred_at or datetime.utcnow()
        extracted = self.extraction.extract(
            organization_id,
            payload.body,
            deal_context=f"{deal.name} ({deal.stage})",
        )
        payload_data = extracted.as_dict()

        merged_requirements = list(
            dict.fromkeys(list(payload.requirements or []) + extracted.requirements)
        )
        merged_commitments = list(
            dict.fromkeys(list(payload.commitments or []) + extracted.commitments)
        )

        interaction = Interaction(
            organization_id=organization_id,
            deal_id=deal.id,
            author_id=actor_id,
            customer_id=deal.customer_id,
            interaction_type=payload.interaction_type.value,
            title=payload.title,
            body=payload.body,
            channel=payload.channel,
            direction=payload.direction,
            duration_minutes=payload.duration_minutes,
            price_discussed=payload.price_discussed,
            currency=payload.currency or deal.currency,
            commitments=merged_commitments,
            requirements=merged_requirements,
            extracted=payload_data,
            sentiment=extracted.sentiment,
            occurred_at=occurred_at,
            source="MANUAL",
        )
        self.session.add(interaction)
        self.session.flush()

        for participant in payload.participants:
            self.session.add(
                InteractionParticipant(
                    interaction_id=interaction.id,
                    contact_id=participant.contact_id,
                    user_id=actor_id if participant.side == "INTERNAL" else None,
                    name=participant.name,
                    role=participant.role,
                    side=participant.side,
                )
            )

        linked_competitors = self._link_competitors(deal, extracted.competitors, occurred_at)
        linked_objections = self._link_objections(deal, extracted.objections, occurred_at)

        memory_content = MemoryService.build_interaction_memory(
            deal,
            interaction,
            customer_name=deal.customer.name if deal.customer else "",
            competitors=linked_competitors,
            objections=linked_objections,
            extracted=payload_data,
        )
        reference = self.memory.retain(
            organization_id,
            content=memory_content,
            kind=MemoryKind.INTERACTION.value,
            deal=deal,
            interaction=interaction,
            customer_id=deal.customer_id,
            context=f"{interaction.interaction_type} interaction on {occurred_at:%Y-%m-%d}",
            tags=[f"type:{interaction.interaction_type}", f"deal:{deal.id}"],
            timestamp=occurred_at,
        )

        deal.last_activity_at = occurred_at
        self.deals.add_event(
            deal,
            event_type=DealEventType.INTERACTION_ADDED.value,
            title=f"{interaction.interaction_type.replace('_', ' ').title()} logged: "
            f"{payload.title or interaction.body[:60]}",
            detail=interaction.body[:400],
            actor_id=actor_id,
            payload={
                "interaction_id": str(interaction.id),
                "memory_sync": reference.sync_status,
                "extracted_objections": linked_objections,
                "extracted_competitors": linked_competitors,
                "extraction_method": extracted.method,
            },
        )
        if linked_objections or linked_competitors:
            self.recommendations.mark_stale_for_deal(deal.id)
        self.session.flush()
        return interaction

    # ------------------------------------------------------------ link helpers
    def _link_competitors(self, deal: Deal, names: list[str], occurred_at: datetime) -> list[str]:
        linked: list[str] = []
        existing = {dc.competitor.name.lower() for dc in deal.deal_competitors}
        for name in names:
            key = name.strip().lower()
            if not key or key in existing:
                if name.strip():
                    linked.append(name.strip())
                continue
            competitor = self.deals.find_competitor(deal.organization_id, name)
            if competitor is None:
                competitor = Competitor(organization_id=deal.organization_id, name=name.strip())
                self.session.add(competitor)
                self.session.flush()
            self.session.add(
                DealCompetitor(deal_id=deal.id, competitor_id=competitor.id, strength="UNKNOWN")
            )
            existing.add(key)
            linked.append(competitor.name)
        if linked:
            self.deals.add_event(
                deal,
                event_type=DealEventType.COMPETITOR_ADDED.value,
                title=f"Competitor identified: {', '.join(linked)}",
                occurred_at=occurred_at,
                payload={"competitors": linked},
            )
            self.session.flush()
        return linked

    def _link_objections(self, deal: Deal, labels: list[str], occurred_at: datetime) -> list[str]:
        linked: list[str] = []
        existing = {do.objection.label.lower() for do in deal.deal_objections}
        for label in labels:
            key = label.strip().lower()
            if not key or key in existing:
                if label.strip():
                    linked.append(label.strip())
                continue
            objection = self.deals.find_objection(deal.organization_id, label)
            if objection is None:
                objection = Objection(organization_id=deal.organization_id, label=label.strip())
                self.session.add(objection)
                self.session.flush()
            self.session.add(
                DealObjection(
                    deal_id=deal.id,
                    objection_id=objection.id,
                    status="OPEN",
                    raised_at=occurred_at,
                )
            )
            existing.add(key)
            linked.append(objection.label)
        if linked:
            self.deals.add_event(
                deal,
                event_type=DealEventType.OBJECTION_ADDED.value,
                title=f"Objection raised: {', '.join(linked)}",
                occurred_at=occurred_at,
                payload={"objections": linked},
            )
            self.session.flush()
        return linked
