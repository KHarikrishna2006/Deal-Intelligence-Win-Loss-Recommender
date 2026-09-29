from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.schemas.analytics import DashboardOut, SearchOut, WinLossOut
from app.services.analytics_service import AnalyticsService
from app.services.search_service import SearchService
from app.services.win_loss_service import WinLossService

router = APIRouter(tags=["analytics"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    return AnalyticsService(db).dashboard(organization.id)


@router.get("/analytics/win-loss", response_model=WinLossOut)
def win_loss(user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    return WinLossService(db).analyze(organization.id)


@router.get("/analytics/health")
def analytics_health(user: CurrentUser, db: DbSession, organization: CurrentOrganization):
    return AnalyticsService(db).health(organization.id)


@router.get("/search", response_model=SearchOut)
def search(
    user: CurrentUser,
    db: DbSession,
    organization: CurrentOrganization,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    types: Annotated[Optional[str], Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
):
    wanted = [t.strip() for t in types.split(",")] if types else None
    return SearchService(db).search(organization.id, q, types=wanted, limit=limit)
