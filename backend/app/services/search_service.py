from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Contact,
    CopilotMessage,
    Customer,
    Deal,
    Interaction,
    MemoryReference,
    Recommendation,
)


class SearchService:
    """Global search across customers, deals, contacts, interactions,
    recommendations and retained memories. Memory content is searched through
    the local index; Hindsight itself is only queried when it is healthy."""

    def __init__(self, session: Session):
        self.session = session

    def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        types: list[str] | None = None,
        limit: int = 40,
    ) -> dict[str, Any]:
        q = f"%{query.strip().lower()}%"
        wanted = set(types or ["customer", "deal", "contact", "interaction", "recommendation", "memory"])
        hits: list[dict[str, Any]] = []
        counts: dict[str, int] = {}

        if "customer" in wanted:
            rows = self.session.execute(
                select(Customer)
                .where(Customer.organization_id == organization_id)
                .where(
                    or_(
                        func.lower(Customer.name).like(q),
                        func.lower(func.coalesce(Customer.industry, "")).like(q),
                        func.lower(func.coalesce(Customer.segment, "")).like(q),
                    )
                )
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "customer",
                        "id": str(row.id),
                        "title": row.name,
                        "subtitle": ", ".join(
                            filter(None, [row.industry, row.segment, row.region])
                        ),
                        "score": 1.0,
                        "extra": {"domain": row.domain},
                    }
                )
            counts["customer"] = len(hits)

        if "deal" in wanted:
            before = len(hits)
            rows = self.session.execute(
                select(Deal)
                .join(Customer, Deal.customer_id == Customer.id)
                .where(Deal.organization_id == organization_id)
                .where(
                    or_(
                        func.lower(Deal.name).like(q),
                        func.lower(Customer.name).like(q),
                        func.lower(func.coalesce(Deal.description, "")).like(q),
                        func.lower(func.coalesce(Deal.loss_reason, "")).like(q),
                        func.lower(func.coalesce(Deal.win_reason, "")).like(q),
                    )
                )
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "deal",
                        "id": str(row.id),
                        "title": row.name,
                        "subtitle": f"{row.stage} - {row.amount} {row.currency}",
                        "score": 1.0,
                        "extra": {"outcome": row.outcome},
                    }
                )
            counts["deal"] = len(hits) - before

        if "contact" in wanted:
            before = len(hits)
            rows = self.session.execute(
                select(Contact)
                .join(Customer, Contact.customer_id == Customer.id)
                .where(Contact.organization_id == organization_id)
                .where(
                    or_(
                        func.lower(Contact.full_name).like(q),
                        func.lower(func.coalesce(Contact.title, "")).like(q),
                        func.lower(func.coalesce(Contact.email, "")).like(q),
                    )
                )
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "contact",
                        "id": str(row.id),
                        "title": row.full_name,
                        "subtitle": row.title or "",
                        "score": 0.9,
                        "extra": {"email": row.email},
                    }
                )
            counts["contact"] = len(hits) - before

        if "interaction" in wanted:
            before = len(hits)
            rows = self.session.execute(
                select(Interaction)
                .where(Interaction.organization_id == organization_id)
                .where(
                    or_(
                        func.lower(Interaction.body).like(q),
                        func.lower(Interaction.title).like(q),
                    )
                )
                .order_by(Interaction.occurred_at.desc())
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "interaction",
                        "id": str(row.id),
                        "title": row.title or f"{row.interaction_type} interaction",
                        "subtitle": row.body[:120],
                        "score": 0.8,
                        "extra": {"deal_id": str(row.deal_id), "type": row.interaction_type},
                    }
                )
            counts["interaction"] = len(hits) - before

        if "recommendation" in wanted:
            before = len(hits)
            rows = self.session.execute(
                select(Recommendation)
                .where(Recommendation.organization_id == organization_id)
                .where(
                    or_(
                        func.lower(Recommendation.title).like(q),
                        func.lower(Recommendation.rationale).like(q),
                    )
                )
                .order_by(Recommendation.created_at.desc())
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "recommendation",
                        "id": str(row.id),
                        "title": row.title,
                        "subtitle": row.evidence_level,
                        "score": 0.7,
                        "extra": {"deal_id": str(row.deal_id), "source": row.source},
                    }
                )
            counts["recommendation"] = len(hits) - before

        if "memory" in wanted:
            before = len(hits)
            rows = self.session.execute(
                select(MemoryReference)
                .where(MemoryReference.organization_id == organization_id)
                .where(func.lower(MemoryReference.content).like(q))
                .order_by(MemoryReference.created_at.desc())
                .limit(limit)
            ).scalars()
            for row in rows:
                hits.append(
                    {
                        "entity_type": "memory",
                        "id": str(row.id),
                        "title": f"Memory - {row.kind}",
                        "subtitle": row.content[:140],
                        "score": 0.6,
                        "extra": {
                            "deal_id": str(row.deal_id) if row.deal_id else None,
                            "bank_id": row.bank_id,
                            "sync_status": row.sync_status,
                        },
                    }
                )
            counts["memory"] = len(hits) - before

        return {"query": query, "hits": hits, "counts": counts, "total": len(hits)}
