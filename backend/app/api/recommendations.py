from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.core.permissions import Action, ensure_role
from app.models import Recommendation, RecommendationFeedback
from app.repositories.recommendation_repository import RecommendationRepository
from app.schemas.recommendation import (
    AnalyzeRequest,
    FeedbackIn,
    FeedbackOut,
    RecommendationOut,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=dict)
def list_recommendations(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    kind: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    repo = RecommendationRepository(db)
    rows, total = repo.list_for_org(organization.id, kind=kind, limit=limit, offset=offset)
    return {
        "items": [RecommendationOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{recommendation_id}", response_model=dict)
def get_recommendation(
    recommendation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    row = db.get(Recommendation, recommendation_id)
    if row is None or row.organization_id != organization.id:
        raise NotFoundError("Recommendation not found.")
    repo = RecommendationRepository(db)
    data = RecommendationOut.model_validate(row).model_dump(mode="json")
    data["feedback"] = [
        FeedbackOut.model_validate(f).model_dump(mode="json") for f in repo.feedback_for(row.id)
    ]
    return data


@router.post("/{recommendation_id}/feedback", response_model=FeedbackOut, status_code=201)
def give_feedback(
    recommendation_id: uuid.UUID,
    payload: FeedbackIn,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    row = db.get(Recommendation, recommendation_id)
    if row is None or row.organization_id != organization.id:
        raise NotFoundError("Recommendation not found.")
    repo = RecommendationRepository(db)
    saved = repo.upsert_feedback(
        recommendation_id=row.id,
        user_id=user.id,
        feedback=payload.feedback,
        comment=payload.comment,
    )
    AuditService(db).record(
        action="recommendation.feedback",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="recommendation",
        entity_id=str(row.id),
        detail={"feedback": payload.feedback},
    )
    db.flush()
    return FeedbackOut.model_validate(saved)
