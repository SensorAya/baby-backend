from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.monitoring_record import MonitoringRecord
from app.models.user import User
from app.monitoring.schemas import MonitoringRecordCreate, MonitoringRecordResponse

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


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
