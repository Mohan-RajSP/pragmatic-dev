"""Mental-health tips endpoints: /tip, /tip/liveness, /tip/stream."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.tip import LivenessResponse, TipResponse
from app.services.tip_service import TipService, get_tip_service

logger = get_logger(__name__)
router = APIRouter(prefix="/tip", tags=["tips"])


@router.get("", response_model=TipResponse, summary="Get the latest mental-health tip")
async def get_tip(service: TipService = Depends(get_tip_service)) -> TipResponse:
    """Return the newest tip from the Redis cache (or null if none yet)."""
    return TipResponse(tip=await service.get_latest_tip())


@router.get(
    "/liveness",
    response_model=LivenessResponse,
    summary="Frontend liveness ping (triggers fresh tip generation)",
)
async def liveness(service: TipService = Depends(get_tip_service)) -> LivenessResponse:
    """Set the Redis trigger; on cold start (empty cache) force an immediate tip."""
    await service.set_liveness_trigger()
    # Cold-start safety: if no tip exists yet, don't wait up to 5 min for Beat —
    # dispatch an immediate generation task (deduped via a Redis lock).
    await service.ensure_tip_available()
    return LivenessResponse()


@router.get("/stream", summary="SSE stream of the latest tip")
async def stream_tips(
    request: Request,
    service: TipService = Depends(get_tip_service),
) -> EventSourceResponse:
    """Stream the latest tip to the client, emitting only when it changes.

    Emits two named SSE events:
      - `tip`       → a new tip payload (the client renders it).
      - `heartbeat` → periodic keepalive (the client shows a "waiting" state and
                      proxies keep the connection open).
    """
    settings = get_settings()

    async def event_generator() -> AsyncIterator[dict]:
        last_sent_id: str | None = None
        heartbeat_accum = 0.0
        while True:
            if await request.is_disconnected():
                logger.debug("Tip SSE client disconnected")
                break

            tip = await service.get_latest_tip()
            if tip is not None and tip.id != last_sent_id:
                last_sent_id = tip.id
                yield {"event": "tip", "data": json.dumps(tip.model_dump())}
                heartbeat_accum = 0.0

            await asyncio.sleep(settings.tip_stream_poll_interval)

            # Periodic heartbeat: keeps proxies from closing an idle connection
            # and lets the UI show a "waiting for next tip" state.
            heartbeat_accum += settings.tip_stream_poll_interval
            if heartbeat_accum >= settings.sse_heartbeat_interval:
                heartbeat_accum = 0.0
                yield {"event": "heartbeat", "data": json.dumps({"ts": time.time()})}

    return EventSourceResponse(event_generator())

