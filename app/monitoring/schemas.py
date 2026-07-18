from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MonitoringRecordCreate(BaseModel):
    """Monitoring data received from the baby activity detector."""

    timestamp: int = Field(..., ge=0, examples=[1752001234])
    face_ratio: int = Field(..., ge=0, le=100, examples=[85])
    face_center_x: int = Field(..., ge=0, examples=[640])
    face_center_y: int = Field(..., ge=0, examples=[360])
    alarm_active: bool = Field(..., examples=[False])


class MonitoringRecordResponse(MonitoringRecordCreate):
    """Stored monitoring record returned by the API."""

    id: UUID
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MonitoringRecordHistoryResponse(BaseModel):
    """One page of monitoring records for the authenticated user."""

    items: list[MonitoringRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int
