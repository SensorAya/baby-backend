from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.llm import client
from app.models.user import User
from app.reports.prompt import SYSTEM_PROMPT, build_report_user_prompt
from app.reports.query import (
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
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def days(self) -> int:
        return 7 if self is ReportPeriod.WEEKLY else 30

    @property
    def title(self) -> str:
        return "婴儿监控周报" if self is ReportPeriod.WEEKLY else "婴儿监控月报"


class MonitoringReportRequest(BaseModel):
    period: ReportPeriod


class MonitoringReportResponse(BaseModel):
    period: ReportPeriod
    days: int
    start_at: datetime
    end_at: datetime
    sample_count: int
    report: str


@router.post("", response_model=MonitoringReportResponse)
async def generate_monitoring_report(
    body: MonitoringReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringReportResponse:
    """Generate a weekly or monthly report for the authenticated user."""
    data = await query_monitoring_report_data(
        db,
        current_user.id,
        body.period.days,
    )
    if data.total_sample_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No monitoring data found for the last {body.period.days} days",
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
        days=body.period.days,
        start_at=data.start_at,
        end_at=data.end_at,
        sample_count=data.total_sample_count,
        report=report.strip(),
    )


__all__ = [
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
