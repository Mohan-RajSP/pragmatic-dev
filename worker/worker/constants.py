"""Shared constants for the worker service.

The Celery task name is a **contract** shared with the backend dispatcher, so it
lives here as a single source of truth rather than as scattered string literals.
"""

from __future__ import annotations

# Name under which the tip-generation task is registered on the broker.
# The backend enqueues tasks by this exact name (see PLAN.md contract).
TIP_GENERATION_TASK = "tips.generate"

