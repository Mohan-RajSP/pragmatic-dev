"""Service layer for the mental-health tips feature.

The backend only *reads* tips from Redis (the Celery worker generates and
writes them) and toggles the liveness trigger. Tips are stored in a Redis list
where index 0 is the newest (worker uses LPUSH + LTRIM to cap the size).
"""

from __future__ import annotations

import json

import redis.asyncio as redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.tip import Tip
from app.services.task_dispatcher import TaskDispatcher

logger = get_logger(__name__)


class TipService:
    """Reads tips and manages the liveness trigger in Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        dispatcher: TaskDispatcher,
        settings: Settings | None = None,
    ) -> None:
        self._redis = redis_client
        self._dispatcher = dispatcher
        self._settings = settings or get_settings()

    async def get_latest_tip(self) -> Tip | None:
        """Return the newest tip (list index 0) or None if the cache is empty."""
        raw = await self._redis.lindex(self._settings.tips_list_key, 0)
        if not raw:
            return None
        return self._parse(raw)

    async def set_liveness_trigger(self) -> None:
        """Mark that the frontend is alive so the worker generates a fresh tip."""
        await self._redis.set(self._settings.tips_trigger_key, "true")
        logger.debug("Liveness trigger set to true")

    async def ensure_tip_available(self) -> bool:
        """Force an immediate tip generation if the cache is empty (cold start).

        Uses a short-lived `SET NX` lock so that concurrent liveness pings (many
        tabs / users) dispatch at most one bootstrap task. Returns True if a
        generation task was dispatched.
        """
        if await self.get_latest_tip() is not None:
            return False

        acquired = await self._redis.set(
            self._settings.tip_bootstrap_lock_key,
            "1",
            nx=True,
            ex=self._settings.tip_bootstrap_lock_ttl,
        )
        if not acquired:
            logger.debug("Cold-start dispatch skipped; another request holds the lock")
            return False

        await self._dispatcher.dispatch_tip_generation(force=True)
        logger.info("Cold start: dispatched immediate tip-generation task")
        return True

    @staticmethod
    def _parse(raw: str) -> Tip | None:
        try:
            return Tip.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse tip payload from Redis: %r", raw)
            return None


def get_tip_service() -> TipService:
    """FastAPI dependency factory for `TipService`."""
    from app.services.redis_client import get_redis
    from app.services.task_dispatcher import get_task_dispatcher

    return TipService(get_redis(), get_task_dispatcher())

