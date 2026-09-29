from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


class AuditService:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        action: str,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        row = AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=ip_address,
            request_id=request_id,
        )
        self.session.add(row)
        return row

    def recent(
        self, organization_id: uuid.UUID, limit: int = 50
    ) -> list[AuditLog]:
        return list(
            self.session.execute(
                select(AuditLog)
                .where(AuditLog.organization_id == organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            ).scalars()
        )
