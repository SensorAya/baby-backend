from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class AlarmTransition(StrEnum):
    TRIGGERED = "triggered"
    CLEARED = "cleared"


class AlarmEventCreate(BaseModel):
    timestamp: int = Field(..., ge=0, examples=[1752000660])
    event: AlarmTransition
    face_ratio: int = Field(..., ge=0, le=100, examples=[20])
    baby_ratio: int = Field(..., ge=0, le=100, examples=[20])


class AlarmEventResponse(AlarmEventCreate):
    id: UUID
    user_id: UUID
    session_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlarmStateResponse(BaseModel):
    active: bool
    alarm: AlarmEventResponse | None


class AlarmStreamMessage(BaseModel):
    type: str
    active: bool
    alarm: AlarmEventResponse | None


__all__ = [
    "AlarmEventCreate",
    "AlarmEventResponse",
    "AlarmStateResponse",
    "AlarmStreamMessage",
    "AlarmTransition",
]
