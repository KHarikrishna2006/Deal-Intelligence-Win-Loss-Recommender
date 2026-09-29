from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Deal, DealEvent, Interaction, Recommendation
from app.models.enums import DealStage
from app.services.win_loss_service import WinLossService, _reason_key


class AnalyticsService:
    def __init__(self, session: Session):
        self.session = session
        self.win_loss = WinLossService(session)

    def dashboard(self, organization_id: uuid.UUID) -> dict[str, Any]:
        deals = list(
            self.session.execute(
                select(Deal).where(Deal.organization_id == organization_id)
            ).scalars()
        )
        analysis = self.win_loss.analyze(organization_id)

        open_deals = [d for d in deals if d.status == "OPEN"]
        won = [d for d in deals if d.outcome == "WON"]
        lost = [d for d in deals if d.outcome == "LOST"]
        closed = won + lost

        competitor_outcomes: dict[str, Counter] = {}
        for deal in closed:
            for dc in deal.deal_competitors:
                bucket = competitor_outcomes.setdefault(dc.competitor.name, Counter())
                bucket["total"] += 1
                bucket["won" if deal.outcome == "WON" else "lost"] += 1

        objections: Counter[str] = Counter()
        for deal in deals:
            for do in deal.deal_objections:
                objections[do.objection.label] += 1

        trend: Counter[str] = Counter()
        for deal in closed:
            if deal.closed_at:
                trend[deal.closed_at.strftime("%Y-%m")] += 1
        for deal in deals:
            trend[deal.created_at.strftime("%Y-%m")] += 1
        trend_points = []
        today = datetime.utcnow().replace(day=1)
        for i in range(11, -1, -1):
            month = (today - timedelta(days=31 * i)).strftime("%Y-%m")
            trend_points.append({"label": month, "value": float(trend.get(month, 0))})

        recent_events = list(
            self.session.execute(
                select(DealEvent)
                .join(Deal, Deal.id == DealEvent.deal_id)
                .where(Deal.organization_id == organization_id)
                .order_by(DealEvent.created_at.desc())
                .limit(12)
            ).scalars()
        )

        kpis = analysis["kpis"]
        kpis["active_deals"] = len(open_deals)
        kpis["pipeline_value"] = float(sum(d.amount or 0 for d in open_deals))
        kpis["won_deals"] = len(won)
        kpis["lost_deals"] = len(lost)
        kpis["closed_total"] = len(closed)
        kpis["win_rate"] = round((len(won) / len(closed)) * 100, 1) if closed else None
        kpis["average_deal_size"] = (
            round(sum(float(d.amount or 0) for d in closed) / len(closed), 2) if closed else None
        )
        kpis["average_sales_cycle_days"] = WinLossService._average_cycle(closed)

        return {
            "kpis": kpis,
            "pipeline_by_stage": [
                {
                    "label": stage.value,
                    "value": float(
                        sum(d.amount or 0 for d in open_deals if d.stage == stage.value)
                    ),
                    "secondary": float(
                        sum(1 for d in open_deals if d.stage == stage.value)
                    ),
                }
                for stage in DealStage
                if stage not in (DealStage.CLOSED_WON, DealStage.CLOSED_LOST)
            ],
            "win_loss": [
                {"label": "Won", "value": len(won)},
                {"label": "Lost", "value": len(lost)},
            ],
            "loss_reasons": analysis["loss_reasons"],
            "competitor_outcomes": [
                {
                    "label": name,
                    "value": float(counts["won"]),
                    "secondary": float(counts["lost"]),
                }
                for name, counts in sorted(
                    competitor_outcomes.items(), key=lambda kv: kv[1]["total"], reverse=True
                )[:8]
            ],
            "objections": [{"label": k, "value": v} for k, v in objections.most_common(8)],
            "deal_trend": trend_points,
            "recent_activity": [
                {
                    "id": str(e.id),
                    "deal_id": str(e.deal_id),
                    "title": e.title,
                    "detail": e.detail,
                    "event_type": e.event_type,
                    "occurred_at": e.occurred_at.isoformat(),
                }
                for e in recent_events
            ],
            "top_competitors": analysis["common_competitors"],
            "top_objections": analysis["common_objections"],
        }

    def health(self, organization_id: uuid.UUID) -> dict[str, Any]:
        return {
            "deals": int(
                self.session.execute(
                    select(func.count(Deal.id)).where(
                        Deal.organization_id == organization_id
                    )
                ).scalar_one()
                or 0
            ),
            "interactions": int(
                self.session.execute(
                    select(func.count(Interaction.id)).where(
                        Interaction.organization_id == organization_id
                    )
                ).scalar_one()
                or 0
            ),
            "recommendations": int(
                self.session.execute(
                    select(func.count(Recommendation.id)).where(
                        Recommendation.organization_id == organization_id
                    )
                ).scalar_one()
                or 0
            ),
        }
