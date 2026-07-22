import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.alarm_event import AlarmEvent
    from app.models.monitoring_record import MonitoringRecord
    from app.models.user import User


class MonitoringSession(Base):
    """One complete monitoring run, delimited by start and stop heartbeats."""

    __tablename__ = "monitoring_sessions"
    __table_args__ = (
        CheckConstraint("started_at >= 0", name="ck_monitoring_sessions_started_at"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_monitoring_sessions_ended_after_start",
        ),
        Index(
            "uq_monitoring_sessions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index(
            "ix_monitoring_sessions_user_started_id",
            "user_id",
            "started_at",
            "id",
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
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ended_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="monitoring_sessions")
    records: Mapped[list["MonitoringRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alarm_events: Mapped[list["AlarmEvent"]] = relationship(
        back_populates="session",
        passive_deletes=True,
    )
