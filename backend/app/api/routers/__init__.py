"""API routers package.

Aggregates every router module into a single `api_router` that the app
includes. Registration lives here (in the package `__init__`) so adding a new
router is a one-line change next to its import.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import chat, health, tips

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tips.router)
api_router.include_router(chat.router)

__all__ = ["api_router"]

