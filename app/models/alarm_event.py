import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.monitoring_session import MonitoringSession
    from app.models.user import User


class AlarmEvent(Base):
    """A device alarm transition that can be delivered to signed-in clients."""

    __tablename__ = "alarm_events"
    __table_args__ = (
        CheckConstraint("timestamp >= 0", name="ck_alarm_events_timestamp"),
        CheckConstraint(
            "event IN ('triggered', 'cleared')",
            name="ck_alarm_events_event",
        ),
        CheckConstraint(
            "face_ratio BETWEEN 0 AND 100",
            name="ck_alarm_events_face_ratio",
        ),
        CheckConstraint(
            "baby_ratio BETWEEN 0 AND 100",
            name="ck_alarm_events_baby_ratio",
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(9), nullable=False)
    face_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    baby_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="alarm_events")
    session: Mapped["MonitoringSession | None"] = relationship(
        back_populates="alarm_events"
    )
