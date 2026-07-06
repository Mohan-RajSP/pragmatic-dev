"""Chat endpoints: POST /chat (submit) and GET /chat/stream (SSE reply)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatSubmitResponse
from app.services.chat_service import DONE_MARKER, ChatService, get_chat_service

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatSubmitResponse, summary="Submit a chat message")
async def submit_chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatSubmitResponse:
    """Accept a user message; the reply is delivered via GET /chat/stream."""
    await service.submit_message(payload.session_id, payload.message)
    return ChatSubmitResponse(session_id=payload.session_id)


@router.get("/stream", summary="SSE stream of the assistant reply")
async def stream_chat(
    request: Request,
    session_id: str = Query(..., min_length=1),
    service: ChatService = Depends(get_chat_service),
) -> EventSourceResponse:
    """Stream the assistant's reply token-by-token for the given session."""
    settings = get_settings()

    async def event_generator() -> AsyncIterator[dict]:
        try:
            async for token in service.stream_response(session_id):
                if await request.is_disconnected():
                    logger.debug("Chat SSE client disconnected: %s", session_id)
                    break
                yield {"event": "message", "data": token}
        except Exception:  # pragma: no cover - surfaced to client as error event
            logger.exception("Error while streaming chat response")
            yield {"event": "error", "data": "An error occurred while generating the response."}
        finally:
            yield {"event": "done", "data": DONE_MARKER}

    return EventSourceResponse(
        event_generator(),
        ping=int(settings.sse_heartbeat_interval),
    )

