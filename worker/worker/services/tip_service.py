"""Tips service (worker side) — Redis persistence for tips.

Storage model (shared contract with the backend):
- `tips_list_key` is a Redis list, newest at index 0.
  New tips are added with LPUSH, then LTRIM caps the list at `tips_max_items`
  (FIFO — oldest tips fall off the end).
- `tips_trigger_key` is a string flag ("true"/"false") set by the backend's
  liveness endpoint and cleared here after a scheduled generation.
"""

from __future__ import annotations

import json
import time
import uuid

import redis
from redis.exceptions import LockError
from redis.lock import Lock

from worker.core.config import Settings, get_settings
from worker.core.logging import get_logger

logger = get_logger(__name__)


class TipService:
    """Reads/writes tips and the trigger flag in Redis."""

    def __init__(self, redis_client: redis.Redis, settings: Settings | None = None) -> None:
        self._redis = redis_client
        self._settings = settings or get_settings()

    def acquire_generation_lock(self) -> Lock | None:
        """Try to acquire the generation lock without blocking.

        Returns the held `Lock` on success, or `None` if another generation is
        already in progress. The lock has a TTL so it self-heals if a worker
        dies mid-task.
        """
        lock = self._redis.lock(
            self._settings.tips_lock_key,
            timeout=self._settings.tips_lock_ttl,
        )
        acquired = lock.acquire(blocking=False)
        return lock if acquired else None

    def release_generation_lock(self, lock: Lock) -> None:
        """Release the generation lock, tolerating an already-expired lock."""
        try:
            lock.release()
        except LockError:
            # The lock's TTL expired before we released it — nothing to do.
            logger.debug("Generation lock already expired on release")

    def mark_retry_in_progress(self, ttl: int) -> None:
        """Flag that a retry chain is active (with a self-healing TTL)."""
        self._redis.set(self._settings.tips_retry_marker_key, "1", ex=ttl)

    def is_retry_in_progress(self) -> bool:
        """Return True if a retry chain is currently active."""
        return self._redis.exists(self._settings.tips_retry_marker_key) == 1

    def clear_retry_in_progress(self) -> None:
        """Clear the retry-chain marker (on success or exhaustion)."""
        self._redis.delete(self._settings.tips_retry_marker_key)

    def is_triggered(self) -> bool:
        """Return True if the liveness trigger flag is set."""
        return self._redis.get(self._settings.tips_trigger_key) == "true"

    def clear_trigger(self) -> None:
        """Reset the trigger flag after a scheduled generation."""
        self._redis.set(self._settings.tips_trigger_key, "false")
        logger.debug("Trigger flag cleared (set to false)")

    def record_skip(self, reason: str) -> None:
        """Record the latest skipped-generation event for the SSE stream to relay.

        Stores a small JSON payload with a timestamp so the backend stream can
        detect a *new* skip (by comparing `ts`) and emit a `skipped` SSE event.
        A TTL keeps Redis tidy — the value only needs to outlive the poll window.
        """
        payload = {"reason": reason, "ts": time.time()}
        self._redis.set(
            self._settings.tips_skip_event_key,
            json.dumps(payload),
            ex=int(self._settings.tip_schedule_seconds * 2),
        )
        logger.debug("Recorded skip event (reason=%s)", reason)

    def get_recent_tip_texts(self, limit: int | None = None) -> list[str]:
        """Return recent tip texts (newest first) for anti-duplication context.

        Used to prime the LLM prompt so it doesn't repeat or closely paraphrase
        tips it already produced. Malformed entries are skipped defensively.
        """
        end = (limit - 1) if limit else -1
        raw_items = self._redis.lrange(self._settings.tips_list_key, 0, end)
        texts: list[str] = []
        for raw in raw_items:
            try:
                texts.append(json.loads(raw)["text"])
            except (json.JSONDecodeError, KeyError, TypeError):
                # Skip a corrupt/legacy entry rather than fail the whole batch.
                continue
        return texts

    def add_tip(self, text: str) -> dict:
        """Create a tip record, push it as newest, and cap the list size.

        Returns the stored tip dict (matches the backend `Tip` schema).
        """
        tip = {
            "id": str(uuid.uuid4()),
            "text": text,
            "created_at": time.time(),
        }
        pipe = self._redis.pipeline()
        pipe.lpush(self._settings.tips_list_key, json.dumps(tip))
        pipe.ltrim(self._settings.tips_list_key, 0, self._settings.tips_max_items - 1)
        pipe.execute()
        logger.info("Stored new tip %s (cap=%d)", tip["id"], self._settings.tips_max_items)
        return tip


def get_tip_service() -> TipService:
    """Factory for `TipService`."""
    from worker.services.redis_client import get_redis

    return TipService(get_redis())

