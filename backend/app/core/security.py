from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings
from app.core.exceptions import UnauthorizedError

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode(
        "utf-8"
    )


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: str,
    *,
    organization_id: str,
    role: str,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    minutes = expires_minutes or settings.jwt_expires_minutes
    exp = now + timedelta(minutes=minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "org": organization_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "deal-intelligence",
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, exp


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "org", "role"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Session expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid session token.") from exc
