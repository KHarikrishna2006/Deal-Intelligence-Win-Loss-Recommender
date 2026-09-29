from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Recommendation, RecommendationFeedback


class RecommendationRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, recommendation: Recommendation) -> Recommendation:
        self.session.add(recommendation)
        return recommendation

    def latest_for_deal(
        self, deal_id: uuid.UUID, *, active_only: bool = True
    ) -> Optional[Recommendation]:
        stmt = select(Recommendation).where(Recommendation.deal_id == deal_id)
        if active_only:
            stmt = stmt.where(Recommendation.status == "ACTIVE")
        return self.session.execute(
            stmt.order_by(Recommendation.created_at.desc()).limit(1)
        ).scalar_one_or_none()

    def list_for_deal(self, deal_id: uuid.UUID, limit: int = 50) -> list[Recommendation]:
        return list(
            self.session.execute(
                select(Recommendation)
                .where(Recommendation.deal_id == deal_id)
                .order_by(Recommendation.created_at.desc())
                .limit(limit)
            ).scalars()
        )

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Recommendation], int]:
        stmt = select(Recommendation).where(
            Recommendation.organization_id == organization_id
        )
        count = select(func.count(Recommendation.id)).where(
            Recommendation.organization_id == organization_id
        )
        if kind:
            stmt = stmt.where(Recommendation.kind == kind)
            count = count.where(Recommendation.kind == kind)
        rows = list(
            self.session.execute(
                stmt.order_by(Recommendation.created_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        total = int(self.session.execute(count).scalar_one() or 0)
        return rows, total

    def mark_stale_for_deal(self, deal_id: uuid.UUID, reason: str | None = None) -> int:
        stmt = select(Recommendation).where(
            Recommendation.deal_id == deal_id, Recommendation.status == "ACTIVE"
        )
        rows = list(self.session.execute(stmt).scalars())
        for row in rows:
            row.status = "SUPERSEDED"
        return len(rows)

    def feedback_for(self, recommendation_id: uuid.UUID) -> list[RecommendationFeedback]:
        return list(
            self.session.execute(
                select(RecommendationFeedback).where(
                    RecommendationFeedback.recommendation_id == recommendation_id
                )
            ).scalars()
        )

    def upsert_feedback(
        self,
        *,
        recommendation_id: uuid.UUID,
        user_id: uuid.UUID,
        feedback: str,
        comment: str | None,
    ) -> RecommendationFeedback:
        existing = self.session.execute(
            select(RecommendationFeedback).where(
                RecommendationFeedback.recommendation_id == recommendation_id,
                RecommendationFeedback.user_id == user_id,
            )
        ).scalar_one_or_none()
        if existing:
            existing.feedback = feedback
            existing.comment = comment
            return existing
        row = RecommendationFeedback(
            recommendation_id=recommendation_id,
            user_id=user_id,
            feedback=feedback,
            comment=comment,
        )
        self.session.add(row)
        return row
