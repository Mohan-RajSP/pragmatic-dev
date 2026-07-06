"""Pydantic schemas for the mental-health tips feature."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Tip(BaseModel):
    """A single mental-health tip."""

    id: str = Field(..., description="Unique tip identifier")
    text: str = Field(..., description="The tip content")
    created_at: float = Field(..., description="Unix timestamp when the tip was created")


class TipResponse(BaseModel):
    """Response for GET /tip."""

    tip: Tip | None = Field(default=None, description="Latest tip, or null if none exist yet")


class LivenessResponse(BaseModel):
    """Response for GET /tip/liveness."""

    message: str = "liveness check successful"

