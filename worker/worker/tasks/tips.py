"""Tip-generation Celery task.

Task name: `tips.generate` (contract shared with the backend dispatcher).

kwargs:
    force=True  -> generate a tip unconditionally (cold-start / manual dispatch).
    force=False -> generate only if the Redis trigger flag is set (Beat path);
                   clears the flag after a successful generation.

Concurrency & retries:
- A Redis lock guarantees only one generation runs at a time (status "locked").
- On failure the task retries with capped exponential backoff, so an early
  failure recovers quickly instead of waiting for the next Beat tick.
- A "retry-in-progress" marker guarantees only ONE retry chain exists: if a
  fresh task (e.g. the next Beat tick) starts while an earlier failure is still
  retrying, it skips ("retry_in_progress") instead of spawning a parallel chain.
"""

from __future__ import annotations

from typing import Any

from celery.exceptions import MaxRetriesExceededError

from worker.celery_app import celery_app
from worker.chains.tip_chain import generate_tip_text
from worker.constants import TIP_GENERATION_TASK
from worker.core.config import get_settings
from worker.core.logging import get_logger
from worker.services.tip_service import get_tip_service

logger = get_logger(__name__)


@celery_app.task(
    name=TIP_GENERATION_TASK,
    bind=True,
    max_retries=get_settings().tip_max_retries,
)
def generate_tip(self: Any, force: bool = False) -> dict[str, Any]:
    """Generate a mental-health tip and store it in Redis.

    Returns a small status dict for observability / result backend.
    """
    settings = get_settings()
    service = get_tip_service()

    # Mutual exclusion: never run two generations concurrently.
    lock = service.acquire_generation_lock()
    if lock is None:
        logger.info("Tip generation skipped: another generation is already running")
        return {"status": "locked"}

    try:
        # Single retry chain: a fresh task (retries == 0) must NOT start a second
        # parallel chain while an earlier failure is still retrying. Continuations
        # of the active chain (retries > 0) proceed normally.
        if self.request.retries == 0 and service.is_retry_in_progress():
            logger.info("Tip generation skipped: a retry chain is already in progress")
            return {"status": "skipped", "reason": "retry_in_progress"}

        # Beat path: only generate when a client has recently pinged liveness.
        if not force and not service.is_triggered():
            logger.info("Tip generation skipped: trigger not set (force=False)")
            return {"status": "skipped", "reason": "trigger_not_set"}

        try:
            text = generate_tip_text()
        except Exception as exc:  # transient LLM/network errors -> retry
            countdown = min(
                settings.tip_retry_base_delay * (2 ** self.request.retries),
                settings.tip_retry_max_delay,
            )
            try:
                # Mark the chain active so a concurrent fresh task won't also
                # retry. TTL covers the gap until the next attempt and self-heals
                # if this worker dies.
                service.mark_retry_in_progress(
                    ttl=countdown + settings.tip_retry_marker_buffer
                )
                logger.warning(
                    "Tip generation failed; retrying in %ss (attempt %d/%d)",
                    countdown,
                    self.request.retries + 1,
                    self.max_retries,
                )
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                # Retry budget exhausted — end the chain and give up cleanly.
                service.clear_retry_in_progress()
                logger.error(
                    "Tip generation failed after %d retries; giving up",
                    self.max_retries,
                )
                return {"status": "failed", "reason": "max_retries_exceeded"}

        tip = service.add_tip(text)
        # Success ends any active retry chain.
        service.clear_retry_in_progress()

        # In the Beat path, reset the trigger so we don't keep regenerating until
        # a fresh liveness ping arrives. (Left untouched on forced/cold-start.)
        if not force:
            service.clear_trigger()

        logger.info("Tip generated (force=%s): %s", force, tip["id"])
        return {"status": "generated", "id": tip["id"], "force": force}
    finally:
        service.release_generation_lock(lock)










