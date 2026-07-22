from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.llm import client
from app.models.user import User
from app.models.monitoring_session import MonitoringSession
from app.reports.prompt import SYSTEM_PROMPT, build_report_user_prompt
from app.reports.query import (
    ActivitySummary,
    DailyMonitoringSummary,
    EventSummary,
    FaceVisibilityTrend,
    MonitoringReportData,
    MonitoringSummary,
    SamplingQualitySummary,
    format_monitoring_report_data,
    query_monitoring_report_data,
    query_monitoring_report_text,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportPeriod(StrEnum):
    SESSION = "session"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def days(self) -> int:
        return {
            ReportPeriod.SESSION: 1,
            ReportPeriod.DAILY: 1,
            ReportPeriod.WEEKLY: 7,
            ReportPeriod.MONTHLY: 30,
        }[self]

    @property
    def title(self) -> str:
        return {
            ReportPeriod.SESSION: "婴儿单次监测报告",
            ReportPeriod.DAILY: "婴儿监控日报",
            ReportPeriod.WEEKLY: "婴儿监控周报",
            ReportPeriod.MONTHLY: "婴儿监控月报",
        }[self]


class MonitoringReportRequest(BaseModel):
    period: ReportPeriod
    session_id: UUID | None = None

    @model_validator(mode="after")
    def validate_session_id(self) -> "MonitoringReportRequest":
        if self.session_id is not None and self.period is not ReportPeriod.SESSION:
            raise ValueError("session_id is only valid when period='session'")
        return self


class MonitoringReportResponse(BaseModel):
    period: ReportPeriod
    days: int
    start_at: datetime
    end_at: datetime
    sample_count: int
    session_id: UUID | None
    report: str


@router.post("", response_model=MonitoringReportResponse)
async def generate_monitoring_report(
    body: MonitoringReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringReportResponse:
    """Generate a single-session, daily, weekly, or monthly report."""
    report_days = body.period.days
    report_start: datetime | None = None
    report_end: datetime | None = None
    session_id: UUID | None = None
    if body.period is ReportPeriod.SESSION:
        statement = select(MonitoringSession).where(
            MonitoringSession.user_id == current_user.id,
            MonitoringSession.ended_at.is_not(None),
        )
        if body.session_id is not None:
            statement = statement.where(MonitoringSession.id == body.session_id)
        else:
            statement = statement.order_by(
                MonitoringSession.ended_at.desc(),
                MonitoringSession.id.desc(),
            ).limit(1)
        session = (await db.execute(statement)).scalar_one_or_none()
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No completed monitoring session found",
            )
        session_id = session.id
        report_start = datetime.fromtimestamp(session.started_at, tz=timezone.utc)
        report_end = datetime.fromtimestamp(session.ended_at, tz=timezone.utc)
        local_timezone = ZoneInfo("Asia/Taipei")
        report_days = (
            report_end.astimezone(local_timezone).date()
            - report_start.astimezone(local_timezone).date()
        ).days + 1

    data = await query_monitoring_report_data(
        db,
        current_user.id,
        report_days,
        now=report_end,
        start_at=report_start,
        session_id=session_id,
    )
    if data.total_sample_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed monitoring data found for the selected period",
        )

    monitoring_json = format_monitoring_report_data(data)
    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_report_user_prompt(
                        body.period.title,
                        monitoring_json,
                    ),
                },
            ],
            max_completion_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
        )
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The configured LLM service is unavailable",
        ) from exc

    report = completion.choices[0].message.content if completion.choices else None
    if not report or not report.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The configured LLM service returned an empty report",
        )

    return MonitoringReportResponse(
        period=body.period,
        days=report_days,
        start_at=data.start_at,
        end_at=data.end_at,
        sample_count=data.total_sample_count,
        session_id=session_id,
        report=report.strip(),
    )


__all__ = [
    "ActivitySummary",
    "DailyMonitoringSummary",
    "EventSummary",
    "FaceVisibilityTrend",
    "MonitoringReportData",
    "MonitoringReportRequest",
    "MonitoringReportResponse",
    "MonitoringSummary",
    "ReportPeriod",
    "SamplingQualitySummary",
    "build_report_user_prompt",
    "format_monitoring_report_data",
    "generate_monitoring_report",
    "query_monitoring_report_data",
    "query_monitoring_report_text",
    "router",
]
