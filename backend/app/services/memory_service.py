from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    Deal,
    DealEvent,
    Interaction,
    MemoryKind,
    MemoryReference,
    Recommendation,
)
from app.services.hindsight_service import (
    HindsightService,
    HindsightUnavailableError,
    hindsight_service,
)

logger = get_logger(__name__)

MEMORY_MISSION = (
    "I am the deal memory layer for a B2B sales team. I retain what happened in "
    "customer conversations, which competitors and objections appeared, what was "
    "priced, how deals ended and why. I only store facts that were explicitly "
    "recorded; I never speculate about outcomes or customer intent."
)


class MemoryService:
    """Bridges PostgreSQL records and Hindsight contextual memory.

    PostgreSQL stays the source of truth. Hindsight only receives distilled,
    contextual summaries - never a dump of the relational rows.
    """

    def __init__(self, session: Session, hindsight: HindsightService | None = None):
        self.session = session
        self.hindsight = hindsight or hindsight_service

    # ----------------------------------------------------------------- status
    def status(self, organization_id: uuid.UUID) -> dict[str, Any]:
        info = self.hindsight.status(organization_id)
        info["local_reference_count"] = int(
            self.session.execute(
                select(func.count(MemoryReference.id)).where(
                    MemoryReference.organization_id == organization_id
                )
            ).scalar_one()
            or 0
        )
        return info

    # ---------------------------------------------------------------- builders
    @staticmethod
    def build_interaction_memory(
        deal: Deal,
        interaction: Interaction,
        *,
        customer_name: str,
        competitors: list[str],
        objections: list[str],
        extracted: dict[str, Any] | None = None,
    ) -> str:
        parts = [
            f"CUSTOMER: {customer_name}",
            f"DEAL: {deal.name} (stage {deal.stage}, amount {deal.amount} {deal.currency})",
            f"INTERACTION: {interaction.interaction_type} - {interaction.title or 'untitled'} "
            f"on {interaction.occurred_at:%Y-%m-%d}",
            f"CONTEXT: {interaction.body.strip()}",
        ]
        if competitors:
            parts.append(f"COMPETITORS: {', '.join(competitors)}")
        if objections:
            parts.append(f"OBJECTIONS RAISED: {', '.join(objections)}")
        if extracted and extracted.get("pricing"):
            pricing = extracted["pricing"]
            parts.append(
                f"PRICING: amount={pricing.get('amount')} {pricing.get('currency') or ''} "
                f"terms={pricing.get('terms') or 'unspecified'}"
            )
        if extracted and extracted.get("commitments"):
            parts.append(f"COMMITMENTS: {'; '.join(extracted['commitments'])}")
        if extracted and extracted.get("requirements"):
            parts.append(f"REQUIREMENTS: {'; '.join(extracted['requirements'])}")
        if extracted and extracted.get("sentiment"):
            parts.append(f"CUSTOMER SENTIMENT: {extracted['sentiment']}")
        if deal.outcome:
            reason = deal.win_reason if deal.outcome == "WON" else deal.loss_reason
            parts.append(f"OUTCOME: {deal.outcome}")
            if reason:
                parts.append(f"REASON: {reason}")
        return "\n".join(parts)

    @staticmethod
    def build_outcome_memory(deal: Deal, customer_name: str) -> str:
        reason = deal.win_reason if deal.outcome == "WON" else deal.loss_reason
        return "\n".join(
            [
                f"CUSTOMER: {customer_name}",
                f"DEAL: {deal.name}",
                f"AMOUNT: {deal.amount} {deal.currency}",
                f"FINAL STAGE: {deal.stage}",
                f"OUTCOME: {deal.outcome}",
                f"REASON: {reason or 'not recorded'}",
                "LESSON: this deal is closed and should be used as historical evidence "
                "for future opportunities with similar profiles.",
            ]
        )

    @staticmethod
    def build_deal_context_memory(deal: Deal, customer_name: str) -> str:
        return "\n".join(
            [
                f"CUSTOMER: {customer_name}",
                f"DEAL: {deal.name}",
                f"STAGE: {deal.stage}",
                f"AMOUNT: {deal.amount} {deal.currency}",
                f"EXPECTED CLOSE: {deal.expected_close_date or 'unknown'}",
                f"DESCRIPTION: {deal.description or 'n/a'}",
            ]
        )

    # ------------------------------------------------------------------ retain
    def retain(
        self,
        organization_id: uuid.UUID,
        *,
        content: str,
        kind: str,
        deal: Deal | None = None,
        interaction: Interaction | None = None,
        customer_id: uuid.UUID | None = None,
        context: str | None = None,
        tags: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> MemoryReference:
        meta: dict[str, str] = {
            "organization_id": str(organization_id),
            "kind": kind,
        }
        if deal is not None:
            meta.update(
                {
                    "deal_id": str(deal.id),
                    "deal_name": deal.name,
                    "stage": deal.stage,
                    "amount": str(deal.amount),
                    "currency": deal.currency,
                    "outcome": deal.outcome or "open",
                }
            )
            if customer_id is None and deal.customer_id:
                meta["customer_id"] = str(deal.customer_id)
            customer_name = deal.customer.name if deal.customer else ""
            if customer_name:
                meta["customer_name"] = customer_name
        if customer_id:
            meta["customer_id"] = str(customer_id)
        if interaction is not None:
            meta["interaction_id"] = str(interaction.id)
            meta["interaction_type"] = interaction.interaction_type

        effective_tags = list(tags or [])
        if deal is not None:
            effective_tags.append(f"stage:{deal.stage}")
            if deal.outcome:
                effective_tags.append(f"outcome:{deal.outcome}")

        reference = MemoryReference(
            organization_id=organization_id,
            bank_id=self.hindsight.bank_id(organization_id),
            deal_id=deal.id if deal else None,
            customer_id=customer_id or (deal.customer_id if deal else None),
            interaction_id=interaction.id if interaction else None,
            kind=kind,
            content=content,
            context=context,
            meta=meta,
            tags=effective_tags,
            occurred_at=timestamp or (interaction.occurred_at if interaction else None),
        )

        try:
            self.hindsight.retain_memory(
                organization_id,
                content,
                context=context,
                metadata=meta,
                tags=effective_tags,
                timestamp=timestamp or (interaction.occurred_at if interaction else None),
            )
            reference.sync_status = "SYNCED"
        except HindsightUnavailableError as exc:
            reference.sync_status = "FAILED"
            reference.sync_error = f"{exc.code}: {exc.message}"[:400]
            logger.warning("Hindsight retain failed: %s", exc.message)

        self.session.add(reference)
        self.session.flush()
        return reference

    # ------------------------------------------------------------------ recall
    def recall_for_deal(
        self, organization_id: uuid.UUID, queries: list[str], *, max_tokens: int = 3000
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        status = self.hindsight.status(organization_id)
        if not status.get("available"):
            return [], status
        try:
            hits = self.hindsight.search_deal_history(
                organization_id, queries=queries, max_tokens=max_tokens
            )
        except HindsightUnavailableError as exc:
            status = {"available": False, "reason": exc.message, "code": exc.code}
            return [], status
        return [h.as_dict() for h in hits], status

    def list_references(
        self,
        organization_id: uuid.UUID,
        *,
        deal_id: uuid.UUID | None = None,
        kind: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryReference], int]:
        stmt = select(MemoryReference).where(
            MemoryReference.organization_id == organization_id
        )
        count = select(func.count(MemoryReference.id)).where(
            MemoryReference.organization_id == organization_id
        )
        if deal_id:
            stmt = stmt.where(MemoryReference.deal_id == deal_id)
            count = count.where(MemoryReference.deal_id == deal_id)
        if kind:
            stmt = stmt.where(MemoryReference.kind == kind)
            count = count.where(MemoryReference.kind == kind)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(MemoryReference.content).like(like))
            count = count.where(func.lower(MemoryReference.content).like(like))
        rows = list(
            self.session.execute(
                stmt.order_by(MemoryReference.created_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        total = int(self.session.execute(count).scalar_one() or 0)
        return rows, total

    # ---------------------------------------------------------------- timeline
    def deal_timeline(self, deal_id: uuid.UUID, limit: int = 300) -> list[dict[str, Any]]:
        """Merges database events and retained memories into one ordered view.

        `source` is deliberately explicit so the UI can visually separate
        'DATABASE EVENT' from 'MEMORY INSIGHT'.
        """
        items: list[dict[str, Any]] = []

        events = list(
            self.session.execute(
                select(DealEvent)
                .where(DealEvent.deal_id == deal_id)
                .order_by(DealEvent.occurred_at.asc())
                .limit(limit)
            ).scalars()
        )
        for event in events:
            items.append(
                {
                    "source": "database",
                    "occurred_at": event.occurred_at,
                    "title": event.title,
                    "detail": event.detail,
                    "kind": event.event_type,
                    "reference_id": event.id,
                    "meta": event.payload or {},
                }
            )

        interactions = list(
            self.session.execute(
                select(Interaction)
                .where(Interaction.deal_id == deal_id)
                .order_by(Interaction.occurred_at.asc())
                .limit(limit)
            ).scalars()
        )
        for interaction in interactions:
            items.append(
                {
                    "source": "database",
                    "occurred_at": interaction.occurred_at,
                    "title": f"{interaction.interaction_type.replace('_', ' ').title()}: "
                    f"{interaction.title or 'interaction'}",
                    "detail": (interaction.body or "")[:400],
                    "kind": "INTERACTION",
                    "reference_id": interaction.id,
                    "meta": {
                        "sentiment": interaction.sentiment,
                        "type": interaction.interaction_type,
                    },
                }
            )

        references = list(
            self.session.execute(
                select(MemoryReference)
                .where(MemoryReference.deal_id == deal_id)
                .order_by(MemoryReference.created_at.asc())
                .limit(limit)
            ).scalars()
        )
        for ref in references:
            items.append(
                {
                    "source": "memory",
                    "occurred_at": ref.occurred_at or ref.created_at,
                    "title": f"Memory retained - {ref.kind.replace('_', ' ').title()}",
                    "detail": ref.content[:400],
                    "kind": ref.kind,
                    "reference_id": ref.id,
                    "meta": {
                        "bank_id": ref.bank_id,
                        "sync_status": ref.sync_status,
                        "tags": ref.tags or [],
                    },
                }
            )

        recommendations = list(
            self.session.execute(
                select(Recommendation)
                .where(Recommendation.deal_id == deal_id)
                .order_by(Recommendation.created_at.asc())
                .limit(limit)
            ).scalars()
        )
        for rec in recommendations:
            items.append(
                {
                    "source": "system",
                    "occurred_at": rec.created_at,
                    "title": f"Recommendation generated: {rec.title}",
                    "detail": (rec.rationale or "")[:400],
                    "kind": "RECOMMENDATION",
                    "reference_id": rec.id,
                    "meta": {"evidence_level": rec.evidence_level, "source": rec.source},
                }
            )

        items.sort(key=lambda i: i["occurred_at"] or datetime.min)
        return items[:limit]
