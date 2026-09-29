from __future__ import annotations

import uuid
from typing import Annotated, Any, Callable, Generator

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Action, allowed_roles, ensure_role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Organization, User

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication required.")
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Session token is malformed.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is unavailable.")
    if str(user.organization_id) != payload.get("org"):
        raise UnauthorizedError("Session no longer matches the account organisation.")
    if user.role != payload.get("role"):
        raise UnauthorizedError("Session role is out of date. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_organization(user: CurrentUser, db: DbSession) -> Organization:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise ForbiddenError("Organisation not found.")
    return org


CurrentOrganization = Annotated[Organization, Depends(get_organization)]


def require_roles(*roles: str) -> Callable:
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError(f"Role '{user.role}' cannot perform this action.")
        return user

    return checker


def require_permission(action: str) -> Callable:
    def checker(user: CurrentUser) -> User:
        ensure_role(user.role, action)
        return user

    return checker


def permissions_for(role: str) -> list[str]:
    from app.core.permissions import _MATRIX

    return [action for action, roles in _MATRIX.items() if role in roles]
