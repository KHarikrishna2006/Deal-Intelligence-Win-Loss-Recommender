from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(Exception):
    """Base class for errors that map cleanly onto an HTTP response."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code

    def to_http(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail={"code": self.code, "message": self.message, "details": self.details},
        )


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class UpstreamUnavailableError(AppError):
    """Hindsight / LLM / other dependency is unreachable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "upstream_unavailable"


class InsufficientDataError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "insufficient_data"
