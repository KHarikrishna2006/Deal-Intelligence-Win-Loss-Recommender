from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Deal, DealCompetitor, DealObjection, Interaction, Objection
from app.models.enums import DealStage

MIN_CLOSED_FOR_INSIGHT = 3


def _reason_key(text: Optional[str]) -> str:
    if not text:
        return "Not recorded"
    first = text.strip().split(".")[0].strip()
    return first[:90] if first else "Not recorded"


class WinLossService:
    """Computes win/loss intelligence from PostgreSQL records only.

    When there is not enough closed history, the response says so instead of
    inventing statistics.
    """

    def __init__(self, session: Session):
        self.session = session

    def analyze(self, organization_id: uuid.UUID) -> dict[str, Any]:
        closed = list(
            self.session.execute(
                select(Deal).where(
                    Deal.organization_id == organization_id,
                    Deal.outcome.is_not(None),
                )
            ).scalars()
        )
        all_deals = list(
            self.session.execute(
                select(Deal).where(Deal.organization_id == organization_id)
            ).scalars()
        )

        won = [d for d in closed if d.outcome == "WON"]
        lost = [d for d in closed if d.outcome == "LOST"]
        total_closed = len(closed)
        sufficient = total_closed >= MIN_CLOSED_FOR_INSIGHT

        win_rate = round((len(won) / total_closed) * 100, 1) if total_closed else None

        objections_counter: Counter[str] = Counter()
        objection_losses: Counter[str] = Counter()
        competitor_counter: Counter[str] = Counter()
        competitor_wins: Counter[str] = Counter()
        competitor_losses: Counter[str] = Counter()
        loss_reasons: Counter[str] = Counter()
        win_reasons: Counter[str] = Counter()
        stage_failures: Counter[str] = Counter()
        stage_totals: Counter[str] = Counter()
        requirements_counter: Counter[str] = Counter()
        pricing_losses = 0
        competitor_losses_total = 0

        for deal in closed:
            for do in deal.deal_objections:
                label = do.objection.label
                objections_counter[label] += 1
                if deal.outcome == "LOST":
                    objection_losses[label] += 1
            for dc in deal.deal_competitors:
                name = dc.competitor.name
                competitor_counter[name] += 1
                if deal.outcome == "WON":
                    competitor_wins[name] += 1
                else:
                    competitor_losses[name] += 1
            if deal.outcome == "LOST":
                loss_reasons[_reason_key(deal.loss_reason)] += 1
            else:
                win_reasons[_reason_key(deal.win_reason)] += 1
            stage_totals[deal.stage] += 1
            if deal.outcome == "LOST":
                stage_failures[deal.stage] += 1

        for deal in all_deals:
            for do in deal.deal_objections:
                label = do.objection.label.lower()
                if label.startswith(("pricing", "budget", "cost")) and deal.outcome == "LOST":
                    pricing_losses += 1
            if deal.outcome == "LOST" and deal.deal_competitors:
                competitor_losses_total += 1

        for row in self.session.execute(
            select(Interaction.requirements, Interaction.deal_id).where(
                Interaction.organization_id == organization_id,
                Interaction.requirements.is_not(None),
            )
        ).all():
            for req in row[0] or []:
                requirements_counter[str(req)[:80]] += 1

        avg_cycle = self._average_cycle(closed)
        avg_size = (
            sum(float(d.amount or 0) for d in closed) / total_closed if total_closed else None
        )

        return {
            "kpis": {
                "active_deals": sum(1 for d in all_deals if d.status == "OPEN"),
                "pipeline_value": float(
                    sum(d.amount or 0 for d in all_deals if d.status == "OPEN")
                ),
                "won_deals": len(won),
                "lost_deals": len(lost),
                "win_rate": win_rate,
                "average_deal_size": round(avg_size, 2) if avg_size is not None else None,
                "average_sales_cycle_days": avg_cycle,
                "closed_total": total_closed,
            },
            "win_loss_distribution": [
                {"label": "Won", "value": len(won)},
                {"label": "Lost", "value": len(lost)},
            ],
            "pipeline_by_stage": [
                {
                    "label": stage.value,
                    "value": sum(
                        1 for d in all_deals if d.stage == stage.value and d.status == "OPEN"
                    ),
                    "secondary": float(
                        sum(
                            d.amount or 0
                            for d in all_deals
                            if d.stage == stage.value and d.status == "OPEN"
                        )
                    ),
                }
                for stage in DealStage
                if stage not in (DealStage.CLOSED_WON, DealStage.CLOSED_LOST)
            ],
            "common_objections": [
                {"label": k, "value": v} for k, v in objections_counter.most_common(10)
            ],
            "common_competitors": [
                {"label": k, "value": v} for k, v in competitor_counter.most_common(10)
            ],
            "loss_reasons": [
                {"label": k, "value": v} for k, v in loss_reasons.most_common(10)
            ],
            "win_reasons": [{"label": k, "value": v} for k, v in win_reasons.most_common(10)],
            "stage_failure_rates": [
                {
                    "label": stage,
                    "value": round((stage_failures[stage] / stage_totals[stage]) * 100, 1),
                    "secondary": stage_totals[stage],
                }
                for stage, total in stage_totals.most_common()
                if total
            ],
            "competitor_outcomes": [
                {
                    "competitor": name,
                    "total": competitor_counter[name],
                    "won": competitor_wins[name],
                    "lost": competitor_losses[name],
                }
                for name in competitor_counter.most_common(10)
            ],
            "pricing_related_losses": pricing_losses,
            "competitor_related_losses": competitor_losses_total,
            "recurring_requirements": [
                {"label": k, "value": v} for k, v in requirements_counter.most_common(10)
            ],
            "sufficient_data": sufficient,
            "data_quality": {
                "closed_deals": total_closed,
                "minimum_required": MIN_CLOSED_FOR_INSIGHT,
                "deals_with_loss_reason": sum(
                    1 for d in lost if (d.loss_reason or "").strip()
                ),
                "deals_with_win_reason": sum(1 for d in won if (d.win_reason or "").strip()),
            },
            "insufficient_reason": (
                None
                if sufficient
                else f"Insufficient historical data: {total_closed} closed deal(s) recorded, "
                f"{MIN_CLOSED_FOR_INSIGHT} required for pattern analysis."
            ),
        }

    @staticmethod
    def _average_cycle(closed: list[Deal]) -> Optional[int]:
        days = []
        for deal in closed:
            if deal.created_at and deal.closed_at:
                delta = deal.closed_at - deal.created_at
                if delta.total_seconds() > 0:
                    days.append(delta.days)
        return int(round(sum(days) / len(days))) if days else None

    def objection_stats(self, organization_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(Objection.label, Deal.outcome)
            .join(DealObjection, DealObjection.objection_id == Objection.id)
            .join(Deal, Deal.id == DealObjection.deal_id)
            .where(Deal.organization_id == organization_id, Deal.outcome.is_not(None))
        ).all()
        totals: Counter[str] = Counter()
        losses: Counter[str] = Counter()
        for label, outcome in rows:
            totals[label] += 1
            if outcome == "LOST":
                losses[label] += 1
        return [
            {"label": label, "total": total, "lost": losses[label]}
            for label, total in totals.most_common()
        ]
