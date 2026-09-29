from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_client_ip, permissions_for
from app.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationAppError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Organization, User
from app.schemas.auth import LoginIn, OrganizationOut, RegisterIn, SessionOut, TokenOut, UserOut
from app.services.audit_service import AuditService

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(value: str) -> str:
    keep = "".join(c.lower() if c.isalnum() else "-" for c in value.strip())
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-")[:60] or "org"


def _issue(db, user: User, organization: Organization, request: Request) -> SessionOut:
    token, expires_at = create_access_token(
        str(user.id),
        organization_id=str(organization.id),
        role=user.role,
    )
    return SessionOut(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(organization),
        permissions=permissions_for(user.role),
    )


@router.post("/register", response_model=SessionOut, status_code=201)
def register(payload: RegisterIn, request: Request, db: DbSession):
    email = payload.email.lower().strip()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise ConflictError("An account with that email already exists.")

    existing_orgs = db.execute(
        select(func.count(Organization.id)).where(Organization.slug == _slugify(payload.organization_name))
    ).scalar_one()
    slug = _slugify(payload.organization_name)
    if existing_orgs:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    organization = Organization(
        name=payload.organization_name.strip(), slug=slug, is_demo=False
    )
    db.add(organization)
    db.flush()

    user = User(
        organization_id=organization.id,
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="ADMIN",
        title=payload.title,
    )
    db.add(user)
    db.flush()

    AuditService(db).record(
        action="auth.register",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    db.flush()
    return _issue(db, user, organization, request)


@router.post("/login", response_model=SessionOut)
def login(payload: LoginIn, request: Request, db: DbSession):
    email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        AuditService(db).record(
            action="auth.login_failed",
            detail={"email": email},
            ip_address=get_client_ip(request),
        )
        raise UnauthorizedError("Incorrect email or password.")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.")

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    organization = db.get(Organization, user.organization_id)
    if organization is None:
        raise UnauthorizedError("Organisation not found.")

    AuditService(db).record(
        action="auth.login",
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="user",
        entity_id=str(user.id),
        ip_address=get_client_ip(request),
    )
    db.flush()
    return _issue(db, user, organization, request)


@router.post("/logout", status_code=204)
def logout(user: CurrentUser, request: Request, db: DbSession):
    AuditService(db).record(
        action="auth.logout",
        organization_id=user.organization_id,
        actor_id=user.id,
        ip_address=get_client_ip(request),
    )
    return Response(status_code=204)


@router.get("/me", response_model=SessionOut)
def me(user: CurrentUser, db: DbSession):
    organization = db.get(Organization, user.organization_id)
    if organization is None:
        raise UnauthorizedError("Organisation not found.")
    return SessionOut(
        access_token="",
        expires_at=datetime.max.replace(tzinfo=timezone.utc),
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(organization),
        permissions=permissions_for(user.role),
    )


@router.get("/users", response_model=list[UserOut])
def list_users(user: CurrentUser, db: DbSession):
    rows = db.execute(
        select(User)
        .where(User.organization_id == user.organization_id)
        .order_by(User.full_name)
    ).scalars()
    return [UserOut.model_validate(r) for r in rows]
