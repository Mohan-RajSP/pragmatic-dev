"""Celery application + Beat schedule for the worker.

- Broker/back-end default to the shared Redis instance.
- `include` registers the task modules so their `@task` names are discoverable.
- Beat runs the tip-generation task every `tip_schedule_seconds` with
  `force=False` (respects the liveness trigger flag).
"""

from __future__ import annotations

from celery import Celery

from worker.constants import TIP_GENERATION_TASK
from worker.core.config import get_settings
from worker.core.logging import configure_logging

configure_logging()
settings = get_settings()

celery_app = Celery(
    "pragmatic-dev-worker",
    broker=settings.effective_broker_url,
    backend=settings.effective_result_backend,
    include=["worker.tasks.tips"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

# Periodic schedule: generate a tip every N seconds, respecting the trigger.
# `expires` discards a scheduled message if it can't run in time (a newer tick
# supersedes it), preventing backlog build-up during an outage.
celery_app.conf.beat_schedule = {
    "generate-tip-periodically": {
        "task": TIP_GENERATION_TASK,
        "schedule": settings.tip_schedule_seconds,
        "kwargs": {"force": False},
        "options": {"expires": settings.tip_task_expires},
    }
}



