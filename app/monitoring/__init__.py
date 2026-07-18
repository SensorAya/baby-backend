from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.monitoring_record import MonitoringRecord
from app.models.user import User
from app.monitoring.schemas import (
    MonitoringRecordCreate,
    MonitoringRecordHistoryResponse,
    MonitoringRecordResponse,
)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/history", response_model=MonitoringRecordHistoryResponse)
async def get_monitoring_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one page of the authenticated user's monitoring history."""
    user_filter = MonitoringRecord.user_id == current_user.id
    total = (
        await db.execute(
            select(func.count()).select_from(MonitoringRecord).where(user_filter)
        )
    ).scalar_one()

    records = (
        (
            await db.execute(
                select(MonitoringRecord)
                .where(user_filter)
                .order_by(MonitoringRecord.timestamp.desc(), MonitoringRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return MonitoringRecordHistoryResponse(
        items=records,
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
):
    """Store one baby activity monitoring record."""
    record = MonitoringRecord(user_id=current_user.id, **body.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
