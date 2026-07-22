from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.monitoring.periods import AggregationPeriod


class MonitoringEvent(StrEnum):
    START = "start"
    STOP = "stop"


class MonitoringRecordCreate(BaseModel):
    """One heartbeat received from the baby activity detector."""

    timestamp: int = Field(..., ge=0, examples=[1752001234])
    face_ratio: int = Field(..., ge=0, le=100, examples=[85])
    face_center_x: int = Field(..., ge=0, examples=[640])
    face_center_y: int = Field(..., ge=0, examples=[360])
    event: MonitoringEvent | None = Field(..., examples=["start"])
    baby_center_x: int = Field(..., ge=0, examples=[640])
    baby_center_y: int = Field(..., ge=0, examples=[360])
    baby_ratio: int = Field(..., ge=0, le=100, examples=[85])
    activity_level: int = Field(..., ge=0, le=100, examples=[24])


class MonitoringRecordResponse(MonitoringRecordCreate):
    """Stored heartbeat returned by the API."""

    id: UUID
    user_id: UUID
    session_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MonitoringSessionSummary(BaseModel):
    """One complete session or a calendar grouping of complete sessions."""

    key: str
    period: AggregationPeriod
    session_id: UUID | None
    started_at: int
    ended_at: int
    duration_seconds: int
    session_count: int
    sample_count: int
    average_face_ratio: float | None
    average_baby_ratio: float | None
    average_activity_level: float | None
    stationary_sample_count: int
    minor_activity_sample_count: int
    major_activity_sample_count: int
    alarm_event_count: int


class MonitoringHistoryResponse(BaseModel):
    """One page of completed monitoring units for the authenticated user."""

    items: list[MonitoringSessionSummary]
    period: AggregationPeriod
    total: int
    page: int
    page_size: int
    pages: int
