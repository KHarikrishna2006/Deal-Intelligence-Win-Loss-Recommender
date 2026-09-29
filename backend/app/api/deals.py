from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentOrganization, CurrentUser, DbSession, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import Action
from app.models import CopilotMessage, Deal, User
from app.models.enums import DealStage, DealStatus
from app.repositories.deal_repository import DealRepository
from app.schemas.deal import (
    CompetitorIn,
    DealCreate,
    DealDetailOut,
    DealOut,
    DealOutcomeIn,
    DealSummaryOut,
    DealUpdate,
    ObjectionIn,
    PipelineOut,
    StageStat,
)
from app.schemas.interaction import InteractionCreate, InteractionDetailOut
from app.schemas.recommendation import CopilotIn, CopilotOut, RecommendationCreateOut
from app.schemas.analytics import MemoryReferenceOut, TimelineItem
from app.services.audit_service import AuditService
from app.services.copilot_service import CopilotService
from app.services.deal_service import DealService
from app.services.interaction_service import InteractionService
from app.services.memory_service import MemoryService
from app.services.recommendation_service import RecommendationService
from app.services.similarity_service import SimilarDealService

router = APIRouter(prefix="/deals", tags=["deals"])


def _get_deal(db: DbSession, org, deal_id: uuid.UUID) -> Deal:
    return DealService(db).get(org.id, deal_id)


@router.get("", response_model=dict)
def list_deals(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    owner_id: Annotated[Optional[uuid.UUID], Query()] = None,
    stage: Annotated[Optional[str], Query()] = None,
    status: Annotated[Optional[str], Query()] = None,
    outcome: Annotated[Optional[str], Query()] = None,
    customer_id: Annotated[Optional[uuid.UUID], Query()] = None,
    competitor: Annotated[Optional[str], Query()] = None,
    min_amount: Annotated[Optional[Decimal], Query(ge=0)] = None,
    max_amount: Annotated[Optional[Decimal], Query(ge=0)] = None,
    risk: Annotated[Optional[str], Query()] = None,
    from_date: Annotated[Optional[str], Query()] = None,
    to_date: Annotated[Optional[str], Query()] = None,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[str, Query()] = "updated_at",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
):
    from datetime import date as _date

    service = DealService(db)
    rows, total = service.list(
        organization.id,
        owner_id=owner_id,
        stage=stage,
        status=status,
        outcome=outcome,
        customer_id=customer_id,
        competitor=competitor,
        min_amount=min_amount,
        max_amount=max_amount,
        risk=risk,
        from_date=_date.fromisoformat(from_date) if from_date else None,
        to_date=_date.fromisoformat(to_date) if to_date else None,
        search=search,
        limit=limit,
        offset=offset,
        sort=sort,
        direction=direction,
    )
    return {
        "items": [service.serialize_summary(d) for d in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=DealOut, status_code=201)
def create_deal(
    payload: DealCreate,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.create(organization.id, user, payload)
    AuditService(db).record(
        action="deal.create",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="deal",
        entity_id=str(deal.id),
    )
    db.flush()
    return DealOut.model_validate(service.serialize_summary(deal))


@router.get("/pipeline", response_model=PipelineOut)
def pipeline(user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    service = DealService(db)
    rows, _ = service.list(organization.id, status=DealStatus.OPEN.value, limit=500)
    buckets: dict[str, list[Deal]] = {}
    for deal in rows:
        buckets.setdefault(deal.stage, []).append(deal)
    stages = [
        StageStat(
            stage=stage.value,
            count=len(buckets.get(stage.value, [])),
            total_amount=sum((d.amount or 0) for d in buckets.get(stage.value, [])),
        )
        for stage in DealStage
    ]
    return PipelineOut(
        stages=stages,
        total_open_amount=sum((d.amount or 0) for d in rows),
        open_count=len(rows),
    )


@router.get("/{deal_id}", response_model=DealDetailOut)
def get_deal(deal_id: uuid.UUID, user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    return DealDetailOut.model_validate(service.serialize_detail(deal))


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    deal = service.update(organization.id, user, deal, payload)
    AuditService(db).record(
        action="deal.update",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="deal",
        entity_id=str(deal.id),
        detail=payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.flush()
    return DealOut.model_validate(service.serialize_summary(deal))


@router.delete("/{deal_id}", response_model=DealOut)
def archive_deal(deal_id: uuid.UUID, user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    deal = service.archive(organization.id, user, deal)
    AuditService(db).record(
        action="deal.archive",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="deal",
        entity_id=str(deal.id),
    )
    return DealOut.model_validate(service.serialize_summary(deal))


@router.post("/{deal_id}/outcome", response_model=DealOut)
def record_outcome(
    deal_id: uuid.UUID,
    payload: DealOutcomeIn,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    deal = service.record_outcome(organization.id, user, deal, payload)
    AuditService(db).record(
        action="deal.outcome",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="deal",
        entity_id=str(deal.id),
        detail={"outcome": payload.outcome},
    )
    db.flush()
    return DealOut.model_validate(service.serialize_summary(deal))


@router.get("/{deal_id}/timeline", response_model=list[TimelineItem])
def timeline(deal_id: uuid.UUID, user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    DealService(db).get(organization.id, deal_id)
    items = MemoryService(db).deal_timeline(deal_id)
    return [TimelineItem(**item) for item in items]


@router.get("/{deal_id}/memory", response_model=dict)
def deal_memory(deal_id: uuid.UUID, user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    DealService(db).get(organization.id, deal_id)
    memory = MemoryService(db)
    references, total = memory.list_references(organization.id, deal_id=deal_id, limit=100)
    status = memory.status(organization.id)
    hits, hit_status = memory.recall_for_deal(
        organization.id,
        [
            f"history of deal {deal_id}",
            "objections competitors pricing and outcomes recorded for this deal",
        ],
        max_tokens=2000,
    )
    wanted = str(deal_id)
    scoped = [
        h for h in hits if (h.get("metadata") or {}).get("deal_id") == wanted
    ]
    related = [
        h for h in hits if (h.get("metadata") or {}).get("deal_id") != wanted
    ]
    return {
        "status": status,
        "references": [MemoryReferenceOut.model_validate(r).model_dump(mode="json") for r in references],
        "total": total,
        "recalled": scoped[:20],
        "related": related[:10],
        "related_count": len(related),
        "recall_status": hit_status,
    }


@router.get("/{deal_id}/similar", response_model=dict)
def similar_deals(
    deal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    include_memory: Annotated[bool, Query()] = True,
):
    deal = DealService(db).get(organization.id, deal_id)
    result = SimilarDealService(db).find_similar(
        organization.id, deal, include_memory=include_memory
    )
    result["deal_id"] = str(deal.id)
    return result


@router.post("/{deal_id}/analyze", response_model=RecommendationCreateOut)
def analyze_deal(
    deal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    regenerate: Annotated[bool, Query()] = False,
    include_memory: Annotated[bool, Query()] = True,
):
    from app.schemas.recommendation import RecommendationOut

    deal = DealService(db).get(organization.id, deal_id)
    result = RecommendationService(db).analyze(
        organization.id,
        deal,
        include_memory=include_memory,
        regenerate=regenerate,
        actor_id=user.id,
    )
    AuditService(db).record(
        action="deal.analyze",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="deal",
        entity_id=str(deal.id),
        detail={"method": result["method"]},
    )
    db.flush()
    return RecommendationCreateOut(
        recommendation=RecommendationOut.model_validate(result["recommendation"]),
        similar_deals=result["similar_deals"],
        risks=result["risks"],
        memory_hits=result["memory_hits"],
        memory_status=result["memory_status"],
        llm_status=result.get("llm_status") or {},
        method=result["method"],
        warnings=result.get("warnings") or [],
    )


@router.get("/{deal_id}/recommendations", response_model=dict)
def list_recommendations(
    deal_id: uuid.UUID, user: CurrentUser, db: DbSession, organization: CurrentOrganization
):
    from app.schemas.recommendation import FeedbackOut, RecommendationOut

    from app.repositories.recommendation_repository import RecommendationRepository

    DealService(db).get(organization.id, deal_id)
    repo = RecommendationRepository(db)
    rows = repo.list_for_deal(deal_id)
    out = []
    for row in rows:
        item = RecommendationOut.model_validate(row).model_dump(mode="json")
        item["feedback"] = [
            FeedbackOut.model_validate(f).model_dump(mode="json") for f in repo.feedback_for(row.id)
        ]
        out.append(item)
    return {"items": out, "total": len(out)}


@router.post("/{deal_id}/copilot", response_model=CopilotOut)
def copilot(
    deal_id: uuid.UUID,
    payload: CopilotIn,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    deal = DealService(db).get(organization.id, deal_id)
    result = CopilotService(db).ask(organization.id, deal, payload.question)

    db.add(
        CopilotMessage(
            organization_id=organization.id,
            deal_id=deal.id,
            user_id=user.id,
            role="user",
            content=payload.question,
        )
    )
    db.add(
        CopilotMessage(
            organization_id=organization.id,
            deal_id=deal.id,
            user_id=user.id,
            role="assistant",
            content=result["answer"],
            citations=result["citations"],
            tool_trace=result["tool_trace"],
            unavailable_reason=result.get("unavailable_reason"),
            created_at_model=result.get("model"),
        )
    )
    db.flush()
    return CopilotOut(**result)


class CompetitorBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    strength: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = None


@router.post("/{deal_id}/competitors", status_code=201)
def add_competitor(
    deal_id: uuid.UUID,
    payload: CompetitorBody,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    row = service.add_competitor(deal, payload.name, payload.strength, payload.notes)
    db.flush()
    return {"id": str(row.id), "competitor": row.competitor.name, "strength": row.strength}


@router.post("/{deal_id}/objections", status_code=201)
def add_objection(
    deal_id: uuid.UUID,
    payload: ObjectionIn,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    row = service.add_objection(deal, payload.label, payload.status, payload.resolution)
    db.flush()
    return {"id": str(row.id), "objection": row.objection.label, "status": row.status}


class ResolveObjectionBody(BaseModel):
    resolution: str = Field(min_length=1, max_length=2000)


@router.patch("/{deal_id}/objections/{objection_id}")
def resolve_objection(
    deal_id: uuid.UUID,
    objection_id: uuid.UUID,
    payload: ResolveObjectionBody,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    service = DealService(db)
    deal = service.get(organization.id, deal_id)
    row = service.resolve_objection(deal, objection_id, payload.resolution)
    db.flush()
    return {"id": str(row.id), "objection": row.objection.label, "status": row.status}


@router.post("/{deal_id}/interactions", response_model=InteractionDetailOut, status_code=201)
def add_interaction(
    deal_id: uuid.UUID,
    payload: InteractionCreate,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    deal = DealService(db).get(organization.id, deal_id)
    interaction = InteractionService(db).ingest(organization.id, deal, payload, actor_id=user.id)
    AuditService(db).record(
        action="interaction.create",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="interaction",
        entity_id=str(interaction.id),
        detail={"deal_id": str(deal.id)},
    )
    db.flush()
    data = {
        "id": interaction.id,
        "deal_id": interaction.deal_id,
        "interaction_type": interaction.interaction_type,
        "title": interaction.title,
        "body": interaction.body,
        "channel": interaction.channel,
        "direction": interaction.direction,
        "duration_minutes": interaction.duration_minutes,
        "sentiment": interaction.sentiment,
        "price_discussed": interaction.price_discussed,
        "currency": interaction.currency,
        "commitments": interaction.commitments,
        "requirements": interaction.requirements,
        "extracted": interaction.extracted,
        "occurred_at": interaction.occurred_at,
        "created_at": interaction.created_at,
        "is_demo": interaction.is_demo,
        "participants": [
            {
                "id": p.id,
                "name": p.name,
                "role": p.role,
                "side": p.side,
            }
            for p in interaction.participants
        ],
        "author_name": user.full_name,
    }
    return InteractionDetailOut(**data)


@router.get("/{deal_id}/interactions", response_model=dict)
def list_interactions(
    deal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    DealService(db).get(organization.id, deal_id)
    from app.repositories.interaction_repository import InteractionRepository

    repo = InteractionRepository(db)
    rows = repo.list_for_deal(deal_id, limit=limit, offset=offset)
    total = repo.count_for_deal(deal_id)
    from app.schemas.interaction import InteractionOut

    return {
        "items": [InteractionOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
    }
