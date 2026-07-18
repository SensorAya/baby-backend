import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class MonitoringRecord(Base):
    __tablename__ = "monitoring_records"
    __table_args__ = (
        CheckConstraint("timestamp >= 0", name="ck_monitoring_records_timestamp"),
        CheckConstraint(
            "face_ratio BETWEEN 0 AND 100",
            name="ck_monitoring_records_face_ratio",
        ),
        CheckConstraint(
            "face_center_x >= 0",
            name="ck_monitoring_records_face_center_x",
        ),
        CheckConstraint(
            "face_center_y >= 0",
            name="ck_monitoring_records_face_center_y",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    face_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    face_center_x: Mapped[int] = mapped_column(Integer, nullable=False)
    face_center_y: Mapped[int] = mapped_column(Integer, nullable=False)
    alarm_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="monitoring_records")
