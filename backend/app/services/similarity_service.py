from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Deal
from app.repositories.deal_repository import DealRepository
from app.services.memory_service import MemoryService

OUTCOME_LABEL = {"WON": "Won", "LOST": "Lost"}


class SimilarDealService:
    """Finds historical deals that resemble a live opportunity.

    Two sources are combined:
      * structured similarity from PostgreSQL (always available)
      * contextual memories from Hindsight (available when the service is up)

    Each result carries a human-readable `why_relevant` string - similarity is
    never presented without a reason.
    """

    def __init__(self, session: Session):
        self.session = session
        self.deals = DealRepository(session)
        self.memory = MemoryService(session)

    @staticmethod
    def _shared_attributes(target: Deal, candidate: Deal) -> dict[str, Any]:
        target_competitors = {dc.competitor.name.lower() for dc in target.deal_competitors}
        candidate_competitors = {dc.competitor.name.lower() for dc in candidate.deal_competitors}
        target_objections = {do.objection.label.lower() for do in target.deal_objections}
        candidate_objections = {do.objection.label.lower() for do in candidate.deal_objections}

        shared_competitors = sorted(target_competitors & candidate_competitors)
        shared_objections = sorted(target_objections & candidate_objections)

        reasons: list[str] = []
        if shared_competitors:
            reasons.append(f"same competitor: {', '.join(shared_competitors)}")
        if shared_objections:
            reasons.append(f"same objection: {', '.join(shared_objections)}")
        if target.customer_id == candidate.customer_id:
            reasons.append("same customer account")
        if target.stage == candidate.stage:
            reasons.append(f"reached the same stage ({target.stage})")

        amount_ratio = None
        if target.amount and candidate.amount:
            low, high = sorted([float(target.amount), float(candidate.amount)])
            amount_ratio = high / low if low else None
            if amount_ratio and amount_ratio <= 1.35:
                reasons.append("comparable deal size")
            elif amount_ratio and amount_ratio <= 2.0:
                reasons.append("similar order of magnitude")

        if target.customer and candidate.customer:
            if target.customer.industry and target.customer.industry == candidate.customer.industry:
                reasons.append(f"same industry ({target.customer.industry})")
            if target.customer.segment and target.customer.segment == candidate.customer.segment:
                reasons.append(f"same segment ({target.customer.segment})")

        if not reasons:
            reasons.append("matched on deal profile and timing")

        return {
            "shared_competitors": shared_competitors,
            "shared_objections": shared_objections,
            "amount_ratio": round(amount_ratio, 2) if amount_ratio else None,
            "reasons": reasons,
        }

    def find_similar(
        self,
        organization_id: uuid.UUID,
        deal: Deal,
        *,
        include_memory: bool = True,
        limit: int = 6,
    ) -> dict[str, Any]:
        competitor_ids = [dc.competitor_id for dc in deal.deal_competitors]
        objection_ids = [do.objection_id for do in deal.deal_objections]

        candidates = self.deals.similar(
            organization_id,
            exclude_id=deal.id,
            customer_id=deal.customer_id,
            stage=deal.stage,
            amount=deal.amount or Decimal("0"),
            competitor_ids=competitor_ids,
            objection_ids=objection_ids,
            limit=limit * 2,
        )

        results: list[dict[str, Any]] = []
        for candidate in candidates:
            shared = self._shared_attributes(deal, candidate)
            results.append(
                {
                    "deal_id": candidate.id,
                    "deal_name": candidate.name,
                    "customer_name": candidate.customer.name if candidate.customer else "",
                    "amount": float(candidate.amount or 0),
                    "currency": candidate.currency,
                    "stage": candidate.stage,
                    "outcome": candidate.outcome,
                    "outcome_label": OUTCOME_LABEL.get(candidate.outcome or "", "Unknown"),
                    "competitors": [
                        dc.competitor.name for dc in candidate.deal_competitors
                    ],
                    "key_objections": [
                        do.objection.label for do in candidate.deal_objections
                    ],
                    "loss_reason": candidate.loss_reason,
                    "win_reason": candidate.win_reason,
                    "closed_at": candidate.closed_at.isoformat() if candidate.closed_at else None,
                    "why_relevant": "; ".join(shared["reasons"]),
                    "shared": shared,
                    "source": "database",
                }
            )
            if len(results) >= limit:
                break

        memory_status: dict[str, Any] = {"available": False, "reason": "not_requested"}
        memory_hits: list[dict[str, Any]] = []
        if include_memory:
            queries = self._queries(deal)
            memory_hits, memory_status = self.memory.recall_for_deal(
                organization_id, queries, max_tokens=2500
            )

        return {
            "deal_id": str(deal.id),
            "similar_deals": results,
            "memory_hits": memory_hits[:20],
            "memory_status": memory_status,
            "structured_count": len(results),
            "memory_count": len(memory_hits),
        }

    @staticmethod
    def _queries(deal: Deal) -> list[str]:
        customer = deal.customer.name if deal.customer else ""
        competitors = ", ".join(dc.competitor.name for dc in deal.deal_competitors)
        objections = ", ".join(do.objection.label for do in deal.deal_objections)
        queries = [
            f"deals with {customer} or similar enterprise customers in {deal.stage}",
            f"why were deals lost with objection {objections}" if objections else "",
            f"competitor {competitors} deals outcome" if competitors else "",
            f"pricing and procurement objections on deals around {deal.amount} {deal.currency}",
            "actions that preceded winning enterprise deals",
        ]
        return [q for q in queries if q.strip()]
