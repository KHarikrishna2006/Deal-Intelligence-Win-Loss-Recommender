from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import analytics, auth, customers, deals, health, interactions, memory, recommendations
from app.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger, request_id_var

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "AI Deal Intelligence & Win-Loss Recommender. PostgreSQL is the source of "
            "truth; Hindsight is the contextual memory layer."
        ),
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["x-request-id"] = request_id
        if not request.url.path.endswith(("/health", "/ready")):
            logger.info(
                "%s %s -> %s (%sms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": getattr(request.state, "request_id", "-"),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = detail
        else:
            payload = {"code": "http_error", "message": str(detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    **payload,
                    "request_id": getattr(request.state, "request_id", "-"),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request payload is invalid.",
                    "details": exc.errors(),
                    "request_id": getattr(request.state, "request_id", "-"),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error.",
                    "request_id": getattr(request.state, "request_id", "-"),
                }
            },
        )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(customers.router, prefix=settings.api_prefix)
    app.include_router(deals.router, prefix=settings.api_prefix)
    app.include_router(interactions.router, prefix=settings.api_prefix)
    app.include_router(recommendations.router, prefix=settings.api_prefix)
    app.include_router(memory.router, prefix=settings.api_prefix)
    app.include_router(analytics.router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": settings.app_name, "api": settings.api_prefix, "docs": "/api/docs"}

    return app


app = create_app()
