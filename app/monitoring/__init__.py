from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.alarm_event import AlarmEvent
from app.models.monitoring_record import MonitoringRecord
from app.models.monitoring_session import MonitoringSession
from app.models.user import User
from app.monitoring.periods import AggregationPeriod
from app.monitoring.query import query_monitoring_history
from app.monitoring.schemas import (
    MonitoringEvent,
    MonitoringHistoryResponse,
    MonitoringRecordCreate,
    MonitoringRecordResponse,
)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/history", response_model=MonitoringHistoryResponse)
async def get_monitoring_history(
    period: AggregationPeriod = Query(AggregationPeriod.SESSION),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringHistoryResponse:
    """Return completed sessions grouped by session, day, week, or month."""
    items, total = await query_monitoring_history(
        db,
        current_user.id,
        period,
        page,
        page_size,
    )
    return MonitoringHistoryResponse(
        items=items,
        period=period,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "",
    response_model=MonitoringRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_record(
    body: MonitoringRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringRecord:
    """Store a heartbeat and maintain its start-to-stop monitoring session."""
    await db.execute(select(User).where(User.id == current_user.id).with_for_update())
    active_session = (
        await db.execute(
            select(MonitoringSession)
            .where(
                MonitoringSession.user_id == current_user.id,
                MonitoringSession.ended_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if body.event is MonitoringEvent.START:
        if active_session is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A monitoring session is already active",
            )
        active_session = MonitoringSession(
            user_id=current_user.id,
            started_at=body.timestamp,
        )
        db.add(active_session)
        await db.flush()
    elif active_session is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active monitoring session; send event='start' first",
        )

    latest_timestamp = (
        await db.execute(
            select(MonitoringRecord.timestamp)
            .where(MonitoringRecord.session_id == active_session.id)
            .order_by(MonitoringRecord.timestamp.desc(), MonitoringRecord.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_timestamp is not None and body.timestamp < latest_timestamp:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Heartbeat timestamp is older than the active session's latest record",
        )

    latest_alarm_event = (
        await db.execute(
            select(AlarmEvent.event)
            .where(
                AlarmEvent.user_id == current_user.id,
                AlarmEvent.timestamp <= body.timestamp,
            )
            .order_by(AlarmEvent.timestamp.desc(), AlarmEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    record = MonitoringRecord(
        user_id=current_user.id,
        session_id=active_session.id,
        alarm_active=latest_alarm_event == "triggered",
        **body.model_dump(),
    )
    db.add(record)

    if body.event is MonitoringEvent.STOP:
        active_session.ended_at = body.timestamp
        active_session.completed_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Monitoring session state changed; retry the heartbeat",
        ) from exc
    await db.refresh(record)
    return record


__all__ = ["router"]
