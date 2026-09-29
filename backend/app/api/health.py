from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.services.hindsight_service import HindsightService
from app.services.llm_service import LLMService

router = APIRouter(tags=["health"])

_STARTED = time.time()


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe. Never touches a dependency."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - _STARTED, 1),
    }


@router.get("/ready")
def ready(response: Response) -> dict[str, Any]:
    """Readiness probe: database is required, memory/LLM are reported only."""
    checks: dict[str, Any] = {}
    ok = True

    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {
            "available": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["database"] = {"available": False, "error": type(exc).__name__}

    checks["hindsight"] = HindsightService().status()
    checks["llm"] = LLMService().health()

    if not ok:
        response.status_code = 503
    return {
        "status": "ready" if ok else "degraded",
        "checks": checks,
        "degraded_reasons": [
            name for name, value in checks.items() if isinstance(value, dict) and not value.get("available")
        ],
    }
