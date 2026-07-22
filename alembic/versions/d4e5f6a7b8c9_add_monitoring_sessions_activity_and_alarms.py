"""add monitoring sessions activity and alarms

Revision ID: d4e5f6a7b8c9
Revises: a7b4c1d9e6f2
Create Date: 2026-07-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "a7b4c1d9e6f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create complete monitoring sessions and real-time alarm event storage."""
    op.create_table(
        "monitoring_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_monitoring_sessions_ended_after_start",
        ),
        sa.CheckConstraint(
            "started_at >= 0",
            name="ck_monitoring_sessions_started_at",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_monitoring_sessions_user_id"),
        "monitoring_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_sessions_user_started_id",
        "monitoring_sessions",
        ["user_id", "started_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_monitoring_sessions_one_active_per_user",
        "monitoring_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.add_column(
        "monitoring_records",
        sa.Column("session_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "monitoring_records",
        sa.Column("event", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "monitoring_records",
        sa.Column(
            "activity_level",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_monitoring_records_activity_level",
        "monitoring_records",
        "activity_level BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_monitoring_records_event",
        "monitoring_records",
        "event IS NULL OR event IN ('start', 'stop')",
    )
    op.create_foreign_key(
        "fk_monitoring_records_session_id",
        "monitoring_records",
        "monitoring_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_monitoring_records_session_id"),
        "monitoring_records",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "alarm_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("event", sa.String(length=9), nullable=False),
        sa.Column("face_ratio", sa.Integer(), nullable=False),
        sa.Column("baby_ratio", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "baby_ratio BETWEEN 0 AND 100",
            name="ck_alarm_events_baby_ratio",
        ),
        sa.CheckConstraint(
            "event IN ('triggered', 'cleared')",
            name="ck_alarm_events_event",
        ),
        sa.CheckConstraint(
            "face_ratio BETWEEN 0 AND 100",
            name="ck_alarm_events_face_ratio",
        ),
        sa.CheckConstraint("timestamp >= 0", name="ck_alarm_events_timestamp"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["monitoring_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_alarm_events_session_id"),
        "alarm_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alarm_events_timestamp"),
        "alarm_events",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alarm_events_user_id"),
        "alarm_events",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove alarm events, session boundaries, and activity fields."""
    op.drop_index(op.f("ix_alarm_events_user_id"), table_name="alarm_events")
    op.drop_index(op.f("ix_alarm_events_timestamp"), table_name="alarm_events")
    op.drop_index(op.f("ix_alarm_events_session_id"), table_name="alarm_events")
    op.drop_table("alarm_events")

    op.drop_index(
        op.f("ix_monitoring_records_session_id"),
        table_name="monitoring_records",
    )
    op.drop_constraint(
        "fk_monitoring_records_session_id",
        "monitoring_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_monitoring_records_event",
        "monitoring_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_monitoring_records_activity_level",
        "monitoring_records",
        type_="check",
    )
    op.drop_column("monitoring_records", "activity_level")
    op.drop_column("monitoring_records", "event")
    op.drop_column("monitoring_records", "session_id")

    op.drop_index(
        "uq_monitoring_sessions_one_active_per_user",
        table_name="monitoring_sessions",
    )
    op.drop_index(
        "ix_monitoring_sessions_user_started_id",
        table_name="monitoring_sessions",
    )
    op.drop_index(
        op.f("ix_monitoring_sessions_user_id"),
        table_name="monitoring_sessions",
    )
    op.drop_table("monitoring_sessions")
