"""Synchronous Redis client provider for the worker.

Celery tasks run in synchronous worker processes, so we use the sync `redis`
client here (not `redis.asyncio`). The client is a per-process singleton via
`@lru_cache` (consistent with `get_settings`).
"""

from __future__ import annotations

from functools import lru_cache

import redis

from worker.core.config import get_settings
from worker.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_redis() -> redis.Redis:
    """Return the shared sync Redis client (created once per process)."""
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Initialized Redis client at %s", settings.redis_url)
    return client


