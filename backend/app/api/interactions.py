from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.repositories.interaction_repository import InteractionRepository
from app.schemas.interaction import InteractionDetailOut, InteractionOut

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.get("", response_model=dict)
def list_interactions(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    deal_id: Annotated[Optional[uuid.UUID], Query()] = None,
    customer_id: Annotated[Optional[uuid.UUID], Query()] = None,
    type_: Annotated[Optional[str], Query(alias="type")] = None,
    search: Annotated[Optional[str], Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    repo = InteractionRepository(db)
    if deal_id:
        rows = repo.list_for_deal(deal_id, limit=limit, offset=offset)
        total = repo.count_for_deal(deal_id)
    else:
        rows, total = repo.list_for_org(
            organization.id,
            type_=type_,
            search=search,
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )
    return {
        "items": [InteractionOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{interaction_id}", response_model=InteractionDetailOut)
def get_interaction(
    interaction_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
):
    repo = InteractionRepository(db)
    row = repo.get(organization.id, interaction_id)
    from app.core.exceptions import NotFoundError

    if row is None:
        raise NotFoundError("Interaction not found.")
    return InteractionDetailOut(
        id=row.id,
        deal_id=row.deal_id,
        interaction_type=row.interaction_type,
        title=row.title,
        body=row.body,
        channel=row.channel,
        direction=row.direction,
        duration_minutes=row.duration_minutes,
        sentiment=row.sentiment,
        price_discussed=row.price_discussed,
        currency=row.currency,
        commitments=row.commitments,
        requirements=row.requirements,
        extracted=row.extracted,
        occurred_at=row.occurred_at,
        created_at=row.created_at,
        is_demo=row.is_demo,
        participants=[
            {"id": p.id, "name": p.name, "role": p.role, "side": p.side}
            for p in row.participants
        ],
        author_name=None,
    )
