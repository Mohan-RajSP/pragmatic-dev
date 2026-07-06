"""FastAPI application entrypoint.

Wires together configuration, logging, CORS, routers, and lifecycle hooks.
Run in dev with: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.redis_client import close_redis, get_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown resources (Redis connection pool)."""
    configure_logging()
    get_redis()  # eagerly initialize the shared client
    logger.info("Application startup complete")
    try:
        yield
    finally:
        await close_redis()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Application factory (keeps construction testable and explicit)."""
    settings = get_settings()
    app = FastAPI(
        title="Pragmatic-dev Backend",
        version="0.1.0",
        description="Mental-health tips + chat backend.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Only apply a prefix when explicitly set. Guard against an empty/whitespace
    # value and normalize a missing leading slash (FastAPI requires "/...").
    prefix = settings.api_prefix.strip()
    if prefix and not prefix.startswith("/"):
        prefix = f"/{prefix}"
    if prefix:
        app.include_router(api_router, prefix=prefix)
    else:
        app.include_router(api_router)
    return app


app = create_app()

