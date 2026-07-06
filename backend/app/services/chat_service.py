"""Service layer for the chat feature.

Chat uses **direct `astream`** (no Celery). Because SSE (EventSource) is a GET
transport, submission and streaming are split into two steps bridged by Redis:

1. `POST /chat`  -> `submit_message()` stores the pending message in Redis with
   a short TTL, keyed by session_id.
2. `GET /chat/stream` -> `stream_response()` claims that message (atomic
   GETDEL), runs the LangGraph workflow, and yields tokens as they stream.

Each run is scoped to the `session_id` via the LangGraph thread config
(`configurable.thread_id`). The graph's in-process `MemorySaver` uses this key
to keep multi-turn context within a session (volatile — lost on refresh /
restart, which is acceptable for the current phase).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as redis

from app.chains.chat_graph import build_chat_graph
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from langchain_core.messages import HumanMessage

logger = get_logger(__name__)

DONE_MARKER = "[DONE]"


class ChatService:
    """Bridges POST submission and SSE streaming; runs the chat graph."""

    def __init__(self, client: redis.Redis, settings: Settings | None = None) -> None:
        self._redis = client
        self._settings = settings or get_settings()

    def _pending_key(self, session_id: str) -> str:
        return f"{self._settings.chat_pending_key_prefix}{session_id}"

    async def submit_message(self, session_id: str, message: str) -> None:
        """Store the user's message so the SSE stream can pick it up."""
        await self._redis.set(
            self._pending_key(session_id),
            message,
            ex=self._settings.chat_pending_ttl,
        )
        logger.debug("Stored pending chat message for session %s", session_id)

    async def stream_response(self, session_id: str) -> AsyncIterator[str]:
        """Yield assistant tokens for the pending message of this session.

        Yields plain text chunks; the endpoint wraps them as SSE events and
        appends a terminal DONE marker.
        """
        # Atomically claim the pending message (Redis 6.2+ GETDEL).
        message = await self._redis.getdel(self._pending_key(session_id))
        if not message:
            logger.info("No pending message for session %s", session_id)
            yield "No pending message found for this session. Submit via POST /chat first."
            return

        graph = build_chat_graph()
        inputs = {"messages": [HumanMessage(content=message)]}
        # Per-session isolation + memory: `thread_id` scopes this run to the
        # session and is the key the in-process MemorySaver uses to restore the
        # prior turns. We only send the new user message; the checkpointer
        # supplies the history. Memory is volatile (lost on refresh/restart).
        config = {"configurable": {"thread_id": session_id}}

        async for event in graph.astream_events(inputs, version="v2", config=config):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                text = getattr(chunk, "content", "")
                if text:
                    yield text


def get_chat_service() -> ChatService:
    """FastAPI dependency factory for `ChatService`."""
    from app.services.redis_client import get_redis

    return ChatService(get_redis())





