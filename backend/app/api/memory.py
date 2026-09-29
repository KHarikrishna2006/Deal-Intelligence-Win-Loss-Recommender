from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.models import MemoryReference, Recommendation
from app.schemas.analytics import MemoryReferenceOut, MemoryStatusOut, TimelineItem
from app.services.memory_service import MemoryService
from app.services.hindsight_service import HindsightService, HindsightUnavailableError

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/status", response_model=MemoryStatusOut)
def status(user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    info = MemoryService(db).status(organization.id)
    return MemoryStatusOut(
        available=bool(info.get("available")),
        configured_url=info.get("configured_url", ""),
        enabled=bool(info.get("enabled")),
        bank_id=info.get("bank_id"),
        version=info.get("version"),
        reason=info.get("reason"),
        code=info.get("code"),
        local_reference_count=int(info.get("local_reference_count") or 0),
    )


@router.get("/references", response_model=dict)
def references(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    deal_id: Annotated[Optional[uuid.UUID], Query()] = None,
    kind: Annotated[Optional[str], Query()] = None,
    search: Annotated[Optional[str], Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows, total = MemoryService(db).list_references(
        organization.id, deal_id=deal_id, kind=kind, search=search, limit=limit, offset=offset
    )
    return {
        "items": [MemoryReferenceOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/search", response_model=dict)
def search(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    q: Annotated[str, Query(min_length=1, max_length=400)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    use_hindsight: Annotated[bool, Query()] = True,
):
    """Searches the local memory index and, when healthy, Hindsight itself."""
    service = MemoryService(db)
    rows, total = service.list_references(organization.id, search=q, limit=limit)
    local = [MemoryReferenceOut.model_validate(r).model_dump(mode="json") for r in rows]

    remote: list[dict[str, Any]] = []
    remote_status: dict[str, Any] = {"available": False, "reason": "not_requested"}
    if use_hindsight:
        remote, remote_status = service.recall_for_deal(
            organization.id, [q], max_tokens=2000
        )

    return {
        "query": q,
        "local": local,
        "local_total": total,
        "remote": remote,
        "remote_status": remote_status,
    }


@router.get("/timeline", response_model=dict)
def org_timeline(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    deal_id: Annotated[Optional[uuid.UUID], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    if deal_id is None:
        raise NotFoundError("deal_id is required for a deal memory timeline.")
    items = MemoryService(db).deal_timeline(deal_id, limit=limit)
    return {"items": [TimelineItem(**item).model_dump(mode="json") for item in items]}


@router.get("/insights", response_model=dict)
def insights(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    query: Annotated[str, Query(min_length=3, max_length=400)],
):
    """Runs a Hindsight `reflect` over the organisation's memory bank."""
    service = MemoryService(db)
    status_info = service.status(organization.id)
    if not status_info.get("available"):
        return {
            "available": False,
            "reason": status_info.get("reason"),
            "code": status_info.get("code"),
            "text": "",
        }
    hindsight = HindsightService()
    try:
        result = hindsight.reflect_on_memory(
            organization.id,
            query,
            context="Sales deal memory bank for one organisation.",
            budget="low",
        )
    except HindsightUnavailableError as exc:
        return {"available": False, "reason": exc.message, "code": exc.code, "text": ""}
    return {"available": True, "text": result["text"], "structured": result["structured"]}
