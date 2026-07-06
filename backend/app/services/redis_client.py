"""Async Redis connection provider (singleton).

A single shared connection pool is created for the process lifetime and
disposed on shutdown. This keeps connection handling in one place (SRP) and
lets endpoints/services depend on an abstraction via `get_redis()`.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return the shared async Redis client, creating it on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Initialized Redis client at %s", settings.redis_url)
    return _client


async def close_redis() -> None:
    """Close the shared Redis client (called on app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Closed Redis client")

