from __future__ import annotations

from app.core.exceptions import ForbiddenError


class Role:
    ADMIN = "ADMIN"
    SALES_MANAGER = "SALES_MANAGER"
    SALES_REP = "SALES_REP"

    ALL = (ADMIN, SALES_MANAGER, SALES_REP)
    MANAGERIAL = (ADMIN, SALES_MANAGER)


class Action:
    READ_DEAL = "deal:read"
    WRITE_DEAL = "deal:write"
    DELETE_DEAL = "deal:delete"
    RECORD_OUTCOME = "deal:record_outcome"
    READ_ANALYTICS = "analytics:read"
    MANAGE_USERS = "user:manage"
    MANAGE_ORG = "org:manage"
    EXPORT = "export"


_MATRIX: dict[str, set[str]] = {
    Action.READ_DEAL: set(Role.ALL),
    Action.WRITE_DEAL: set(Role.ALL),
    Action.DELETE_DEAL: set(Role.MANAGERIAL),
    Action.RECORD_OUTCOME: set(Role.ALL),
    Action.READ_ANALYTICS: set(Role.ALL),
    Action.MANAGE_USERS: {Role.ADMIN},
    Action.MANAGE_ORG: {Role.ADMIN},
    Action.EXPORT: set(Role.MANAGERIAL),
}


def allowed_roles(action: str) -> set[str]:
    return _MATRIX.get(action, set())


def ensure_role(role: str, action: str) -> None:
    if role not in allowed_roles(action):
        raise ForbiddenError(f"Role '{role}' is not permitted to perform '{action}'.")


def can_edit_deal(role: str, owner_id: str, user_id: str) -> bool:
    if role in Role.MANAGERIAL:
        return True
    return owner_id == user_id
