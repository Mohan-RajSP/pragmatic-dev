"""Dispatches background tasks to the Celery worker.

The backend does not import the worker's task code — it enqueues tasks **by
name** onto the shared Redis broker. This keeps the backend and worker
decoupled (they only share the broker URL and a task-name contract).

Contract with the worker:
    task name : settings.tip_generation_task  (default "tips.generate")
    kwargs    : {"force": bool}
        force=True  -> generate a tip unconditionally (cold-start / manual)
        force=False -> generate only if the Redis trigger flag is set (Beat)
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from celery import Celery

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_celery_client() -> Celery:
    """Return a shared Celery client configured against the Redis broker.

    Cached as a per-process singleton (no graceful shutdown needed — it only
    publishes messages; the broker connection is managed by kombu).
    """
    settings = get_settings()
    return Celery(
        "pragmatic-dev-dispatcher",
        broker=settings.effective_broker_url,
        backend=settings.effective_result_backend,
    )


class TaskDispatcher:
    """Thin async-friendly wrapper around Celery `send_task`."""

    def __init__(self, client: Celery, settings: Settings | None = None) -> None:
        self._celery_client = client
        self._settings = settings or get_settings()

    async def dispatch_tip_generation(self, *, force: bool = True) -> None:
        """Enqueue the tip-generation task onto the worker queue.

        Why run `send_task` in a thread:
        `Celery.send_task` is a *synchronous, blocking* call — it performs
        network I/O to publish the message to the Redis broker and has no
        `await` points of its own. If we called it directly here, it would
        block the single event-loop thread for the full duration of that I/O,
        stalling every other concurrent request and SSE stream until it
        returned (and hanging the whole API if the broker were slow).

        `asyncio.to_thread` offloads the blocking call to a worker thread and
        returns an awaitable. Awaiting it yields control back to the event
        loop, which is then free to service other coroutines while the publish
        completes on the other thread. This works well because the call is
        I/O-bound: Python releases the GIL during the blocking socket I/O.

        Args:
            force: True  -> worker generates a tip unconditionally (cold start).
                   False -> worker generates only if the Redis trigger is set.
        """
        await asyncio.to_thread(
            self._celery_client.send_task,
            self._settings.tip_generation_task,
            kwargs={"force": force},
        )
        logger.info(
            "Dispatched tip-generation task '%s' (force=%s)",
            self._settings.tip_generation_task,
            force,
        )


def get_task_dispatcher() -> TaskDispatcher:
    """FastAPI dependency factory for `TaskDispatcher`."""
    return TaskDispatcher(get_celery_client())

