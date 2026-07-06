"""Health-check endpoint for container orchestration."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service + Redis health check")
async def health() -> dict[str, str]:
    """Return service status and Redis connectivity."""
    redis_status = "ok"
    try:
        await get_redis().ping()
    except Exception:  # pragma: no cover - report degraded rather than crash
        redis_status = "unavailable"
    return {"status": "ok", "redis": redis_status}

