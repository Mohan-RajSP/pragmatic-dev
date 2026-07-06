"""Pydantic schemas for the chat feature."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    session_id: str = Field(..., min_length=1, description="Client-generated session identifier")
    message: str = Field(..., min_length=1, max_length=8000, description="User message")


class ChatSubmitResponse(BaseModel):
    """Response for POST /chat — the message is accepted for streaming."""

    session_id: str
    status: str = "accepted"
    detail: str = "Connect to /chat/stream with this session_id to receive the reply."

