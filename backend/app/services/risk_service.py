from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Contact,
    Deal,
    DealCompetitor,
    DealObjection,
    Interaction,
    Objection,
)
from app.models.enums import DealStage
from app.services.similarity_service import SimilarDealService

_LEVEL_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


class RiskService:
    """Detects deal risks from recorded data only.

    Every risk carries evidence. Nothing here asserts certainty - the language
    is deliberately 'suggests' / 'may indicate'.
    """

    def __init__(self, session: Session):
        self.session = session

    def detect(self, organization_id: uuid.UUID, deal: Deal) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []

        interactions = list(
            self.session.execute(
                select(Interaction)
                .where(Interaction.deal_id == deal.id)
                .order_by(Interaction.occurred_at.desc())
            ).scalars()
        )

        if not interactions:
            risks.append(
                {
                    "key": "no_interaction",
                    "title": "No customer interaction recorded",
                    "why_it_matters": "Without any logged contact there is nothing to base a "
                    "forecast or a next step on.",
                    "evidence": "This deal has zero interactions in the system.",
                    "suggested_investigation": "Log the first discovery call and capture "
                    "requirements verbatim.",
                    "level": "HIGH",
                }
            )
        else:
            last = interactions[0].occurred_at
            days = (datetime.utcnow() - last.replace(tzinfo=None)).days
            if days >= 21:
                risks.append(
                    {
                        "key": "no_recent_interaction",
                        "title": f"No customer contact for {days} days",
                        "why_it_matters": "Long gaps correlate with stalled evaluations and "
                        "quiet loss of internal champions.",
                        "evidence": f"Most recent interaction: {last:%Y-%m-%d} "
                        f"({interactions[0].interaction_type}).",
                        "suggested_investigation": "Confirm the evaluation is still active and "
                        "identify what changed internally.",
                        "level": "HIGH" if days >= 45 else "MEDIUM",
                    }
                )

        contacts = list(
            self.session.execute(
                select(Contact).where(Contact.customer_id == deal.customer_id)
            ).scalars()
        )
        if contacts:
            if not any(c.is_decision_maker for c in contacts):
                risks.append(
                    {
                        "key": "unclear_decision_maker",
                        "title": "No decision maker identified",
                        "why_it_matters": "Deals without a named economic buyer tend to stall at "
                        "approval time.",
                        "evidence": f"{len(contacts)} contact(s) recorded, none flagged as "
                        "decision maker.",
                        "suggested_investigation": "Ask your champion who signs off and request "
                        "an introduction.",
                        "level": "MEDIUM",
                    }
                )
            if not any(c.is_procurement for c in contacts):
                risks.append(
                    {
                        "key": "procurement_not_identified",
                        "title": "Procurement contact not identified",
                        "why_it_matters": "Procurement objections discovered late force pricing "
                        "concessions after value is already agreed.",
                        "evidence": "No contact on this account is flagged as procurement.",
                        "suggested_investigation": "Confirm the purchasing path before the next "
                        "commercial discussion.",
                        "level": "MEDIUM",
                    }
                )
        else:
            risks.append(
                {
                    "key": "no_contacts",
                    "title": "No contacts recorded for this customer",
                    "why_it_matters": "Stakeholder mapping is the usual defence against surprise "
                    "rejections.",
                    "evidence": "Customer profile has zero contacts.",
                    "suggested_investigation": "Add at least a champion and an economic buyer.",
                    "level": "MEDIUM",
                }
            )

        open_objections = [
            do
            for do in deal.deal_objections
            if (do.status or "OPEN").upper() in ("OPEN", "RAISED")
        ]
        for do in open_objections:
            label = do.objection.label
            historical = self._objection_history(organization_id, do.objection_id)
            repeat = historical.get("total", 0)
            losses = historical.get("lost", 0)
            level = "HIGH" if losses >= 2 and repeat >= 3 else "MEDIUM"
            risks.append(
                {
                    "key": f"unresolved_objection:{label.lower()}",
                    "title": f"Unresolved objection: {label}",
                    "why_it_matters": "Open objections without a recorded resolution are the "
                    "most common reason a proposal is paused.",
                    "evidence": (
                        f"Objection '{label}' is open on this deal. Across the organisation it "
                        f"has appeared in {repeat} closed deal(s), {losses} of them lost."
                        if repeat
                        else f"Objection '{label}' is open on this deal; no closed-deal history "
                        "for it yet."
                    ),
                    "suggested_investigation": f"Write down what evidence would remove the "
                    f"'{label}' concern and schedule a session for it.",
                    "level": level,
                }
            )

        if any(do.objection.label.lower().startswith(("pricing", "budget", "cost")) for do in open_objections):
            pricing_hits = self._pricing_objection_counts(organization_id)
            if pricing_hits["total"] >= 2:
                risks.append(
                    {
                        "key": "repeated_pricing_objection",
                        "title": "Pricing objections repeat across deals",
                        "why_it_matters": "Repeated pricing pushback usually signals a packaging "
                        "or justification gap, not a one-off negotiation tactic.",
                        "evidence": f"Pricing/budget objections appear on {pricing_hits['total']} "
                        f"deals, {pricing_hits['lost']} of which were lost.",
                        "suggested_investigation": "Establish total cost of ownership before "
                        "offering another discount.",
                        "level": "HIGH" if pricing_hits["lost"] >= 3 else "MEDIUM",
                    }
                )

        if deal.deal_competitors:
            names = ", ".join(dc.competitor.name for dc in deal.deal_competitors)
            losses = self._competitor_losses(organization_id, deal.deal_competitors)
            risks.append(
                {
                    "key": "strong_competitor_presence",
                    "title": f"Competitive deal: {names}",
                    "why_it_matters": "Competitive deals are decided on differentiation, and "
                    "late differentiation is expensive to recover from.",
                    "evidence": (
                        f"{names} appears in {losses['total']} closed deal(s) in this "
                        f"organisation; {losses['lost']} were lost."
                        if losses["total"]
                        else f"{names} is on this deal; no closed-deal history yet."
                    ),
                    "suggested_investigation": "Confirm where we win against this competitor and "
                    "build the comparison into the next call.",
                    "level": "MEDIUM",
                }
            )

        if deal.expected_close_date:
            days_left = (deal.expected_close_date - datetime.utcnow().date()).days
            if days_left < 0 and deal.status == "OPEN":
                risks.append(
                    {
                        "key": "close_date_passed",
                        "title": f"Close date passed by {-days_left} days",
                        "why_it_matters": "An overdue close date hides genuine slippage from the "
                        "forecast.",
                        "evidence": f"Expected close {deal.expected_close_date:%Y-%m-%d}, deal "
                        "still open.",
                        "suggested_investigation": "Re-validate the timeline with the customer "
                        "and move the date or explain the slip.",
                        "level": "HIGH",
                    }
                )
            elif 0 <= days_left <= 14 and deal.stage not in (
                DealStage.NEGOTIATION.value,
                DealStage.CLOSED_WON.value,
                DealStage.CLOSED_LOST.value,
            ):
                risks.append(
                    {
                        "key": "close_date_approaching",
                        "title": f"Close date in {days_left} days at stage {deal.stage}",
                        "why_it_matters": "Closing on schedule from an early stage usually means "
                        "the evaluation plan is not agreed.",
                        "evidence": f"Expected close {deal.expected_close_date:%Y-%m-%d} while "
                        f"stage is {deal.stage}.",
                        "suggested_investigation": "Agree a mutual action plan with dated owner "
                        "commitments.",
                        "level": "MEDIUM",
                    }
                )

        if not (deal.next_action or "").strip():
            risks.append(
                {
                    "key": "missing_next_action",
                    "title": "No next action recorded",
                    "why_it_matters": "Without a committed next step, momentum depends entirely "
                    "on the customer.",
                    "evidence": "The next action field is empty.",
                    "suggested_investigation": "Record the next meeting, its owner and its goal.",
                    "level": "LOW",
                }
            )

        losses = self._similar_historical_losses(organization_id, deal)
        if losses["count"] > 0:
            risks.append(
                {
                    "key": "similar_historical_losses",
                    "title": "Similar historical deals were lost",
                    "why_it_matters": "A repeated failure pattern is worth checking before it "
                    "repeats on this opportunity.",
                    "evidence": losses["evidence"],
                    "suggested_investigation": losses["suggested"],
                    "level": "HIGH" if losses["count"] >= 3 else "MEDIUM",
                }
            )

        risks.sort(key=lambda r: _LEVEL_ORDER.get(r.get("level", "MEDIUM"), 1))
        return risks

    # ------------------------------------------------------------- helpers
    def _objection_history(self, organization_id: uuid.UUID, objection_id: uuid.UUID) -> dict:
        rows = self.session.execute(
            select(Deal.outcome)
            .join(DealObjection, DealObjection.deal_id == Deal.id)
            .where(
                Deal.organization_id == organization_id,
                DealObjection.objection_id == objection_id,
                Deal.outcome.is_not(None),
            )
        ).all()
        outcomes = [r[0] for r in rows]
        return {"total": len(outcomes), "lost": sum(1 for o in outcomes if o == "LOST")}

    def _pricing_objection_counts(self, organization_id: uuid.UUID) -> dict:
        pricing_terms = ("pricing", "budget", "cost")
        labels = [
            o.id
            for o in self.session.execute(
                select(Objection).where(Objection.organization_id == organization_id)
            ).scalars()
            if o.label.lower().startswith(pricing_terms)
        ]
        if not labels:
            return {"total": 0, "lost": 0}
        rows = self.session.execute(
            select(Deal.outcome)
            .join(DealObjection, DealObjection.deal_id == Deal.id)
            .where(
                Deal.organization_id == organization_id,
                DealObjection.objection_id.in_(labels),
                Deal.outcome.is_not(None),
            )
        ).all()
        outcomes = [r[0] for r in rows]
        return {"total": len(outcomes), "lost": sum(1 for o in outcomes if o == "LOST")}

    def _competitor_losses(self, organization_id: uuid.UUID, deal_competitors) -> dict:
        ids = [dc.competitor_id for dc in deal_competitors]
        rows = self.session.execute(
            select(Deal.outcome)
            .join(DealCompetitor, DealCompetitor.deal_id == Deal.id)
            .where(
                Deal.organization_id == organization_id,
                DealCompetitor.competitor_id.in_(ids),
                Deal.outcome.is_not(None),
            )
        ).all()
        outcomes = [r[0] for r in rows]
        return {"total": len(outcomes), "lost": sum(1 for o in outcomes if o == "LOST")}

    def _similar_historical_losses(self, organization_id: uuid.UUID, deal: Deal) -> dict:
        similarity = SimilarDealService(self.session).find_similar(
            organization_id, deal, include_memory=False, limit=6
        )
        lost = [s for s in similarity["similar_deals"] if s.get("outcome") == "LOST"]
        if not lost:
            return {"count": 0, "evidence": "", "suggested": ""}
        reasons = [s.get("loss_reason") for s in lost if s.get("loss_reason")]
        names = ", ".join(f"{s['deal_name']} ({s['customer_name']})" for s in lost[:3])
        evidence = f"{len(lost)} similar closed deal(s) ended lost: {names}."
        if reasons:
            unique = sorted({r.strip().split(".")[0] for r in reasons})[:3]
            evidence += f" Recorded loss reasons: {'; '.join(unique)}."
        return {
            "count": len(lost),
            "evidence": evidence,
            "suggested": "Compare this opportunity against those losses and address the recorded "
            "reason explicitly.",
        }
